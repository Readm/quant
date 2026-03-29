# factors/base_operators.py
# 基础时间序列算子（因子库底层依赖）
# 从 factor_library.py 中抽取并补全缺失的函数

import math
from typing import List, Tuple

def sma(data: List[float], period: int) -> List[float]:
    """简单移动平均"""
    n = len(data)
    out = [float("nan")] * (period - 1)
    for i in range(period - 1, n):
        out.append(sum(data[i - period + 1:i + 1]) / period)
    return out

def ema(data: List[float], period: int) -> List[float]:
    """指数移动平均"""
    n = len(data)
    if n == 0:
        return []
    k = 2.0 / (period + 1)
    out = [float("nan")] * (period - 1)
    # 第一笔 EMA = SMA
    if period <= n:
        first = sum(data[:period]) / period
        out.append(first)
        for i in range(period, n):
            out.append(data[i] * k + out[-1] * (1 - k))
    return out

def roc(data: List[float], period: int) -> List[float]:
    """Rate of Change（变化率）"""
    n = len(data)
    out = [float("nan")] * period
    for i in range(period, n):
        if data[i - period] != 0 and not math.isnan(data[i - period]):
            out.append((data[i] - data[i - period]) / data[i - period] * 100.0)
        else:
            out.append(float("nan"))
    return out

def momentum(data: List[float], period: int) -> List[float]:
    """动量：当前价 - N日前价"""
    n = len(data)
    out = [float("nan")] * period
    for i in range(period, n):
        out.append(data[i] - data[i - period])
    return out

def rsi(data: List[float], period: int = 14) -> List[float]:
    """相对强弱指标（RSI）"""
    n = len(data)
    if n < period + 1:
        return [float("nan")] * n
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        diff = data[i] - data[i - 1]
        gains[i] = max(diff, 0)
        losses[i] = max(-diff, 0)
    out = [float("nan")] * period
    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period
    if avg_loss == 0:
        out.append(100.0)
    else:
        rs = avg_gain / avg_loss
        out.append(100.0 - 100.0 / (1.0 + rs))
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            out.append(100.0)
        else:
            rs = avg_gain / avg_loss
            out.append(100.0 - 100.0 / (1.0 + rs))
    return out

def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """平均真实波幅（ATR）"""
    n = len(highs)
    tr = [float("nan")] * n
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        h_l = highs[i] - lows[i]
        h_c = abs(highs[i] - closes[i - 1])
        l_c = abs(lows[i] - closes[i - 1])
        tr[i] = max(h_l, h_c, l_c)
    return ema(tr, period)

def bollinger_bands(data: List[float], period: int = 20, num_std: float = 2.0):
    """布林带：(middle, upper, lower)"""
    mid = sma(data, period)
    std_dev = [float("nan")] * (period - 1)
    for i in range(period - 1, len(data)):
        window = data[i - period + 1:i + 1]
        m = sum(window) / period
        variance = sum((x - m) ** 2 for x in window) / period
        std_dev.append(math.sqrt(variance))
    upper = [float("nan")] * len(data)
    lower = [float("nan")] * len(data)
    for i in range(len(data)):
        if not math.isnan(mid[i]):
            upper[i] = mid[i] + num_std * std_dev[i]
            lower[i] = mid[i] - num_std * std_dev[i]
    return mid, upper, lower

def stochastic(highs: List[float], lows: List[float], closes: List[float],
               k_period: int = 9, d_period: int = 3) -> Tuple[List[float], List[float]]:
    """随机指标 K/D 值"""
    n = len(closes)
    k_vals = [float("nan")] * n
    for i in range(k_period - 1, n):
        window_h = highs[i - k_period + 1:i + 1]
        window_l = lows[i - k_period + 1:i + 1]
        hh = max(window_h)
        ll = min(window_l)
        if hh != ll:
            k_vals[i] = (closes[i] - ll) / (hh - ll) * 100.0
        else:
            k_vals[i] = 50.0
    d_vals = sma(k_vals, d_period)
    return k_vals, d_vals

def volume_ratio(volumes: List[float], period: int = 20) -> List[float]:
    """成交量比率（VR）：当前成交量 / 移动平均成交量"""
    n = len(volumes)
    ma_vol = sma(volumes, period)
    out = [float("nan")] * (period - 1)
    for i in range(period - 1, n):
        if ma_vol[i] > 0 and not math.isnan(ma_vol[i]):
            out.append(volumes[i] / ma_vol[i])
        else:
            out.append(1.0)
    return out

