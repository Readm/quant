"""
pbo_analysis.py — PBO（Probability of Backtest Overfitting）
=======================================================
实现基于多重滚动窗口的过拟合概率评估。

核心思想：
  将数据切分为 N 个重叠的 train/test 窗口对，
  在 train 上优化参数，在 test 上验证。
  如果策略在 test 上的表现显著差于 train，
  说明策略过拟合了。

PBO 计算：
  1. 对每个参数组合，计算其在所有 test 窗口上的 Sharpe ratio 均值
  2. PBO = 策略 test Sharpe > 基准策略（median of all strategies） test Sharpe 的概率
  3. PBO 越高 → 策略越稳健（不是过拟合）

参考：Bailey, Borwein, Lopez de Prado "The Probability of Backtest Overfitting"
     https://arxiv.org/abs/1412.7926
"""

import math
from typing import List, Dict, Optional, Callable, Tuple
from dataclasses import dataclass


# ═══════════════════════════════════════════════════════════
#  核心 PBO 计算
# ═══════════════════════════════════════════════════════════

@dataclass
class PBOResult:
    pbo: float              # PBO 值 [0, 1]，越高越稳健
    sharpe_train_avg: float # train 上平均 Sharpe
    sharpe_test_avg: float  # test 上平均 Sharpe
    overfit_ratio: float    # sharpe_train / sharpe_test（越大越过拟合）
    n_windows: int          # 窗口数量
    n_params: int           # 参数组合数量
    sharpe_test_median: float # test 上 Sharpe 中位数
    sharpe_test_std: float   # test 上 Sharpe 标准差

    def summary(self) -> str:
        return (
            f"PBO={self.pbo:.1%} | "
            f"Train Sharpe={self.sharpe_train_avg:.3f} | "
            f"Test Sharpe={self.sharpe_test_avg:.3f} | "
            f"过拟合率={self.overfit_ratio:.2f}x | "
            f"窗口={self.n_windows} | "
            f"参数组合={self.n_params}"
        )


