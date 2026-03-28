"""
regime_engine.py — 市场状态识别 + 策略自适应切换
======================================================
核心理念：不同市场状态用不同策略
  趋势市（ADX↑ + Bandwidth扩张）→ 趋势策略（MACD / 均线 / 海龟）
  震荡市（ADX↓ + Bandwidth收缩）→ 均值回归（布林带 / RSI）
  过渡期                        → 观望/轻仓

判断指标：
  ADX > 25  → 有趋势
  Bandwidth < 历史20%分位  → 波动收缩（震荡蓄势）
  Bandwidth > 历史80%分位  → 波动扩张（趋势展开）
"""

import sys, math
from pathlib import Path
from typing import List, Dict, Tuple, Callable, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from strategies.backtest_engine import backtest_signal

# ═══════════════════════════════════════════════════════
# 指标计算
# ═══════════════════════════════════════════════════════

def ma(arr: List[float], n: int) -> List[float]:
    return [sum(arr[max(0, i-n+1):i+1]) / min(n, i+1) for i in range(len(arr))]

def atr(highs: List[float], lows: List[float], closes: List[float], n: int = 14) -> List[float]:
    trs = [0.0]
    for i in range(1, len(highs)):
        tr = max(highs[i]-lows[i],
                 abs(highs[i]-closes[i-1]),
                 abs(lows[i]-closes[i-1]))
        trs.append(tr)
    out = [0.0] * (n-1)
    for i in range(n-1, len(trs)):
        out.append(sum(trs[i-n+1:i+1]) / n)
    return out

def adx(highs: List[float], lows: List[float], closes: List[float], n: int = 14) -> Tuple[List[float], List[float], List[float]]:
    """
    返回 (adx, p_di, m_di)
    adx > 25 → 有趋势
    """
    p_dm = [max(highs[i]-highs[i-1], 0) for i in range(1, len(highs))]
    m_dm = [max(lows[i-1]-lows[i],   0) for i in range(1, len(highs))]
    tr_arr = [max(highs[i]-lows[i],
                  abs(highs[i]-closes[i-1]),
                  abs(lows[i]-closes[i-1]))
             for i in range(1, len(highs))]

    pad = [0.0] * (n-1)
    p_di = pad + [
        a/b*100 if b > 0 else 0
        for a, b in zip(ma(p_dm, n), ma(tr_arr, n))
    ]
    m_di = pad + [
        a/b*100 if b > 0 else 0
        for a, b in zip(ma(m_dm, n), ma(tr_arr, n))
    ]
    dx = [abs(p_di[i]-m_di[i]) / (p_di[i]+m_di[i]+1e-9) * 100
          for i in range(n-1, len(p_di))]
    adx_ = [0.0] * (n*2-2) + ma(dx[n-1:], n)
    return adx_, p_di, m_di

def boll_bands(closes: List[float], n: int = 20, k: float = 2.0):
    std = []
    for i in range(len(closes)):
        s = closes[max(0, i-n+1):i+1]
        m = sum(s)/len(s)
        std.append(math.sqrt(sum((x-m)**2 for x in s) / len(s)))
    mid = ma(closes, n)
    return [m+k*s for m,s in zip(mid,std)], mid, [m-k*s for m,s in zip(mid,std)]

def bandwidth(closes: List[float], n: int = 20, k: float = 2.0) -> List[float]:
    upper, mid, lower = boll_bands(closes, n, k)
    return [(upper[i]-lower[i])/mid[i] if mid[i] != 0 else 0 for i in range(len(closes))]

