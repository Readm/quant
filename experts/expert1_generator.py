"""
expert1_generator.py — 策略生成专家（纯Python版，无外部依赖）
"""

import uuid, random, math
from dataclasses import dataclass
from typing import Optional


# ─────────────────────────────────────────────
#  BacktestReport
# ─────────────────────────────────────────────

@dataclass
class BacktestReport:
    strategy_id: str
    strategy_name: str
    tags: list
    params: dict

    total_return:    float = 0.0
    sharpe_ratio:    float = 0.0
    max_drawdown_pct: float = 0.0
    annualized_return: float = 0.0
    volatility:       float = 0.0
    total_trades:     int   = 0
    win_rate:         float = 0.0
    profit_factor:    float = 0.0
    avg_holding_days: float = 0.0
    calmar_ratio:     float = 0.0
    sortino_ratio:    float = 0.0
    daily_returns:    list  = None

    def __post_init__(self):
        if self.daily_returns is None:
            self.daily_returns = []


# ─────────────────────────────────────────────
#  工具函数
# ─────────────────────────────────────────────

def ma(closes: list, period: int) -> list:
    n = len(closes)
    out = [0.0] * n
    for i in range(period - 1, n):
        out[i] = sum(closes[i - period + 1:i + 1]) / period
    return out

def rsi(closes: list, period: int) -> list:
    n = len(closes)
    out = [50.0] * n
    for i in range(period, n):
        gains = [closes[i] - closes[i-1] for i in range(period, i+1)
                 if closes[i] - closes[i-1] > 0]
        losses = [- (closes[i] - closes[i-1]) for i in range(period, i+1)
                  if closes[i] - closes[i-1] < 0]
        avg_gain = sum(gains) / period if gains else 0.0
        avg_loss = sum(losses) / period if losses else 1e-9
        rs = avg_gain / avg_loss
        out[i] = 100 - 100 / (1 + rs)
    return out

def ema(closes: list, period: int) -> list:
    n = len(closes)
    k = 2 / (period + 1)
    out = [closes[0]] * n
    for i in range(1, n):
        out[i] = closes[i] * k + out[i-1] * (1 - k)
    return out

def macd(closes: list, fast=12, slow=26, signal=9):
    ef = ema(closes, fast)
    es = ema(closes, slow)
    macd_line = [ef[i] - es[i] for i in range(len(closes))]
    sig = ema(macd_line, signal)
    return macd_line, sig

def std(values: list) -> float:
    n = len(values)
    if n < 2: return 0.0
    m = sum(values) / n
    return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))

def sortino(daily_returns: list, target=0.0) -> float:
    downside = [r - target for r in daily_returns if r < target]
    if not downside: return 0.0
    down_std = std(downside) * math.sqrt(252)
    ann = sum(daily_returns) / len(daily_returns) * 252
    return ann / (down_std + 1e-9)

