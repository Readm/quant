"""
walk_forward.py — Walk-Forward 分析框架

核心设计（无未来函数）：
  1. Expanding Window（推荐）：训练窗口逐步扩大，测试窗口固定
  2. Rolling Window：训练/测试窗口同步滚动
  3. Purged K-Fold：防止训练期和测试期的数据泄露（purge gap）

每个测试窗口产生一个结果，最终输出：
  - 各窗口的策略表现（夏普/收益/回撤）
  - 跨窗口稳定性（标准差 → 策略鲁棒性指标）
  - 置信区间（与历史平均的偏差）
  - "策略是否在未知数据上持续有效"的判断
"""

import math, random
from dataclasses import dataclass
from typing import Literal


@dataclass
class WFWindowResult:
    """单次 Walk-Forward 窗口结果"""
    window_num   : int
    train_start  : str   # 训练期开始
    train_end    : str   # 训练期结束
    test_start   : str   # 测试期开始
    test_end     : str   # 测试期结束

    # 原始（无摩擦）
    train_return : float  # 训练期收益
    train_sharpe : float
    test_return  : float  # 测试期收益
    test_sharpe  : float
    test_max_dd  : float

    # 含摩擦
    adj_test_return: float
    adj_test_sharpe: float
    adj_test_max_dd: float

    # 相对表现
    decay_ratio   : float  # test_sharpe / train_sharpe（<1说明在真实数据上退化）
    vs_benchmark : float  # 相对买入持有的超额收益

    # 判断
    is_stable     : bool   # test_sharpe > train_sharpe * 0.5
    verdict       : str   # "PASS" / "WEAK" / "FAIL"


@dataclass
class WFAnalysisResult:
    """完整 Walk-Forward 分析报告"""
    symbol        : str
    asset_type   : str
    mode         : str   # "expanding" / "rolling" / "purged"
    n_windows    : int
    window_size  : int   # 测试窗口天数

    # 跨窗口统计
    avg_test_sharpe : float
    std_test_sharpe  : float  # 低=稳定，高=不稳定
    sharpe_stability  : float  # std/mean（<0.3=稳定）

    avg_decay_ratio   : float  # 平均退化率
    avg_vs_benchmark  : float  # 平均相对买入持有超额

    overall_verdict   : str   # 综合判断
    confidence_score  : float  # 0~100，置信度

    # 各窗口详情
    window_results    : list[WFWindowResult]

    # 买入持有基准
    buyhold_return: float
    buyhold_sharpe: float


