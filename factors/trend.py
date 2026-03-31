# factors/trend.py
# 趋势类因子
# Ichimoku Cloud · Parabolic SAR · KST · TRIX · Donchian · Aroon

import math
from typing import List, Tuple
from factors.base_operators import sma, ema, roc, _min_idx

def ichimoku_cloud(highs: list, lows: list, closes: list,
                   tenkan: int = 9, kijun: int = 26, senkou_b: int = 52,
                   displacement: int = 26
                   ) -> Tuple[List[float], List[float], List[float], List[float], List[float]]:
    """
    Ichimoku Cloud（一目均衡表）
    返回 (tenkan_sen, kijun_sen, senkou_a, senkou_b, chikou_span)
    """
    n = len(closes)
    def _mid(h_arr, l_arr, period, idx):
        if idx < period - 1:
            return float("nan")
        return (max(h_arr[idx - period + 1:idx + 1]) + min(l_arr[idx - period + 1:idx + 1])) / 2.0

    tenkan_s  = [float("nan")] * n
    kijun_s   = [float("nan")] * n
    senkou_a  = [float("nan")] * n
    senkou_b_ = [float("nan")] * n
    chikou    = [float("nan")] * n

    for i in range(n):
        tenkan_s[i]  = _mid(highs, lows, tenkan, i)
        kijun_s[i]   = _mid(highs, lows, kijun, i)
        senkou_a[i]  = (tenkan_s[i] + kijun_s[i]) / 2.0 \
            if not (math.isnan(tenkan_s[i]) or math.isnan(kijun_s[i])) else float("nan")
        senkou_b_[i] = _mid(highs, lows, senkou_b, i)
        chikou[i]    = closes[i - displacement] if i >= displacement else float("nan")
    return tenkan_s, kijun_s, senkou_a, senkou_b_, chikou


def ichimoku_signal(closes: list, highs: list, lows: list,
                    tenkan: int = 9, kijun: int = 26,
                    senkou_b: int = 52) -> List[int]:
    """
    Ichimoku 交易信号：1=多/-1=空/0=中性
    金叉(tenkan上穿kijun)+价格站上云顶 → 多；死叉 → 空
    """
    tenkan_s, kijun_s, senkou_a, senkou_b, _ = ichimoku_cloud(highs, lows, closes, tenkan, kijun, senkou_b)
    n = len(closes)
    signal = [0] * n
    for i in range(1, n):
        if math.isnan(tenkan_s[i]) or math.isnan(kijun_s[i]):
            continue
        above_prev = tenkan_s[i - 1] >= kijun_s[i - 1] if not math.isnan(tenkan_s[i - 1]) else False
        above_now  = tenkan_s[i] >= kijun_s[i]
        cloud_top  = senkou_a[i] if not math.isnan(senkou_a[i]) else senkou_b[i]
        cloud_bot  = senkou_b[i] if not math.isnan(senkou_b[i]) else senkou_a[i]
        if above_now and not above_prev and closes[i] > cloud_top:
            signal[i] = 1
        elif not above_now and above_prev and closes[i] < cloud_bot:
            signal[i] = -1
    return signal


def parabolic_sar(highs: list, lows: list, closes: list,
                  af_start: float = 0.02, af_step: float = 0.02,
                  af_max: float = 0.2) -> List[float]:
    """
    Parabolic SAR（抛物线止损转向）
    返回 SAR 值序列（SAR < close → 多；SAR > close → 空）
    """
    n = len(closes)
    if n < 2:
        return [float("nan")] * n
    sar   = [float("nan")] * n
    trend = 1   # 1=上涨，-1=下跌
    af    = af_start
    ep    = highs[0]
    sar[0] = lows[0]
    for i in range(1, n):
        sar[i] = sar[i - 1] + af * (ep - sar[i - 1])
        if trend == 1:
            sar[i] = min(sar[i], sar[i - 1] if i > 1 else sar[i])
            sar[i] = min(sar[i], lows[i - 1])
            if i > 1:
                sar[i] = min(sar[i], lows[i - 2])
            if lows[i] < sar[i]:
                trend = -1
                sar[i] = ep
                ep = lows[i]
                af = af_start
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + af_step, af_max)
        else:
            sar[i] = max(sar[i], sar[i - 1] if i > 1 else sar[i])
            sar[i] = max(sar[i], highs[i - 1])
            if i > 1:
                sar[i] = max(sar[i], highs[i - 2])
            if highs[i] > sar[i]:
                trend = 1
                sar[i] = ep
                ep = highs[i]
                af = af_start
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + af_step, af_max)
    return sar


