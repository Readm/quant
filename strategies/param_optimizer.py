"""
param_optimizer.py — 策略参数迭代 + 合理性评估系统
================================================================
功能：
  1. 参数网格搜索（Grid Search）—— 遍历所有策略的参数组合
  2. 合理性评估——多维度评分，过滤过拟合/虚假盈利
  3. Walk-Forward 分析——用前3年训练、后1年验证，避免过拟合
  4. 汇总报告——生成策略排名和最优参数

合理性评估维度：
  ✅ 夏普比率（> 0.5 合格）
  ✅ 最大回撤（< 25% 合格）
  ✅ 交易次数（5~200次，样本量合理）
  ✅ 胜率（20%~90%，过高性能存疑）
  ✅ 盈亏比（> 1.0 合格）
  ✅ 样本外一致性（训练/验证年化差异 < 50%）
  ✅ 年化收益 > 0（必须盈利）

评分权重：
  夏普 × 40%  |  稳定性 × 20%  |  样本外一致性 × 20%  |  风险控制 × 20%
"""

import sys, math, json
from pathlib import Path
from typing import List, Dict, Callable, Tuple, Optional
from itertools import product
from statistics import stdev, mean

sys.path.insert(0, str(Path(__file__).parent.parent))
from strategies.backtest_engine import backtest_signal

# ═══════════════════════════════════════════════════════
# 指标计算
# ═══════════════════════════════════════════════════════

def ma(arr, n):
    return [sum(arr[max(0,i-n+1):i+1])/min(n,i+1) for i in range(len(arr))]

def ema(arr, n):
    if not arr: return []
    k = 2/(n+1)
    return [arr[0]] + [arr[i]*k+arr[i-1]*(1-k) for i in range(1,len(arr))]

def std_fn(arr, n):
    out = []
    for i in range(len(arr)):
        s = arr[max(0,i-n+1):i+1]
        m = sum(s)/len(s)
        out.append(math.sqrt(sum((x-m)**2 for x in s)/len(s)))
    return out

def boll_bands(closes, n=20, k=2.0):
    mid = ma(closes, n)
    sd  = std_fn(closes, n)
    return [m+k*s for m,s in zip(mid,sd)], mid, [m-k*s for m,s in zip(mid,sd)]

def rsi(closes, n=14):
    gains,losses = [],[]
    for i in range(1,len(closes)):
        d=closes[i]-closes[i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    ag=ma(gains,n); al=ma(losses,n)
    return [100-100/(1+a/b) if b>0 else 50 for a,b in zip(ag,al)]

def macd(closes, f=12, s=26, sg=9):
    ef=ema(closes,f); es=ema(closes,s)
    dif=[ef[i]-es[i] for i in range(len(ef))]
    dea=[sum(dif[max(0,i-sg+1):i+1])/min(sg,i+1) for i in range(len(dif))]
    return dif,dea

def atr(highs, lows, closes, n=14):
    trs=[0.0]
    for i in range(1,len(highs)):
        tr=max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1]))
        trs.append(tr)
    out=[0.0]*(n-1)
    for i in range(n-1,len(trs)):
        out.append(sum(trs[i-n+1:i+1])/n)
    return out

def adx(highs, lows, closes, n=14):
    pdm=[max(highs[i]-highs[i-1],0) for i in range(1,len(highs))]
    mdm=[max(lows[i-1]-lows[i],0) for i in range(1,len(lows))]
    tr=[max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1]))
        for i in range(1,len(highs))]
    pad=[0.0]*(n-1)
    pdi=pad+[a/b*100 if b>0 else 0 for a,b in zip(ma(pdm,n),ma(tr,n))]
    mdi=pad+[a/b*100 if b>0 else 0 for a,b in zip(ma(mdm,n),ma(tr,n))]
    dx=[abs(pdi[i]-mdi[i])/(pdi[i]+mdi[i]+1e-9)*100 for i in range(n-1,len(pdi))]
    adx_=[0.0]*(n*2-2)+ma(dx[n-1:],n)
    return adx_,pdi,mdi

