# factors/momentum.py
# 动量类因子
# Force Index · Elder Ray · Chaikin Oscillator · PPO · Momentum Matrix

import math
from typing import List, Tuple
from factors.base_operators import sma, ema, roc

def force_index(closes: list, volumes: list, period: int = 13) -> List[float]:
    """
    Force Index（.force Index）
    衡量价格变动背后的成交量驱动力
    正值→多头力量；负值→空头力量
    """
    n = min(len(closes), len(volumes))
    fi = [float("nan")] * n
    fi[0] = 0.0
    for i in range(1, n):
        fi[i] = (closes[i] - closes[i - 1]) * volumes[i]
    return ema(fi, period)


def elder_ray(closes: list, highs: list, lows: list,
             period: int = 13) -> Tuple[List[float], List[float]]:
    """
    Elder Ray（艾达透视指标）：(bull_power, bear_power)
    多头力道 = 最高价 - EMA；空头力道 = 最低价 - EMA
    """
    ema_val = ema(closes, period)
    n = len(closes)
    bull = [float("nan")] * n
    bear = [float("nan")] * n
    for i in range(n):
        if math.isnan(ema_val[i]):
            continue
        bull[i] = highs[i] - ema_val[i]
        bear[i] = lows[i]  - ema_val[i]
    return bull, bear


def elder_ray_signal(closes: list, highs: list, lows: list,
                    period: int = 13) -> List[int]:
    """Elder Ray 买入信号：EMA上升 + bull_power 由负转正"""
    bull, bear = elder_ray(closes, highs, lows, period)
    ema_val = ema(closes, period)
    n = len(closes)
    signal = [0] * n
    for i in range(1, n):
        if math.isnan(ema_val[i]) or math.isnan(bull[i]) or math.isnan(bull[i - 1]):
            continue
        ema_rising      = ema_val[i] > ema_val[i - 1]
        bull_turning_up = bull[i] > 0 and bull[i - 1] <= 0
        bear_turning_down = bear[i] < 0 and bear[i - 1] >= 0
        if ema_rising and bull_turning_up:
            signal[i] = 1
        elif not ema_rising and bear_turning_down:
            signal[i] = -1
    return signal


def ppo(closes: list, fast: int = 12, slow: int = 26,
       signal: int = 9) -> Tuple[List[float], List[float]]:
    """
    PPO（价格震荡百分比）— MACD的百分比版本
    (EMA_fast - EMA_slow) / EMA_slow * 100
    """
    ef = ema(closes, fast)
    es = ema(closes, slow)
    n = len(closes)
    ppo_vals = [float("nan")] * n
    for i in range(n):
        e = es[i] if not math.isnan(es[i]) else 0.0
        f = ef[i] if not math.isnan(ef[i]) else 0.0
        if abs(e) > 1e-10 and not math.isnan(es[i]):
            ppo_vals[i] = (f - e) / e * 100.0
    # Compute signal line on valid (non-NaN) segment only to avoid NaN chain
    sig = [float("nan")] * n
    valid_ppo = [v for v in ppo_vals if not math.isnan(v)]
    if len(valid_ppo) >= signal:
        valid_sig = ema(valid_ppo, signal)
        vi = 0
        for i in range(n):
            if not math.isnan(ppo_vals[i]):
                if vi < len(valid_sig):
                    sig[i] = valid_sig[vi]
                vi += 1
    return ppo_vals, sig


def ppo_signal(closes: list) -> List[int]:
    """PPO 交叉信号"""
    p, s = ppo(closes)
    return [
        1 if p[i] > s[i] and not math.isnan(p[i])
        else -1 if p[i] < s[i] and not math.isnan(p[i])
        else 0
        for i in range(len(closes))
    ]


def momentum_matrix(closes: list) -> dict:
    """
    动量矩阵：5个时间框架（5/10/20/60/120日）
    全部正 → 强劲多头；全部负 → 强劲空头
    """
    periods = [5, 10, 20, 60, 120]
    from factors.base_operators import momentum
    result = {}
    for p in periods:
        vals = momentum(closes, p)
        valid = [v for v in vals if not math.isnan(v)]
        result[f"roc_{p}"] = valid[-1] if valid else float("nan")
    return result


def multi_roc_signal(closes: list,
                     periods: list = None) -> List[int]:
    """
    多周期ROC一致性信号
    短周期全部正 → 做多；长周期全部负 → 做空
    """
    if periods is None:
        periods = [5, 10, 20]
    n = len(closes)
    signal = [0] * n
    for i in range(max(periods), n):
        vals = []
        for p in periods:
            if i >= p:
                r = (closes[i] - closes[i - p]) / closes[i - p] if closes[i - p] != 0 else 0.0
                vals.append(r)
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        if all(v > 0 for v in vals) and avg > 0.01:
            signal[i] = 1
        elif all(v < 0 for v in vals) and avg < -0.01:
            signal[i] = -1
    return signal