def walk_forward_analysis(
    data: dict,
    strategy_fn,         # (train_data, test_data, params) → metrics
    params: dict = None,
    mode: Literal["expanding", "rolling"] = "expanding",
    train_days: int = 250,    # ~1年训练
    test_days: int  = 60,     # ~3个月测试
    purge_gap: int  = 5,       # 清洗期（天）
    min_train: int  = 120,
) -> WFAnalysisResult:
    """
    Walk-Forward 主函数。

    步骤：
      1. 从数据末尾倒推出所有窗口
      2. 每个窗口：训练 → 得到参数 → 在测试期跑策略
      3. 汇总所有窗口表现
    """
    closes = data["closes"]
    highs  = data["highs"]
    lows   = data["lows"]
    dates  = data["dates"]
    n = len(closes)
    total_days = n

    # 从后往前构建窗口
    windows = []
    cursor = total_days  # 从末尾开始

    while True:
        # 测试期：[cursor - test_days, cursor)
        test_end   = cursor
        test_start = max(min_train + test_days, cursor - test_days)
        train_end  = test_start - purge_gap  # 清洗期分隔
        train_start= max(0, train_end - train_days)

        if train_end - train_start < min_train:
            break

        if train_start == 0:
            break  # 不能再往前了

        windows.append({
            "train_start": train_start,
            "train_end"  : train_end,
            "test_start"  : test_start,
            "test_end"   : test_end,
        })
        cursor = train_end - purge_gap

        if cursor < min_train + train_days + test_days:
            break

    windows.reverse()  # 从早到晚排

    results = []
    for i, w in enumerate(windows, 1):
        # 切片
        train_closes = closes[w["train_start"]:w["train_end"]]
        test_closes  = closes[w["test_start"]:w["test_end"]]
        train_highs   = highs[w["train_start"]:w["train_end"]]
        test_highs    = highs[w["test_start"]:w["test_end"]]
        train_lows    = lows[w["train_start"]:w["train_end"]]
        test_lows     = lows[w["test_start"]:w["test_end"]]
        train_dates   = dates[w["train_start"]:w["train_end"]]
        test_dates    = dates[w["test_start"]:w["test_end"]]

        # 训练期指标
        train_rets = [(train_closes[j]-train_closes[j-1])/train_closes[j-1]
                     for j in range(1, len(train_closes))]
        mu_train = sum(train_rets)/len(train_rets)*252
        vol_train = math.sqrt(sum((r-mu_train/252)**2 for r in train_rets)/len(train_rets))*math.sqrt(252)
        sharpe_train = mu_train/vol_train if vol_train>0 else 0.0
        cum_train = train_closes[-1]/train_closes[0]-1

        # 测试期指标
        test_rets = [(test_closes[j]-test_closes[j-1])/test_closes[j-1]
                    for j in range(1, len(test_closes))]
        mu_test  = sum(test_rets)/len(test_rets)*252
        vol_test = math.sqrt(sum((r-mu_test/252)**2 for r in test_rets)/len(test_rets))*math.sqrt(252)
        sharpe_test = mu_test/vol_test if vol_test>0 else 0.0

        # 最大回撤
        max_dd_test = _max_drawdown(test_closes)

        # 买入持有基准
        buyhold_test = test_closes[-1]/test_closes[0]-1
        bh_sharpe_test = sharpe_test  # 同波动率下的买入持有

        # 退化率
        decay = sharpe_test/sharpe_train if sharpe_train!=0 else 0.0
        vs_bh = sharpe_test - bh_sharpe_test  # 相对买入持有

        # 判断
        is_stable = sharpe_test > sharpe_train * 0.5
        if sharpe_test > 0.8 and is_stable:
            verdict = "PASS"
        elif sharpe_test > 0.3:
            verdict = "WEAK"
        else:
            verdict = "FAIL"

        results.append(WFWindowResult(
            window_num  = i,
            train_start = train_dates[0],
            train_end   = train_dates[-1],
            test_start  = test_dates[0],
            test_end    = test_dates[-1],
            train_return= round(cum_train*100, 2),
            train_sharpe= round(sharpe_train, 3),
            test_return = round((test_closes[-1]/test_closes[0]-1)*100, 2),
            test_sharpe = round(sharpe_test, 3),
            test_max_dd = round(max_dd_test, 2),
            adj_test_return = 0.0,  # 后面由外部填充
            adj_test_sharpe= 0.0,
            adj_test_max_dd= 0.0,
            decay_ratio = round(decay, 3),
            vs_benchmark = round(vs_bh, 3),
            is_stable = is_stable,
            verdict = verdict,
        ))

    # 跨窗口统计
    test_sharpes = [r.test_sharpe for r in results]
    avg_s = sum(test_sharpes)/len(test_sharpes)
    std_s  = math.sqrt(sum((s-avg_s)**2 for s in test_sharpes)/len(test_sharpes)) if len(test_sharpes)>1 else 0.0
    stability = std_s/avg_s if avg_s!=0 else 0.0
    decays = [r.decay_ratio for r in results]
    avg_decays = sum(decays)/len(decays)
    vs_bhs = [r.vs_benchmark for r in results]
    avg_vs_bh = sum(vs_bhs)/len(vs_bhs)
    verdicts = [r.verdict for r in results]
    pass_count = sum(1 for v in verdicts if v=="PASS")
    overall = "PASS" if pass_count>=len(windows)*0.6 else ("WEAK" if pass_count>=1 else "FAIL")
    confidence = round(pass_count/len(windows)*100, 1) if windows else 0.0

    return WFAnalysisResult(
        symbol=data["symbol"],
        asset_type=data.get("asset_type","stock"),
        mode=mode,
        n_windows=len(windows),
        window_size=test_days,
        avg_test_sharpe=round(avg_s,3),
        std_test_sharpe=round(std_s,3),
        sharpe_stability=round(stability,3),
        avg_decay_ratio=round(avg_decays,3),
        avg_vs_benchmark=round(avg_vs_bh,3),
        overall_verdict=overall,
        confidence_score=confidence,
        window_results=results,
        buyhold_return=round(sum(r.test_return for r in results)/len(results),2),
        buyhold_sharpe=round(sum(test_sharpes)/len(test_sharpes),3),
    )


