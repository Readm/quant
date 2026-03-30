"""
init_data.py — 一键初始化本地数据缓存
=======================================
首次克隆后运行此脚本，自动采集所有必要的真实数据。

数据源：
  - 美股 / 加密货币：yfinance（需联网）
  - A股：Qlib cn_data（需本地安装，见下方说明）

用法：
  python3 scripts/init_data.py                    # 默认标的，2020-2024
  python3 scripts/init_data.py --no-ashare        # 仅美股/加密（无需 Qlib）
  python3 scripts/init_data.py --start 2022-01-01 # 自定义起始日期
  python3 scripts/init_data.py --ashare-market csi300  # 采集整个 CSI300

Qlib cn_data 安装方法（A股数据）：
  pip install pyqlib
  python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn
  （数据约 2-4 GB，覆盖 A股至 2022-12-30）
"""
import sys, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── 默认标的 ────────────────────────────────────────────────────
US_CRYPTO_SYMBOLS = [
    "SPY", "QQQ",                           # 美股 ETF
    "BTCUSDT", "ETHUSDT", "SOLUSDT",        # 加密货币
    "NVDA", "AAPL", "MSFT", "GOOGL",        # 科技股
]

ASHARE_SYMBOLS = [
    "SH000300",   # 沪深300指数
    "SH600519",   # 贵州茅台
    "SH600036",   # 招商银行
    "SH601318",   # 中国平安
    "SZ000858",   # 五粮液
    "SH600900",   # 长江电力
    "SH601166",   # 兴业银行
]

QLIB_DATA_DIR  = "~/.qlib/qlib_data/cn_data"
ASHARE_END     = "2022-12-30"   # cn_data 当前最新日期


def collect_us_crypto(symbols, start, end, data_dir):
    print(f"\n[1/2] 采集美股/加密货币 ({len(symbols)} 个标的) ...")
    from scripts.collectors.yfinance_collector import fetch_yfinance, save_raw
    ok = fail = 0
    for sym in symbols:
        print(f"  {sym} ...", end=" ", flush=True)
        rows = fetch_yfinance(sym, start, end)
        if rows:
            save_raw(sym, rows, data_dir)
            ok += 1
        else:
            print(f"FAILED")
            fail += 1
    print(f"  完成: {ok} 成功, {fail} 失败")


def collect_ashare(symbols, market, start, end, data_dir):
    print(f"\n[2/2] 采集 A股数据 ...")
    try:
        import qlib
        qlib.init(provider_uri=QLIB_DATA_DIR, region="cn")
        from qlib.data import D
    except ImportError:
        print("  ⚠ pyqlib 未安装，跳过 A股。安装方法：pip install pyqlib")
        return
    except Exception as e:
        print(f"  ⚠ Qlib 初始化失败: {e}")
        print(f"  ⚠ 请确认已下载 cn_data 到 {QLIB_DATA_DIR}")
        return

    from scripts.collectors.qlib_collector import fetch_qlib, save_raw

    all_syms = list(symbols)
    if market:
        instr = D.instruments(market=market)
        market_syms = D.list_instruments(instr, start_time=start, end_time=end, as_list=True)
        print(f"  {market} 共 {len(market_syms)} 支")
        all_syms = list(dict.fromkeys(all_syms + market_syms))

    ok = fail = 0
    for sym in all_syms:
        print(f"  {sym} ...", end=" ", flush=True)
        rows = fetch_qlib(sym, start, end, D)
        if rows:
            save_raw(sym, rows, data_dir)
            ok += 1
        else:
            print("no data")
            fail += 1
    print(f"  完成: {ok} 成功, {fail} 失败")


def write_manifest(data_dir):
    import json
    from datetime import datetime
    manifest = {"fetched_at": datetime.now().isoformat(), "symbols": {}}
    for p in sorted(Path(data_dir).glob("*.json")):
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
            }
        except Exception:
            continue
    manifest_path = Path(data_dir) / "_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\n  数据清单: {manifest_path} ({len(manifest['symbols'])} 个标的)")


def main():
    parser = argparse.ArgumentParser(description="初始化本地数据缓存")
    parser.add_argument("--start",          default="2020-01-01", help="起始日期")
    parser.add_argument("--end",            default="2024-12-31", help="结束日期（US/Crypto）")
    parser.add_argument("--data-dir",       default="data/raw",   help="数据输出目录")
    parser.add_argument("--no-ashare",      action="store_true",  help="跳过 A股采集")
    parser.add_argument("--no-us-crypto",   action="store_true",  help="跳过美股/加密采集")
    parser.add_argument("--ashare-market",  default=None,         help="批量采集 A股市场（csi300/csi500）")
    parser.add_argument("--ashare-end",     default=ASHARE_END,   help=f"A股数据结束日期（默认 {ASHARE_END}）")
    args = parser.parse_args()

    Path(args.data_dir).mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  Quant System — 数据初始化")
    print("=" * 60)
    print(f"  输出目录: {args.data_dir}")
    print(f"  US/Crypto 周期: {args.start} → {args.end}")
    print(f"  A股周期:        {args.start} → {args.ashare_end}")

    if not args.no_us_crypto:
        collect_us_crypto(US_CRYPTO_SYMBOLS, args.start, args.end, args.data_dir)

    if not args.no_ashare:
        collect_ashare(ASHARE_SYMBOLS, args.ashare_market, args.start, args.ashare_end, args.data_dir)

    write_manifest(args.data_dir)
    print("\n初始化完成！运行回测：")
    print("  python3 scripts/run_pipeline.py --symbols SPY BTCUSDT --days 300")


if __name__ == "__main__":
    main()
