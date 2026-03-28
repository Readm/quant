"""
backtest_engine.py — 基于真实数据的回测引擎
支持：真实数据 + 合成数据 + Walk-Forward 验证 + 摩擦成本
"""
import math, random
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Trade:
    entry_px: float; exit_px: float
    entry_idx: int; exit_idx: int
    ret: float; ret_dollar: float
    pnl: float  # 扣除成本后的净利润


@dataclass
class BacktestResult:
    name: str; symbol: str
    ann_ret: float; sharpe: float; max_dd: float
    n_trades: int; win_rate: float
    avg_holding: float
    equity_curve: list[float]
    trades: list[Trade]
    cost_total: float
    adj_ann_ret: float; adj_sharpe: float
    source: str  # "Stooq" or "Synthetic"

    def to_dict(self):
        return {
            "name"        : self.name,
            "symbol"      : self.symbol,
            "ann_ret"    : round(self.ann_ret, 2),
            "adj_ann_ret": round(self.adj_ann_ret, 2),
            "sharpe"     : round(self.sharpe, 3),
            "adj_sharpe" : round(self.adj_sharpe, 3),
            "max_dd"     : round(self.max_dd, 2),
            "n_trades"   : self.n_trades,
            "win_rate"   : round(self.win_rate * 100, 1),
            "cost_total" : round(self.cost_total, 0),
            "avg_holding": round(self.avg_holding, 1),
            "equity_final": round(self.equity_curve[-1], 2) if self.equity_curve else 0,
            "source"     : self.source,
        }


class BacktestEngine:
    """
    统一回测引擎。
    支持任何 signal_func(data, params) -> [0,0,1,-1,0,...] 的策略。
    """

    def __init__(self, initial_capital: float = 1_000_000.0,
                 commission: float = 0.04,   # % 单边
                 spread_bps: float = 20,    # 基点（买卖双边）
                 stamp_tax: float = 0.0,    # 印花税（卖出时）
                 slippage_bps: float = 5):  # 滑点
        self.initial  = initial_capital
        self.commission  = commission / 100   # → 小数
        self.spread_bps  = spread_bps / 10000
        self.stamp       = stamp_tax / 100
        self.slippage    = slippage_bps / 10000

    def run(self, name: str, symbol: str,
            closes: list, dates: list,
            signal_fn: Callable, params: dict,
            source: str = "Unknown") -> BacktestResult:
        """
        参数：
          signal_fn: (closes, params) -> [0/1/-1, ...]
                     1=买入, -1=卖出, 0=持有
          dates/closes: 真实或合成数据
        """
        n = len(closes)
        if n < 20:
            raise ValueError(f"数据太短: {n}天")

        sig = signal_fn(closes, params)
        if len(sig) != n:
            raise ValueError(f"signal长度{n} != 数据长度{len(sig)}")

        # ── 模拟交易 ──────────────────────────────────────────
        cash = self.initial; pos = 0
        entry_px = 0.0; entry_idx = 0
        equity = [self.initial]
        trades: list[Trade] = []
        cost_total = 0.0

        for i in range(1, n):
            px = closes[i]
            # 滑点后的实际成交价
            slip = px * self.slippage

            if sig[i] == 1 and pos == 0:
                # 买入（滑点不利方向）
                cost = px * (1 + self.slippage)
                pos = int(cash * 0.98 / cost)  # 预留手续费
                cost_per = cost * pos
                comm = cost_per * self.commission
                total_cost = comm + cost_per * self.spread_bps * 2
                cash -= cost_per + total_cost
                cost_total += total_cost
                entry_px = px; entry_idx = i

            elif sig[i] == -1 and pos > 0:
                # 卖出（滑点不利方向）
                proceeds = px * (1 - self.slippage)
                comm = proceeds * self.commission
                stamp = proceeds * self.stamp
                total_cost = comm + stamp + proceeds * self.spread_bps * 2
                net = proceeds * pos - total_cost
                ret = (px - entry_px) / entry_px
                pnl = cash + net - self.initial
                cash += net
                trades.append(Trade(
                    entry_px=entry_px, exit_px=px,
                    entry_idx=entry_idx, exit_idx=i,
                    ret=round(ret * 100, 2),
                    ret_dollar=round(pnl, 0),
                    pnl=round(pnl, 0),
                ))
                pos = 0

            elif pos > 0:
                pass  # 持有

            equity.append(cash + pos * px)

        # ── 止盈/止损（可选）───────────────────────────────
        # 当前版本：不加额外止盈止损，策略逻辑内嵌

        # ── 统计数据 ─────────────────────────────────────────
        final_eq = equity[-1]
        ann_ret = ((final_eq / self.initial) ** (252 / max(n - 1, 1)) - 1) * 100

        # 收益序列
        rets_seq = [(equity[i] - equity[i - 1]) / equity[i - 1]
                    for i in range(1, len(equity))]
        vol = math.sqrt(sum(r * r for r in rets_seq) / max(len(rets_seq), 1)) * math.sqrt(252)
        sharpe = ann_ret / vol if vol > 0 else 0.0

        # 最大回撤
        peak = self.initial; max_dd = 0.0
        for v in equity:
            if v > peak: peak = v
            dd = (v - peak) / peak
            if dd < max_dd: max_dd = dd
        max_dd = abs(max_dd) * 100

        # 交易统计
        wins = [t for t in trades if t.ret > 0]
        win_rate = len(wins) / len(trades) if trades else 0.0
        avg_hold = sum(t.exit_idx - t.entry_idx for t in trades) / max(len(trades), 1)

        # 含成本调整后收益
        adj_ret = ann_ret - (cost_total / self.initial) * 100
        adj_sharpe = adj_ret / vol if vol > 0 else 0.0

        return BacktestResult(
            name=name, symbol=symbol,
            ann_ret=round(ann_ret, 2), sharpe=round(sharpe, 3),
            max_dd=round(max_dd, 2),
            n_trades=len(trades), win_rate=win_rate,
            avg_holding=avg_hold,
            equity_curve=equity,
            trades=trades,
            cost_total=round(cost_total, 0),
            adj_ann_ret=round(adj_ret, 2),
            adj_sharpe=round(adj_sharpe, 3),
            source=source,
        )


