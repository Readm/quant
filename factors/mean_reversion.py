# factors/mean_reversion.py
# 均值回归 / 超买超卖类因子
# MFI · RVI · OBOS · KDWav

import math
from typing import List, Tuple
from factors.base_operators import sma, ema, rsi, stochastic, volume_ratio

def money_flow_index(highs: list, lows: list, closes: list,
                    volumes: list, period: int = 14) -> List[float]:
    """
    MFI（资金流量指标）
    价格+成交量确认的超买超卖，类似RSI但含成交量
    MFI>80 超买；MFI<20 超卖
    """
    n = min(len(closes), len(volumes), len(highs), len(lows))
    typical = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    raw_mf  = [typical[i] * volumes[i] for i in range(n)]
    mfi = [float("nan")] * n
    for i in range(period, n):
        pos_flow = sum(raw_mf[j] for j in range(i - period + 1, i + 1) if typical[j] > typical[j - 1]) if i > 0 else 0.0
        neg_flow = sum(raw_mf[j] for j in range(i - period + 1, i + 1) if typical[j] < typical[j - 1]) if i > 0 else 0.0
        if neg_flow == 0:
            mfi[i] = 100.0
        else:
            mr = pos_flow / neg_flow
            mfi[i] = 100.0 - 100.0 / (1.0 + mr)
    return mfi


def mfi_signal(closes: list, highs: list, lows: list,
              volumes: list, period: int = 14) -> List[int]:
    """MFI 超买超卖信号：>80 空/-1=超卖 1=超跌买入"""
    mfi_vals = money_flow_index(highs, lows, closes, volumes, period)
    n = len(mfi_vals)
    signal = [0] * n
    for i in range(period, n):
        v = mfi_vals[i]
        if math.isnan(v):
            continue
        if v > 80:
            signal[i] = -1   # 超买，空
        elif v < 20:
            signal[i] = 1    # 超卖，多
    return signal


def rvi(highs: list, lows: list, closes: list, period: int = 10) -> List[float]:
    """
    RVI（相对活力指数）
    上涨日收在高位的比例；>50→多；<50→空
    """
    n = len(closes)
    rvi_vals = [float("nan")] * n
    for i in range(period, n):
        num = 0.0
        den = 1e-10
        for j in range(i - period + 1, i + 1):
            close_range = highs[j] - lows[j]
            if close_range > 1e-9:
                num += (closes[j] - lows[j]) / close_range
                den += 1.0
        rvi_vals[i] = (num / den) * 100.0
    return rvi_vals


def rvi_signal(closes: list, highs: list, lows: list, period: int = 10) -> List[int]:
    """RVI 信号：<30 超卖买入，>70 超买卖出"""
    rvi_vals = rvi(highs, lows, closes, period)
    return [
        1 if (rvi_vals[i] if not math.isnan(rvi_vals[i]) else 50) < 30
        else -1 if (rvi_vals[i] if not math.isnan(rvi_vals[i]) else 50) > 70
        else 0
        for i in range(len(closes))
    ]


def kdwave(highs: list, lows: list, closes: list,
         k_period: int = 9, d_period: int = 3
         ) -> Tuple[List[float], List[float], List[int]]:
    """
    KDWav（KDJ波动波形）
    K/D 金叉 + 股价在中轨上方 → 多
    K/D 死叉 + 股价在中轨下方 → 空
    """
    from factors.base_operators import bollinger_bands
    k_vals, d_vals = stochastic(highs, lows, closes, k_period, d_period)
    bb_mid, _, _ = bollinger_bands(closes, 20, 2.0)
    n = len(closes)
    signal = [0] * n
    for i in range(1, n):
        if math.isnan(k_vals[i]) or math.isnan(d_vals[i]):
            continue
        kd_gold = k_vals[i] > d_vals[i] and k_vals[i - 1] <= d_vals[i - 1]
        kd_dead = k_vals[i] < d_vals[i] and k_vals[i - 1] >= d_vals[i - 1]
        above_bb = closes[i] > bb_mid[i] if not math.isnan(bb_mid[i]) else True
        if kd_gold and above_bb:
            signal[i] = 1
        elif kd_dead and not above_bb:
            signal[i] = -1
    return k_vals, d_vals, signal


def obos_composite(closes: list, volumes: list,
                  rsi_period: int = 14, atr_period: int = 14,
                  volume_ma: int = 20) -> Tuple[List[float], List[int]]:
    """
    OBOS（超买超卖综合指标）
    RSI + 成交量确认 → 综合超买超卖评分
    返回 (obos_score 0~100, signal: 1/-1/0)
    """
    vr = volume_ratio(volumes, volume_ma)
    rsi_vals = rsi(closes, rsi_period)
    n = len(closes)
    obos = [float("nan")] * n
    for i in range(n):
        r = rsi_vals[i] if not math.isnan(rsi_vals[i]) else 50.0
        v = vr[i]       if not math.isnan(vr[i])       else 1.0
        obos[i] = r if v < 1.5 else max(0, min(100, r * 1.1))
    signal = [0] * n
    for i in range(n):
        o = obos[i]
        if math.isnan(o):
            continue
        if o > 75:
            signal[i] = -1
        elif o < 25:
            signal[i] = 1
    return obos, signal
