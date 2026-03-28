"""
backtest_engine.py — 邢不行策略框架 · 统一回测引擎
============================================================
支持：
  - 单标的单策略
  - 多标的批量回测
  - 多策略横向对比
  - 分年统计
"""

import math
from typing import List, Callable, Optional
from datetime import datetime


def backtest_signal(name: str, rows: List[dict],
                    signal_fn: Callable,
                    commission: float = 0.001,
                    slippage: float = 0.0005,
                    initial: float = 1_000_000.0,
                    position_pct: float = 0.98,
                    min_trade_interval: int = 1) -> Optional[dict]:
    """
    统一回测引擎

    参数：
        rows          : [{date, open, high, low, close, volume}]
        signal_fn     : (closes, highs, lows, opens, volumes) → [0/1/-1]
        commission    : 手续费率（双边，默认 0.1%）
        slippage      : 滑点（默认 0.05%）
        initial       : 初始资金
        position_pct  : 每次买入使用资金比例
        min_trade_interval: 最小交易间隔（避免过度交易）
    """
    if len(rows) < 30:
        return None

    closes  = [r["close"]  for r in rows]
    highs   = [r["high"]   for r in rows]
    lows    = [r["low"]    for r in rows]
    opens   = [r["open"]   for r in rows]
    volumes = [r["volume"] for r in rows]

    sigs = signal_fn(closes, highs, lows, opens, volumes)

    cash = initial
    pos  = 0
    entry_px = 0.0
    equity = [initial]
    trades = []
    last_trade_idx = -999
    total_commission = 0.0

    for i in range(1, len(rows)):
        px  = closes[i]
        sig = sigs[i] if i < len(sigs) else 0
        can_trade = (i - last_trade_idx) >= min_trade_interval

        # 买入开多
        if sig == 1 and pos == 0 and can_trade:
            buy_px = px * (1 + slippage)
            spent  = int(cash * position_pct / buy_px)
            comm   = spent * buy_px * commission
            cash  -= spent * buy_px + comm
            total_commission += comm
            pos  = spent
            entry_px = px
            last_trade_idx = i

        # 卖出平多
        elif sig == -1 and pos > 0:
            sell_px = px * (1 - slippage)
            comm    = pos * sell_px * commission
            ret_pct = (sell_px - entry_px) / entry_px
            trades.append({
                "entry": round(entry_px, 4),
                "exit":  round(sell_px, 4),
                "ret":   round(ret_pct, 6),
                "ret_pct": round(ret_pct * 100, 2),
                "date_entry": rows[i - 1]["date"],
                "date_exit":  rows[i]["date"],
            })
            cash += pos * sell_px - comm
            total_commission += comm
            pos = 0

        # 权益曲线（时刻更新）
        equity.append(cash + pos * px)

    final_equity = equity[-1]

    # ── 年化收益率 ──────────────────────────────
    n_days = max(len(rows) - 1, 1)
    ann_return_decimal = (final_equity / initial) ** (365.0 / n_days) - 1
    ann_return_pct = ann_return_decimal * 100

    # ── 年化波动率（权益曲线收益率）──────────────
    daily_rets = [(equity[i] - equity[i-1]) / max(equity[i-1], 1.0)
                  for i in range(1, len(equity))]
    vol_decimal = math.sqrt(
        sum(r*r for r in daily_rets) / max(len(daily_rets), 1) * 365.0
    ) if daily_rets else 0.0

    # ── 夏普比率（权益曲线法，无风险利率=0）──────
    daily_avg_ret = sum(daily_rets) / max(len(daily_rets), 1) if daily_rets else 0
    sharpe = (daily_avg_ret * 365.0 - 0) / (vol_decimal * math.sqrt(365.0)) \
             if vol_decimal > 0 else 0.0

    # ── 最大回撤 ────────────────────────────────
    peak = initial
    mdd_pct = 0.0
    mdd_idx = 0
    peak_idx = 0
    for i, v in enumerate(equity):
        if v > peak:
            peak = v
            peak_idx = i
        dd = (v - peak) / peak
        if dd < mdd_pct:
            mdd_pct = dd
            mdd_idx = i

    # ── 交易统计 ───────────────────────────────
    wins   = [t for t in trades if t["ret"] > 0]
    losses = [t for t in trades if t["ret"] <= 0]
    win_rate = len(wins) / max(len(trades), 1) * 100

    avg_win = sum(t["ret"] for t in wins)   / max(len(wins),   1) if wins   else 0
    avg_loss = sum(t["ret"] for t in losses) / max(len(losses), 1) if losses else 0

    gross_profit = avg_win * len(wins)
    gross_loss   = abs(avg_loss) * len(losses)
    profit_factor = gross_profit / (gross_loss + 1e-12)

    # ── 整理结果 ───────────────────────────────
    return {
        "strategy":          name,
        "symbol":            rows[0].get("symbol", ""),
        "period_days":       len(rows),
        "start":             rows[0]["date"],
        "end":               rows[-1]["date"],
        "initial":           round(initial, 2),
        "final":             round(final_equity, 2),
        "ann_return_pct":    round(ann_return_pct, 2),
        "sharpe":            round(sharpe, 3),
        "max_drawdown_pct":  round(abs(mdd_pct) * 100, 2),
        "total_trades":      len(trades),
        "win_rate_pct":      round(win_rate, 1),
        "profit_factor":     round(profit_factor, 2),
        "avg_win_pct":       round(avg_win  * 100, 2),
        "avg_loss_pct":      round(avg_loss * 100, 2),
        "commission_cost":   round(total_commission, 2),
        "equity_curve":      [round(e, 2) for e in equity],
        "trades":            trades,
        # 辅助字段
        "_vol_annual_decimal": round(vol_decimal, 4),
        "_mdd_date":          rows[mdd_idx]["date"] if mdd_idx > 0 else rows[0]["date"],
        "_peak_date":         rows[peak_idx]["date"] if peak_idx > 0 else rows[0]["date"],
    }


def summary_table(results: List[dict]) -> str:
    """生成横向对比 Markdown 表格"""
    if not results:
        return ""
    header = (
        f"| {'策略':<26} | {'年化':>8} | {'夏普':>6} | "
        f"{'最大回撤':>8} | {'交易次数':>7} | {'胜率':>6} | {'盈亏比':>7} |\n"
    )
    sep = "| " + "─"*26 + " | " + "─"*8 + " | " + "─"*6 + " | " \
        + "─"*8 + " | " + "─"*7 + " | " + "─"*6 + " | " + "─"*7 + " |"
    lines = [header, sep]
    for r in sorted(results, key=lambda x: x["ann_return_pct"], reverse=True):
        bar = "".join("█" if r["ann_return_pct"] > 0 else "▁"
                      for _ in range(min(int(abs(r["ann_return_pct"]) / 5), 10))
                     )[:10]
        lines.append(
            f"| {r['strategy']:<26} "
            f"| {r['ann_return_pct']:>+7.1f}% "
            f"| {r['sharpe']:>6.3f} "
            f"| {r['max_drawdown_pct']:>7.1f}% "
            f"| {r['total_trades']:>7d} "
            f"| {r['win_rate_pct']:>5.1f}% "
            f"| {r['profit_factor']:>7.2f} |"
        )
    return "\n".join(lines)