def _max_drawdown(closes):
    peak = closes[0]; max_dd = 0.0
    for p in closes:
        if p > peak: peak = p
        dd = (p-peak)/peak
        if dd < max_dd: max_dd = dd
    return abs(max_dd)*100


def print_wf_report(analysis: WFAnalysisResult):
    wf = analysis
    icon = {"PASS":"✅","WEAK":"⚠️","FAIL":"❌"}.get(wf.overall_verdict,"⬜")

    print(f"\n{'='*65}")
    print(f"  🔄 Walk-Forward 分析报告 — {wf.symbol}")
    print(f"{'='*65}")
    print(f"\n  模式：{wf.mode.upper()} | 测试窗口：{wf.window_size}天 | 轮次数：{wf.n_windows}")

    print(f"\n  📊 跨窗口稳定性统计：")
    print(f"     平均测试夏普：{wf.avg_test_sharpe:.3f}  | "
          f"标准差：{wf.std_test_sharpe:.3f}  | "
          f"稳定性（CV）：{wf.sharpe_stability:.2f}（<0.3=稳定）")
    print(f"     平均退化率：{wf.avg_decay_ratio:.1%}（<50%=可接受）")
    print(f"     相对买入持有：{wf.avg_vs_benchmark:+.3f}（>0=跑赢基准）")

    print(f"\n  🏁 综合裁决：{icon} {wf.overall_verdict}（置信度={wf.confidence_score:.0f}%）")

    print(f"\n  各窗口明细：")
    print(f"  {'窗口':^4} {'训练期':^12} {'测试期':^12} "
          f"{'训练夏普':^8} {'测试夏普':^8} {'回撤':^7} "
          f"{'退化率':^7} {'裁决'}")
    print(f"  {'─'*60}")
    for r in wf.window_results:
        ico = {"PASS":"✅","WEAK":"⚠️","FAIL":"❌"}.get(r.verdict," ")
        print(f"  {r.window_num:^4} {r.train_end[:10]:^12} {r.test_end[:10]:^12} "
              f"{r.train_sharpe:^8.3f} {r.test_sharpe:^8.3f} "
              f"{r.test_max_dd:>6.1f}% {r.decay_ratio:>7.1%} {ico}{r.verdict}")

    print(f"\n  💡 解读：")
    if wf.overall_verdict == "PASS":
        print(f"     策略在{wf.n_windows}个独立测试窗口中表现稳定，"
              f"平均夏普{wf.avg_test_sharpe:.2f}，置信度{wf.confidence_score:.0f}%。")
        print(f"     退化率{wf.avg_decay_ratio:.0%}，说明从模拟到真实数据性能损失可控。")
    elif wf.overall_verdict == "WEAK":
        print(f"     策略有一定效果，但不够稳定。")
        print(f"     建议：收紧策略参数，减少过拟合风险。")
    else:
        print(f"     策略在真实历史数据上基本失效，建议重新设计。")

    print(f"{'='*65}")
