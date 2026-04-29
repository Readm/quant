"""
portfolio_backtest.py — 多股持仓组合回测引擎
=============================================
在每个调仓日：
  1. 对所有标的用因子打分（跨截面排名）
  2. 选出 top-n_stocks（分数 > 0 的候选中）
  3. 按 weight_method 分配权重
  4. 执行换仓（平旧仓 → 建新仓）

变异参数（均在 candidate["portfolio_params"] 中）：
  n_stocks         — 同时持仓的股票数量 (1~5)
  rebalance_freq   — 调仓频率，单位交易日 (5/10/20/60)
  weight_method    — 权重分配方式 ("equal"/"score_weighted"/"vol_inverse")
  max_position_pct — 单只股票最大仓位占比 (0.3~1.0)
"""
import math
from typing import Dict, List

# ── 交易成本（与 expert1a/1b 保持一致）──────────────────────────────
from config.settings import TRADING_COST as _TC
BUY_COST  = _TC["buy"]
SELL_COST = _TC["sell"]

# ── 默认组合参数 ────────────────────────────────────────────────────
DEFAULT_PORTFOLIO_PARAMS = {
    "n_stocks":         2,
    "rebalance_freq":   10,             # v5.3: 20→10, 更频繁调仓
    "weight_method":    "vol_inverse",  # v5.3: equal→vol_inverse, 低波动高权重
    "max_position_pct": 0.95,
}


# ── 因子打分：策略信号 → 连续分数 ────────────────────────────────────
# ── 指标读取辅助 ─────────────────────────────────────────────────────
def _ind_at(indicators: dict, t: int, key: str, default: float = 0.0) -> float:
    """从 indicators dict 中安全读取第 t 个时间点的值"""
    arr = indicators.get(key)
    if arr is None or t >= len(arr):
        return default
    v = arr[t]
    return float(v) if v is not None else default


# ── 各策略因子打分函数 ────────────────────────────────────────────────

def _score_ma_cross(c, data, indicators, params, t):
    fast = int(params.get("fast", 20))
    slow = int(params.get("slow", 60))
    if t < slow:
        return 0.0
    ma_f = sum(c[t - fast:t]) / fast
    ma_s = sum(c[t - slow:t]) / slow
    return (ma_f / ma_s - 1) * 100 if ma_s > 0 else 0.0


def _score_macd(c, data, indicators, params, t):
    fp  = int(params.get("fp", 12))
    sp  = int(params.get("sp", 26))
    sig = int(params.get("sig", 9))
    if t < sp + sig:
        return 0.0
    def _ema_val(arr, period, end):
        k = 2.0 / (period + 1)
        e = arr[end - period]
        for i in range(end - period + 1, end + 1):
            e = arr[i] * k + e * (1 - k)
        return e
    fast_ema  = _ema_val(c, fp, t)
    slow_ema  = _ema_val(c, sp, t)
    macd_line = fast_ema - slow_ema
    return _ind_at(indicators, t, "macd_hist", macd_line)


def _score_momentum(c, data, indicators, params, t):
    lb = int(params.get("lookback", 20))
    if t < lb:
        return 0.0
    return (c[t] / c[t - lb] - 1) * 100 if c[t - lb] > 0 else 0.0


def _score_adx_trend(c, data, indicators, params, t):
    adx_v  = _ind_at(indicators, t, "adx", 0.0)
    hist_v = _ind_at(indicators, t, "macd_hist", None)
    if hist_v is not None and hist_v != 0.0:
        direction = 1.0 if hist_v > 0 else -1.0
    else:
        ma_len = 20
        if t >= ma_len:
            ma = sum(c[t - ma_len:t]) / ma_len
            direction = 1.0 if c[t] > ma else -1.0
        else:
            direction = 0.0
    return adx_v * direction


def _score_kst(c, data, indicators, params, t):
    r1 = int(params.get("r1", 10))
    r2 = int(params.get("r2", 15))
    if t < r2:
        return 0.0
    roc1 = (c[t] / c[t - r1] - 1) * 100 if c[t - r1] > 0 else 0.0
    roc2 = (c[t] / c[t - r2] - 1) * 100 if c[t - r2] > 0 else 0.0
    return roc1 + roc2 * 2


def _score_trix(c, data, indicators, params, t):
    period = int(params.get("period", 15))
    w = period * 3 + 2
    if t < w:
        return 0.0
    seg = c[t - w:t + 1]
    def _ema(vals, p):
        k = 2.0 / (p + 1)
        e = vals[0]
        for v in vals[1:]:
            e = v * k + e * (1 - k)
        return e
    e1 = [_ema(seg[:i + 1], period) for i in range(len(seg))]
    e2 = [_ema(e1[:i + 1], period) for i in range(len(e1))]
    e3 = [_ema(e2[:i + 1], period) for i in range(len(e2))]
    if len(e3) >= 2 and e3[-2] > 0:
        return (e3[-1] / e3[-2] - 1) * 1000
    return 0.0


def _score_donchian_breakout(c, data, indicators, params, t):
    period = int(params.get("period", 20))
    highs  = data.get("highs", c)
    lows   = data.get("lows",  c)
    if t < period:
        return 0.0
    upper = max(highs[t - period:t])
    lower = min(lows[t  - period:t])
    mid   = (upper + lower) / 2.0
    return (c[t] - mid) / mid * 100 if mid > 0 else 0.0


def _score_aroon_signal(c, data, indicators, params, t):
    period = int(params.get("period", 25))
    highs  = data.get("highs", c)
    lows   = data.get("lows",  c)
    if t < period:
        return 0.0
    seg_h = list(highs[t - period:t + 1])
    seg_l = list(lows[t  - period:t + 1])
    aroon_up   = (period - (len(seg_h) - 1 - seg_h[::-1].index(max(seg_h)))) / period * 100
    aroon_down = (period - (len(seg_l) - 1 - seg_l[::-1].index(min(seg_l)))) / period * 100
    return aroon_up - aroon_down


def _score_ichimoku_signal(c, data, indicators, params, t):
    tenkan = int(params.get("tenkan", 9))
    kijun  = int(params.get("kijun", 26))
    highs  = data.get("highs", c)
    lows   = data.get("lows",  c)
    if t < max(tenkan, kijun):
        return 0.0
    t_line = (max(highs[t - tenkan:t]) + min(lows[t - tenkan:t])) / 2
    k_line = (max(highs[t - kijun:t])  + min(lows[t - kijun:t]))  / 2
    return (t_line / k_line - 1) * 100 if k_line > 0 else 0.0


