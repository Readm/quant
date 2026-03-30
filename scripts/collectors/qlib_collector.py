"""
qlib_collector.py — 从 Qlib cn_data 采集 A股真实 OHLCV 数据
==============================================================
数据源：~/.qlib/qlib_data/cn_data（本地缓存，覆盖至 2022-12-30）
输出：data/raw/{SYMBOL}_{date}.json，与 stooq_collector 格式完全一致

用法：
  python -m scripts.collectors.qlib_collector SH600519 SH000300
  python -m scripts.collectors.qlib_collector --market csi300 --start 2021-01-01 --end 2022-12-30
  python -m scripts.collectors.qlib_collector --market csi300  # 默认全量
"""
import sys, json, argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

QLIB_DATA_DIR = "~/.qlib/qlib_data/cn_data"
DEFAULT_START  = "2020-01-01"
DEFAULT_END    = "2022-12-30"   # cn_data 当前最新日期


def _init_qlib():
    import qlib
    qlib.init(provider_uri=QLIB_DATA_DIR, region="cn")
    from qlib.data import D
    return D


def fetch_qlib(symbol: str, start: str, end: str, D) -> list | None:
    """
    从 qlib 获取单支股票 OHLCV，返回与 stooq_collector 兼容的 rows 列表。
    qlib 存储：adjusted = real * factor  →  real = adjusted / factor
    """
    try:
        df = D.features(
            [symbol],
            ["$open", "$high", "$low", "$close", "$volume", "$factor"],
            start_time=start, end_time=end, freq="day"
        )
    except Exception as e:
        print(f"  [qlib] {symbol} 查询失败: {e}")
        return None

    if df is None or df.empty:
        print(f"  [qlib] {symbol} 无数据（{start} → {end}）")
        return None

    rows = []
    for (_, dt), row in df.iterrows():
        factor = row["$factor"]
        if factor == 0 or factor != factor:   # 0 或 NaN
            continue
        rows.append({
            "date":  dt.strftime("%Y-%m-%d"),
            "open":  round(float(row["$open"])   / factor, 3),
            "high":  round(float(row["$high"])   / factor, 3),
            "low":   round(float(row["$low"])    / factor, 3),
            "close": round(float(row["$close"])  / factor, 3),
            "vol":   round(float(row["$volume"]), 0),
        })

    rows.sort(key=lambda r: r["date"])
    return rows if rows else None


class _FloatEncoder(json.JSONEncoder):
    def default(self, o):
        try:
            return float(o)
        except (TypeError, ValueError):
            return super().default(o)


def save_raw(symbol: str, rows: list, data_dir: str = "data/raw"):
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now().strftime("%Y%m%d")
    path = Path(data_dir) / f"{symbol.upper()}_{date_tag}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "symbol":     symbol,
            "source":     "qlib/cn_data",
            "fetched_at": datetime.now().isoformat(),
            "count":      len(rows),
            "rows":       rows,
        }, f, ensure_ascii=False, indent=2, cls=_FloatEncoder)
    print(f"  saved {path.name} ({len(rows)} rows, {rows[0]['date']} → {rows[-1]['date']})")
    return path


def main():
    parser = argparse.ArgumentParser(description="Qlib A股数据采集器")
    parser.add_argument("symbols", nargs="*", default=[],
                        help="股票代码，如 SH600519 SH000300")
    parser.add_argument("--market", default=None,
                        help="批量采集市场（csi300 / csi500 / csi100 / all）")
    parser.add_argument("--start",    default=DEFAULT_START)
    parser.add_argument("--end",      default=DEFAULT_END)
    parser.add_argument("--data-dir", default="data/raw")
    parser.add_argument("--limit",    type=int, default=0,
                        help="最多采集 N 支（0=全量，调试用）")
    args = parser.parse_args()

    print(f"Qlib A股数据采集器")
    print(f"  数据源: {QLIB_DATA_DIR}")
    print(f"  周期:   {args.start} → {args.end}")
    print(f"  输出:   {args.data_dir}")
    print()

    D = _init_qlib()

    symbols = list(args.symbols)
    if args.market:
        from qlib.data import D as _D
        instr = _D.instruments(market=args.market)
        all_syms = _D.list_instruments(instr, start_time=args.start,
                                       end_time=args.end, as_list=True)
        print(f"  {args.market} 共 {len(all_syms)} 支")
        symbols += all_syms

    if not symbols:
        print("ERROR: 请指定标的或 --market")
        sys.exit(1)

    # 去重
    symbols = list(dict.fromkeys(symbols))
    if args.limit > 0:
        symbols = symbols[:args.limit]

    ok = fail = 0
    for sym in symbols:
        print(f"  采集 {sym} ...")
        rows = fetch_qlib(sym, args.start, args.end, D)
        if rows:
            save_raw(sym, rows, args.data_dir)
            ok += 1
        else:
            fail += 1

    print(f"\n完成: {ok} 成功, {fail} 失败")

    # 更新 manifest
    manifest = {"fetched_at": datetime.now().isoformat(), "source": "qlib/cn_data", "symbols": {}}
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
                "file":   p.name,
                "count":  len(rows),
                "period": f"{rows[0]['date']} → {rows[-1]['date']}",
                "source": d.get("source", ""),
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