def max_drawdown_from_returns(daily_returns: list) -> float:
    """返回最大回撤百分比"""
    if not daily_returns: return 0.0
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in daily_returns:
        equity *= (1 + r)
        if equity > peak:
            peak = equity
        dd = (equity - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return abs(max_dd) * 100


# ─────────────────────────────────────────────
#  策略模板库
# ─────────────────────────────────────────────

TEMPLATES = {
    "ma_cross": {
        "name": "双均线交叉策略",
        "params": [
            ("fast_period", 5,  60, 20),
            ("slow_period",20, 200, 60),
        ],
    },
    "rsi_reversion": {
        "name": "RSI均值回归策略",
        "params": [
            ("rsi_period",  7, 30, 14),
            ("lower_bound",20, 50, 30),
            ("upper_bound",50, 80, 70),
        ],
    },
    "macd_trend": {
        "name": "MACD趋势策略",
        "params": [
            ("fast_period",  8, 20, 12),
            ("slow_period", 16, 40, 26),
            ("signal_period",5, 15,  9),
        ],
    },
    "volatility_breakout": {
        "name": "波动率突破策略",
        "params": [
            ("window", 10, 60, 30),
            ("mult",   1.5, 4.0, 2.0),
        ],
    },
    "bollinger_breakout": {
        "name": "布林带突破策略",
        "params": [
            ("bb_period", 10, 40, 20),
            ("bb_std",    1.5, 4.0, 2.0),
        ],
    },
    "momentum": {
        "name": "动量策略",
        "params": [
            ("lookback", 10, 60, 20),
            ("threshold",0.03, 0.12, 0.05),
        ],
    },
}


# ─────────────────────────────────────────────
#  信号计算
# ─────────────────────────────────────────────

def compute_signals(name: str, params: dict, closes: list,
                    highs: list, lows: list) -> list:
    n = len(closes)
    signals = [0] * n

    if "均线" in name:
        fp = params.get("fast_period", 20)
        sp = params.get("slow_period", 60)
        if n <= sp: return signals
        ma_f = ma(closes, fp)
        ma_s = ma(closes, sp)
        for i in range(sp, n):
            if ma_f[i] > ma_s[i] and ma_f[i-1] <= ma_s[i-1]:
                signals[i] = 1
            elif ma_f[i] < ma_s[i] and ma_f[i-1] >= ma_s[i-1]:
                signals[i] = -1

    elif "RSI" in name:
        period = int(params.get("rsi_period", 14))
        lower  = int(params.get("lower_bound", 30))
        upper  = int(params.get("upper_bound", 70))
        if n <= period: return signals
        rsi_vals = rsi(closes, period)
        for i in range(period, n):
            if rsi_vals[i-1] < lower and rsi_vals[i] >= lower:
                signals[i] = 1
            elif rsi_vals[i-1] > upper and rsi_vals[i] <= upper:
                signals[i] = -1

    elif "MACD" in name:
        fp = int(params.get("fast_period", 12))
        sp = int(params.get("slow_period", 26))
        sig = int(params.get("signal_period", 9))
        if n <= sp + sig: return signals
        macd_l, sig_l = macd(closes, fp, sp, sig)
        for i in range(sp + sig, n):
            if macd_l[i] > sig_l[i] and macd_l[i-1] <= sig_l[i-1]:
                signals[i] = 1
            elif macd_l[i] < sig_l[i] and macd_l[i-1] >= sig_l[i-1]:
                signals[i] = -1

    elif "波动率" in name:
        window = int(params.get("window", 30))
        mult   = params.get("mult", 2.0)
        if n <= window: return signals
        for i in range(window, n):
            h_range = max(highs[i-window:i+1]) - min(lows[i-window:i+1])
            upper = closes[i-window] + mult * h_range
            lower = closes[i-window] - mult * h_range
            if closes[i-1] <= upper and closes[i] > upper:
                signals[i] = 1
            elif closes[i-1] >= lower and closes[i] < lower:
                signals[i] = -1

    elif "布林" in name:
        period = int(params.get("bb_period", 20))
        std_n  = params.get("bb_std", 2.0)
        if n <= period: return signals
        for i in range(period, n):
            mid = sum(closes[i-period+1:i+1]) / period
            s   = std(closes[i-period+1:i+1])
            upper = mid + std_n * s
            lower = mid - std_n * s
            if closes[i-1] < upper and closes[i] >= upper:
                signals[i] = 1
            elif closes[i-1] > lower and closes[i] <= lower:
                signals[i] = -1

    elif "动量" in name:
        lookback = int(params.get("lookback", 20))
        thr      = params.get("threshold", 0.05)
        if n <= lookback: return signals
        for i in range(lookback, n):
            ret = (closes[i] - closes[i-lookback]) / closes[i-lookback]
            if ret > thr:
                signals[i] = 1
            elif ret < -thr:
                signals[i] = -1

    else:
        # 默认：简单均线斜率
        if n >= 20:
            ma20 = ma(closes, 20)
            for i in range(20, n):
                slope = (ma20[i] - ma20[i-5]) / ma20[i-5]
                if slope > 0.01:
                    signals[i] = 1
                elif slope < -0.01:
                    signals[i] = -1

    return signals


# ─────────────────────────────────────────────
#  单次回测
# ─────────────────────────────────────────────

def backtest(strategy_name: str, params: dict, closes: list,
             highs: list, lows: list, initial_cash: float = 1_000_000.0) -> BacktestReport:
    n = len(closes)
    if n < 60:
        return BacktestReport(strategy_id="", strategy_name=strategy_name,
                              tags=[], params=params, total_trades=0)

    signals = compute_signals(strategy_name, params, closes, highs, lows)

    cash      = initial_cash
    position  = 0
    entry_px  = 0.0
    entries   = []
    trades    = []
    equity    = [initial_cash]
    daily_rets = []

    for i in range(1, n):
        price = closes[i]
        signal= signals[i]
        pos_v = cash + position * price

        # 入场
        if signal == 1 and position == 0:
            position   = int(cash * 0.95 / price)
            entry_px   = price
            cash      -= position * price
            entries.append({"entry_px": entry_px, "holding": 0})
        # 持仓计数
        if position > 0 and entries:
            entries[-1]["holding"] += 1
        # 出场
        should_exit = False
        exit_reason = ""
        if signal == -1 and position > 0:
            should_exit = True; exit_reason = "信号平仓"
        elif position > 0 and entry_px > 0:
            if (entry_px - price) / entry_px > 0.09:
                should_exit = True; exit_reason = "止损-9%"
            elif (entry_px - price) / entry_px > 0.05 and "RSI" in strategy_name:
                should_exit = True; exit_reason = "RSI超卖"

        if should_exit:
            cash += position * price
            ret = (price - entry_px) / entry_px
            if entries:
                entries[-1].update({"exit_px": price, "ret": ret})
            trades.append(ret)
            position = 0; entry_px = 0.0

        eq = cash + position * price
        equity.append(eq)
        if i > 1:
            daily_rets.append((eq - equity[i-1]) / equity[i-1])

    # 最终结算
    final_eq = cash + position * closes[-1]
    total_ret = (final_eq - initial_cash) / initial_cash

    ann_ret = ((final_eq / initial_cash) ** (252 / (n - 1)) - 1) if n > 1 else 0.0
    vol     = std(daily_rets) * math.sqrt(252) if daily_rets else 0.0
    sharpe  = ann_ret / vol if vol > 0 else 0.0
    sortino_v = sortino(daily_rets)
    max_dd_pct = max_drawdown_from_returns(daily_rets)
    calmar   = ann_ret / (max_dd_pct / 100) if max_dd_pct > 0 else 0.0

    wins = [t for t in trades if t > 0]
    loss = [t for t in trades if t < 0]
    win_rate = len(wins) / len(trades) if trades else 0.0
    avg_win  = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(loss) / len(loss)) if loss else 1.0
    pf       = avg_win / avg_loss if avg_loss > 0 else 0.0
    avg_hold = sum(e.get("holding", 0) for e in entries) / len(entries) if entries else 0.0

    return BacktestReport(
        strategy_id     = "",
        strategy_name   = strategy_name,
        tags            = [strategy_name],
        params          = params,
        total_return    = round(total_ret * 100, 2),
        sharpe_ratio    = round(sharpe, 3),
        max_drawdown_pct= round(max_dd_pct, 2),
        annualized_return = round(ann_ret * 100, 2),
        volatility      = round(vol * 100, 2),
        total_trades    = len(trades),
        win_rate        = round(win_rate * 100, 2),
        profit_factor   = round(pf, 2),
        avg_holding_days= round(avg_hold, 1),
        calmar_ratio    = round(calmar, 3),
        sortino_ratio   = round(sortino_v, 3),
        daily_returns   = [round(r, 4) for r in daily_rets],
    )


