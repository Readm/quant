"""
stooq_collector.py — 从 Stooq.com 采集真实 OHLCV 数据
===============================
用法:
  python -m scripts.collectors.stooq_collector AAPL MSFT SPY
  python -m scripts.collectors.stooq_collector 000300.SH --days 500

数据输出到: data/raw/{symbol}_{date}.json
"""
import sys, json, ssl, urllib.request, time, argparse
from pathlib import Path
from datetime import datetime

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

STOOQ_MAP = {
    "BTCUSDT":"btc.v","ETHUSDT":"eth.v","SOLUSDT":"sol.v",
    "AAPL":"aapl.us","NVDA":"nvda.us","TSLA":"tsla.us",
    "MSFT":"msft.us","GOOGL":"googl.us","AMZN":"amzn.us",
    "SPY":"spy.us","QQQ":"qqq.us",
    "00700.HK":"700.hk","09988.HK":"9988.hk",
    "000001.SH":"000001.sh","000300.SH":"000300.sh",
    "510300.SH":"510300.sh","600519.SH":"600519.sh",
}


def fetch_stooq(symbol, start="20230101", end="20241231"):
    """从 Stooq 获取原始数据"""
    code = STOOQ_MAP.get(symbol.upper())
    if not code:
        print(f"[{symbol}] 代码未映射"); return None
    url = f"https://stooq.com/q/d/l/?s={code}&d1={start}&d2={end}&i=d"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            raw = r.read().decode("utf-8")
    except Exception as e:
        print(f"[{symbol}] 网络错误: {e}"); return None
    rows = []
    for line in raw.strip().split("\n"):
        if not line or "Date" in line: continue
        p = line.split(",")
        if len(p) < 6: continue
        try:
            rows.append({"date":p[0].strip(),"open":float(p[1]),
                         "high":float(p[2]),"low":float(p[3]),
                         "close":float(p[4]),"vol":float(p[5])})
        except ValueError: continue
    rows.reverse()
    return rows


def save_raw(symbol, rows, data_dir="data/raw"):
    """保存原始 JSON"""
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y%m%d")
    path = Path(data_dir) / f"{symbol.upper()}_{date}.json"
    with open(path,"w",encoding="utf-8") as f:
        json.dump({"symbol":symbol,"fetched_at":datetime.now().isoformat(),
                   "count":len(rows),"rows":rows}, f, ensure_ascii=False, indent=2)
    print(f"  💾 {path.name} ({len(rows)} 条)")
    return path


def main():
    parser = argparse.ArgumentParser(description="Stooq 数据采集器")
    parser.add_argument("symbols", nargs="*", default=["AAPL","SPY","000300.SH"])
    parser.add_argument("--days", type=int, default=500)
    parser.add_argument("--start", default="20230101")
    parser.add_argument("--end",   default="20241231")
    parser.add_argument("--data-dir", default="data/raw")
    args = parser.parse_args()

    print(f"📡 Stooq 数据采集器（{len(args.symbols)} 个标的）")
    print(f"   周期: {args.start} → {args.end}（最多 {args.days} 天）")
    print()

    for sym in args.symbols:
        print(f"  正在采集 {sym}...")
        rows = fetch_stooq(sym, start=args.start, end=args.end)
        if rows and len(rows) > args.days:
            rows = rows[-args.days:]
        if rows:
            save_raw(sym, rows, args.data_dir)
        else:
            print(f"  ⚠️  {sym} 无数据")
        time.sleep(0.5)  # 礼貌延迟
    print("\n✅ 采集完成！运行回测：python -m backtest --symbol <标的>")
    # 生成采集报告
    manifest = {"fetched_at":datetime.now().isoformat(),"symbols":{}}
    for p in sorted(Path(args.data_dir).glob("*.json")):
        d = json.load(open(p))
        sym = d["symbol"]
        rows = d["rows"]
        closes = [r["close"] for r in rows]
        manifest["symbols"][sym] = {
            "file":p.name,"count":len(rows),
            "period":f"{rows[0]['date']} → {rows[-1]['date']}",
            "first_close":closes[0],"last_close":closes[-1],
            "change_pct":round((closes[-1]/closes[0]-1)*100,2)
        }
    manifest_path = Path(args.data_dir) / "_manifest.json"
    with open(manifest_path,"w") as f:
        json.dump(manifest,f,ensure_ascii=False,indent=2)
    print(f"  📋 数据清单: {manifest_path.name}")


if __name__ == "__main__":
    main()
