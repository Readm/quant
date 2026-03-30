"""
yfinance_collector.py — 通过 yfinance 采集美股/加密货币真实 OHLCV 数据
=========================================================================
覆盖：SPY QQQ AAPL NVDA TSLA MSFT GOOGL META AMZN BTC-USD ETH-USD SOL-USD
输出：data/raw/{SYMBOL}_{date}.json，与 qlib_collector 格式完全一致

用法：
  python -m scripts.collectors.yfinance_collector SPY BTCUSDT
  python -m scripts.collectors.yfinance_collector --all --start 2020-01-01 --end 2024-12-31
"""
import sys, json, argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# yfinance 符号映射（项目内部符号 → yfinance 符号）
SYMBOL_MAP = {
    "BTCUSDT":  "BTC-USD",
    "ETHUSDT":  "ETH-USD",
    "SOLUSDT":  "SOL-USD",
    "BNBUSDT":  "BNB-USD",
    "XRPUSDT":  "XRP-USD",
    "ADAUSDT":  "ADA-USD",
    "SPY":      "SPY",
    "QQQ":      "QQQ",
    "AAPL":     "AAPL",
    "NVDA":     "NVDA",
    "TSLA":     "TSLA",
    "MSFT":     "MSFT",
    "GOOGL":    "GOOGL",
    "META":     "META",
    "AMZN":     "AMZN",
    "00700.HK": "0700.HK",
    "09988.HK": "9988.HK",
}

DEFAULT_SYMBOLS = ["SPY", "QQQ", "BTCUSDT", "ETHUSDT", "SOLUSDT",
                   "AAPL", "NVDA", "TSLA", "MSFT"]


def fetch_yfinance(symbol: str, start: str, end: str) -> list | None:
    """
    用 yfinance 获取 OHLCV，返回与 stooq/qlib 兼容的 rows 列表。
    symbol：项目内部符号（如 BTCUSDT、SPY）
    """
    import yfinance as yf

    yf_sym = SYMBOL_MAP.get(symbol.upper(), symbol.upper())

    try:
        df = yf.download(yf_sym, start=start, end=end, progress=False, auto_adjust=True)
    except Exception as e:
        print(f"  [yfinance] {symbol} ({yf_sym}) 下载失败: {e}")
        return None

    if df is None or df.empty:
        print(f"  [yfinance] {symbol} ({yf_sym}) 无数据")
        return None

    # yfinance multi-level columns when downloading single ticker
    if hasattr(df.columns, "levels"):
        df.columns = df.columns.get_level_values(0)

    rows = []
    for dt, row in df.iterrows():
        try:
            rows.append({
                "date":  dt.strftime("%Y-%m-%d"),
                "open":  round(float(row["Open"]),  4),
                "high":  round(float(row["High"]),  4),
                "low":   round(float(row["Low"]),   4),
                "close": round(float(row["Close"]), 4),
                "vol":   round(float(row["Volume"]), 0),
            })
        except (KeyError, ValueError):
            continue

    rows.sort(key=lambda r: r["date"])
    return rows if rows else None


def save_raw(symbol: str, rows: list, data_dir: str = "data/raw"):
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now().strftime("%Y%m%d")
    path = Path(data_dir) / f"{symbol.upper()}_{date_tag}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "symbol":     symbol,
            "source":     "yfinance",
            "fetched_at": datetime.now().isoformat(),
            "count":      len(rows),
            "rows":       rows,
        }, f, ensure_ascii=False, indent=2)
    print(f"  saved {path.name} ({len(rows)} rows, {rows[0]['date']} → {rows[-1]['date']})")
    return path


def main():
    parser = argparse.ArgumentParser(description="yfinance 数据采集器（美股/加密货币）")
    parser.add_argument("symbols", nargs="*", default=[],
                        help="标的代码（项目内部符号），如 SPY BTCUSDT")
    parser.add_argument("--all",      action="store_true", help="采集所有预设标的")
    parser.add_argument("--start",    default="2020-01-01")
    parser.add_argument("--end",      default="2024-12-31")
    parser.add_argument("--data-dir", default="data/raw")
    args = parser.parse_args()

    symbols = list(args.symbols)
    if args.all:
        symbols = list(dict.fromkeys(DEFAULT_SYMBOLS + symbols))
    if not symbols:
        symbols = DEFAULT_SYMBOLS

    print(f"yfinance 数据采集器")
    print(f"  标的:   {', '.join(symbols)}")
    print(f"  周期:   {args.start} → {args.end}")
    print(f"  输出:   {args.data_dir}")
    print()

    ok = fail = 0
    for sym in symbols:
        print(f"  采集 {sym} ...")
        rows = fetch_yfinance(sym, args.start, args.end)
        if rows:
            save_raw(sym, rows, args.data_dir)
            ok += 1
        else:
            fail += 1

    print(f"\n完成: {ok} 成功, {fail} 失败")

    # 更新 manifest
    manifest = {"fetched_at": datetime.now().isoformat(), "source": "yfinance", "symbols": {}}
    for p in sorted(Path(args.data_dir).glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            d = json.load(open(p))
            rows = d.get("rows", [])
            if not rows:
                continue
            closes = [r["close"] for r in rows]
            manifest["symbols"][d["symbol"]] = {
                "file":       p.name,
                "count":      len(rows),
                "period":     f"{rows[0]['date']} → {rows[-1]['date']}",
                "source":     d.get("source", ""),
                "last_close": closes[-1],
                "change_pct": round((closes[-1] / closes[0] - 1) * 100, 2),
            }
        except Exception:
            continue
    manifest_path = Path(args.data_dir) / "_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"  manifest: {manifest_path}")


if __name__ == "__main__":
    main()
