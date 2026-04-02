"""
backtest/indicators.py — 技术指标预计算层

职责：将原始 OHLCV dict 转换成 indicators dict，
供 backtest/engine.py 的 compute_factor_score 读取。

依赖方向（无循环）：
  factors.base_operators  ←  本文件  →  experts.modules.data_fetcher
  local_data.py           →  本文件
  data_loader.py          →  本文件
"""

from factors.base_operators import sma, rsi, atr


def compute_indicators(data: dict) -> dict:
    """
    输入：OHLCV dict，含 closes / highs / lows / volumes 字段。
    输出：indicators dict，key 对应 compute_factor_score 中的 _ind_at 调用。

    返回的指标：
        returns  — 日收益率序列
        ma5/10/20/60/200 — 简单移动平均
        rsi14    — 14日 RSI
        atr14    — 14日 ATR
        adx      — Wilder ADX（来自 data_fetcher，失败时填 0）
    """
    closes  = data.get('closes',  [])
    highs   = data.get('highs',   [])
    lows    = data.get('lows',    [])
    n = len(closes)
    if n < 60:
        return {}

    rets = [0.0] + [(closes[i] / closes[i - 1] - 1) for i in range(1, n)]

    # ADX / MA5 / MA10 来自 data_fetcher（含 Wilder 平滑）
    from experts.modules.data_fetcher import compute_realistic_indicators as _cri
    _ext   = _cri({'closes': closes, 'highs': highs or closes, 'lows': lows or closes})
    adx_v  = _ext.get('adx',  [0.0] * n)
    ma5_v  = _ext.get('ma5',  [0.0] * n)
    ma10_v = _ext.get('ma10', [0.0] * n)

    return {
        'returns': rets,
        'ma5':     ma5_v,
        'ma10':    ma10_v,
        'ma20':    sma(closes, 20),
        'ma60':    sma(closes, 60),
        'ma200':   sma(closes, 200) if n >= 200 else [None] * n,
        'rsi14':   rsi(closes, 14),
        'atr14':   atr(highs, lows, closes, 14),
        'adx':     adx_v,
    }