def _score_rsi(c, data, indicators, params, t):
    v     = _ind_at(indicators, t, "rsi14", 50.0)
    lower = float(params.get("lower", 30))
    upper = float(params.get("upper", 70))
    mid   = (lower + upper) / 2
    return mid - v


def _score_bollinger(c, data, indicators, params, t):
    period   = int(params.get("period", 20))
    std_mult = float(params.get("std_mult", 2.0))
    if t < period:
        return 0.0
    seg  = c[t - period:t]
    mean = sum(seg) / period
    std  = (sum((x - mean) ** 2 for x in seg) / period) ** 0.5
    if std <= 0:
        return 0.0
    return -(c[t] - mean) / (std_mult * std) * 100


def _score_vol_surge(c, data, indicators, params, t):
    vol_ma_p = int(params.get("vol_ma", 20))
    vols     = data.get("volumes", [1.0] * len(c))
    if t < vol_ma_p:
        return 0.0
    avg_v = sum(vols[t - vol_ma_p:t]) / vol_ma_p
    return -(float(vols[t]) / avg_v - 1) * 100 if avg_v > 0 else 0.0


def _score_mean_reversion_proxy(c, data, indicators, params, t):
    """mfi_signal / rvi_signal / kdwave / multi_roc_signal / obos_composite / elder_ray_signal"""
    lb = max(int(params.get("period", 10)), 5)
    if t < lb:
        return 0.0
    mom = (c[t] / c[t - lb] - 1) * 100 if c[t - lb] > 0 else 0.0
    return -mom


def _score_smart_money(c, data, indicators, params, t):
    period  = max(int(params.get("period", 20)), 5)
    vol_w   = float(params.get("vol_weight", 1.5))
    vols    = data.get("volumes", [1.0] * len(c))
    if t < period:
        return 0.0
    avg_vol = sum(float(v or 1) for v in vols[t - period:t]) / period
    if avg_vol <= 0:
        return 0.0
    score = 0.0
    for i in range(t - period, t):
        if i < 1:
            continue
        chg       = (c[i] / c[i - 1] - 1) if c[i - 1] > 0 else 0.0
        vol_ratio = float(vols[i] or 1) / avg_vol if avg_vol > 0 else 1.0
        weight    = vol_ratio ** vol_w if chg > 0 else (1.0 / (vol_ratio ** vol_w + 1e-6))
        score    += chg * weight
    return score * 100


def _score_gap_break(c, data, indicators, params, t):
    min_gap  = float(params.get("min_gap_pct", 0.02))
    lookback = max(int(params.get("lookback", 10)), 3)
    lows     = data.get("lows", c)
    n        = len(c)
    if t < lookback + 1:
        return 0.0
    best_gap = 0.0
    for i in range(max(1, t - lookback), t):
        if c[i - 1] > 0:
            gap_pct = float(lows[i]) / c[i - 1] - 1
            if gap_pct > min_gap:
                filled = any(float(lows[j]) < c[i - 1] for j in range(i, t + 1) if j < n)
                if not filled:
                    recency  = (t - i + 1)
                    best_gap = max(best_gap, gap_pct * 100 / recency)
    return best_gap


def _score_limit_board(c, data, indicators, params, t):
    gain_thr = float(params.get("gain_thr", 0.07))
    lookback = max(int(params.get("lookback", 15)), 5)
    if t < lookback + 1:
        return 0.0
    score = 0.0
    for i in range(t - lookback, t):
        if i < 1 or c[i - 1] <= 0:
            continue
        daily_gain = c[i] / c[i - 1] - 1
        if daily_gain >= gain_thr:
            weight = (i - (t - lookback) + 1) / lookback
            score += daily_gain * weight * 100
    last_chg = (c[t] / c[t - 1] - 1) if c[t - 1] > 0 else 0.0
    if last_chg < -0.02:
        score *= 0.5
    return score


def _score_trend_composite(c, data, indicators, params, t):
    ma_fast = max(int(params.get("ma_fast", 10)), 3)
    ma_slow = max(int(params.get("ma_slow", 30)), ma_fast + 5)
    mom_p   = max(int(params.get("mom_period", 15)), 5)
    vol_p   = max(int(params.get("vol_period", 20)), 5)
    vols    = data.get("volumes", [1.0] * len(c))
    if t < max(ma_slow, mom_p, vol_p):
        return 0.0
    maf     = sum(c[t - ma_fast:t]) / ma_fast
    mas     = sum(c[t - ma_slow:t]) / ma_slow
    ma_sig  = (maf / mas - 1) * 100 if mas > 0 else 0.0
    mom_sig = (c[t] / c[t - mom_p] - 1) * 100 if c[t - mom_p] > 0 else 0.0
    avg_vol = sum(float(v or 1) for v in vols[t - vol_p:t]) / vol_p
    vol_sig = (float(vols[t] or 1) / avg_vol - 1) if avg_vol > 0 else 0.0
    raw = ma_sig * 0.4 + mom_sig * 0.4 + vol_sig * 20 * 0.2
    if ma_sig > 0 and mom_sig > 0 and vol_sig > 0:
        raw *= 1.3
    elif ma_sig < 0 and mom_sig < 0:
        raw *= 1.2
    return raw


def _score_lanban_fade(c, data, indicators, params, t):
    limit_thr    = float(params.get("limit_thr", 0.08))
    fade_days    = max(int(params.get("fade_days", 3)), 1)
    confirm_days = max(int(params.get("confirm_days", 2)), 1)
    highs        = data.get("highs", c)
    if t < fade_days + confirm_days + 2:
        return 0.0
    signal = 0.0
    for i in range(max(1, t - fade_days - confirm_days), t - confirm_days + 1):
        if i < 1 or c[i - 1] <= 0:
            continue
        hi                 = float(highs[i])
        intraday_high_gain = hi / c[i - 1] - 1
        close_gain         = c[i] / c[i - 1] - 1
        if intraday_high_gain >= limit_thr and close_gain < intraday_high_gain * 0.5:
            strength  = (intraday_high_gain - close_gain) * 100
            recency_w = 1.0 / (t - i + 1)
            signal   += strength * recency_w
    if signal > 0 and t >= 2:
        recent_gain = (c[t] / c[t - 2] - 1) if c[t - 2] > 0 else 0.0
        if recent_gain > 0.05:
            signal *= 0.5
    return signal


