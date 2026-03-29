# factors/volume.py
# 量价类因子
# AD · VPT · Signal Horizon · Mass Index · Ergodic

import math
from typing import List, Tuple
from factors.base_operators import sma, ema, atr

def accdist(highs: list, lows: list, closes: list,
           volumes: list) -> List[float]:
    """
    AD（累积派发线）— 量价背离分析
    创新高+AD下降 → 主力出货；创新低+AD上升 → 主力吸筹
    """
    n = min(len(closes), len(volumes), len(highs), len(lows))
    ad = [float("nan")] * n
    accum = 0.0
    for i in range(n):
        if i == 0:
            ad[0] = 0.0
            continue
        if highs[i] != lows[i]:
            mf = 2.0 * closes[i] - lows[i] - highs[i]
            accum += volumes[i] * mf / (highs[i] - lows[i])
        ad[i] = accum
    return ad


def accumulation_distribution_signal(closes: list, highs: list,
                                   lows: list, volumes: list) -> List[int]:
    """AD 背离信号：价格创新高而AD下降→空；价格创新低而AD上升→多"""
    ad = accdist(highs, lows, closes, volumes)
    n = len(closes)
    signal = [0] * n
    for i in range(1, n):
        price_rising = closes[i] > closes[i - 1]
        ad_rising    = ad[i] > ad[i - 1] if not (math.isnan(ad[i]) or math.isnan(ad[i - 1])) else False
        if price_rising and not ad_rising:
            signal[i] = -1
        elif not price_rising and ad_rising:
            signal[i] = 1
    return signal


def volume_price_trend(closes: list, volumes: list) -> List[float]:
    """VPT（成交量价格趋势）"""
    n = min(len(closes), len(volumes))
    vpt = [float("nan")] * n
    accum = 0.0
    for i in range(1, n):
        if closes[i - 1] == 0:
            accum += 0.0
        else:
            accum += (closes[i] - closes[i - 1]) / closes[i - 1] * volumes[i]
        vpt[i] = accum
    return vpt


def mass_index(highs: list, lows: list, ema_period: int = 9,
              ema2_period: int = 25) -> List[float]:
    """
    Mass Index（梅斯指标）
    高位反转信号：mass>27后跌穿26.5→趋势反转
    """
    tr_vals = [float("nan")] * len(highs)
    for i in range(1, len(highs)):
        tr_vals[i] = max(highs[i] - lows[i],
                         abs(highs[i] - closes[i - 1]) if i > 0 else 0.0,
                         abs(lows[i] - closes[i - 1])  if i > 0 else 0.0)
    ema1 = ema(tr_vals, ema_period)
    ema2 = ema(ema1, ema2_period)
    n = len(highs)
    mass = [float("nan")] * n
    for i in range(ema2_period - 1, n):
        if math.isnan(ema1[i]) or math.isnan(ema2[i]):
            continue
        mass[i] = ema1[i] / (ema2[i] + 1e-10)
    return mass


def ergodic_oscillator(closes: list, highs: list, lows: list,
                      period: int = 20, smooth: int = 5) -> Tuple[List[float], List[float]]:
    """
    Ergodic Oscillator（遍历摆动指标）
    返回 (ergodic_line, signal_line)
    """
    from factors.base_operators import sma as base_sma
    n = len(closes)
    signal = [0.0] * n
    sma_c = sma(closes, period)
    for i in range(n):
        if math.isnan(sma_c[i]):
            continue
        hl = highs[i] - lows[i]
        signal[i] = (closes[i] - sma_c[i]) / (hl + 1e-10) if abs(hl) > 1e-10 else 0.0
    ergodic = [float("nan")] * n
    for i in range(smooth - 1, n):
        window = [signal[j] for j in range(i - smooth + 1, i + 1) if not math.isnan(signal[j])]
        if window:
            ergodic[i] = sum(window) / len(window)
    sig_line = sma(ergodic, smooth)
    return ergodic, sig_line


def ergodic_signal(closes: list, highs: list, lows: list) -> List[int]:
    """Ergodic 信号：signal_line > 0 → 多"""
    e, s = ergodic_oscillator(closes, highs, lows)
    return [1 if s[i] > 0 and not math.isnan(s[i]) else -1 for i in range(len(closes))]


def signal_horizon(highs: list, lows: list, closes: list,
                  smooth: int = 5) -> Tuple[List[float], List[float]]:
    """
    Signal Horizon（信号地平线）
    趋势强度 = (close - rolling_low) / (rolling_high - rolling_low + 1e-10)
    """
    n = len(closes)
    sh_vals = [float("nan")] * n
    for i in range(smooth, n):
        window_c = closes[i - smooth + 1:i + 1]
        window_h = highs[i - smooth + 1:i + 1]
        window_l = lows[i - smooth + 1:i + 1]
        lo = min(window_l)
        hi = max(window_h)
        if abs(hi - lo) < 1e-10:
            sh_vals[i] = 0.5
        else:
            sh_vals[i] = (closes[i] - lo) / (hi - lo)
    sig = sma(sh_vals, smooth)
    return sh_vals, sig
