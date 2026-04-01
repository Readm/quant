#!/usr/bin/env python3
"""
prepare_tushare.py — 将 Tushare CSV 数据转换为系统 JSON 格式
============================================================
功能：
  1. 读取 data/tushare/daily + adj_factor，计算前复权价格
  2. 合并 daily_basic / moneyflow / stk_limit 为 extensions
  3. 输出到 data/raw/{symbol}_{today}.json

用法：
  python3 scripts/prepare_tushare.py                  # 默认4只A股
  python3 scripts/prepare_tushare.py --symbols SH600519 SH600036
  python3 scripts/prepare_tushare.py --symbols all    # 全A股（仅限沪深，排除北交所）
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

_ROOT    = Path(__file__).parent.parent
TS_DIR   = _ROOT / "data" / "tushare"
RAW_DIR  = _ROOT / "data" / "raw"
RAW_DIR.mkdir(exist_ok=True)

TODAY = datetime.today().strftime("%Y%m%d")

DEFAULT_SYMBOLS = ["SH600519", "SH600036", "SH601318", "SZ000858"]


# ── 格式转换 ─────────────────────────────────────────────────────────

def our_to_ts(sym: str) -> str:
    """SH600519 → 600519.SH"""
    if sym.upper().startswith("SH"):
        return sym[2:] + ".SH"
    if sym.upper().startswith("SZ"):
        return sym[2:] + ".SZ"
    return sym


def ts_to_our(ts_code: str) -> str:
    """600519.SH → SH600519"""
    code, exch = ts_code.upper().split(".")
    return exch + code


# ── 前复权计算 ────────────────────────────────────────────────────────

def apply_adj_factor(daily: pd.DataFrame, adj: pd.DataFrame) -> pd.DataFrame:
    """
    计算前复权价格（qfq）。
    公式：adj_price = raw_price × adj_factor / adj_factor_latest
    """
    if adj.empty:
        return daily

    adj = adj[["trade_date", "adj_factor"]].copy()
    adj["trade_date"] = adj["trade_date"].astype(str)
    daily = daily.copy()
    daily["trade_date"] = daily["trade_date"].astype(str)

    merged = daily.merge(adj, on="trade_date", how="left")
    merged["adj_factor"] = merged["adj_factor"].ffill().fillna(1.0)

    latest_adj = merged["adj_factor"].iloc[-1]
    if latest_adj == 0:
        latest_adj = 1.0

    ratio = merged["adj_factor"] / latest_adj
    for col in ["open", "high", "low", "close"]:
        if col in merged.columns:
            merged[col] = (merged[col] * ratio).round(4)

    return merged


# ── 单标的准备 ───────────────────────────────────────────────────────

def prepare_symbol(our_sym: str, n_days: int = 0) -> bool:
    """
    处理一只股票，输出 data/raw/{our_sym}_{today}.json。
    返回 True = 成功，False = 失败。
    """
    ts_code = our_to_ts(our_sym)

    # ── 加载日线 ──────────────────────────────────────────────────
    daily_path = TS_DIR / "daily" / f"{ts_code}.csv"
    if not daily_path.exists():
        print(f"  {our_sym}: ❌ daily 文件不存在")
        return False

    daily = pd.read_csv(daily_path, dtype={"trade_date": str})
    if daily.empty or "close" not in daily.columns:
        print(f"  {our_sym}: ❌ daily 数据为空")
        return False
    daily = daily.sort_values("trade_date").reset_index(drop=True)

    # ── 应用复权因子 ──────────────────────────────────────────────
    adj_path = TS_DIR / "adj_factor" / f"{ts_code}.csv"
    if adj_path.exists():
        adj = pd.read_csv(adj_path, dtype={"trade_date": str})
        daily = apply_adj_factor(daily, adj)

    # ── 截取最近 n_days ──────────────────────────────────────────
    if n_days > 0 and len(daily) > n_days:
        daily = daily.tail(n_days).reset_index(drop=True)

    dates = daily["trade_date"].tolist()
    n = len(daily)

    # ── 构建 rows ────────────────────────────────────────────────
    rows = []
    for _, row in daily.iterrows():
        rows.append({
            "date":  str(row["trade_date"]),
            "open":  float(row.get("open",  row["close"])),
            "high":  float(row.get("high",  row["close"])),
            "low":   float(row.get("low",   row["close"])),
            "close": float(row["close"]),
            "vol":   float(row.get("vol",   0.0)),
            "amount": float(row.get("amount", 0.0)),
        })

    # ── 构建 extensions ──────────────────────────────────────────
    extensions = {}

    # daily_basic: PE/PB/换手率/市值
    basic_path = TS_DIR / "daily_basic" / f"{ts_code}.csv"
    if basic_path.exists():
        basic = pd.read_csv(basic_path, dtype={"trade_date": str}).sort_values("trade_date")
        basic_map = dict(zip(basic["trade_date"], basic.to_dict("records")))
        for field, alias in [
            ("pe",            "pe"),
            ("pb",            "pb"),
            ("turnover_rate", "turnover_rate"),
            ("total_mv",      "total_mv"),
            ("circ_mv",       "circ_mv"),
            ("volume_ratio",  "volume_ratio"),
        ]:
            if field in basic.columns:
                arr = [float(basic_map[d][field]) if d in basic_map and basic_map[d][field] == basic_map[d][field]
                       else float("nan")
                       for d in dates]
                extensions[alias] = arr

    # moneyflow: 主力资金
    mf_path = TS_DIR / "moneyflow" / f"{ts_code}.csv"
    if mf_path.exists():
        mf = pd.read_csv(mf_path, dtype={"trade_date": str}).sort_values("trade_date")
        mf_map = dict(zip(mf["trade_date"], mf.to_dict("records")))
        for field in ["buy_elg_amount", "sell_elg_amount",   # 超大单
                      "buy_lg_amount",  "sell_lg_amount",    # 大单
                      "net_mf_amount",  "net_mf_vol"]:       # 净主力
            if field in mf.columns:
                arr = [float(mf_map[d][field]) if d in mf_map and mf_map[d][field] == mf_map[d][field]
                       else float("nan")
                       for d in dates]
                extensions[field] = arr

    # stk_limit: 涨跌停价格
    sl_path = TS_DIR / "stk_limit" / f"{ts_code}.csv"
    if sl_path.exists():
        sl = pd.read_csv(sl_path, dtype={"trade_date": str}).sort_values("trade_date")
        sl_map = dict(zip(sl["trade_date"], sl.to_dict("records")))
        for field in ["up_limit", "down_limit"]:
            if field in sl.columns:
                arr = [float(sl_map[d][field]) if d in sl_map and sl_map[d][field] == sl_map[d][field]
                       else float("nan")
                       for d in dates]
                extensions[field] = arr

    # ── 写入 JSON ────────────────────────────────────────────────
    out = {
        "symbol":     our_sym,
        "source":     "tushare_qfq",
        "fetched_at": TODAY,
        "count":      n,
        "rows":       rows,
        "extensions": extensions,
    }

    out_path = RAW_DIR / f"{our_sym}_{TODAY}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return True


# ── 主流程 ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Tushare → 系统 JSON 格式转换")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="股票代码（SH600519 格式）或 'all'（全沪深）")
    parser.add_argument("--days", type=int, default=0,
                        help="截取最近 N 天（0=全量）")
    args = parser.parse_args()

    if args.symbols and args.symbols[0].lower() == "all":
        meta_path = TS_DIR / "metadata" / "stock_basic.csv"
        meta = pd.read_csv(meta_path)
        # 排除北交所
        meta = meta[~meta["ts_code"].str.endswith(".BJ")]
        symbols = [ts_to_our(c) for c in meta["ts_code"].tolist()]
        print(f"全量沪深股票: {len(symbols)} 只（已排除北交所）")
    elif args.symbols:
        symbols = args.symbols
    else:
        symbols = DEFAULT_SYMBOLS

    print(f"准备 {len(symbols)} 只股票的数据...")
    ok = fail = 0
    for sym in symbols:
        success = prepare_symbol(sym, n_days=args.days)
        if success:
            ok += 1
        else:
            fail += 1

    print(f"\n完成: {ok} 成功, {fail} 失败")
    print(f"输出目录: {RAW_DIR}")


if __name__ == "__main__":
    main()