def _score_vol_price_diverge(c, data, indicators, params, t):
    lookback    = max(int(params.get("lookback", 20)), 10)
    sensitivity = float(params.get("sensitivity", 1.0))
    vols        = data.get("volumes", [1.0] * len(c))
    if t < lookback + 1:
        return 0.0
    price_mom  = (c[t] / c[t - lookback] - 1) * 100 if c[t - lookback] > 0 else 0.0
    vol_early  = sum(float(v or 1) for v in vols[t - lookback:t - lookback // 2]) / (lookback // 2)
    vol_recent = sum(float(v or 1) for v in vols[t - lookback // 2:t]) / max(lookback // 2, 1)
    vol_trend  = (vol_recent / vol_early - 1) if vol_early > 0 else 0.0
    diverge_score = -price_mom * sensitivity
    if price_mom > 0 and vol_trend < -0.1:
        diverge_score = abs(price_mom) * (1 + abs(vol_trend)) * sensitivity
    elif price_mom < 0 and vol_trend > 0.1:
        diverge_score = abs(price_mom) * 0.8 * sensitivity
    return diverge_score


def _score_multi_signal_combo(c, data, indicators, params, t):
    rsi_period = max(int(params.get("rsi_period", 14)), 5)
    rsi_lower  = float(params.get("rsi_lower", 35))
    bb_period  = max(int(params.get("bb_period", 20)), 10)
    vol_thr    = float(params.get("vol_surge_thr", 1.5))
    vols       = data.get("volumes", [1.0] * len(c))
    if t < max(rsi_period, bb_period) + 1:
        return 0.0
    rsi_v = _ind_at(indicators, t, "rsi14", 50.0)
    if rsi_period != 14:
        gains  = [max(c[i] - c[i - 1], 0)  for i in range(t - rsi_period, t) if i >= 1]
        losses = [max(c[i - 1] - c[i], 0)  for i in range(t - rsi_period, t) if i >= 1]
        avg_g  = sum(gains)  / rsi_period if gains  else 0.0
        avg_l  = sum(losses) / rsi_period if losses else 1e-6
        rs     = avg_g / avg_l if avg_l > 0 else 100
        rsi_v  = 100 - 100 / (1 + rs)
    rsi_sig = max(0.0, rsi_lower - rsi_v) / rsi_lower
    seg     = c[t - bb_period:t]
    mean    = sum(seg) / bb_period
    std     = (sum((x - mean) ** 2 for x in seg) / bb_period) ** 0.5
    bb_sig  = max(0.0, -(c[t] - mean) / (2.0 * std + 1e-6))
    avg_vol = sum(float(v or 1) for v in vols[t - bb_period:t]) / bb_period
    cur_vol = float(vols[t] or 1)
    vol_sig = min(cur_vol / avg_vol / vol_thr, 2.0) if avg_vol > 0 else 1.0
    return (rsi_sig * 40 + bb_sig * 40) * (0.5 + 0.5 * vol_sig)


def _score_mean_rev_composite(c, data, indicators, params, t):
    period  = max(int(params.get("period", 20)), 10)
    z_enter = float(params.get("z_enter", 1.5))
    z_exit  = float(params.get("z_exit", 0.5))
    if t < period + 1:
        return 0.0
    seg  = c[t - period:t]
    mean = sum(seg) / period
    std  = (sum((x - mean) ** 2 for x in seg) / period) ** 0.5
    if std <= 0:
        return 0.0
    z = (c[t] - mean) / std
    if abs(z) < z_exit:
        return 0.0
    signal = -z
    if t >= 3:
        recent_chg = (c[t] / c[t - 2] - 1) if c[t - 2] > 0 else 0.0
        if z < -z_exit and recent_chg > 0:
            signal *= 1.4
        elif z > z_exit and recent_chg < 0:
            signal *= 1.4
    return signal * 20


# ── 通用信号代理评分工厂 ──────────────────────────────────────────────
def _make_signal_score(template_key: str):
    """返回一个评分函数，调用 generate_signal() 获取信号值。"""
    from factors.signals import generate_signal, FACTOR_TABLE
    key_to_fid = {v[0]: k for k, v in FACTOR_TABLE.items()}
    fid = key_to_fid.get(template_key)

    def _score(closes, data, indicators, params, t):
        if not fid:
            return 0.0
        highs = data.get("highs", closes)
        lows  = data.get("lows",  closes)
        vols  = data.get("volumes", [1e9] * len(closes))
        try:
            signals = generate_signal(fid, list(closes), list(highs), list(lows), list(vols))
            if t < len(signals):
                return float(signals[t]) * 100.0
        except Exception:
            pass
        return 0.0
    return _score


def _score_composite(closes, data, indicators, params, t):
    """加权组合多个因子分数。
    params = {
        "factors": [
            {"key": "rsi", "weight": 0.6, "period": 14, "lower": 30, "upper": 70},
            {"key": "momentum", "weight": 0.4, "lookback": 20},
        ]
    }
    """
    factors = params.get("factors", [])
    if not factors:
        return 0.0
    total_score = 0.0
    total_weight = 0.0
    for factor in factors:
        key = factor["key"]
        fn = _SCORE_REGISTRY.get(key)
        if fn is None:
            continue
        # Pass factor-specific params merged with top-level params
        factor_params = {k: v for k, v in factor.items() if k != "key" and k != "weight"}
        score = fn(closes, data, indicators, factor_params, t)
        weight = float(factor.get("weight", 1.0))
        total_score += score * weight
        total_weight += weight
    if total_weight <= 0:
        return 0.0
    return total_score / total_weight


def _combo_get_factor_scores(closes, data, indicators, factors, t):
    """Helper for combo modes: evaluate all factors and return (scores, weights, keys)."""
    scores, weights, keys = [], [], []
    for factor in factors:
        key = factor.get("key", "")
        fn = _SCORE_REGISTRY.get(key)
        if fn is None:
            continue
        f_params = {k: v for k, v in factor.items() if k not in ("key", "weight")}
        score = fn(closes, data, indicators, f_params, t)
        scores.append(score)
        weights.append(float(factor.get("weight", 1.0)))
        keys.append(key)
    return scores, weights, keys


def _combo_score_and(closes, data, indicators, params, t):
    """AND mode: all factors must produce positive signals.
    params = {"factors": [{"key": "rsi", ...}, {"key": "momentum", ...}]}
    """
    factors = params.get("factors", [])
    scores, _, _ = _combo_get_factor_scores(closes, data, indicators, factors, t)
    if not scores:
        return 0.0
    for s in scores:
        if s <= 0:
            return 0.0
    return sum(scores) / len(scores)


def _combo_score_or(closes, data, indicators, params, t):
    """OR mode: any positive signal triggers, take the strongest."""
    factors = params.get("factors", [])
    scores, _, _ = _combo_get_factor_scores(closes, data, indicators, factors, t)
    if not scores:
        return 0.0
    # Take the strongest signal (positive or negative)
    return max(scores, key=abs)


def _combo_score_weighted(closes, data, indicators, params, t):
    """Weighted sum mode: same as _score_composite, renamed for registry consistency."""
    return _score_composite(closes, data, indicators, params, t)


def _combo_score_rank(closes, data, indicators, params, t):
    """Rank aggregation: normalize each factor to [0,1] via rank, then equal-weight average.
    Requires knowing the full universe of scores. Uses params.get('_universe_scores') if available.
    Simple fallback: divide by factor's typical range.
    """
    factors = params.get("factors", [])
    scores, _, _ = _combo_get_factor_scores(closes, data, indicators, factors, t)
    if not scores:
        return 0.0
    # Normalize each factor score by its factor's estimated typical range
    # This avoids one factor dominating due to scale differences
    normalized = []
    for s in scores:
        normalized.append(max(-1.0, min(1.0, s / 100.0)))
    return sum(normalized) / len(normalized) * 100.0


def _combo_score_product(closes, data, indicators, params, t):
    """Product / geometric mean: multiply scores. Any near-zero score suppresses result."""
    factors = params.get("factors", [])
    scores, _, _ = _combo_get_factor_scores(closes, data, indicators, factors, t)
    if not scores:
        return 0.0
    product = 1.0
    for s in scores:
        if abs(s) < 0.01:
            return 0.0
        product *= s
    # Geometric mean preserving sign
    n = len(scores)
    if product < 0:
        return -((-product) ** (1.0 / n))
    return product ** (1.0 / n)


def _combo_score_hierarchical(closes, data, indicators, params, t):
    """Hierarchical: layer1 must pass (score > 0), then layer2 scores.
    params = {
        "factors": [{"key": "adx", ...}, {"key": "momentum", ...}],
        "layer_split": 1  # first N factors are layer1, rest are layer2
    }
    """
    factors = params.get("factors", [])
    layer_split = int(params.get("layer_split", 1))
    if not factors or layer_split <= 0 or layer_split >= len(factors):
        return 0.0

    layer1_factors = factors[:layer_split]
    layer2_factors = factors[layer_split:]

    # Layer 1: all must pass
    s1, _, _ = _combo_get_factor_scores(closes, data, indicators, layer1_factors, t)
    if not s1:
        return 0.0
    for s in s1:
        if s <= 0:
            return 0.0

    # Layer 2: score
    s2, w2, _ = _combo_get_factor_scores(closes, data, indicators, layer2_factors, t)
    if not s2:
        return sum(s1) / len(s1)  # fallback to layer1 avg

    total = sum(s * w for s, w in zip(s2, w2))
    total_w = sum(w2)
    return total / total_w if total_w > 0 else 0.0


def _combo_score_conditional(closes, data, indicators, params, t):
    """Conditional weighting: weights change based on a condition factor.
    params = {
        "factors": [
            {"key": "momentum", "weight_trend": 0.7, "weight_sideways": 0.3},
            {"key": "rsi",      "weight_trend": 0.3, "weight_sideways": 0.7},
        ],
        "condition": {"key": "adx_trend", "params": {"adx_thr": 25}, "trend_threshold": 25}
    }
    When condition > threshold → use weight_trend, else use weight_sideways.
    """
    condition = params.get("condition", {})
    cond_key = condition.get("key", "")
    cond_params = {k: v for k, v in condition.items() if k not in ("key", "trend_threshold")}
    trend_threshold = float(condition.get("trend_threshold", 25))

    factors = params.get("factors", [])

    # Evaluate condition factor
    if cond_key:
        fn = _SCORE_REGISTRY.get(cond_key)
        if fn:
            cond_score = fn(closes, data, indicators, cond_params, t)
            is_trend = cond_score >= trend_threshold
        else:
            is_trend = True  # default if condition factor not found
    else:
        is_trend = True

    # Score with regime-appropriate weights
    total_score = 0.0
    total_weight = 0.0
    for factor in factors:
        key = factor.get("key", "")
        fn = _SCORE_REGISTRY.get(key)
        if fn is None:
            continue
        f_params = {k: v for k, v in factor.items()
                    if k not in ("key", "weight_trend", "weight_sideways")}
        score = fn(closes, data, indicators, f_params, t)
        weight = float(factor.get("weight_trend" if is_trend else "weight_sideways", 1.0))
        total_score += score * weight
        total_weight += weight

    return total_score / total_weight if total_weight > 0 else 0.0


def _apply_gate(score, closes, data, indicators, params, t):
    """Apply conditional gate: return 0.0 if condition not met, else return original score.
    params = {
        "gate": {"type": "volume_surge", "param": 2.0},
    }
    """
    gate = params.get("gate")
    if not gate:
        return score
    gate_type = gate.get("type")
    gate_param = gate.get("param", 2.0)

    if gate_type == "volume_surge":
        vols = data.get("volumes", [1.0]*len(closes))
        if t < 20:
            return score
        n_back = min(20, t)
        avg_vol = sum(float(vols[i]) for i in range(t - n_back, t)) / n_back
        return score if float(vols[t]) / max(avg_vol, 1e-9) > gate_param else 0.0

    elif gate_type == "above_ma":
        if t < 200:
            return score
        ma = sum(closes[t-200:t]) / 200
        return score if closes[t] > ma else 0.0

    elif gate_type == "below_ma":
        if t < 200:
            return score
        ma = sum(closes[t-200:t]) / 200
        return score if closes[t] < ma else 0.0

    elif gate_type == "adx_filter":
        adx = indicators.get("adx", [0]*len(closes))
        if t < len(adx):
            return score if adx[t] > gate_param else 0.0
        return 0.0

    elif gate_type == "low_vol":
        atr = indicators.get("atr", [1]*len(closes))
        if t < len(atr) and atr[t] > 0:
            return score if (atr[t] / closes[t]) < gate_param else 0.0
        return score

    return score


def _detect_regime(closes, indicators, t):
    """
    Detect current market regime.
    - "trend": ADX > 25 and price above 200-day MA
    - "mean_reversion": ADX <= 25 or price oscillating near MA
    - "high_vol": ATR/price > 0.03 (high volatility)
    Returns: "trend", "mean_reversion", or "high_vol"
    """
    if t < 200:
        return "mean_reversion"

    adx = indicators.get("adx", [0] * len(closes))
    adx_val = adx[t] if t < len(adx) else 0

    ma_200 = sum(closes[t - 200:t]) / 200
    price_position = (closes[t] - ma_200) / ma_200 if ma_200 > 0 else 0

    atr = indicators.get("atr", [1] * len(closes))
    atr_val = atr[t] if t < len(atr) else closes[t] * 0.02
    vol_ratio = atr_val / closes[t] if closes[t] > 0 else 0.02

    if vol_ratio > 0.03:
        return "high_vol"

    if adx_val > 25 and abs(price_position) > 0.02:
        return "trend"

    return "mean_reversion"


# ── 因子打分注册表 ────────────────────────────────────────────────────
_SCORE_REGISTRY = {
    "ma_cross":          _score_ma_cross,
    "macd":              _score_macd,
    "momentum":          _score_momentum,
    "adx_trend":         _score_adx_trend,
    "kst":               _score_kst,
    "trix":              _score_trix,
    "donchian_breakout": _score_donchian_breakout,
    "aroon_signal":      _score_aroon_signal,
    "ichimoku_signal":   _score_ichimoku_signal,
    "rsi":               _score_rsi,
    "bollinger":         _score_bollinger,
    "vol_surge":         _score_vol_surge,
    "mfi_signal":        _score_mean_reversion_proxy,
    "rvi_signal":        _score_mean_reversion_proxy,
    "kdwave":            _score_mean_reversion_proxy,
    "multi_roc_signal":  _score_mean_reversion_proxy,
    "obos_composite":    _score_mean_reversion_proxy,
    "elder_ray_signal":  _score_mean_reversion_proxy,
    "smart_money":       _score_smart_money,
    "gap_break":         _score_gap_break,
    "limit_board":       _score_limit_board,
    "trend_composite":   _score_trend_composite,
    "lanban_fade":       _score_lanban_fade,
    "vol_price_diverge": _score_vol_price_diverge,
    "multi_signal_combo":_score_multi_signal_combo,
    "mean_rev_composite":_score_mean_rev_composite,
    # ── v5: 补全缺失因子 ──────────────────────────────────────────
    "force_index":               _make_signal_score("force_index"),
    "ppo":                       _make_signal_score("ppo"),
    "accdist":                   _make_signal_score("accdist"),
    "accumulation_distribution_signal": _make_signal_score("accumulation_distribution_signal"),
    "volume_price_trend":        _make_signal_score("volume_price_trend"),
    "mass_index":                _make_signal_score("mass_index"),
    "ergodic_oscillator":        _make_signal_score("ergodic_oscillator"),
    "signal_horizon":            _make_signal_score("signal_horizon"),
    "ultraspline":               _make_signal_score("ultraspline"),
    "ultraband_signal":          _make_signal_score("ultraband_signal"),
    "chanlun_bi":                _make_signal_score("chanlun_bi"),
    "chanlun_tao":               _make_signal_score("chanlun_tao"),
    "_composite":                _score_composite,
    # combo modes (v5.15d)
    "_combo_and":          _combo_score_and,
    "_combo_or":           _combo_score_or,
    "_combo_weighted":     _combo_score_weighted,
    "_combo_rank":         _combo_score_rank,
    "_combo_product":      _combo_score_product,
    "_combo_hierarchical": _combo_score_hierarchical,
    "_combo_conditional":  _combo_score_conditional,
}


# ── 因子打分入口 ──────────────────────────────────────────────────────
def compute_factor_score(
    closes: list, data: dict, indicators: dict,
    params: dict, template_key: str, t: int,
) -> float:
    """
    在第 t 个时间点给该标的打出一个因子分数（越高越倾向持有）。
    正值 = 做多信号，负值 = 做空信号，0 = 中性。
    新增策略只需在 _SCORE_REGISTRY 中注册，无需修改本函数。
    """
    n = len(closes)
    if t < 2 or t >= n:
        return 0.0

    fn = _SCORE_REGISTRY.get(template_key)
    if fn is not None:
        return fn(closes, data, indicators, params, t)

    # 动态注册的生成因子（research pipeline 产出）
    from experts.factor_library import GENERATED_FACTORS
    if template_key in GENERATED_FACTORS:
        extensions = data.get("extensions", {})
        return GENERATED_FACTORS[template_key](closes, data, indicators, extensions, params, t)

    return 0.0


def _score_regime_adaptive(closes, data, indicators, params, t):
    """
    Score based on detected market regime by selecting different factors.
    params = {
        "branches": {
            "trend_factor": {"key": "macd", "fp": 12, "sp": 26, "sig": 9},
            "mr_factor": {"key": "rsi", "period": 14, "lower": 30, "upper": 70},
            "safe_factor": {"key": "bollinger", "period": 20, "std_mult": 2.0},
        }
    }
    """
    regime = _detect_regime(closes, indicators, t)
    branches = params.get("branches", {})

    if regime == "trend" and "trend_factor" in branches:
        branch = branches["trend_factor"]
        key = branch.get("key", "")
        branch_params = {k: v for k, v in branch.items() if k != "key"}
        return compute_factor_score(closes, data, indicators, branch_params, key, t)

    elif regime == "mean_reversion" and "mr_factor" in branches:
        branch = branches["mr_factor"]
        key = branch.get("key", "")
        branch_params = {k: v for k, v in branch.items() if k != "key"}
        return compute_factor_score(closes, data, indicators, branch_params, key, t)

    elif regime == "high_vol" and "safe_factor" in branches:
        branch = branches["safe_factor"]
        key = branch.get("key", "")
        branch_params = {k: v for k, v in branch.items() if k != "key"}
        return compute_factor_score(closes, data, indicators, branch_params, key, t)

    return 0.0


def compute_weights(
    selected: list,
    scores: dict,
    method: str,
    closes_by_sym: dict,
    t: int,
    max_pos: float = 0.95,
) -> dict:
    """
    按选定方式计算各标的目标权重（合计 ≤ 1）。

    method:
        "equal"          — 等权（1/N）
        "score_weighted" — 按因子分数正比分配
        "vol_inverse"    — 按20日波动率倒数分配（低波动率 → 更高权重）
    """
    if not selected:
        return {}
    n = len(selected)

    if method == "equal":
        w = min(1.0 / n, max_pos)
        return {s: w for s in selected}

    elif method == "score_weighted":
        raw = {s: max(float(scores.get(s, 0.0)), 1e-6) for s in selected}
        total = sum(raw.values())
        if total <= 0:
            w = min(1.0 / n, max_pos)
            return {s: w for s in selected}
        return {s: min(v / total, max_pos) for s, v in raw.items()}

    elif method == "vol_inverse":
        vol_map = {}
        for s in selected:
            cl = closes_by_sym.get(s, [])
            if t >= 21 and len(cl) > t:
                rets = [(cl[i] / cl[i - 1] - 1) for i in range(t - 19, t + 1)
                        if cl[i - 1] > 0]
                if rets:
                    m   = sum(rets) / len(rets)
                    std = math.sqrt(sum((r - m) ** 2 for r in rets) / len(rets))
                    vol_map[s] = max(std, 1e-6)
                else:
                    vol_map[s] = 1.0
            else:
                vol_map[s] = 1.0
        inv   = {s: 1.0 / vol_map[s] for s in selected}
        total = sum(inv.values())
        return {s: min(v / total, max_pos) for s, v in inv.items()}

    # 未知方法 → 等权
    w = min(1.0 / n, max_pos)
    return {s: w for s in selected}


# ── 主类 ──────────────────────────────────────────────────────────────
class PortfolioBacktester:
    """
    多股组合回测引擎。

    流程：
      - 每隔 rebalance_freq 个交易日触发调仓
      - 调仓时：对所有标的打因子分数 → 选 top-n_stocks → 计算权重 → 换仓
      - 支持同一标的被多策略持仓（仓位合并）

    参数通过 candidate["portfolio_params"] 传入，均是可变异的搜索参数。
    """

    def __init__(
        self,
        symbols_data: list,       # [{symbol, data, indicators}, ...]
        expert,                   # TrendExpert / MeanReversionExpert（用于 strategy_type）
        candidate: dict,          # {template_key, params, strategy_id, ...}
        portfolio_params: dict,   # {n_stocks, rebalance_freq, weight_method, max_position_pct}
    ):
        self.symbols_data    = symbols_data
        self.expert          = expert
        self.cand            = candidate
        self.pp              = {**DEFAULT_PORTFOLIO_PARAMS, **portfolio_params}
        self._holding_entry_prices = {}  # sym → entry price (for risk overlay)
        self._holding_peak_prices  = {}  # sym → peak price (for trailing stop)

    @staticmethod
    def _get_limit_threshold(symbol: str) -> tuple:
        """Return (limit_up_pct, limit_down_pct) based on A-share board rules.
        Symbol format: '000001.SZ' or '600519.SH'
        主板 (±10%)  : 60xxxx.SH, 00xxxx.SZ, 001xxx.SZ, 002xxx.SZ, 003xxx.SZ
        创业板/科创板 (±20%): 300xxx.SZ, 301xxx.SZ, 688xxx.SH
        北交所 (±30%) : 8xxxxx
        """
        code = symbol.split(".")[0]
        if code.startswith("688") or code.startswith("300") or code.startswith("301"):
            return (19.95, -19.95)  # STAR/ChiNext ±20%
        elif code.startswith("8"):
            return (29.95, -29.95)  # 北交所 ±30%
        return (9.95, -9.95)        # 主板/SME ±10%

    def _select_stocks(self, scores, sym_list, closes_by_sym, data_by_sym, ind_by_sym, pctchg_by_sym, t, exec_t, n_stocks):
        """
        Single-stage or two-stage stock selection.
        
        params.selection_stage == "two_stage":  
          Phase 1: primary_factor → pool_size (wide pool)
          Phase 2: secondary_factor → n_stocks (final selection)
        else: normal single stage.
        """
        params = self.cand.get("params", {})
        stage = params.get("selection_stage", "single")
        
        def _sym_up_limit(sym):
            return self._get_limit_threshold(sym)[0]
        
        if stage == "two_stage":
            pool_size = int(params.get("pool_size", 100))
            primary_key = params.get("primary_factor", {}).get("key", "")
            secondary_key = params.get("secondary_factor", {}).get("key", "")
            
            if not primary_key or not secondary_key:
                # Fallback to single stage
                pass
            else:
                # Phase 1: Primary factor → wide pool
                primary_scores = {}
                for sym in sym_list:
                    sc = compute_factor_score(
                        closes_by_sym[sym], data_by_sym[sym],
                        ind_by_sym[sym], {}, primary_key, t,
                    )
                    primary_scores[sym] = sc
                primary_pos = {s: sc for s, sc in primary_scores.items() if sc > 0}
                # Limit-up filter
                pchg_exec = {s: (pctchg_by_sym[s][exec_t]
                                 if exec_t < len(pctchg_by_sym.get(s, [])) else 0.0)
                             for s in primary_pos}
                primary_pos = {s: sc for s, sc in primary_pos.items()
                               if pchg_exec.get(s, 0.0) < _sym_up_limit(s)}
                pool_set = set(sorted(primary_pos, key=primary_pos.__getitem__, reverse=True)[:pool_size])
                
                # Phase 2: Secondary factor → narrow selection
                secondary_scores = {}
                for sym in sym_list:
                    if sym not in pool_set:
                        continue
                    sc = compute_factor_score(
                        closes_by_sym[sym], data_by_sym[sym],
                        ind_by_sym[sym], {}, secondary_key, t,
                    )
                    secondary_scores[sym] = sc
                secondary_pos = {s: sc for s, sc in secondary_scores.items() if sc > 0}
                selected = sorted(secondary_pos, key=secondary_pos.__getitem__, reverse=True)[:n_stocks]
                
                # Return with the secondary scores (for weight computation)
                return selected, secondary_pos
        
        # Single stage (default)
        positive = {s: sc for s, sc in scores.items() if sc > 0}
        pchg_exec = {s: (pctchg_by_sym[s][exec_t]
                         if exec_t < len(pctchg_by_sym.get(s, [])) else 0.0)
                     for s in positive}
        positive = {s: sc for s, sc in positive.items()
                    if pchg_exec.get(s, 0.0) < _sym_up_limit(s)}
        selected = sorted(positive, key=positive.__getitem__, reverse=True)[:n_stocks]
        return selected, positive

    def _apply_risk_overlay(self, holdings, closes_by_sym, t, exec_t, initial_cash):
        """
        Apply risk rules (stop-loss, take-profit, trailing-stop) to existing holdings.
        Returns (sell_proceeds, trades_list, remaining_holdings).
        """
        risk_rules = self.cand.get("params", {}).get("risk_rules", {})
        if not risk_rules:
            return 0.0, [], holdings

        sell_proceeds = 0.0
        trades_list = []
        remaining = {}

        for sym, shares in holdings.items():
            entry_price = self._holding_entry_prices.get(sym, 0)
            current_price = closes_by_sym[sym][exec_t] if exec_t < len(closes_by_sym[sym]) else 0

            if current_price <= 0 or entry_price <= 0:
                remaining[sym] = shares
                continue

            pnl_pct = (current_price - entry_price) / entry_price
            force_sell = False
            reason = ""

            # Stop-loss
            stop_loss = float(risk_rules.get("stop_loss", 0))
            if stop_loss > 0 and pnl_pct < -stop_loss:
                force_sell = True
                reason = "stop_loss"

            # Take-profit
            take_profit = float(risk_rules.get("take_profit", 0))
            if take_profit > 0 and pnl_pct > take_profit:
                force_sell = True
                reason = "take_profit"

            # Trailing stop
            trailing = float(risk_rules.get("trailing_stop", 0))
            if trailing > 0:
                peak = self._holding_peak_prices.get(sym, entry_price)
                if current_price > peak:
                    self._holding_peak_prices[sym] = current_price
                    peak = current_price
                if not force_sell and (peak - current_price) / peak > trailing:
                    force_sell = True
                    reason = "trailing_stop"

            if force_sell:
                gross = shares * current_price
                net = gross - gross * SELL_COST
                sell_proceeds += net
                cost_basis = shares * entry_price * (1 + BUY_COST)
                trade_return = (net - cost_basis) / cost_basis if cost_basis > 0 else 0.0
                trades_list.append(trade_return)
                self._holding_entry_prices.pop(sym, None)
                self._holding_peak_prices.pop(sym, None)
            else:
                remaining[sym] = shares

        return sell_proceeds, trades_list, remaining

    # ── 主入口 ──────────────────────────────────────────────────────
    def run(self, initial_cash: float = 1_000_000.0, oos_days: int = 0):
        """
        执行组合回测，返回 BacktestReport。
        oos_days > 0 时：IS 区间 = [1, n-oos_days)，OOS 区间 = [n-oos_days, n)。
        OOS 结果写入 report.oos_annualized_return。
        """
        from experts.specialists.factor_combo_expert import BacktestReport

        pp             = self.pp
        n_stocks       = max(1, int(pp["n_stocks"]))
        rebalance_freq = max(1, int(pp["rebalance_freq"]))
        weight_method  = str(pp["weight_method"])
        max_pos        = float(pp["max_position_pct"])
        template_key   = self.cand.get("template_key", "")
        params         = self.cand.get("params", {})
        strategy_id    = self.cand.get("strategy_id", "")
        base_name      = self.cand.get("strategy_name", template_key)

        strategy_name = (
            f"{base_name}"
            f"[N{n_stocks}/R{rebalance_freq}/{weight_method[0].upper()}]"
        )

        # ── 准备各标的数据 ───────────────────────────────────────
        sym_list      = [sd["symbol"] for sd in self.symbols_data]
        closes_by_sym = {sd["symbol"]: [float(c) for c in sd["data"]["closes"]]
                         for sd in self.symbols_data}
        data_by_sym   = {sd["symbol"]: sd["data"]       for sd in self.symbols_data}
        ind_by_sym    = {sd["symbol"]: sd["indicators"]  for sd in self.symbols_data}
        # 各板块涨跌幅限制: _get_limit_threshold 按代码前缀区分
        pctchg_by_sym = {sd["symbol"]: sd["data"].get("pct_chgs", [])
                         for sd in self.symbols_data}

        _MIN_BARS = 600
        if len(closes_by_sym) > 1:
            closes_by_sym = {s: c for s, c in closes_by_sym.items() if len(c) >= _MIN_BARS}
            data_by_sym   = {s: d for s, d in data_by_sym.items()   if s in closes_by_sym}
            ind_by_sym    = {s: i for s, i in ind_by_sym.items()     if s in closes_by_sym}
            sym_list      = [s for s in sym_list                     if s in closes_by_sym]

        if not closes_by_sym:
            return BacktestReport(strategy_id=strategy_id, strategy_name=strategy_name,
                                  strategy_type=self.cand.get("strategy_type", "trend"))
        n = min(len(v) for v in closes_by_sym.values())
        if n < 30:
            return BacktestReport(strategy_id=strategy_id, strategy_name=strategy_name,
                                  strategy_type=self.cand.get("strategy_type", "trend"))

        # IS 区间：[1, train_end)；OOS 区间：[train_end, n)
        train_end = n - oos_days if (oos_days > 0 and n > oos_days + 200) else n

        sim_kw = dict(
            closes_by_sym=closes_by_sym, data_by_sym=data_by_sym,
            ind_by_sym=ind_by_sym, pctchg_by_sym=pctchg_by_sym,
            sym_list=sym_list, params=params, template_key=template_key,
            n_stocks=n_stocks, rebalance_freq=rebalance_freq,
            weight_method=weight_method, max_pos=max_pos,
            initial_cash=initial_cash,
        )

        equity, trades, daily_rets, exec_shortfalls = self._sim_range(1, train_end, **sim_kw)
        report = self._build_report(strategy_id, strategy_name, params,
                                    equity, trades, daily_rets, exec_shortfalls, train_end, initial_cash)

        if oos_days > 0 and train_end < n:
            _, _, oos_rets, _ = self._sim_range(train_end, n, **sim_kw)
            if oos_rets:
                report.oos_annualized_return = round(
                    sum(oos_rets) / len(oos_rets) * 252 * 100, 2)

        return report

    def _sim_range(self, t_start: int, t_end: int,
                   closes_by_sym, data_by_sym, ind_by_sym, pctchg_by_sym,
                   sym_list, params, template_key, n_stocks, rebalance_freq,
                   weight_method, max_pos, initial_cash):
        """从 t_start 到 t_end 运行一段模拟，返回 (equity, trades, daily_rets)。"""
        cash     = float(initial_cash)
        holdings: Dict[str, float] = {}
        equity   = [cash]
        trades   = []
        daily_rets = []

        exec_shortfalls = []
        for t in range(t_start, t_end):
            # 信号在 t 日收盘后生成，次日 (t+1) 开盘/收盘成交，消除同日未来函数
            if (t - t_start) % rebalance_freq == 0 and t + 1 < t_end:
                exec_t = t + 1
                scores = {
                    sym: compute_factor_score(
                        closes_by_sym[sym], data_by_sym[sym],
                        ind_by_sym[sym], params, template_key, t,
                    )
                    for sym in sym_list
                }
                # Phase 2: 信号门控 — 对每个标的打分后应用门控条件
                for sym in list(scores.keys()):
                    scores[sym] = _apply_gate(
                        scores[sym], closes_by_sym[sym], data_by_sym[sym],
                        ind_by_sym[sym], params, t,
                    )
                selected, positive = self._select_stocks(
                    scores, sym_list, closes_by_sym, data_by_sym, ind_by_sym,
                    pctchg_by_sym, t, exec_t, n_stocks,
                )

                target_w = compute_weights(
                    selected, positive, weight_method, closes_by_sym, exec_t, max_pos,
                )

                # Phase 4: 风险覆盖层 — 止损/止盈/跟踪止盈
                risk_proceeds, risk_trades, new_holdings = self._apply_risk_overlay(
                    holdings, closes_by_sym, t, exec_t, initial_cash,
                )
                holdings = new_holdings

                sell_proceeds = risk_proceeds
                for sym in list(holdings.keys()):
                    pchg = (pctchg_by_sym[sym][exec_t]
                            if exec_t < len(pctchg_by_sym.get(sym, [])) else 0.0)
                    if pchg <= self._get_limit_threshold(sym)[1]:  # limit down check
                        continue
                    shares = holdings.pop(sym)
                    price  = closes_by_sym[sym][exec_t]
                    gross  = shares * price
                    net    = gross - gross * SELL_COST
                    sell_proceeds += net
                    entry_price = self._holding_entry_prices.pop(sym, 0)
                    self._holding_peak_prices.pop(sym, None)
                    cost_basis = shares * entry_price * (1 + BUY_COST)
                    trade_return = (net - cost_basis) / cost_basis if cost_basis > 0 else 0.0
                    trades.append(trade_return)
                for rt in risk_trades:
                    trades.append(rt)
                cash += sell_proceeds

                total_eq = cash
                for sym in selected:
                    w     = target_w.get(sym, 0.0)
                    alloc = total_eq * w
                    price = closes_by_sym[sym][exec_t]
                    if price <= 0 or alloc <= 0:
                        continue
                    cost   = alloc * BUY_COST
                    shares = (alloc - cost) / price
                    cash  -= alloc
                    holdings[sym] = shares
                    # Track entry and peak prices for risk overlay
                    self._holding_entry_prices[sym] = price
                    self._holding_peak_prices[sym] = price
                    # 执行损耗: 信号价(t日收盘) → 实际成交价(t+1日收盘)
                    sig_price = closes_by_sym[sym][t]
                    if sig_price > 0:
                        exec_shortfalls.append((price - sig_price) / sig_price)

            port_val = cash + sum(
                holdings[sym] * closes_by_sym[sym][t]
                for sym in holdings
                if t < len(closes_by_sym[sym])
            )
            prev = equity[-1]
            equity.append(port_val)
            daily_rets.append((port_val - prev) / prev if prev > 0 else 0.0)

        return equity, trades, daily_rets, exec_shortfalls

    # ── 统计指标 ────────────────────────────────────────────────────
    def _build_report(self, sid, name, params, equity, trades,
                       daily_rets, exec_shortfalls, n, cash):
        from experts.specialists.factor_combo_expert import BacktestReport
        final = float(equity[-1])
        tr    = final / cash - 1
        ann   = (final / cash) ** (252 / max(n - 1, 1)) - 1
        vol   = self._std(daily_rets) * math.sqrt(252) if daily_rets else 0.0
        # Sharpe = mean(r_i) / σ(r_i) * √252 (标准定义)
        mean_daily = sum(daily_rets) / n if daily_rets and n > 0 else 0.0
        s = (mean_daily * 252) / vol if vol > 0 else 0.0
        sortino_v = self._sortino(daily_rets)
        max_dd_v  = self._max_dd(daily_rets)
        calmar    = ann / (max_dd_v / 100) if max_dd_v > 0 else 0.0
        wins  = [t for t in trades if t > 0]
        loss  = [t for t in trades if t < 0]
        wr    = len(wins) / len(trades) if trades else 0.0
        avg_w = sum(wins) / len(wins) if wins else 0.0
        avg_l = abs(sum(loss) / len(loss)) if loss else 1e-9
        pf    = avg_w / avg_l if avg_l > 1e-9 else 0.0
        # 执行损耗统计
        if exec_shortfalls:
            sorted_es = sorted(exec_shortfalls)
            n_es = len(sorted_es)
            es_median = sorted_es[n_es // 2] if n_es % 2 else (sorted_es[n_es//2 - 1] + sorted_es[n_es//2]) / 2
            es_mean = sum(exec_shortfalls) / n_es
        else:
            es_median = 0.0
            es_mean = 0.0
        return BacktestReport(
            strategy_id       = sid,
            strategy_name     = name,
            strategy_type     = self.cand.get("strategy_type", "trend"),
            tags              = self.cand.get("tags", []),
            params            = {**params, **{f"pf_{k}": v
                                              for k, v in self.pp.items()}},
            total_return      = round(tr * 100, 2),
            sharpe_ratio      = round(s, 3),
            max_drawdown_pct  = round(max_dd_v, 2),
            annualized_return = round(ann * 100, 2),
            volatility        = round(vol * 100, 2),
            total_trades      = len(trades),
            win_rate          = round(wr * 100, 2),
            profit_factor     = round(pf, 2),
            avg_holding_days  = round(n / max(len(trades), 1), 1),
            calmar_ratio      = round(calmar, 3),
            sortino_ratio     = round(sortino_v, 3),
            daily_returns     = [round(r, 4) for r in daily_rets],
            execution_shortfall_median = round(es_median * 100, 2),
            execution_shortfall_mean   = round(es_mean * 100, 2),
        )

    @staticmethod
    def _std(vals: list) -> float:
        n = len(vals)
        if n < 2:
            return 0.0
        m = sum(vals) / n
        return math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1))

    @staticmethod
    def _sortino(rets: list, target: float = 0.0) -> float:
        down = [r for r in rets if r < target]
        if not down:
            return 0.0
        ann_ret = sum(rets) / len(rets) * 252 if rets else 0.0
        dstd = PortfolioBacktester._std(down) * math.sqrt(252)
        return ann_ret / (dstd + 1e-9)

    @staticmethod
    def _max_dd(rets: list) -> float:
        eq = 1.0; peak = 1.0; max_dd = 0.0
        for r in rets:
            eq *= (1 + r)
            if eq > peak:
                peak = eq
            dd = (eq - peak) / peak
            if dd < max_dd:
                max_dd = dd
        return abs(max_dd) * 100

# ── 后续注册（依赖函数已定义） ──────────────────────────────────────────
_SCORE_REGISTRY["_regime_adaptive"] = _score_regime_adaptive
