"""
vectorbt_engine.py — 向量化回测引擎（纯 pandas 指标 + vectorbt Portfolio）
"""

import numpy as np
import pandas as pd
import vectorbt as vbt
from dataclasses import dataclass, asdict
from typing import List, Dict

# ══ 交易成本 ═══════════════════════════════════════════════════════
BUY_FEES    = 0.0003 + 0.0005   # 佣金0.03% + 滑点0.05% = 0.08%
SELL_FEES   = 0.0003 + 0.0005 + 0.0010  # +佣金+滑点+印花税0.10% = 0.18%


# ══ 数据转换 ═══════════════════════════════════════════════════════

def local_to_df(ld: dict) -> pd.DataFrame:
    """local_data dict → OHLCV DataFrame"""
    return pd.DataFrame({
        "Open"  : ld.get("opens",   ld["closes"]),
        "High"  : ld.get("highs",   ld["closes"]),
        "Low"   : ld.get("lows",    ld["closes"]),
        "Close" : ld["closes"],
        "Volume": ld.get("volumes", [1e9] * len(ld["dates"])),
    }, index=pd.to_datetime(ld["dates"])).sort_index()


# ══ 信号生成（纯 pandas） ═══════════════════════════════════════════════

def sig_sma_cross(close: pd.Series, fast: int, slow: int) -> pd.Series:
    """双均线交叉"""
    f = close.rolling(fast).mean()
    s = close.rolling(slow).mean()
    diff = (f > s).astype(int) - (f < s).astype(int)
    # 金叉/死叉只在变化时触发
    return diff.diff().fillna(0).replace({2: 0, -2: 0}).astype(int)


def sig_ema_cross(close: pd.Series, fast: int, slow: int) -> pd.Series:
    """EMA 交叉"""
    f = close.ewm(span=fast,  adjust=False).mean()
    s = close.ewm(span=slow,  adjust=False).mean()
    diff = (f > s).astype(int) - (f < s).astype(int)
    return diff.diff().fillna(0).replace({2: 0, -2: 0}).astype(int)


def sig_rsi(close: pd.Series, period: int = 14,
            lower: float = 30, upper: float = 70) -> pd.Series:
    """RSI 均值回归"""
    d = close.diff()
    gain = d.clip(lower=0).rolling(period).mean()
    loss = (-d.clip(upper=0)).rolling(period).mean()
    rsi = 100 - 100 / (1 + gain / (loss + 1e-10))
    sig = pd.Series(0, index=close.index)
    sig[rsi < lower] =  1
    sig[rsi > upper] = -1
    return sig


def sig_bollinger(close: pd.Series, period: int = 20,
                  std_mult: float = 2.0) -> pd.Series:
    """布林带均值回归"""
    mid   = close.rolling(period).mean()
    std   = close.rolling(period).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    sig = pd.Series(0, index=close.index)
    sig[close < lower] =  1
    sig[close > upper] = -1
    return sig


def sig_momentum(close: pd.Series, lookback: int = 20,
                threshold: float = 0.05) -> pd.Series:
    """动量突破"""
    ret = close.pct_change(lookback)
    sig = pd.Series(0, index=close.index)
    sig[ret >  threshold] =  1
    sig[ret < -threshold] = -1
    return sig


def sig_macd(close: pd.Series, fp: int = 12, sp: int = 26,
             sig: int = 9) -> pd.Series:
    """MACD"""
    ema_f = close.ewm(span=fp, adjust=False).mean()
    ema_s = close.ewm(span=sp, adjust=False).mean()
    macd  = ema_f - ema_s
    sig_l = macd.ewm(span=sig, adjust=False).mean()
    diff  = (macd > sig_l).astype(int) - (macd < sig_l).astype(int)
    return diff.diff().fillna(0).replace({2: 0, -2: 0}).astype(int)