# ─────────────────────────────────────────────
#  候选生成
# ─────────────────────────────────────────────

def generate_candidates(count: int = 6,
                        market: str = "stocks",
                        feedback: list = None) -> list:
    """返回 [(name, params, tags)] 列表"""
    keys = list(TEMPLATES.keys())
    candidates = []
    for i in range(count):
        fb_item = (feedback[i] if feedback and i < len(feedback) else {}) or {}
        fb_type = fb_item.get("feedback_type", "")

        # 根据反馈选择模板
        if "均线" in fb_type:   tkey = "ma_cross"
        elif "RSI" in fb_type:  tkey = "rsi_reversion"
        elif "MACD" in fb_type: tkey = "macd_trend"
        elif "波动" in fb_type: tkey = "volatility_breakout"
        elif "布林" in fb_type: tkey = "bollinger_breakout"
        else:                   tkey = keys[i % len(keys)]

        tpl = TEMPLATES[tkey]
        params = {}
        for pname, lo, hi, default in tpl["params"]:
            if random.random() < 0.67:
                params[pname] = default
            else:
                if isinstance(default, int):
                    params[pname] = random.randint(lo, hi)
                else:
                    params[pname] = round(random.uniform(lo, hi), 2)

        candidates.append({
            "name"  : tpl["name"],
            "params": params,
            "tags"  : [tpl["name"], market],
            "id"    : f"strat_{uuid.uuid4().hex[:8]}",
        })
    return candidates


# ─────────────────────────────────────────────
#  单轮迭代（Expert1主流程）
# ─────────────────────────────────────────────

def run_iteration(symbols_data: list, feedback: list = None) -> dict:
    """
    symbols_data: list of (symbol_name, closes, highs, lows)
    返回: {round, candidates, reports, passed, rejected}
    """
    candidates = generate_candidates(count=6, feedback=feedback)
    reports = []

    for cand in candidates:
        all_metrics = []
        for sym_name, closes, highs, lows in symbols_data:
            rpt = backtest(cand["name"], cand["params"], closes, highs, lows)
            all_metrics.append(rpt)

        # 聚合（平均）
        valid = [r for r in all_metrics if r.total_trades > 0]
        if not valid:
            continue

        def avg_field(field_name, vals_list=None):
            if vals_list is None:
                vals_list = [r.__dict__[field_name] for r in valid]
            return round(sum(vals_list) / len(vals_list), 3)

        import copy
        base = copy.copy(valid[0])
        base.strategy_id = cand["id"]
        base.strategy_name = cand["name"]
        base.tags = cand["tags"]
        base.params = cand["params"]
        base.total_return     = avg_field("total_return")
        base.sharpe_ratio     = avg_field("sharpe_ratio")
        base.max_drawdown_pct = avg_field("max_drawdown_pct")
        base.annualized_return= avg_field("annualized_return")
        base.volatility       = avg_field("volatility")
        base.total_trades     = int(avg_field("total_trades"))
        base.win_rate         = avg_field("win_rate")
        base.profit_factor    = avg_field("profit_factor")
        base.avg_holding_days = avg_field("avg_holding_days")
        base.calmar_ratio     = avg_field("calmar_ratio")
        base.sortino_ratio    = avg_field("sortino_ratio")
        reports.append(base)

    passed   = [r for r in reports if r.total_trades >= 3]
    rejected = [r for r in reports if r.total_trades < 3]

    return {
        "candidates": candidates,
        "reports"   : reports,
        "passed"    : passed,
        "rejected"  : rejected,
    }