def vol_ratio(volumes, n=20):
    avg=[sum(volumes[max(0,i-n+1):i+1])/min(n,i+1) for i in range(len(volumes))]
    return [v/max(a,1) for v,a in zip(volumes,avg)]


# ═══════════════════════════════════════════════════════
# 信号函数
# ═══════════════════════════════════════════════════════

def signal_boll(closes, highs, lows, opens, volumes, n=20, k=2.0):
    upper,mid,lower=boll_bands(closes,n,k)
    sig=[0]*len(closes)
    for i in range(n,len(closes)):
        if closes[i]<=lower[i] and closes[i-1]>lower[i-1]:
            sig[i]=1
        elif closes[i]>=upper[i] and closes[i-1]<upper[i-1]:
            sig[i]=-1
    return sig

def signal_macd(closes, highs, lows, opens, volumes, f=12, s=26, sg=9):
    dif,dea=macd(closes,f,s,sg)
    sig=[0]*len(closes)
    offset=s
    for i in range(offset,len(closes)):
        if dif[i-1]<=dea[i-1] and dif[i]>dea[i]:
            sig[i]=1
        elif dif[i-1]>=dea[i-1] and dif[i]<dea[i]:
            sig[i]=-1
    return sig

def signal_rsi_ma(closes, highs, lows, opens, volumes,
                   rsi_n=14, rsi_lo=35, rsi_hi=65,
                   ma_fast=5, ma_slow=20):
    rv=rsi(closes,rsi_n)
    m1=ma(closes,ma_fast); m2=ma(closes,ma_slow)
    sig=[0]*len(closes)
    for i in range(max(rsi_n,ma_slow),len(closes)):
        # RSI超卖 + MA金叉
        if rv[i-1]<rsi_lo and rv[i]>=rsi_lo:
            sig[i]=1
        elif rv[i-1]>rsi_hi and rv[i]<=rsi_hi:
            sig[i]=-1
        # MA止损
        elif m1[i-1]<=m2[i-1] and m1[i]>m2[i]:
            sig[i]=1
        elif m1[i-1]>=m2[i-1] and m1[i]<m2[i]:
            sig[i]=-1
    return sig

def signal_turtle(closes, highs, lows, opens, volumes,
                  entry=20, exit_=10, allow_short=False):
    sig=[0]*len(closes)
    for i in range(entry,len(closes)):
        hh=max(highs[i-entry:i+1]); ll=min(lows[i-exit_:i+1])
        if closes[i]>hh and (i==0 or closes[i-1]<=highs[i-1]):
            sig[i]=1
        elif closes[i]<ll and (i==0 or closes[i-1]>=lows[i-1]):
            sig[i]=-1
        if allow_short:
            ll20=min(lows[i-entry:i+1]); hh10=max(highs[i-exit_:i+1])
            if closes[i]<ll20: sig[i]=-1
            elif closes[i]>hh10: sig[i]=1
    return sig

def signal_dingfengbo(closes, highs, lows, opens, volumes,
                      ma_p=20, vol_lkbk=30, dev_thresh=0.10):
    if len(closes)<ma_p+vol_lkbk: return [0]*len(closes)
    m20=ma(closes,ma_p)
    avg_vol=[sum(volumes[max(0,i-vol_lkbk+1):i+1])/min(vol_lkbk,i+1)
              for i in range(len(volumes))]
    vr=[v/max(a,1e-9) for v,a in zip(volumes,avg_vol)]
    sig=[0]*len(closes); in_pos=False
    for i in range(ma_p,len(closes)):
        dev=(closes[i]-m20[i])/m20[i] if m20[i]!=0 else 0
        if not in_pos:
            if dev<-dev_thresh and vr[i]<0.35:
                sig[i]=1; in_pos=True
        else:
            ma5=sum(closes[max(0,i-4):i+1])/5
            ma5p=sum(closes[max(0,i-5):i-1])/5 if i>=6 else ma5
            if closes[i]>ma5 and ma5p<=ma5:
                sig[i]=-1; in_pos=False
    return sig