# ── 标准信号函数库 ─────────────────────────────────────────────

def ma_cross_signal(closes, params):
    """双均线交叉信号"""
    fp = params.get("fast", 20); sp = params.get("slow", 60)
    n = len(closes)
    if n < sp: return [0] * n

    def ma(p):
        out = [0.0] * n
        for i in range(p - 1, n):
            out[i] = sum(closes[i - p + 1:i + 1]) / p
        return out

    m1 = ma(fp); m2 = ma(sp)
    sig = [0] * n
    for i in range(sp, n):
        if m1[i] > m2[i] and m1[i - 1] <= m2[i - 1]:
            sig[i] = 1
        elif m1[i] < m2[i] and m1[i - 1] >= m2[i - 1]:
            sig[i] = -1
    return sig


def rsi_signal(closes, params):
    """RSI 均值回归信号"""
    p = params.get("period", 14)
    lo = params.get("lo", 30); hi = params.get("hi", 70)
    n = len(closes)
    if n < p: return [0] * n

    def rsi(p):
        out = [50.0] * n
        for i in range(p, n):
            gains  = max(0.0, closes[i] - closes[i - 1])
            losses = max(0.0, closes[i - 1] - closes[i])
            ag = sum(max(0, closes[j] - closes[j - 1]) for j in range(p, i + 1)) / p
            al = sum(max(0, closes[j - 1] - closes[j]) for j in range(p, i + 1)) / p
            out[i] = 100 - 100 / (1 + ag / (al + 1e-9))
        return out

    rv = rsi(p)
    sig = [0] * n
    for i in range(p, n):
        if rv[i - 1] < lo and rv[i] >= lo:
            sig[i] = 1   # 超卖 → 买入
        elif rv[i - 1] > hi and rv[i] <= hi:
            sig[i] = -1  # 超买 → 卖出
    return sig


