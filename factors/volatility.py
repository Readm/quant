# factors/volatility.py
# 波幅类因子
# UltraSpline · UltraBand

from typing import List
from factors.base_operators import sma, atr

def ultraspline(highs: List[float], lows: List[float], closes: List[float],
               lookback: int = 20) -> List[float]:
    """
    Ultra-Spline（波动率压缩爆发因子）
    波幅（最高-最低）/ 移动均值 → 波幅收缩至历史低位后爆发
    """
    n = len(highs)
    hml = [highs[i] - lows[i] for i in range(n)]
    hml_sma = sma(hml, lookback)
    out = [float("nan")] * n
    for i in range(n):
        if math.isnan(hml_sma[i]) or hml_sma[i] < 1e-10:
            continue
        out[i] = hml[i] / hml_sma[i]
    return out


import math
from factors.trend import donchian_channel
from factors.base_operators import bollinger_bands

def ultraband_signal(closes: List[float], highs: List[float], lows: List[float],
                    period: int = 20, threshold: float = 0.5) -> List[int]:
    """
    Ultra-Band 突破：波幅收缩至threshold倍历史低位后入场
    布林带2.0倍以下 + ATR突破 → 爆发信号
    """
    upper, middle, lower = donchian_channel(highs, lows, period)
    bb_mid, bb_upper, bb_lower = bollinger_bands(closes, period, 2.0)
    bb_width = [float("nan")] * len(closes)
    for i in range(len(closes)):
        u = bb_upper[i] if not math.isnan(bb_upper[i]) else 0.0
        l = bb_lower[i] if not math.isnan(bb_lower[i]) else 0.0
        m = bb_mid[i]   if not math.isnan(bb_mid[i])   else 0.0
        if abs(u - l) > 1e-10:
            bb_width[i] = (u - l) / (m + 1e-10)
    at = atr(highs, lows, closes, period)
    n = len(closes)
    signal = [0] * n
    for i in range(period, n):
        bw = bb_width[i] if not math.isnan(bb_width[i]) else 1.0
        a  = at[i]       if not math.isnan(at[i])       else 0.0
        if bw < threshold and a > 0 and closes[i] > bb_upper[i]:
            signal[i] = 1
        elif closes[i] < bb_lower[i]:
            signal[i] = -1
    return signal