def macd(data: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD：(dif, dea, histogram)"""
    ema_fast = ema(data, fast)
    ema_slow = ema(data, slow)
    n = len(data)
    dif = [float("nan")] * n
    for i in range(n):
        if not math.isnan(ema_fast[i]) and not math.isnan(ema_slow[i]):
            dif[i] = ema_fast[i] - ema_slow[i]
    dea = ema(dif, signal)
    hist = [float("nan")] * n
    for i in range(n):
        if not math.isnan(dif[i]) and not math.isnan(dea[i]):
            hist[i] = (dif[i] - dea[i]) * 2
    return dif, dea, hist

def adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """ADX 趋向指标（简化版）"""
    n = len(highs)
    tr_list = [float("nan")] * n
    plus_dm = [float("nan")] * n
    minus_dm = [float("nan")] * n
    tr_list[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr_list[i] = max(highs[i] - lows[i],
                         abs(highs[i] - closes[i - 1]),
                         abs(lows[i] - closes[i - 1]))
        h_diff = highs[i] - highs[i - 1]
        l_diff = lows[i - 1] - lows[i]
        plus_dm[i] = max(h_diff, 0) if h_diff > l_diff else 0.0
        minus_dm[i] = max(l_diff, 0) if l_diff > h_diff else 0.0
    atr_vals = ema(tr_list, period)
    plus_di = [float("nan")] * n
    minus_di = [float("nan")] * n
    for i in range(period, n):
        if not math.isnan(atr_vals[i]) and atr_vals[i] > 0:
            plus_di[i] = (ema(plus_dm, period)[i] / atr_vals[i]) * 100
            minus_di[i] = (ema(minus_dm, period)[i] / atr_vals[i]) * 100
    adx_vals = [float("nan")] * n
    for i in range(period * 2, n):
        p = plus_di[i] if not math.isnan(plus_di[i]) else 0
        m = minus_di[i] if not math.isnan(minus_di[i]) else 0
        if p + m > 0:
            adx_vals[i] = abs(p - m) / (p + m) * 100
    return adx_vals

def cci(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """CCI 顺势指标"""
    n = len(closes)
    tp = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    sma_tp = sma(tp, period)
    out = [float("nan")] * n
    for i in range(period - 1, n):
        if math.isnan(sma_tp[i]):
            continue
        mean_dev = sum(abs(tp[j] - sma_tp[i]) for j in range(i - period + 1, i + 1)) / period
        if mean_dev > 0:
            out[i] = (tp[i] - sma_tp[i]) / (0.015 * mean_dev)
    return out

def williams_r(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """Williams %R"""
    n = len(closes)
    out = [float("nan")] * n
    for i in range(period - 1, n):
        window_h = highs[i - period + 1:i + 1]
        window_l = lows[i - period + 1:i + 1]
        hh = max(window_h)
        ll = min(window_l)
        if hh != ll:
            out[i] = (hh - closes[i]) / (hh - ll) * -100.0
        else:
            out[i] = -50.0
    return out

def supertrend(highs: List[float], lows: List[float], closes: List[float],
               period: int = 10, multiplier: float = 3.0) -> Tuple[List[int], List[float]]:
    """Supertrend 超级趋势：(signal, atr_value)"""
    atr_vals = atr(highs, lows, closes, period)
    n = len(closes)
    upper = [float("nan")] * n
    lower = [float("nan")] * n
    final_upper = [float("nan")] * n
    final_lower = [float("nan")] * n
    supertrend = [0] * n
    for i in range(n):
        hl2 = (highs[i] + lows[i]) / 2.0
        upper[i] = hl2 + multiplier * atr_vals[i]
        lower[i] = hl2 - multiplier * atr_vals[i]
    # Compute final bands with trend
    for i in range(1, n):
        if math.isnan(atr_vals[i]):
            continue
        if i == 1:
            final_upper[i] = upper[i]
            final_lower[i] = lower[i]
        else:
            final_upper[i] = upper[i] if (not math.isnan(final_upper[i-1]) and (upper[i] < final_upper[i-1] or closes[i-1] > final_upper[i-1])) else (final_upper[i-1] if not math.isnan(final_upper[i-1]) else upper[i])
            final_lower[i] = lower[i] if (not math.isnan(final_lower[i-1]) and (lower[i] > final_lower[i-1] or closes[i-1] < final_lower[i-1])) else (final_lower[i-1] if not math.isnan(final_lower[i-1]) else lower[i])
        if not math.isnan(final_upper[i]) and closes[i] > final_upper[i]:
            supertrend[i] = 1
        elif not math.isnan(final_lower[i]) and closes[i] < final_lower[i]:
            supertrend[i] = -1
        else:
            supertrend[i] = supertrend[i-1]
    return supertrend, atr_vals

def _min_idx(arr: List[float]):
    """返回 (value, index) of minimum"""
    valid = [(v, i) for i, v in enumerate(arr) if not math.isnan(v)]
    if not valid:
        return float("nan"), -1
    return min(valid, key=lambda x: x[0])
