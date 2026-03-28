#!/usr/bin/env python3
"""直接运行此脚本：从腾讯API采集A股日K并保存到本地"""
import urllib.request, ssl, json, re, sys
from pathlib import Path
from datetime import datetime

CTX = ssl.create_default_context()
CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE

def tencent_daily(symbol, num):
    sym = f"sh{symbol.strip().lstrip('sh').lstrip('sz').strip()}"
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?_var=kd&param={sym},day,,,{num},qfq")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com/"})
    with urllib.request.urlopen(req, context=CTX, timeout=10) as r:
        raw = r.read().decode("utf-8", errors="replace")
    m = re.search(r'=\s*(\{.+})', raw, re.DOTALL)
    if not m: return {}
    try:
        data = json.loads(m.group(1))
        inner = (data.get("data") or {}).get(sym, {}) or {}
        bars = inner.get("qfqday", inner.get("day", []))
        if not bars: return {}
        return {
            "date":  [b[0]  for b in bars],
            "open":  [float(b[1]) for b in bars],
            "high":  [float(b[2]) for b in bars],
            "low":   [float(b[3]) for b in bars],
            "close": [float(b[4]) for b in bars],
            "vol":   [float(b[5]) for b in bars],
        }
    except: return {}

TARGETS = [
    ("000300", "沪深300",  500),
    ("600519", "茅台",      500),
    ("510300", "沪深300ETF",500),
    ("510500", "中证500ETF",500),
    ("510050", "上证50ETF", 500),
    ("601318", "中国平安",  300),
    ("600036", "招商银行",  300),
    ("601888", "中国中免",  300),
    ("000001", "平安银行",  300),
]

OUT_DIR = Path("/workspace/quant/data/raw")
OUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"采集 {len(TARGETS)} 个标的...")
saved = []
for sym, name, num in TARGETS:
    print(f"  {sym}({name})...", end=" ", flush=True)
    d = tencent_daily(sym, num)
    if d.get("date"):
        closes = d["close"]
        chg = (closes[-1]/closes[0]-1)*100
        cache = OUT_DIR / f"{sym}_{'day'}_{num}.json"
        with open(cache, "w", encoding="utf-8") as f:
            json.dump({
                "symbol": sym, "period": "day", "source": "tencent_daily",
                "fetched_at": datetime.now().isoformat(), "count": len(closes),
                **{k: d[k] for k in d}
            }, f, ensure_ascii=False, indent=2)
        print(f"✅ {len(closes)}条, {chg:+.1f}%  → {cache.name}")
        saved.append(sym)
    else:
        print(f"❌ 失败")
print(f"\n完成！成功 {len(saved)}/{len(TARGETS)}")
if saved:
    print("采集完成的数据:", ", ".join(saved))