def rsi(closes: List[float], n: int = 14) -> List[float]:
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i]-closes[i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    avg_g = ma(gains, n); avg_l = ma(losses, n)
    return [100-100/(1+a/b) if b>0 else 50 for a,b in zip(avg_g, avg_l)]

def ema(arr: List[float], n: int) -> List[float]:
    if not arr: return []
    k = 2/(n+1)
    return [arr[0]] + [arr[i]*k + arr[i-1]*(1-k) for i in range(1, len(arr))]

def macd(closes: List[float], f: int = 12, s: int = 26, sig: int = 9):
    ef = ema(closes, f); es = ema(closes, s)
    dif = [ef[i]-es[i] for i in range(len(ef))]
    dea = [sum(dif[max(0,i-sig+1):i+1])/min(sig,i+1) for i in range(len(dif))]
    return dif, dea


# ═══════════════════════════════════════════════════════
#  市场状态识别
# ═══════════════════════════════════════════════════════

ADX_PERIOD   = 14
BOLL_PERIOD   = 20
REGIME_WARMUP = ADX_PERIOD * 3  # 需要足够历史数据才能判断状态


class RegimeDetector:
    """
    实时识别市场状态
    
    States:
      TREND_UP    — 上升趋势（ADX>25 且 +DI > -DI）
      TREND_DOWN  — 下降趋势（ADX>25 且 -DI > +DI）
      VOLATILE    — 波动震荡（ADX<20）
      TRANSITIONAL — 过渡状态（20 ≤ ADX ≤ 25）
    """

    TREND_UP, TREND_DOWN, VOLATILE, TRANSITIONAL = 1, -1, 0, 2

    def __init__(self, adx_thresh: float = 25.0,
                 bw_percentile_lo: float = 20.0,
                 bw_percentile_hi: float = 80.0,
                 bw_lookback: int = 60):
        self.adx_thresh    = adx_thresh
        self.bw_lo = bw_percentile_lo
        self.bw_hi = bw_percentile_hi
        self.bw_lookback = bw_lookback

    def detect(self, closes: List[float], highs: List[float],
               lows: List[float]) -> List[int]:
        """返回每个时点的市场状态"""
        if len(closes) < REGIME_WARMUP:
            return [2] * len(closes)  # TRANSITIONAL until enough data

        adx_vals, p_di, m_di = adx(highs, lows, closes, ADX_PERIOD)
        bw = bandwidth(closes, BOLL_PERIOD)

        # 计算Bandwidth的分位数阈值
        bw_hist = bw[-min(len(bw), self.bw_lookback):]
        bw_lo_val = sorted(bw_hist)[int(len(bw_hist) * self.bw_lo / 100)] if len(bw_hist) >= 5 else 0
        bw_hi_val = sorted(bw_hist)[int(len(bw_hist) * self.bw_hi / 100)] if len(bw_hist) >= 5 else 1

        sig = [2] * REGIME_WARMUP  # 预热期 = 过渡态

        for i in range(REGIME_WARMUP, len(closes)):
            adx_val = adx_vals[i]
            bw_val  = bw[i]

            if adx_val < 20:
                sig.append(self.VOLATILE)
            elif adx_val > self.adx_thresh:
                sig.append(self.TREND_UP if p_di[i] > m_di[i] else self.TREND_DOWN)
            else:
                sig.append(self.TREND_UP if p_di[i] > m_di[i] else self.TREND_DOWN)

        return sig

    def labels(self, closes, highs, lows):
        """返回状态名称列表"""
        states = self.detect(closes, highs, lows)
        names = {self.TREND_UP: "📈上升趋势", self.TREND_DOWN: "📉下降趋势",
                 self.VOLATILE: "🔄震荡", self.TRANSITIONAL: "⏳过渡"}
        return [names[s] for s in states]


# ═══════════════════════════════════════════════════════
#  策略信号生成器
# ═══════════════════════════════════════════════════════

def signal_boll(closes, highs, lows, opens, vols, n=20, k=2.0):
    upper, mid, lower = boll_bands(closes, n, k)
    sig = [0]*len(closes)
    for i in range(n, len(closes)):
        if closes[i] <= lower[i] and closes[i-1] > lower[i-1]:
            sig[i] = 1
        elif closes[i] >= upper[i] and closes[i-1] < upper[i-1]:
            sig[i] = -1
    return sig

def signal_macd(closes, highs, lows, opens, vols, f=12, s=26, sg=9):
    dif, dea = macd(closes, f, s, sg)
    sig = [0]*len(closes)
    for i in range(s, len(closes)):
        if dif[i-1] <= dea[i-1] and dif[i] > dea[i]:
            sig[i] = 1
        elif dif[i-1] >= dea[i-1] and dif[i] < dea[i]:
            sig[i] = -1
    return sig

def signal_ma_cross(closes, highs, lows, opens, vols, fast=5, slow=20):
    m1 = ma(closes, fast); m2 = ma(closes, slow)
    sig = [0]*len(closes)
    for i in range(slow, len(closes)):
        if m1[i-1] <= m2[i-1] and m1[i] > m2[i]:
            sig[i] = 1
        elif m1[i-1] >= m2[i-1] and m1[i] < m2[i]:
            sig[i] = -1
    return sig

def signal_rsi(closes, highs, lows, opens, vols, n=14, lo=35, hi=70):
    rv = rsi(closes, n)
    sig = [0]*len(closes)
    for i in range(n, len(closes)):
        if rv[i-1] < lo and rv[i] >= lo:
            sig[i] = 1
        elif rv[i-1] > hi and rv[i] <= hi:
            sig[i] = -1
    return sig


# ═══════════════════════════════════════════════════════
#  自适应切换回测
# ═══════════════════════════════════════════════════════

def regime_switch_signal(
        closes: List[float],
        highs: List[float],
        lows: List[float],
        opens: List[float],
        volumes: List[float],
        regime_detector: RegimeDetector,
        trend_sig_fn: Callable,    # 趋势策略信号
        vol_sig_fn: Callable,      # 震荡策略信号
        trend_sig_params: dict = {},
        vol_sig_params: dict = {}
) -> List[int]:
    """
    根据当前市场状态自动切换策略

    震荡(VOLATILE)     → 用均值回归策略（布林带 / RSI）
    上升趋势(TREND_UP) → 用趋势策略（MACD / 均线金叉）
    下降趋势(TREND_DOWN) → 做空 或 观望
    过渡态             → 保持上一步仓位
    """
    regimes = regime_detector.detect(closes, highs, lows)

    trend_sig = trend_sig_fn(closes, highs, lows, opens, volumes, **trend_sig_params)
    vol_sig   = vol_sig_fn(closes, highs, lows, opens, volumes, **vol_sig_params)

    sig  = [0] * len(closes)
    pos  = 0  # 当前持仓状态

    for i in range(REGIME_WARMUP, len(closes)):
        regime = regimes[i]

        if regime == RegimeDetector.VOLATILE:
            sig[i] = vol_sig[i]
        elif regime == RegimeDetector.TREND_UP:
            sig[i] = trend_sig[i]
        elif regime == RegimeDetector.TREND_DOWN:
            # 下降趋势：只做空，不做多
            sig[i] = -1 if trend_sig[i] == -1 else 0
        else:
            # 过渡态：空仓观望
            sig[i] = 0

    return sig


# ═══════════════════════════════════════════════════════
#  全量分析
# ═══════════════════════════════════════════════════════

def analyze_regime_stats(rows: List[dict],
                          regime_detector: RegimeDetector) -> Dict:
    """统计各状态分布和平均持续天数"""
    closes = [r["close"] for r in rows]
    highs  = [r["high"]  for r in rows]
    lows   = [r["low"]   for r in rows]
    regimes = regime_detector.detect(closes, highs, lows)

    counts = {0: 0, 1: 0, 2: 0, -1: 0}
    streak = {0: [], 1: [], 2: [], -1: []}
    cur, len_ = regimes[REGIME_WARMUP], 1

    for r in regimes[REGIME_WARMUP+1:]:
        if r == cur:
            len_ += 1
        else:
            streak[cur].append(len_)
            counts[cur] += 1
            cur, len_ = r, 1
    streak[cur].append(len_)

    labels = {1: "上升趋势", -1: "下降趋势", 0: "震荡", 2: "过渡"}
    avg_dur = {labels[k]: round(sum(v)/max(len(v),1), 1) if v else 0
               for k, v in streak.items()}
    pct     = {labels[k]: round(counts[k]/sum(counts.values())*100, 1)
               for k in counts}

    return {
        "counts":    {labels[k]: v for k, v in counts.items()},
        "avg_days":  avg_dur,
        "pct":       pct,
        "regimes":   regimes,
        "labels":    regime_detector.labels(closes, highs, lows),
    }


def full_backtest(rows: List[dict],
                  regime_detector: RegimeDetector,
                  trend_fn, vol_fn,
                  trend_params, vol_params,
                  initial: float = 1_000_000) -> Dict:
    """
    对比三种模式：
    1. 纯趋势策略
    2. 纯震荡策略
    3. 自适应切换（核心创新）
    """
    closes = [r["close"] for r in rows]
    highs  = [r["high"]  for r in rows]
    lows   = [r["low"]   for r in rows]
    opens  = [r["open"]  for r in rows]
    vols   = [r["volume"] for r in rows]

    regimes = regime_detector.detect(closes, highs, lows)

    def run(name, sig_fn):
        r = backtest_signal(name, rows, sig_fn, initial=initial)
        return r if r else {}

    r_trend  = run("趋势(MACD)",         lambda c,h,l,o,v: trend_fn(c,h,l,o,v,**trend_params))
    r_vol    = run("震荡(布林带)",        lambda c,h,l,o,v: vol_fn(c,h,l,o,v,**vol_params))

    # 自适应切换信号
    combined_sig = regime_switch_signal(
        closes, highs, lows, opens, vols,
        regime_detector,
        trend_fn, vol_fn,
        trend_params, vol_params
    )
    r_adapt  = run("自适应切换(ADX+Bandwidth)",  lambda c,h,l,o,v: combined_sig)

    return {
        "trend": r_trend,
        "vol":   r_vol,
        "adapt": r_adapt,
    }
