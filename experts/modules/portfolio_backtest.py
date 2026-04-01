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
BUY_COST  = 0.0003 + 0.0005           # 佣金+滑点 = 0.08%
SELL_COST = 0.0003 + 0.0005 + 0.0010  # 佣金+滑点+印花税 = 0.18%

# ── 默认组合参数 ────────────────────────────────────────────────────
DEFAULT_PORTFOLIO_PARAMS = {
    "n_stocks":         2,
    "rebalance_freq":   20,
    "weight_method":    "equal",
    "max_position_pct": 0.95,
}


# ── 因子打分：策略信号 → 连续分数 ────────────────────────────────────
def compute_factor_score(
    closes: list, data: dict, indicators: dict,
    params: dict, template_key: str, t: int,
) -> float:
    """
    在第 t 个时间点给该标的打出一个因子分数（越高越倾向持有）。
    正值 = 做多信号，负值 = 做空信号，0 = 中性。
    """
    n = len(closes)
    if t < 2 or t >= n:
        return 0.0
    c = closes

    def _ind(key: str, default: float = 0.0) -> float:
        """Safely read indicator value at t, returning default for None or missing."""
        arr = indicators.get(key)
        if arr is None or t >= len(arr):
            return default
        v = arr[t]
        return float(v) if v is not None else default

    # ── 趋势策略 ───────────────────────────────────────────────────
    if template_key == "ma_cross":
        fast = int(params.get("fast", 20))
        slow = int(params.get("slow", 60))
        if t < slow:
            return 0.0
        ma_f = sum(c[t - fast:t]) / fast
        ma_s = sum(c[t - slow:t]) / slow
        return (ma_f / ma_s - 1) * 100 if ma_s > 0 else 0.0

    elif template_key == "macd":
        # Compute MACD histogram directly from closes if indicator not available
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
        fast_ema = _ema_val(c, fp, t)
        slow_ema = _ema_val(c, sp, t)
        macd_line = fast_ema - slow_ema
        return _ind("macd_hist", macd_line)

    elif template_key == "momentum":
        lb = int(params.get("lookback", 20))
        if t < lb:
            return 0.0
        return (c[t] / c[t - lb] - 1) * 100 if c[t - lb] > 0 else 0.0

    elif template_key == "adx_trend":
        adx_v  = _ind("adx", 0.0)
        # Direction: use MACD hist if available, else use short MA vs long MA
        hist_v = _ind("macd_hist", None)
        if hist_v is not None and hist_v != 0.0:
            direction = 1.0 if hist_v > 0 else -1.0
        else:
            # Fallback: price above MA20 = uptrend
            ma_len = 20
            if t >= ma_len:
                ma = sum(c[t - ma_len: t]) / ma_len
                direction = 1.0 if c[t] > ma else -1.0
            else:
                direction = 0.0
        return adx_v * direction

    elif template_key == "kst":
        r1 = int(params.get("r1", 10))
        r2 = int(params.get("r2", 15))
        if t < r2:
            return 0.0
        roc1 = (c[t] / c[t - r1] - 1) * 100 if c[t - r1] > 0 else 0.0
        roc2 = (c[t] / c[t - r2] - 1) * 100 if c[t - r2] > 0 else 0.0
        return roc1 + roc2 * 2

    elif template_key == "trix":
        period = int(params.get("period", 15))
        w = period * 3 + 2
        if t < w:
            return 0.0
        seg = c[t - w: t + 1]

        def _ema(vals, p):
            k = 2.0 / (p + 1)
            e = vals[0]
            for v in vals[1:]:
                e = v * k + e * (1 - k)
            return e

        # triple EMA ROC
        e1 = [_ema(seg[:i + 1], period) for i in range(len(seg))]
        e2 = [_ema(e1[:i + 1], period) for i in range(len(e1))]
        e3 = [_ema(e2[:i + 1], period) for i in range(len(e2))]
        if len(e3) >= 2 and e3[-2] > 0:
            return (e3[-1] / e3[-2] - 1) * 1000
        return 0.0

    elif template_key == "donchian_breakout":
        period = int(params.get("period", 20))
        highs  = data.get("highs", c)
        lows   = data.get("lows",  c)
        if t < period:
            return 0.0
        upper = max(highs[t - period: t])
        lower = min(lows[t  - period: t])
        mid   = (upper + lower) / 2.0
        return (c[t] - mid) / mid * 100 if mid > 0 else 0.0

    elif template_key == "aroon_signal":
        period = int(params.get("period", 25))
        highs  = data.get("highs", c)
        lows   = data.get("lows",  c)
        if t < period:
            return 0.0
        seg_h = list(highs[t - period: t + 1])
        seg_l = list(lows[t  - period: t + 1])
        aroon_up   = (period - (len(seg_h) - 1 - seg_h[::-1].index(max(seg_h)))) / period * 100
        aroon_down = (period - (len(seg_l) - 1 - seg_l[::-1].index(min(seg_l)))) / period * 100
        return aroon_up - aroon_down

    elif template_key == "ichimoku_signal":
        tenkan = int(params.get("tenkan", 9))
        kijun  = int(params.get("kijun", 26))
        highs  = data.get("highs", c)
        lows   = data.get("lows",  c)
        if t < kijun:
            return 0.0
        t_line = (max(highs[t - tenkan: t]) + min(lows[t - tenkan: t])) / 2
        k_line = (max(highs[t - kijun:  t]) + min(lows[t - kijun:  t])) / 2
        return (t_line / k_line - 1) * 100 if k_line > 0 else 0.0

    # ── 均值回归策略（低值 = 超卖 = 正分）────────────────────────
    elif template_key == "rsi":
        v     = _ind("rsi14", 50.0)
        lower = float(params.get("lower", 30))
        upper = float(params.get("upper", 70))
        mid   = (lower + upper) / 2
        return mid - v  # 超卖时为正，超买时为负

    elif template_key == "bollinger":
        # bollinger: 计算当时收盘价相对布林带的位置（均值回归）
        period   = int(params.get("period", 20))
        std_mult = float(params.get("std_mult", 2.0))
        if t < period:
            return 0.0
        seg  = c[t - period: t]
        mean = sum(seg) / period
        std  = (sum((x - mean)**2 for x in seg) / period) ** 0.5
        if std <= 0:
            return 0.0
        return -(c[t] - mean) / (std_mult * std) * 100  # 低于均值 → 正

    elif template_key == "vol_surge":
        vol_ma_p = int(params.get("vol_ma", 20))
        vols = data.get("volumes", [1.0] * n)
        if t < vol_ma_p:
            return 0.0
        avg_v = sum(vols[t - vol_ma_p: t]) / vol_ma_p
        # 量能放大 → 反转信号（量大 = 分数低）
        return -(float(vols[t]) / avg_v - 1) * 100 if avg_v > 0 else 0.0

    elif template_key in ("mfi_signal", "rvi_signal", "kdwave",
                          "multi_roc_signal", "obos_composite", "elder_ray_signal"):
        # 短期动量倒置（均值回归：涨多了卖，跌多了买）
        lb = max(int(params.get("period", 10)), 5)
        if t < lb:
            return 0.0
        mom = (c[t] / c[t - lb] - 1) * 100 if c[t - lb] > 0 else 0.0
        return -mom  # 均值回归：跌越多分越高

    # ── 创新趋势策略 ───────────────────────────────────────────────

    elif template_key == "smart_money":
        # 主力资金流：OBV加权累计，成交量×涨跌幅 累积判断机构方向
        period = max(int(params.get("period", 20)), 5)
        vol_w  = float(params.get("vol_weight", 1.5))
        vols   = data.get("volumes", [1.0] * n)
        if t < period:
            return 0.0
        avg_vol = sum(float(v or 1) for v in vols[t - period: t]) / period
        if avg_vol <= 0:
            return 0.0
        score = 0.0
        for i in range(t - period, t):
            if i < 1:
                continue
            chg = (c[i] / c[i - 1] - 1) if c[i - 1] > 0 else 0.0
            vol_ratio = float(vols[i] or 1) / avg_vol if avg_vol > 0 else 1.0
            # 放量上涨 = 主力买入；缩量下跌 = 主力控盘
            weight = vol_ratio ** vol_w if chg > 0 else (1.0 / (vol_ratio ** vol_w + 1e-6))
            score += chg * weight
        return score * 100

    elif template_key == "gap_break":
        # 跳空缺口突破：检测向上跳空且缺口未被回补 → 强趋势信号
        min_gap = float(params.get("min_gap_pct", 0.02))
        lookback = max(int(params.get("lookback", 10)), 3)
        lows = data.get("lows", c)
        if t < lookback + 1:
            return 0.0
        best_gap = 0.0
        for i in range(max(1, t - lookback), t):
            # 跳空：当日最低 > 前日最高（简化：当日开盘 > 前日收盘 * (1+gap)）
            if c[i - 1] > 0:
                gap_pct = (float(lows[i]) / c[i - 1] - 1)
                if gap_pct > min_gap:
                    # 检查缺口是否被回补（之后各日最低 > 前日收盘）
                    filled = any(float(lows[j]) < c[i - 1] for j in range(i, t + 1) if j < n)
                    if not filled:
                        # 缺口越新、越大，信号越强
                        recency = (t - i + 1)
                        best_gap = max(best_gap, gap_pct * 100 / recency)
        return best_gap

    elif template_key == "limit_board":
        # 涨停动能：统计 lookback 内近涨停天数，多 = 强趋势
        gain_thr = float(params.get("gain_thr", 0.07))
        lookback = max(int(params.get("lookback", 15)), 5)
        if t < lookback + 1:
            return 0.0
        # 统计近期大涨日，加权（越近权重越高）
        score = 0.0
        for i in range(t - lookback, t):
            if i < 1 or c[i - 1] <= 0:
                continue
            daily_gain = c[i] / c[i - 1] - 1
            if daily_gain >= gain_thr:
                weight = (i - (t - lookback) + 1) / lookback  # 越近权重越高
                score += daily_gain * weight * 100
        # 最近一日没有大涨的话减弱信号
        last_chg = (c[t] / c[t - 1] - 1) if c[t - 1] > 0 else 0.0
        if last_chg < -0.02:
            score *= 0.5
        return score

    elif template_key == "trend_composite":
        # 趋势复合信号：均线 + 动量 + 量能确认，三者一致才出强信号
        ma_fast  = max(int(params.get("ma_fast", 10)), 3)
        ma_slow  = max(int(params.get("ma_slow", 30)), ma_fast + 5)
        mom_p    = max(int(params.get("mom_period", 15)), 5)
        vol_p    = max(int(params.get("vol_period", 20)), 5)
        vols     = data.get("volumes", [1.0] * n)
        if t < max(ma_slow, mom_p, vol_p):
            return 0.0
        # 1. 均线信号
        maf = sum(c[t - ma_fast: t]) / ma_fast
        mas = sum(c[t - ma_slow: t]) / ma_slow
        ma_sig = (maf / mas - 1) * 100 if mas > 0 else 0.0
        # 2. 动量信号
        mom_sig = (c[t] / c[t - mom_p] - 1) * 100 if c[t - mom_p] > 0 else 0.0
        # 3. 量能信号（近期成交量 vs 历史均量）
        avg_vol = sum(float(v or 1) for v in vols[t - vol_p: t]) / vol_p
        recent_vol = float(vols[t] or 1)
        vol_sig = (recent_vol / avg_vol - 1) if avg_vol > 0 else 0.0
        # 三者加权，方向一致时乘以提升系数
        raw = ma_sig * 0.4 + mom_sig * 0.4 + vol_sig * 20 * 0.2
        if ma_sig > 0 and mom_sig > 0 and vol_sig > 0:
            raw *= 1.3  # 三重确认
        elif ma_sig < 0 and mom_sig < 0:
            raw *= 1.2  # 趋势反转确认
        return raw

    # ── 创新均值回归策略 ─────────────────────────────────────────

    elif template_key == "lanban_fade":
        # 烂板反转：检测近期"烂板"（近涨停但收盘大幅回落）后的超卖反弹
        limit_thr   = float(params.get("limit_thr", 0.08))
        fade_days   = max(int(params.get("fade_days", 3)), 1)
        confirm_days= max(int(params.get("confirm_days", 2)), 1)
        highs       = data.get("highs", c)
        if t < fade_days + confirm_days + 2:
            return 0.0
        signal = 0.0
        for i in range(max(1, t - fade_days - confirm_days), t - confirm_days + 1):
            if i < 1 or c[i - 1] <= 0:
                continue
            hi = float(highs[i])
            intraday_high_gain = hi / c[i - 1] - 1
            close_gain         = c[i] / c[i - 1] - 1
            # 烂板条件：盘中近涨停，但收盘回落超过一半涨幅
            if intraday_high_gain >= limit_thr and close_gain < intraday_high_gain * 0.5:
                # 烂板强度：盘中涨幅越大、收盘越低 = 越强的反弹信号
                strength = (intraday_high_gain - close_gain) * 100
                # 距今越近信号越强
                recency_w = 1.0 / (t - i + 1)
                signal += strength * recency_w
        # 若当前价格已经从烂板低点反弹过多，信号衰减
        if signal > 0 and t >= 2:
            recent_gain = (c[t] / c[t - 2] - 1) if c[t - 2] > 0 else 0.0
            if recent_gain > 0.05:
                signal *= 0.5
        return signal

    elif template_key == "vol_price_diverge":
        # 量价背离：价格上涨但成交量萎缩 → 趋势弱，均值回归机会
        lookback    = max(int(params.get("lookback", 20)), 10)
        sensitivity = float(params.get("sensitivity", 1.0))
        vols        = data.get("volumes", [1.0] * n)
        if t < lookback + 1:
            return 0.0
        # 计算价格动量和量能动量
        price_mom = (c[t] / c[t - lookback] - 1) * 100 if c[t - lookback] > 0 else 0.0
        vol_early  = sum(float(v or 1) for v in vols[t - lookback: t - lookback // 2]) / (lookback // 2)
        vol_recent = sum(float(v or 1) for v in vols[t - lookback // 2: t]) / max(lookback // 2, 1)
        vol_trend  = (vol_recent / vol_early - 1) if vol_early > 0 else 0.0
        # 量价背离：价格涨、量能跌 → 做多（均值回归，价格将回落）
        # 量价同步：价格涨、量能也涨 → 不利于均值回归
        diverge_score = -price_mom * sensitivity  # 基础反转
        if price_mom > 0 and vol_trend < -0.1:
            # 涨价缩量：强背离信号
            diverge_score = abs(price_mom) * (1 + abs(vol_trend)) * sensitivity
        elif price_mom < 0 and vol_trend > 0.1:
            # 跌价放量：恐慌抛售后反弹信号
            diverge_score = abs(price_mom) * 0.8 * sensitivity
        return diverge_score

    elif template_key == "multi_signal_combo":
        # 多信号组合：RSI超卖 + 价格近布林下轨 + 成交量放大 → 强均值回归
        rsi_period = max(int(params.get("rsi_period", 14)), 5)
        rsi_lower  = float(params.get("rsi_lower", 35))
        bb_period  = max(int(params.get("bb_period", 20)), 10)
        vol_thr    = float(params.get("vol_surge_thr", 1.5))
        vols       = data.get("volumes", [1.0] * n)
        if t < max(rsi_period, bb_period) + 1:
            return 0.0
        # 1. RSI信号（超卖 → 正分）
        rsi_v = _ind("rsi14", 50.0)
        if rsi_period != 14:
            # 近似计算非14周期RSI
            gains = [max(c[i] - c[i-1], 0) for i in range(t - rsi_period, t) if i >= 1]
            losses= [max(c[i-1] - c[i], 0) for i in range(t - rsi_period, t) if i >= 1]
            avg_g = sum(gains) / rsi_period if gains else 0.0
            avg_l = sum(losses) / rsi_period if losses else 1e-6
            rs = avg_g / avg_l if avg_l > 0 else 100
            rsi_v = 100 - 100 / (1 + rs)
        rsi_sig = max(0.0, rsi_lower - rsi_v) / rsi_lower  # 越超卖分越高

        # 2. 布林带信号（近下轨 → 正分）
        seg  = c[t - bb_period: t]
        mean = sum(seg) / bb_period
        std  = (sum((x - mean)**2 for x in seg) / bb_period) ** 0.5
        bb_sig = max(0.0, -(c[t] - mean) / (2.0 * std + 1e-6))  # 低于均线正值

        # 3. 成交量信号（放量 → 确认反转）
        avg_vol = sum(float(v or 1) for v in vols[t - bb_period: t]) / bb_period
        cur_vol = float(vols[t] or 1)
        vol_sig = min(cur_vol / avg_vol / vol_thr, 2.0) if avg_vol > 0 else 1.0

        # 三者组合（AND逻辑加权）
        combo = (rsi_sig * 40 + bb_sig * 40) * (0.5 + 0.5 * vol_sig)
        return combo

    elif template_key == "mean_rev_composite":
        # 均值回归复合：Z-Score偏离 + 动量反转 + 成交量确认
        period  = max(int(params.get("period", 20)), 10)
        z_enter = float(params.get("z_enter", 1.5))
        z_exit  = float(params.get("z_exit", 0.5))
        if t < period + 1:
            return 0.0
        seg  = c[t - period: t]
        mean = sum(seg) / period
        std  = (sum((x - mean)**2 for x in seg) / period) ** 0.5
        if std <= 0:
            return 0.0
        z = (c[t] - mean) / std  # Z-Score
        # 超卖（z < -z_enter）→ 强正信号；超买（z > z_enter）→ 强负信号
        if abs(z) < z_exit:
            return 0.0  # 在均值附近，无信号
        signal = -z  # 反转：z负→正分，z正→负分
        # 动量反转确认：如果近2天开始反弹（方向变化），放大信号
        if t >= 3:
            recent_chg = (c[t] / c[t - 2] - 1) if c[t - 2] > 0 else 0.0
            if z < -z_exit and recent_chg > 0:
                signal *= 1.4  # 超卖后开始反弹
            elif z > z_exit and recent_chg < 0:
                signal *= 1.4
        return signal * 20  # 放大到合理分值范围

    # ── 生成因子插件（自动发现）────────────────────────────────────────
    try:
        from experts.factor_library import GENERATED_FACTORS
        if template_key in GENERATED_FACTORS:
            extensions = data.get("extensions", {})
            return GENERATED_FACTORS[template_key](closes, data, indicators, extensions, params, t)
    except Exception:
        pass

    return 0.0


# ── 权重计算 ──────────────────────────────────────────────────────────
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

    # ── 主入口 ──────────────────────────────────────────────────────
    def run(self, initial_cash: float = 1_000_000.0):
        """
        执行组合回测，返回 BacktestReport。
        策略名格式："{策略名}[N{n}/R{freq}/{method}]"
        """
        from experts.specialists.expert1a_trend import BacktestReport

        pp             = self.pp
        n_stocks       = max(1, int(pp["n_stocks"]))
        rebalance_freq = max(1, int(pp["rebalance_freq"]))
        weight_method  = str(pp["weight_method"])
        max_pos        = float(pp["max_position_pct"])
        template_key   = self.cand.get("template_key", "")
        params         = self.cand.get("params", {})
        strategy_id    = self.cand.get("strategy_id", "")
        base_name      = self.cand.get("strategy_name", template_key)

        # 策略名附加组合配置标记
        strategy_name = (
            f"{base_name}"
            f"[N{n_stocks}/R{rebalance_freq}/{weight_method[0].upper()}]"
        )

        # ── 准备各标的数据 ───────────────────────────────────────
        sym_list       = [sd["symbol"]     for sd in self.symbols_data]
        closes_by_sym  = {sd["symbol"]: [float(c) for c in sd["data"]["closes"]]
                          for sd in self.symbols_data}
        data_by_sym    = {sd["symbol"]: sd["data"]      for sd in self.symbols_data}
        ind_by_sym     = {sd["symbol"]: sd["indicators"] for sd in self.symbols_data}

        # 对齐序列长度（取最短）
        n = min(len(v) for v in closes_by_sym.values())
        if n < 30:
            return BacktestReport(
                strategy_id=strategy_id, strategy_name=strategy_name,
                strategy_type=self.cand.get("strategy_type", "trend"),
            )

        # ── 每日模拟 ────────────────────────────────────────────
        cash: float               = float(initial_cash)
        holdings: Dict[str, float] = {}   # {symbol: shares}
        equity: list              = [cash]
        trades: list              = []    # 每笔平仓的收益率
        daily_rets: list          = []
        last_selected: list       = []

        for t in range(1, n):
            # ── 调仓日 ──────────────────────────────────────────
            if (t - 1) % rebalance_freq == 0:
                # 1. 打分
                scores = {
                    sym: compute_factor_score(
                        closes_by_sym[sym], data_by_sym[sym],
                        ind_by_sym[sym], params, template_key, t,
                    )
                    for sym in sym_list
                }
                # 2. 只选正分标的的 Top-N
                positive = {s: sc for s, sc in scores.items() if sc > 0}
                selected = sorted(positive, key=positive.__getitem__,
                                  reverse=True)[:n_stocks]
                last_selected = selected

                # 3. 目标权重
                target_w = compute_weights(
                    selected, positive, weight_method,
                    closes_by_sym, t, max_pos,
                )

                # 4. 平旧仓（记录交易）
                sell_proceeds = 0.0
                for sym in list(holdings.keys()):
                    shares = holdings.pop(sym)
                    price  = closes_by_sym[sym][t]
                    gross  = shares * price
                    cost   = gross * SELL_COST
                    net    = gross - cost
                    sell_proceeds += net
                    trade_ret = (net - initial_cash * 0) / initial_cash  # relative pnl
                    trades.append(net / initial_cash - 1.0 / max(len(sym_list), 1))
                cash += sell_proceeds

                # 5. 建新仓
                total_eq = cash  # 注意：此时 holdings 已清空
                for sym in selected:
                    w     = target_w.get(sym, 0.0)
                    alloc = total_eq * w
                    price = closes_by_sym[sym][t]
                    if price <= 0 or alloc <= 0:
                        continue
                    cost   = alloc * BUY_COST
                    shares = (alloc - cost) / price
                    cash  -= alloc
                    holdings[sym] = shares

            # ── 当日净值 ────────────────────────────────────────
            port_val = cash + sum(
                holdings[sym] * closes_by_sym[sym][t]
                for sym in holdings
                if t < len(closes_by_sym[sym])
            )
            prev = equity[-1]
            equity.append(port_val)
            daily_rets.append((port_val - prev) / prev if prev > 0 else 0.0)

        return self._build_report(
            strategy_id, strategy_name, params,
            equity, trades, daily_rets, n, initial_cash,
        )

    # ── 统计指标 ────────────────────────────────────────────────────
    def _build_report(self, sid, name, params, equity, trades,
                       daily_rets, n, cash):
        from experts.specialists.expert1a_trend import BacktestReport
        final = float(equity[-1])
        tr    = final / cash - 1
        ann   = (final / cash) ** (252 / max(n - 1, 1)) - 1
        vol   = self._std(daily_rets) * math.sqrt(252) if daily_rets else 0.0
        s     = ann / vol if vol > 0 else 0.0
        sortino_v = self._sortino(daily_rets)
        max_dd_v  = self._max_dd(daily_rets)
        calmar    = ann / (max_dd_v / 100) if max_dd_v > 0 else 0.0
        wins  = [t for t in trades if t > 0]
        loss  = [t for t in trades if t < 0]
        wr    = len(wins) / len(trades) if trades else 0.0
        avg_w = sum(wins) / len(wins) if wins else 0.0
        avg_l = abs(sum(loss) / len(loss)) if loss else 1e-9
        pf    = avg_w / avg_l if avg_l > 1e-9 else 0.0
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