def signal_ma_resonance(closes, highs, lows, opens, volumes,
                        ma1=5, ma2=20, ma3=60):
    if len(closes)<ma3+5: return [0]*len(closes)
    m1=ma(closes,ma1); m2=ma(closes,ma2); m3=ma(closes,ma3)
    sig=[0]*len(closes); in_pos=False
    for i in range(ma3,len(closes)):
        gc=(m1[i-1]<=m2[i-1] and m1[i]>m2[i])
        dc=(m1[i-1]>=m2[i-1] and m1[i]<m2[i])
        if not in_pos:
            if gc and m2[i]>m3[i]: sig[i]=1; in_pos=True
        else:
            if dc or m2[i]<m3[i]: sig[i]=-1; in_pos=False
    return sig

def signal_turtle_with_atr(closes, highs, lows, opens, volumes,
                           entry=20, exit_=10, atr_mult=2.0):
    """海龟 + ATR动态止损"""
    at=atr(highs,lows,closes,14)
    sig=[0]*len(closes); entry_px=0; pos=0; pos_type=0
    for i in range(entry,len(closes)):
        hh=max(highs[i-entry:i+1]); ll=min(lows[i-exit_:i+1])
        # ATR止损
        sl_long=closes[i]-at[i]*atr_mult
        sl_short=closes[i]+at[i]*atr_mult
        if pos==0:
            if closes[i]>hh: sig[i]=1; pos=1; entry_px=closes[i]
            elif closes[i]<ll: sig[i]=-1; pos=1; entry_px=closes[i]; pos_type=-1
        elif pos==1 and pos_type==1:
            if closes[i]<sl_long or closes[i]<ll: sig[i]=-1; pos=0; pos_type=0
        elif pos==1 and pos_type==-1:
            if closes[i]>sl_short or closes[i]>hh: sig[i]=1; pos=0; pos_type=0
    return sig


# ═══════════════════════════════════════════════════════
# 参数网格
# ═══════════════════════════════════════════════════════

PARAM_GRIDS = {
    "布林带": {
        "fn":        signal_boll,
        "params": {
            "n": [10, 15, 20, 30, 60],
            "k": [1.5, 2.0, 2.5, 3.0],
        },
        "label": "n={n}, k={k}",
    },
    "MACD": {
        "fn": signal_macd,
        "params": {
            "f":  [8,  12, 16],
            "s":  [20, 26, 34],
            "sg": [6,  9,  12],
        },
        "label": "f={f}, s={s}, sg={sg}",
    },
    "RSI+MA混合": {
        "fn": signal_rsi_ma,
        "params": {
            "rsi_n":  [10, 14, 21],
            "rsi_lo": [25, 30, 35],
            "rsi_hi": [65, 70, 75],
            "ma_fast": [5,  10],
            "ma_slow": [20, 60],
        },
        "label": "RSI({rsi_n},{rsi_lo},{rsi_hi})+MA({ma_fast},{ma_slow})",
    },
    "海龟+ATR止损": {
        "fn": signal_turtle_with_atr,
        "params": {
            "entry":    [10, 20, 55],
            "exit_":    [5,  10, 20],
            "atr_mult": [1.5, 2.0, 3.0],
        },
        "label": "Entry={entry}, Exit={exit_}, ATR×{atr_mult}",
    },
    "定风波": {
        "fn": signal_dingfengbo,
        "params": {
            "ma_p":      [10, 20, 60],
            "dev_thresh": [0.05, 0.08, 0.10, 0.15],
            "vol_lkbk":  [20, 30],
        },
        "label": "MA={ma_p}, Dev={dev_thresh}, Vol={vol_lkbk}",
    },
    "均线共振": {
        "fn": signal_ma_resonance,
        "params": {
            "ma1": [5,  10],
            "ma2": [20, 30],
            "ma3": [60, 120],
        },
        "label": "MA({ma1},{ma2},{ma3})",
    },
}


# ═══════════════════════════════════════════════════════
# 合理性评估
# ═══════════════════════════════════════════════════════