def macd_signal(closes, params):
    """MACD 趋势信号"""
    n = len(closes)
    if n < 26: return [0] * n

    def ema(p):
        k = 2 / (p + 1)
        out = [closes[0]] * n
        for i in range(1, n):
            out[i] = closes[i] * k + out[i - 1] * (1 - k)
        return out

    e12 = ema(12); e26 = ema(26)
    macd = [0.0] * n
    for i in range(26, n): macd[i] = e12[i] - e26[i]

    k = 2 / (9 + 1)
    sig_line = [macd[0]] * n
    for i in range(9, n):
        sig_line[i] = macd[i] * k + sig_line[i - 1] * (1 - k)

    sig = [0] * n
    for i in range(26, n):
        if macd[i] > sig_line[i] and macd[i - 1] <= sig_line[i - 1]:
            sig[i] = 1
        elif macd[i] < sig_line[i] and macd[i - 1] >= sig_line[i - 1]:
            sig[i] = -1
    return sig


def bollinger_signal(closes, params):
    """布林带均值回归信号"""
    p = params.get("period", 20); mult = params.get("std_mult", 2.0)
    n = len(closes)
    if n < p: return [0] * n

    def ma(p):
        out = [0.0] * n
        for i in range(p - 1, n):
            out[i] = sum(closes[i - p + 1:i + 1]) / p
        return out

    mid = ma(p)
    upper = [0.0] * n; lower = [0.0] * n
    for i in range(p - 1, n):
        vals = closes[i - p + 1:i + 1]
        std = math.sqrt(sum((v - mid[i]) ** 2 for v in vals) / p)
        upper[i] = mid[i] + mult * std
        lower[i] = mid[i] - mult * std

    sig = [0] * n
    for i in range(p, n):
        if closes[i] < lower[i] and closes[i - 1] >= lower[i]:
            sig[i] = 1   # 价格突破下轨 → 买入
        elif closes[i] > upper[i] and closes[i - 1] <= upper[i]:
            sig[i] = -1  # 价格突破上轨 → 卖出
    return sig


def volatility_breakout_signal(closes, params):
    """波动率突破信号（ATR 确认）"""
    p = params.get("period", 20); mult = params.get("mult", 1.5)
    n = len(closes)
    if n < p + 1: return [0] * n

    highs = closes; lows = closes  # 简化：无高低数据用收盘价

    def atr(p):
        trs = [0.0] * n
        for i in range(1, n):
            tr = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i - 1]),
                     abs(lows[i]  - closes[i - 1]))
            trs[i] = tr
        out = [trs[0]] * n
        for i in range(p, n):
            out[i] = sum(trs[i - p + 1:i + 1]) / p
        return out

    atr_vals = atr(p)
    recent_high = [0.0] * n
    for i in range(p, n):
        recent_high[i] = max(closes[i - p + 1:i + 1])

    sig = [0] * n
    for i in range(p, n):
        threshold = recent_high[i] + mult * atr_vals[i]
        if closes[i] > threshold:
            sig[i] = 1
        elif closes[i] < recent_high[i] - mult * atr_vals[i]:
            sig[i] = -1
    return sig


# ── Walk-Forward 验证 ────────────────────────────────────────────

