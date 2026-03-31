# factors/signals.py
# 统一信号生成器 + 因子注册表

from typing import List

# 因子 ID → (函数名, 中文描述, 所需参数) 的映射
FACTOR_TABLE = {
    # ── 趋势类 ─────────────────────
    "F17": ("ichimoku_cloud",    "Ichimoku云图",       ["highs", "lows", "closes"]),
    "F18": ("ichimoku_signal",   "Ichimoku金叉",        ["closes", "highs", "lows"]),
    "F19": ("parabolic_sar",    "Parabolic SAR",       ["highs", "lows", "closes"]),
    "F20": ("kst",              "KST多周期动量",        ["closes"]),
    "F21": ("trix",             "TRIX三重指数",         ["closes"]),
    "F22": ("donchian_breakout","Donchian突破",        ["closes", "highs", "lows"]),
    "F23": ("aroon_signal",     "Aroon交叉",           ["closes", "highs", "lows"]),
    # ── 均值回归类 ─────────────────
    "F26": ("mfi_signal",        "MFI资金流",           ["closes", "highs", "lows", "volumes"]),
    "F27": ("rvi_signal",       "RVI相对活力",         ["highs", "lows", "closes"]),
    "F31": ("kdwave",           "KDJ波动波形",          ["highs", "lows", "closes"]),
    "F29": ("multi_roc_signal", "ROC多周期一致",        ["closes"]),
    "F30": ("obos_composite",   "OBOS综合超买超卖",     ["closes", "volumes"]),
    # ── 动量类 ─────────────────────
    "F33": ("force_index",       "Force Index力",       ["closes", "volumes"]),
    "F34": ("elder_ray",         "Elder Ray透视",       ["closes", "highs", "lows"]),
    "F35": ("elder_ray_signal", "Elder Ray信号",        ["closes", "highs", "lows"]),
    "F24": ("ppo",               "PPO信号",             ["closes"]),
    "F28": ("momentum_matrix",   "多周期动量矩阵",       ["closes"]),
    # ── 量价类 ─────────────────────
    "F37": ("accdist",           "A/D累积派发",         ["highs", "lows", "closes", "volumes"]),
    "F38": ("accumulation_distribution_signal", "A/D背离信号", ["closes", "highs", "lows", "volumes"]),
    "F32": ("volume_price_trend","VPT量价趋势",         ["closes", "volumes"]),
    "F41": ("mass_index",        "Mass Index梅斯",       ["highs", "lows"]),
    "F42": ("ergodic_oscillator","Ergodic遍历摆动",     ["closes", "highs", "lows"]),
    "F40": ("signal_horizon",    "Signal Horizon",       ["highs", "lows", "closes"]),
    # ── 波幅类 ─────────────────────
    "F14": ("ultraspline",       "波幅收缩爆发",         ["highs", "lows", "closes"]),
    "F39": ("ultraband_signal",  "Ultra-Band突破",       ["closes", "highs", "lows"]),
    # ── 缠论类 ─────────────────────
    "F46": ("chanlun_bi",        "缠论笔",               ["closes"]),
    "F47": ("chanlun_tao",       "缠论套",               ["closes"]),
    # ── 经典指标（来自 base_operators）─────────
    "F00": ("sma_cross",         "MA5上穿MA20",          ["closes"]),
    "F02": ("macd",              "MACD金叉",              ["closes"]),
    "F06": ("rsi",               "RSI超卖25",            ["closes"]),
    "F09": ("bollinger_bands",   "布林下轨买入",          ["closes"]),
    "F12": ("atr",               "ATR放大确认",           ["highs", "lows", "closes"]),
}


def generate_signal(factor_id: str, closes: List[float],
                    highs: List[float] = None, lows: List[float] = None,
                    volumes: List[float] = None) -> List[int]:
    """
    统一入口：根据因子ID生成交易信号
    returns: [1=多/-1=空/0=中性]
    """
    from factors.trend import (
        ichimoku_signal, kst_signal, trix_signal,
        donchian_breakout, aroon_signal
    )
    from factors.mean_reversion import (
        mfi_signal, rvi_signal, kdwave, obos_composite
    )
    from factors.momentum import force_index, elder_ray_signal, ppo_signal, momentum_matrix, multi_roc_signal
    from factors.volume import (
        accdist, accumulation_distribution_signal,
        volume_price_trend, mass_index, ergodic_oscillator, signal_horizon
    )
    from factors.volatility import ultraspline, ultraband_signal
    from factors.chanlun import chanlun_bi, chanlun_tao
    from factors.base_operators import rsi, bollinger_bands, atr, macd
    import math

    highs  = highs  or closes
    lows   = lows   or closes
    vols   = volumes or [1.0] * len(closes)

    mapping = {
        "ichimoku_signal":           lambda: ichimoku_signal(closes, highs, lows),
        "kst":                       lambda: kst_signal(closes),
        "trix":                      lambda: trix_signal(closes),
        "donchian_breakout":         lambda: donchian_breakout(closes, highs, lows),
        "aroon_signal":              lambda: aroon_signal(closes, highs, lows),
        "ppo":                       lambda: ppo_signal(closes),
        "mfi_signal":                lambda: mfi_signal(closes, highs, lows, vols),
        "rvi_signal":                lambda: rvi_signal(closes, highs, lows),
        "kdwave":                    lambda: kdwave(highs, lows, closes)[2],
        "multi_roc_signal":          lambda: multi_roc_signal(closes),
        "obos_composite":            lambda: obos_composite(closes, vols)[1],
        "force_index":               lambda: [1 if fi > 0 else -1 for fi in force_index(closes, vols)],
        "elder_ray_signal":          lambda: elder_ray_signal(closes, highs, lows),
        "accdist":                   lambda: accdist(highs, lows, closes, vols),
        "accumulation_distribution_signal": lambda: accumulation_distribution_signal(closes, highs, lows, vols),
        "volume_price_trend":        lambda: [1 if vpt > 0 else -1 for vpt in volume_price_trend(closes, vols)],
        "mass_index":                lambda: [1 if mass > 27 else -1 for mass in mass_index(highs, lows)],
        "ergodic_oscillator":        lambda: ergodic_oscillator(closes, highs, lows)[1],
        "ultraband_signal":          lambda: ultraband_signal(closes, highs, lows),
        "ultraspline":               lambda: [1 if u < 0.5 else -1 for u in ultraspline(highs, lows, closes)],
        "chanlun_bi":                lambda: chanlun_bi(closes)[0],
        "chanlun_tao":               lambda: chanlun_tao(*chanlun_bi(closes)),
    }

    fn = mapping.get(factor_id)
    if fn:
        try:
            return fn()
        except Exception:
            return [0] * len(closes)
    return [0] * len(closes)