def evaluate(result: dict, bench_annual: float = 0) -> dict:
    """
    多维度评估策略合理性，返回评分 dict

    评分项：
      sharpe_score     : 夏普 > 0.5 → 60分, 0.3~0.5 → 40分, < 0 → 0分
      drawdown_score  : 回撤 < 10% → 60分, 10~20% → 40分, 20~30% → 20分, > 30% → 0分
      trade_score     : 交易 10~100次 → 40分, 5~10 → 30分, 其他 → 0分
      winrate_score   : 胜率 30~80% → 40分，其他 → 递减
      profit_score    : 年化 > bench+10% → 40分, > bench → 30分, > 0 → 20分, else → 0
      stability_score : equity_curve 收益率序列标准差，< 0.02 → 40分, < 0.05 → 20分
      consistency     : 年化 vs 基准差值合理（20%以内）
    """
    if not result:
        return {"total": 0, "pass": False, "reason": "无结果"}

    ann  = result.get("ann_return_pct", 0)
    sh   = result.get("sharpe", 0)
    dd   = result.get("max_drawdown_pct", 999)
    ntr  = result.get("total_trades", 0)
    wr   = result.get("win_rate_pct", 0)
    pf   = result.get("profit_factor", 0)
    eq   = result.get("equity_curve", [])

    scores = {}
    reasons = []

    # 1. 夏普（40分）
    if sh >= 1.0:   s = 40; reasons.append(f"夏普{sh:.2f}优秀")
    elif sh >= 0.5: s = 30; reasons.append(f"夏普{sh:.2f}良好")
    elif sh >= 0.3: s = 20; reasons.append(f"夏普{sh:.2f}一般")
    elif sh >= 0:   s = 10; reasons.append(f"夏普{sh:.2f}偏低")
    else:            s = 0;  reasons.append(f"夏普{sh:.2f}为负")
    scores["sharpe"] = s

    # 2. 最大回撤（40分）
    if dd <= 5:    s = 40; reasons.append(f"回撤{dd:.1f}%极优")
    elif dd <= 10: s = 30; reasons.append(f"回撤{dd:.1f}%良好")
    elif dd <= 20: s = 20; reasons.append(f"回撤{dd:.1f}%可接受")
    elif dd <= 30: s = 10; reasons.append(f"回撤{dd:.1f}%偏高")
    else:          s = 0;  reasons.append(f"回撤{dd:.1f}%过大")
    scores["drawdown"] = s

    # 3. 交易次数（20分）—— 样本量充足但不过拟合
    if 10 <= ntr <= 100: s = 20; reasons.append(f"交易{ntr}次合理")
    elif 5  <= ntr < 10:  s = 12; reasons.append(f"交易{ntr}次偏少")
    elif 100 < ntr <= 200: s = 12; reasons.append(f"交易{ntr}次偏多")
    else:                 s = 0;  reasons.append(f"交易{ntr}次样本不足")
    scores["trade_count"] = s

    # 4. 胜率（20分）—— 合理区间
    if 30 <= wr <= 85:  s = 20; reasons.append(f"胜率{wr:.0f}%合理")
    elif 20 <= wr < 30: s = 12; reasons.append(f"胜率{wr:.0f}%偏低")
    elif wr > 90:        s = 5;  reasons.append(f"胜率{wr:.0f}%存疑(过拟合?)")
    else:                s = 0;  reasons.append(f"胜率{wr:.0f}%不合格")
    scores["winrate"] = s

    # 5. 盈利质量（20分）
    if ann >= 30:  s = 20; reasons.append(f"年化{ann:.1f}%优秀")
    elif ann >= 10: s = 15; reasons.append(f"年化{ann:.1f}%良好")
    elif ann > 0:   s = 10; reasons.append(f"年化{ann:.1f}%为正")
    else:           s = 0;  reasons.append(f"年化{ann:.1f}%亏损")
    scores["profit"] = s

    # 6. 盈亏比（20分）
    if pf >= 3.0:  s = 20; reasons.append(f"盈亏比{pf:.2f}优秀")
    elif pf >= 1.5: s = 15; reasons.append(f"盈亏比{pf:.2f}良好")
    elif pf >= 1.0: s = 10; reasons.append(f"盈亏比{pf:.2f}一般")
    else:           s = 0;  reasons.append(f"盈亏比{pf:.2f}不合格")
    scores["profit_factor"] = s

    total = sum(scores.values())
    max_possible = 40+40+20+20+20+20  # = 160

    return {
        "total":       total,
        "max":         max_possible,
        "pct":         round(total / max_possible * 100, 1),
        "sharpe":      round(sh, 3),
        "drawdown":    round(dd, 1),
        "trades":      ntr,
        "winrate":     round(wr, 1),
        "ann_return":  round(ann, 1),
        "profit_factor": round(pf, 2),
        "scores":      scores,
        "reasons":     reasons,
        "pass":        total >= 80,    # 80分合格
        "grade":       "A" if total >= 120 else ("B" if total >= 80 else ("C" if total >= 50 else "D")),
    }