def walk_forward_validate(
    closes: list,
    dates: list,
    signal_fn: Callable,
    params: dict,
    initial: float = 1_000_000.0,
    n_train: int = 180,
    n_test: int = 60,
) -> dict:
    """
    Walk-Forward 验证：在多个真实历史窗口测试策略。
    返回：{n_windows, avg_test_sharpe, std_sharpe, decay_ratio, results[]}
    """
    n = len(closes)
    engine = BacktestEngine(initial_capital=initial)
    windows = []
    cursor = n

    while True:
        te = cursor
        ts = max(n_train + n_test, cursor - n_test)
        tr = max(0, ts - n_train)
        if ts - tr < n_train or te - ts < 30:
            break
        tc = closes[tr:ts]; ec = closes[ts:te]
        td = dates[ts:te]
        if len(ec) < 30:
            break

        r_train = engine.run("train", "WF", tc, td[:len(tc)],
                             signal_fn, params, source="Train")
        r_test  = engine.run("test",  "WF", ec, td,
                             signal_fn, params, source="Test")

        decay = r_test.sharpe / abs(r_train.sharpe) if r_train.sharpe != 0 else 0
        windows.append({
            "train_sharpe": r_train.sharpe,
            "test_sharpe" : r_test.sharpe,
            "train_ret"   : r_train.ann_ret,
            "test_ret"    : r_test.adj_ann_ret,
            "decay"       : round(decay, 3),
            "verdict"     : "PASS" if decay >= 0.5 and r_test.sharpe > 0.3 else "FAIL",
        })
        cursor = ts
        if cursor < n_train + n_test * 2:
            break

    if not windows:
        return {"n_windows": 0}

    avg_decay = sum(w["decay"] for w in windows) / len(windows)
    test_sharpes = [w["test_sharpe"] for w in windows]
    avg_ts = sum(test_sharpes) / len(test_sharpes)
    std_ts = math.sqrt(sum((s - avg_ts) ** 2 for s in test_sharpes) / len(test_sharpes))
    cv = std_ts / abs(avg_ts) if avg_ts != 0 else 0

    verdicts = [w["verdict"] for w in windows]
    pass_count = verdicts.count("PASS")
    overall = "PASS" if pass_count >= len(windows) * 0.6 else "WEAK" if pass_count >= 1 else "FAIL"

    return {
        "n_windows"      : len(windows),
        "avg_test_sharpe": round(avg_ts, 3),
        "std_sharpe"    : round(std_ts, 3),
        "sharpe_cv"     : round(cv, 3),        # <0.3 = 稳定
        "avg_decay"     : round(avg_decay, 3), # >0.5 = 稳健
        "overall"       : overall,
        "pass_rate"     : round(pass_count / len(windows), 2),
        "windows"       : windows,
    }


# ── 报告打印 ────────────────────────────────────────────────────

def print_bt_result(r: BacktestResult, wf: dict = None):
    icon = "✅" if r.adj_sharpe > 0.5 else ("⚠️" if r.adj_sharpe > 0.1 else "❌")
    print(f"  {icon} {r.name}（{r.source}）")
    print(f"      年化收益：{r.ann_ret:>+8.1f}%  → 摩擦后 {r.adj_ann_ret:>+8.1f}%")
    print(f"      夏普比率：{r.sharpe:>8.3f}  → 摩擦后 {r.adj_sharpe:>8.3f}")
    print(f"      最大回撤：{r.max_dd:>8.1f}%   交易次数：{r.n_trades:>4}次")
    print(f"      胜率：{r.win_rate*100:>5.1f}%    平均持仓：{r.avg_holding:>5.1f}天")
    print(f"      总成本：{r.cost_total:>10,.0f}元")
    if wf:
        w = wf
        ico = "✅" if w["overall"] == "PASS" else ("⚠️" if w["overall"] == "WEAK" else "❌")
        print(f"      Walk-Forward: {w['n_windows']}窗口 平均退化={w['avg_decay']:.0%} "
              f"CV={w['sharpe_cv']:.2f} {ico}{w['overall']}")
        for i, win in enumerate(wf.get("windows", [])[:3], 1):
            v = "✅" if win["verdict"] == "PASS" else "❌"
            print(f"        窗口{i}: 训练夏普={win['train_sharpe']:.3f} "
                  f"测试夏普={win['test_sharpe']:.3f} 退化={win['decay']:.0%} {v}{win['verdict']}")


def print_multi_result(results: list[BacktestResult], wf_results: dict):
    """打印多策略对比报告"""
    print(f"\n{'='*70}")
    print(f"  📊 多策略回测报告（含 Walk-Forward 验证）")
    print(f"{'='*70}")
    print(f"\n  {'策略':<22} {'来源':<10} {'年化(摩擦后)':>12} "
          f"{'夏普(摩擦后)':>12} {'回撤':>7} {'WF裁决'}")
    print(f"  {'─'*65}")

    for r in results:
        icon = "✅" if r.adj_sharpe > 0.5 else ("⚠️" if r.adj_sharpe > 0.1 else "❌")
        wf = wf_results.get(r.name, {})
        wf_icon = {"PASS":"✅PASS","WEAK":"⚠️WEAK","FAIL":"❌FAIL"}.get(wf.get("overall",""),"  —")
        print(f"  {icon}{r.name:<20} {r.source:<10} "
              f"{r.adj_ann_ret:>+11.1f}% {r.adj_sharpe:>+11.3f} "
              f"{r.max_dd:>6.1f}%  {wf_icon}")

    print(f"{'='*70}")