def compute_pbo(
    closes: List[float],
    signal_fn: Callable,
    param_grid: Dict[str, List],
    n_windows: int = 10,
    train_ratio: float = 0.6,
    risk_free: float = 0.0,
) -> PBOResult:
    """
    计算给定策略/参数网格的 PBO。

    Parameters
    ----------
    closes : list of float
        价格序列（用于生成信号和计算收益）
    signal_fn : callable(close, **params) -> list of int
        信号生成函数，返回 1/0/-1
    param_grid : dict
        参数网格，如 {"period": [14, 21], "lower": [25, 30]}
    n_windows : int
        滚动窗口数量（默认 10）
    train_ratio : float
        每个窗口中 train 数据占比（默认 0.6）
    risk_free : float
        年化无风险收益率（用于 Sharpe 计算）

    Returns
    -------
    PBOResult
        包含 PBO 及相关指标的 dataclass
    """
    n = len(closes)
    if n < 60:
        return PBOResult(
            pbo=0.0, sharpe_train_avg=0.0, sharpe_test_avg=0.0,
            overfit_ratio=0.0, n_windows=n_windows, n_params=0,
            sharpe_test_median=0.0, sharpe_test_std=0.0,
        )

    # ── 生成全部参数组合 ─────────────────────────
    import itertools
    keys, vals = zip(*param_grid.items())
    combos = [dict(zip(keys, v)) for v in itertools.product(*vals)]
    if not combos:
        return PBOResult(
            pbo=0.0, sharpe_train_avg=0.0, sharpe_test_avg=0.0,
            overfit_ratio=0.0, n_windows=n_windows, n_params=0,
            sharpe_test_median=0.0, sharpe_test_std=0.0,
        )

    n_combos = len(combos)
    n_train = int(n * train_ratio)
    step = (n - n_train) // max(n_windows - 1, 1)

    # ── 存储每个参数组合在每个 test 窗口上的 Sharpe ───
    test_sharpes = []   # shape: (n_combos, n_windows)

    for combo in combos:
        sig = signal_fn(closes, **combo)
        combo_test_sharpes = []

        for w in range(n_windows):
            train_start = w * step
            train_end   = train_start + n_train
            test_end    = min(train_end + (n - n_train), n)

            if test_end <= train_end or train_end >= n:
                continue

            # train window Sharpe
            train_rets = _window_returns(closes, sig, train_start, train_end)
            train_sharpe = _sharpe(train_rets, risk_free)

            # test window Sharpe
            test_rets = _window_returns(closes, sig, train_end, test_end)
            if len(test_rets) < 5:
                continue
            test_sharpe = _sharpe(test_rets, risk_free)

            combo_test_sharpes.append(test_sharpe)

        test_sharpes.append(combo_test_sharpes)

    # ── 计算 PBO ─────────────────────────────────
    # 对每个窗口，找出 Sharpe > 中位数的策略比例
    if not test_sharpes or not test_sharpes[0]:
        return PBOResult(
            pbo=0.0, sharpe_train_avg=0.0, sharpe_test_avg=0.0,
            overfit_ratio=0.0, n_windows=n_windows, n_params=n_combos,
            sharpe_test_median=0.0, sharpe_test_std=0.0,
        )

    n_w = len(test_sharpes[0])  # 实际窗口数
    all_test_sharpes = [s for cs in test_sharpes for s in cs]
    sharpe_test_median_val = sorted(all_test_sharpes)[len(all_test_sharpes) // 2]

    # PBO = 该策略在 test 上优于中位数的窗口比例
    above_median_count = 0
    total_count = 0
    sharpe_train_list = []
    sharpe_test_list  = []

    for i, combo in enumerate(combos):
        if len(test_sharpes[i]) < n_w // 2:
            continue
        ts = test_sharpes[i]
        above_median_count += sum(1 for s in ts if s > sharpe_test_median_val)
        total_count        += len(ts)
        sharpe_test_list.append(sum(ts) / len(ts))

        # train Sharpe（用第一个窗口近似）
        train_start = 0
        train_end   = n_train
        train_rets  = _window_returns(closes, sig, train_start, train_end)
        sharpe_train_list.append(_sharpe(train_rets, risk_free))

    pbo_val  = above_median_count / total_count if total_count > 0 else 0.0
    train_avg = sum(sharpe_train_list) / len(sharpe_train_list) if sharpe_train_list else 0.0
    test_avg  = sum(sharpe_test_list)  / len(sharpe_test_list)  if sharpe_test_list  else 0.0
    overfit   = train_avg / test_avg if abs(test_avg) > 1e-9 else 0.0
    test_std  = math.sqrt(sum((s - test_avg)**2 for s in sharpe_test_list) / max(len(sharpe_test_list)-1, 1))

    return PBOResult(
        pbo=round(pbo_val, 4),
        sharpe_train_avg=round(train_avg, 4),
        sharpe_test_avg=round(test_avg, 4),
        overfit_ratio=round(overfit, 4),
        n_windows=n_w,
        n_params=n_combos,
        sharpe_test_median=round(sharpe_test_median_val, 4),
        sharpe_test_std=round(test_std, 4),
    )


# ═══════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════

def _window_returns(closes: List[float], signals: List[int],
                    start: int, end: int) -> List[float]:
    """计算指定窗口内的日收益率序列"""
    rets = []
    for i in range(start + 1, end):
        if signals[i] == 1:         # 持有多头
            if closes[i-1] != 0:
                rets.append((closes[i] - closes[i-1]) / closes[i-1])
        elif signals[i] == -1:      # 持有空头（简化：做空收益）
            if closes[i-1] != 0:
                rets.append(-(closes[i] - closes[i-1]) / closes[i-1])
        else:
            rets.append(0.0)
    return rets


def _sharpe(rets: List[float], risk_free: float = 0.0,
            periods_per_year: int = 252) -> float:
    """年化夏普比率"""
    n = len(rets)
    if n < 5:
        return 0.0
    mean = sum(rets) / n
    std  = math.sqrt(sum((r - mean)**2 for r in rets) / (n - 1)) if n > 1 else 0.0
    ann_ret = mean * periods_per_year
    ann_vol = std  * math.sqrt(periods_per_year)
    return ann_ret / (ann_vol + 1e-10)


# ═══════════════════════════════════════════════════════════
#  集成到专家系统：用 PBO 过滤候选策略
# ═══════════════════════════════════════════════════════════

def pbo_score_adjustment(pbo_result: PBOResult,
                          sharpe: float,
                          threshold_pbo: float = 0.60) -> Tuple[float, str]:
    """
    根据 PBO 调整策略评分。
    如果 PBO < threshold_pbo（0.60），说明策略存在显著过拟合风险，
    需要降低其评分。

    Returns
    -------
    (adjusted_score, reason)
        调整后评分和建议
    """
    if pbo_result.n_params == 0:
        return sharpe, "PBO: 无参数网格，跳过"

    pbo = pbo_result.pbo
    base = sharpe

    if pbo >= 0.80:
        adj = 0.0      # 非常稳健，不调整
        reason = f"PBO={pbo:.0%}（稳健），不调整"
    elif pbo >= 0.60:
        adj = 0.0       # 基本稳健
        reason = f"PBO={pbo:.0%}（可接受），不调整"
    elif pbo >= 0.40:
        adj = -base * 0.20  # 轻度过拟合，降20%
        reason = f"PBO={pbo:.0%}（轻度过拟合），评分×0.80"
    elif pbo >= 0.20:
        adj = -base * 0.50  # 中度过拟合，降50%
        reason = f"PBO={pbo:.0%}（中度过拟合），评分×0.50"
    else:
        adj = -base * 0.80   # 严重过拟合，降80%
        reason = f"PBO={pbo:.0%}（严重过拟合），评分×0.20"

    adjusted = max(0.0, base + adj)
    return round(adjusted, 4), reason


def run_pbo_on_strategy(
    closes: List[float],
    signal_fn: Callable,
    param_grid: Dict,
    sharpe: float,
    n_windows: int = 8,
    train_ratio: float = 0.6,
) -> Dict:
    """
    对单个策略运行完整 PBO 分析，返回可读的诊断报告。
    """
    result = compute_pbo(
        closes, signal_fn, param_grid,
        n_windows=n_windows, train_ratio=train_ratio,
    )
    adj_score, reason = pbo_score_adjustment(result, sharpe)

    return {
        "pbo"             : result.pbo,
        "pbo_label"        : "高稳健" if result.pbo >= 0.80
                             else ("稳健" if result.pbo >= 0.60
                             else ("轻度过拟合" if result.pbo >= 0.40
                             else ("中度过拟合" if result.pbo >= 0.20
                             else "严重过拟合"))),
        "train_sharpe"     : result.sharpe_train_avg,
        "test_sharpe"      : result.sharpe_test_avg,
        "overfit_ratio"    : result.overfit_ratio,
        "n_windows"       : result.n_windows,
        "n_params"         : result.n_params,
        "adjusted_sharpe"  : adj_score,
        "adjust_reason"    : reason,
    }
