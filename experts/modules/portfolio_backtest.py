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
        hist = indicators.get("macd_hist", [0.0] * n)
        return float(hist[t]) if t < len(hist) else 0.0

    elif template_key == "momentum":
        lb = int(params.get("lookback", 20))
        if t < lb:
            return 0.0
        return (c[t] / c[t - lb] - 1) * 100 if c[t - lb] > 0 else 0.0

    elif template_key == "adx_trend":
        adx   = indicators.get("adx",       [0.0] * n)
        hist  = indicators.get("macd_hist",  [0.0] * n)
        adx_v = float(adx[t]) if t < len(adx) else 0.0
        direction = 1.0 if (t < len(hist) and hist[t] > 0) else -1.0
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
        rsi = indicators.get("rsi14", [50.0] * n)
        v   = float(rsi[t]) if t < len(rsi) else 50.0
        lower = float(params.get("lower", 30))
        upper = float(params.get("upper", 70))
        mid   = (lower + upper) / 2
        return mid - v  # 超卖时为正，超买时为负

    elif template_key == "bollinger":
        bb_u = indicators.get("bb_upper", [c[t]] * n)
        bb_l = indicators.get("bb_lower", [c[t]] * n)
        bb_m = indicators.get("bb_mid",   [c[t]] * n)
        band = float(bb_u[t]) - float(bb_l[t])
        if band <= 0:
            return 0.0
        return -(c[t] - float(bb_m[t])) / (band / 2) * 100  # 低于中轨 → 正

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
