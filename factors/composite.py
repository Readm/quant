# factors/composite.py
# 综合类因子（多类别组合）
# Chaikin Oscillator（量价综合）
# KDWave / OBOS 已在 mean_reversion.py 中

from typing import List
import math
from factors.base_operators import ema
from factors.volume import accdist

def chaikin_oscillator(highs: List[float], lows: List[float], closes: List[float],
                      volumes: List[float], fast: int = 3, slow: int = 10) -> List[float]:
    """
    Chaikin Oscillator（蔡金振荡器）
    ADL 的 EMA 差值；上穿0→多；下穿0→空
    """
    ad = accdist(highs, lows, closes, volumes)
    ad_ema_fast = ema(ad, fast)
    ad_ema_slow = ema(ad, slow)
    n = len(closes)
    co = [float("nan")] * n
    for i in range(n):
        f = ad_ema_fast[i] if not math.isnan(ad_ema_fast[i]) else 0.0
        s = ad_ema_slow[i] if not math.isnan(ad_ema_slow[i]) else 0.0
        co[i] = f - s
    return co


def chaikin_signal(closes: List[float], highs: List[float], lows: List[float],
                  volumes: List[float], fast: int = 3, slow: int = 10) -> List[int]:
    """Chaikin Oscillator 交叉信号"""
    co = chaikin_oscillator(highs, lows, closes, volumes, fast, slow)
    n = len(co)
    signal = [0] * n
    for i in range(1, n):
        if math.isnan(co[i]) or math.isnan(co[i - 1]):
            continue
        if co[i] > 0 and co[i - 1] <= 0:
            signal[i] = 1
        elif co[i] < 0 and co[i - 1] >= 0:
            signal[i] = -1
    return signal