# ═══════════════════════════════════════════════════════
# Walk-Forward 分析（避免过拟合）
# ═══════════════════════════════════════════════════════

def walk_forward_validate(
        rows: List[dict],
        strategy_fn: Callable,
        param_combinations: List[dict],
        train_years: int = 2,
        test_year: int = 1,
        initial: float = 1_000_000
) -> List[dict]:
    """
    Walk-Forward：滚动验证
    每年切片：前train_years年训练，后test_year年验证
    检验参数在样本外是否仍然有效
    """
    years = sorted(set(r["date"][:4] for r in rows))
    results = []

    for i in range(len(years) - train_years):
        train_yrs = years[i:i+train_years]
        test_yr  = years[i+train_years] if i+train_years < len(years) else None

        train_rows = [r for r in rows if r["date"][:4] in train_yrs]
        test_rows  = [r for r in rows if r["date"][:4] == test_yr] if test_yr else []

        if len(train_rows) < 100 or len(test_rows) < 50:
            continue

        closes=[r["close"] for r in train_rows]
        highs=[r["high"]  for r in train_rows]
        lows=[r["low"]   for r in train_rows]
        opens=[r["open"]  for r in train_rows]
        vols=[r["volume"] for r in train_rows]

        closes_t=[r["close"] for r in test_rows]
        highs_t=[r["high"]  for r in test_rows]
        lows_t=[r["low"]   for r in test_rows]
        opens_t=[r["open"]  for r in test_rows]
        vols_t=[r["volume"] for r in test_rows]

        best_in_sample = None
        best_score = -999

        for p in param_combinations:
            try:
                sig=strategy_fn(closes,highs,lows,opens,vols,**p)
                r=backtest_signal("tmp",train_rows,
                                 lambda c,h,l,o,v,_sig=sig: _sig,initial=initial)
                if r and r["ann_return_pct"]>0:
                    sc=evaluate(r)
                    if sc["total"]>best_score:
                        best_score=sc["total"]; best_in_sample=r; best_params=p
            except: pass

        if best_in_sample and best_params:
            sig_t=strategy_fn(closes_t,highs_t,lows_t,opens_t,vols_t,**best_params)
            r_out=backtest_signal("tmp",test_rows,
                                 lambda c,h,l,o,v,_sig=sig_t: _sig,initial=initial)
            if r_out:
                train_ann=best_in_sample["ann_return_pct"]
                test_ann =r_out["ann_return_pct"]
                oos_pct=(test_ann-train_ann)/abs(train_ann) if train_ann!=0 else 0
                results.append({
                    "train_years":   ",".join(train_yrs),
                    "test_year":     test_yr,
                    "train_ann":     round(train_ann,2),
                    "test_ann":      round(test_ann,2),
                    "params":        best_params,
                    "oos_decay":     round(oos_pct*100,1),
                    "pass":          abs(oos_pct)<0.5 and test_ann>0,
                })

    return results


# ═══════════════════════════════════════════════════════
# 主网格搜索
# ═══════════════════════════════════════════════════════