def kst(closes: list,
        roc1: int = 10, roc2: int = 15, roc3: int = 20, roc4: int = 30,
        sma1: int = 10, sma2: int = 10, sma3: int = 10, sma4: int = 15
        ) -> Tuple[List[float], List[float]]:
    """
    KST (Know Sure Thing) — 多周期 ROC 平滑指标
    返回 (kst_line, signal_line)
    """
    n = len(closes)
    kst_vals = [float("nan")] * n
    for i in range(n):
        r1 = roc(closes, roc1)
        r2 = roc(closes, roc2)
        r3 = roc(closes, roc3)
        r4 = roc(closes, roc4)
        v1 = r1[i] if i < len(r1) and not math.isnan(r1[i]) else 0.0
        v2 = r2[i] if i < len(r2) and not math.isnan(r2[i]) else 0.0
        v3 = r3[i] if i < len(r3) and not math.isnan(r3[i]) else 0.0
        v4 = r4[i] if i < len(r4) and not math.isnan(r4[i]) else 0.0
        kst_vals[i] = v1 + 2 * v2 + 3 * v3 + 4 * v4
    sig = sma(kst_vals, 9)
    return kst_vals, sig


def kst_signal(closes: list) -> List[int]:
    """KST 交叉信号：kst > signal → 多；kst < signal → 空"""
    k, s = kst(closes)
    return [
        1 if k[i] > s[i] and not math.isnan(k[i])
        else -1 if k[i] < s[i] and not math.isnan(k[i])
        else 0
        for i in range(len(closes))
    ]


def trix(closes: list, period: int = 15, signal: int = 9) -> Tuple[List[float], List[float]]:
    """
    TRIX（三重指数平滑）— 趋势过滤噪音
    返回 (trix_line, signal_line)
    """
    ema1 = ema(closes, period)
    ema2 = ema([v if not math.isnan(v) else 0.0 for v in ema1], period)
    ema3 = ema([v if not math.isnan(v) else 0.0 for v in ema2], period)
    trix_vals = [float("nan")] * len(closes)
    for i in range(1, len(closes)):
        prev = ema3[i - 1] if not math.isnan(ema3[i - 1]) else 0.0
        curr = ema3[i]     if not math.isnan(ema3[i])     else 0.0
        if abs(prev) > 1e-10:
            trix_vals[i] = ((curr - prev) / prev) * 100.0
    sig = sma(trix_vals, signal)
    return trix_vals, sig


def trix_signal(closes: list) -> List[int]:
    """TRIX 交叉信号"""
    t, sig = trix(closes)
    return [
        1 if t[i] > sig[i] and not math.isnan(t[i])
        else -1 if t[i] < sig[i] and not math.isnan(t[i])
        else 0
        for i in range(len(closes))
    ]


def donchian_channel(highs: list, lows: list, period: int = 20
                    ) -> Tuple[List[float], List[float], List[float]]:
    """Donchian Channel（唐奇安通道）：(upper, middle, lower)"""
    n = len(highs)
    upper  = [float("nan")] * n
    middle = [float("nan")] * n
    lower  = [float("nan")] * n
    for i in range(period - 1, n):
        upper[i]  = max(highs[i - period + 1:i + 1])
        lower[i]  = min(lows[i - period + 1:i + 1])
        middle[i] = (upper[i] + lower[i]) / 2.0
    return upper, middle, lower


def donchian_breakout(closes: list, highs: list, lows: list,
                     period: int = 20) -> List[int]:
    """Donchian 突破策略信号：1=上破上轨/-1=下破下轨/0=持有"""
    upper, _, lower = donchian_channel(highs, lows, period)
    n = len(closes)
    signal = [0] * n
    for i in range(period, n):
        # Use previous bar's channel: close > prev upper = breakout
        if math.isnan(upper[i-1]) or math.isnan(lower[i-1]):
            continue
        if closes[i] > upper[i-1]:
            signal[i] = 1
        elif closes[i] < lower[i-1]:
            signal[i] = -1
    return signal


def aroon(highs: list, lows: list, period: int = 25
         ) -> Tuple[List[float], List[float]]:
    """Aroon 指标：(aroon_up, aroon_down)"""
    n = len(highs)
    aroon_up   = [float("nan")] * n
    aroon_down = [float("nan")] * n
    for i in range(period - 1, n):
        _, up_idx   = _min_idx(highs[i - period + 1:i + 1])
        _, down_idx = _min_idx([-v for v in lows[i - period + 1:i + 1]])
        aroon_up[i]   = 100.0 * (period - up_idx)   / period
        aroon_down[i] = 100.0 * (period - down_idx) / period
    return aroon_up, aroon_down


def aroon_signal(closes: list, highs: list, lows: list, period: int = 25) -> List[int]:
    """Aroon 交叉信号：aroon_up 上穿 aroon_down → 多；下穿 → 空"""
    up, down = aroon(highs, lows, period)
    n = len(closes)
    signal = [0] * n
    for i in range(1, n):
        if math.isnan(up[i]) or math.isnan(down[i]):
            continue
        above      = up[i] > down[i]
        above_prev = up[i - 1] > down[i - 1] if not math.isnan(up[i - 1]) else False
        if above and not above_prev:
            signal[i] = 1
        elif not above and above_prev:
            signal[i] = -1
    return signal