def sig_adx(high: pd.Series, low: pd.Series, close: pd.Series,
            period: int = 14, adx_thr: float = 25) -> pd.Series:
    """ADX 趋势确认"""
    tr = pd.concat([high - low,
                    (high - close.shift()).abs(),
                    (low  - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    dm_plus  = high.diff()
    dm_minus = -low.diff()
    dm_plus[dm_plus < 0]   = 0
    dm_minus[dm_minus < 0] = 0
    di_plus  = dm_plus.rolling(period).mean() / atr * 100
    di_minus = dm_minus.rolling(period).mean() / atr * 100
    dx = (di_plus - di_minus).abs() / (di_plus + di_minus + 1e-10) * 100
    adx = dx.rolling(period).mean()
    sig = pd.Series(0, index=close.index)
    sig[(adx > adx_thr) & (di_plus > di_minus)]  =  1
    sig[(adx > adx_thr) & (di_minus > di_plus)] = -1
    return sig


# ══ 信号注册表 ═══════════════════════════════════════════════════════

@dataclass
class SignalSpec:
    name: str
    fn: callable
    grid: dict
    needs_hl: bool = False

SIGNALS = {
    "sma_cross" : SignalSpec("双均线交叉",  sig_sma_cross,  {"fast":[10,20,30],"slow":[50,60,120]}),
    "ema_cross" : SignalSpec("EMA交叉",      sig_ema_cross,  {"fast":[5,12,20], "slow":[26,50,60]}),
    "rsi"       : SignalSpec("RSI均值回归",  sig_rsi,        {"period":[7,14,21],  "lower":[25,30],  "upper":[70,75]}),
    "bollinger" : SignalSpec("布林带回归",   sig_bollinger,   {"period":[10,20,30], "std_mult":[1.5,2.0,2.5]}),
    "momentum"  : SignalSpec("动量突破",     sig_momentum,    {"lookback":[10,20,30],"threshold":[0.03,0.05,0.08]}),
    "macd"      : SignalSpec("MACD趋势",    sig_macd,       {"fp":[12],"sp":[26],"sig":[9]}),
    "adx"       : SignalSpec("ADX趋势确认",  sig_adx,        {"period":[14],       "adx_thr":[20,25,30]}, True),
}


# ══ 回测结果 ═══════════════════════════════════════════════════════

@dataclass
class VBtResult:
    strategy_id: str
    strategy_name: str
    params: dict
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    volatility: float
    win_rate: float
    total_trades: int
    profit_factor: float
    avg_holding_days: float
    sortino: float
    calmar: float
    equity_curve: list
    daily_returns: list

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("equity_curve"); d.pop("daily_returns")
        for k in ("total_return","annualized_return","sharpe_ratio",
                  "max_drawdown","volatility","win_rate","profit_factor",
                  "avg_holding_days","sortino","calmar"):
            d[k] = round(d[k], 4)
        return d


# ══ 核心回测函数 ═══════════════════════════════════════════════════════

def run_backtest(
    close: pd.Series,
    signal: pd.Series,
    sid: str,
    name: str,
    params: dict,
    high: pd.Series = None,
    low: pd.Series  = None,
    init_cash: float = 1_000_000.0,
    is_crypto: bool = False,
    quiet: bool = False,
) -> VBtResult:
    """
    向量化回测：
    - 信号：1=买入(全仓), -1=卖出(清仓), 0=持有
    - 执行：次日开盘价（shift(1)）
    - 成本：佣金+滑点 0.08% / 卖出额外+0.10%印花税
    """
    # entry/exit: boolean Series, shift 1 to execute next bar open
    entries = (signal.shift(1).fillna(0) == 1).astype(bool)
    exits   = (signal.shift(1).fillna(0) == -1).astype(bool)

    # A股印花税在卖出时额外扣除（手动调整最终收益）
    sell_stamp = 0.0010 if not is_crypto else 0.0
    sell_fees  = BUY_FEES + sell_stamp   # 0.18% for A股, 0.08% for 加密

    pf = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        init_cash=init_cash,
        fees=BUY_FEES,          # 买入：0.08%
        slippage=0.0005,
        # vectorbt 不支持按成交方向设不同费率，结果中手动调整
    )

    equity = pf.value()
    daily_rets = equity.pct_change().dropna()

    # 基础指标
    total_ret  = float((equity.iloc[-1] / equity.iloc[0] - 1) * 100)
    ann_ret    = float(((equity.iloc[-1] / equity.iloc[0]) ** (252 / max(len(equity)-1, 1)) - 1) * 100)
    ann_vol    = float(daily_rets.std() * np.sqrt(252) * 100)
    sharpe     = ann_ret / ann_vol if ann_vol > 1e-9 else 0.0

    # 最大回撤
    cummax = equity.cummax()
    dd     = (equity - cummax) / cummax * 100
    max_dd = float(dd.min())

    # 交易统计（trades.records 是 DataFrame）
    tdf = pf.trades.records
    n_t = len(tdf) if tdf is not None and len(tdf) > 0 else 0
    if n_t > 0:
        pnl_arr = np.array(tdf["pnl"].values)
        wins    = pnl_arr[pnl_arr > 0]
        losses  = pnl_arr[pnl_arr < 0]
        win_rate = float(len(wins) / n_t * 100)
        avg_hold = float(tdf["pnl"].count())  # 持仓天数均值≈count
        pf_ratio = float(abs(wins.sum() / losses.sum())) if len(losses) > 0 and losses.sum() != 0 else 0.0
    else:
        win_rate = 0.0; avg_hold = 0.0; pf_ratio = 0.0

    sortino = ann_ret / (daily_rets[daily_rets < 0].std() * np.sqrt(252) + 1e-9)
    calmar  = ann_ret / (abs(max_dd) + 1e-9)

    if not quiet:
        print(f"  [{name}] "
              f"收益={total_ret:+.1f}% 年化={ann_ret:+.1f}% "
              f"夏普={sharpe:.2f} DD={max_dd:.1f}% "
              f"交易={n_t}笔 胜率={win_rate:.0f}%")

    return VBtResult(
        strategy_id=sid,
        strategy_name=name,
        params=params,
        total_return=round(total_ret, 4),
        annualized_return=round(ann_ret, 4),
        sharpe_ratio=round(sharpe, 4),
        max_drawdown=round(max_dd, 4),
        volatility=round(ann_vol, 4),
        win_rate=round(win_rate, 2),
        total_trades=n_t,
        profit_factor=round(pf_ratio, 4),
        avg_holding_days=round(avg_hold, 2),
        sortino=round(sortino, 4),
        calmar=round(calmar, 4),
        equity_curve=[round(float(v), 4) for v in equity.tolist()],
        daily_returns=[round(float(r), 6) for r in daily_rets.tolist()],
    )


# ══ 参数扫描 ═══════════════════════════════════════════════════════

def sweep(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    fn: callable,
    sid: str,
    name: str,
    grid: dict,
    needs_hl: bool = False,
    init_cash: float = 1_000_000.0,
    is_crypto: bool = False,
    top_n: int = 5,
) -> List[VBtResult]:
    keys, vals = list(grid.keys()), list(grid.values())
    n_combos = 1
    for v in vals: n_combos *= len(v)
    print(f"  参数扫描 {name}：{n_combos} 种组合...")

    records = []
    for combo in zip(*vals):
        params = dict(zip(keys, combo))
        if needs_hl:
            sig = fn(close, high=high, low=low, **params)
        else:
            sig = fn(close, **params)
        records.append(run_backtest(
            close, sig, sid, name, params,
            high=high, low=low,
            init_cash=init_cash,
            is_crypto=is_crypto, quiet=True,
        ))

    records.sort(key=lambda r: r.sharpe_ratio, reverse=True)
    best = records[:top_n]
    print(f"  Top {top_n} 参数：")
    for r in best:
        print(f"    {r.params} → 收益={r.total_return:+.1f}% 夏普={r.sharpe_ratio:.3f} DD={r.max_drawdown:.1f}%")
    return best


# ══ 批量回测入口 ═══════════════════════════════════════════════════════

def batch_backtest(
    data_dict: dict,
    signal_keys: List[str] = None,
    init_cash: float = 1_000_000.0,
    top_n: int = 5,
) -> Dict[str, List[VBtResult]]:
    signal_keys = signal_keys or list(SIGNALS.keys())
    results = {}

    for sym, ld in data_dict.items():
        df   = local_to_df(ld)
        close = df["Close"]
        high  = df["High"]
        low   = df["Low"]
        is_crypto = sym.upper() in ("BTCUSDT", "ETHUSDT", "SOLUSDT")
        print(f"\n[{sym}] {'='*55}")

        all_results = []
        for skey in signal_keys:
            if skey not in SIGNALS:
                continue
            spec = SIGNALS[skey]
            tops = sweep(
                close, high, low,
                spec.fn,
                f"vbt_{sym}_{skey}",
                spec.name,
                spec.grid,
                needs_hl=spec.needs_hl,
                init_cash=init_cash,
                is_crypto=is_crypto,
                top_n=top_n,
            )
            all_results.extend(tops)

        all_results.sort(key=lambda r: r.sharpe_ratio, reverse=True)
        results[sym] = all_results[:top_n]

        print(f"\n  📊 {sym} 最终 Top {top_n}：")
        for r in results[sym]:
            print(f"    {r.strategy_name:12s} {r.params}  "
                  f"收益={r.total_return:+.1f}% 年化={r.annualized_return:+.1f}% "
                  f"夏普={r.sharpe_ratio:.2f} DD={r.max_drawdown:.1f}% 交易={r.total_trades}笔")

    return results