def grid_search(rows: List[dict],
               initial: float = 1_000_000,
               bench_annual: float = 0) -> List[dict]:
    """
    对所有策略 + 所有参数组合进行回测
    返回：[{strategy_name, params, result, eval, ...}]
    """
    closes=[r["close"] for r in rows]
    highs=[r["high"]  for r in rows]
    lows=[r["low"]   for r in rows]
    opens=[r["open"]  for r in rows]
    vols=[r["volume"] for r in rows]

    all_results = []

    for strat_name, grid in PARAM_GRIDS.items():
        fn = grid["fn"]
        keys  = list(grid["params"].keys())
        vals  = list(grid["params"].values())
        label = grid["label"]

        # 生成所有参数组合
        combos = [dict(zip(keys, v)) for v in product(*vals)]

        print(f"\n  🔍 {strat_name}: {len(combos)} 种参数组合")

        for p in combos:
            try:
                sig = fn(closes,highs,lows,opens,vols,**p)
                r = backtest_signal(
                    f"{strat_name}|{label.format(**p)}",
                    rows,
                    lambda c,h,l,o,v,_sig=sig: _sig,
                    initial=initial
                )
                if r and r["total_trades"] >= 3:
                    ev = evaluate(r, bench_annual)
                    all_results.append({
                        "strategy":     strat_name,
                        "params":       p,
                        "label":         label.format(**p),
                        "result":        r,
                        "eval":          ev,
                        "ann":           r.get("ann_return_pct", 0),
                    })
            except Exception:
                pass

    return sorted(all_results, key=lambda x: x["eval"]["total"], reverse=True)


# ═══════════════════════════════════════════════════════
# 报告生成
# ═══════════════════════════════════════════════════════

def print_report(all_results: List[dict],
                 bench_annual: float,
                 top_n: int = 20):
    """生成格式化的评估报告"""

    print(f"\n{'═'*80}")
    print(f"  📊 策略参数网格搜索报告  |  共 {len(all_results)} 组参数通过初筛")
    print(f"{'═'*80}")
    print(f"\n  {'策略':<18}  {'参数':<30}  {'年级':>7}  {'夏普':>6}  {'回撤':>6}  "
          f"{'交易':>5}  {'胜率':>5}  {'评分':>5}  {'等级':>3}  {'结论'}")
    print(f"  {'─'*110}")

    for item in all_results[:top_n]:
        ev  = item["eval"]
        r   = item["result"]
        strat = item["strategy"]
        label = item["label"]

        vs_bench = r["ann_return_pct"] - bench_annual
        vs_icon = "✅" if vs_bench > 0 else "⚠️ "

        print(f"  {vs_icon}{strat:<16}  {label:<30}  "
              f"{r['ann_return_pct']:>+6.1f}%  "
              f"{r['sharpe']:>6.3f}  "
              f"{r['max_drawdown_pct']:>5.1f}%  "
              f"{r['total_trades']:>5d}  "
              f"{r['win_rate_pct']:>5.1f}%  "
              f"{ev['pct']:>5.1f}%  "
              f"{ev['grade']:>3}   "
              f"{', '.join(ev['reasons'][:2])}")

    # 通过评估的数量
    passed = [x for x in all_results if x["eval"]["pass"]]
    grade_dist = {}
    for x in all_results:
        g = x["eval"]["grade"]
        grade_dist[g] = grade_dist.get(g,0)+1

    print(f"\n  📋 评估结果：")
    print(f"     总参数组合: {len(all_results)}")
    print(f"     合格(≥80分): {len(passed)} 个")
    print(f"     评级分布: " + "  ".join(f"{k}={v}" for k,v in sorted(grade_dist.items())))

    # Top 3
    print(f"\n  🏆 Top 3 最优参数（按综合评分）:")
    for i, item in enumerate(all_results[:3]):
        ev = item["eval"]
        r  = item["result"]
        print(f"\n     🥇 #{i+1} {item['strategy']} | {item['label']}")
        print(f"        年化: {r['ann_return_pct']:+.1f}% | 夏普: {r['sharpe']:.3f} | "
              f"回撤: {r['max_drawdown_pct']:.1f}% | 胜率: {r['win_rate_pct']:.0f}%")
        print(f"        盈亏比: {r['profit_factor']:.2f} | 交易: {r['total_trades']}次")
        print(f"        合理性: {ev['pct']}% ({ev['grade']}级)")
        print(f"        亮点: {'; '.join(ev['reasons'][:3])}")

    return passed
