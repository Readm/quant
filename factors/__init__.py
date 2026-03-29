# factors/__init__.py
# 因子库统一导出

from factors.base_operators import (
    sma, ema, roc, momentum, rsi, atr,
    bollinger_bands, stochastic, volume_ratio,
    macd, adx, cci, williams_r, supertrend,
)
from factors.trend import (
    ichimoku_cloud, ichimoku_signal,
    parabolic_sar,
    kst, kst_signal,
    trix, trix_signal,
    donchian_channel, donchian_breakout,
    aroon, aroon_signal,
)
from factors.mean_reversion import (
    money_flow_index, mfi_signal,
    rvi, rvi_signal,
    kdwave,
    obos_composite,
)
from factors.momentum import (
    force_index,
    elder_ray, elder_ray_signal,
    chaikin_oscillator, chaikin_signal,
    ppo, ppo_signal,
    momentum_matrix, multi_roc_signal,
)
from factors.volume import (
    accdist, accumulation_distribution_signal,
    volume_price_trend,
    mass_index,
    ergodic_oscillator, ergodic_signal,
    signal_horizon,
)
from factors.volatility import (
    ultraspline, ultraband_signal,
)
from factors.chanlun import (
    chanlun_bi, chanlun_tao,
)
from factors.signals import generate_signal, FACTOR_TABLE

__all__ = [
    # base
    "sma", "ema", "roc", "momentum", "rsi", "atr",
    "bollinger_bands", "stochastic", "volume_ratio",
    "macd", "adx", "cci", "williams_r", "supertrend",
    # trend
    "ichimoku_cloud", "ichimoku_signal",
    "parabolic_sar",
    "kst", "kst_signal",
    "trix", "trix_signal",
    "donchian_channel", "donchian_breakout",
    "aroon", "aroon_signal",
    # mean reversion
    "money_flow_index", "mfi_signal",
    "rvi", "rvi_signal",
    "kdwave",
    "obos_composite",
    # momentum
    "force_index",
    "elder_ray", "elder_ray_signal",
    "chaikin_oscillator", "chaikin_signal",
    "ppo", "ppo_signal",
    "momentum_matrix", "multi_roc_signal",
    # volume
    "accdist", "accumulation_distribution_signal",
    "volume_price_trend",
    "mass_index",
    "ergodic_oscillator", "ergodic_signal",
    "signal_horizon",
    # volatility
    "ultraspline", "ultraband_signal",
    # chanlun
    "chanlun_bi", "chanlun_tao",
    # signals
    "generate_signal", "FACTOR_TABLE",
]
