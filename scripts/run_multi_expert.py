#!/usr/bin/env python3
"""run_multi_expert.py — 多专家系统 v3.5 数据层整合"""
import sys, math, random, ssl, urllib.request, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
ctx = ssl.create_default_context()
ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE

# ── 腾讯证券 API ──────────────────────────────────────────
def fetch_tx(sym, start, end, count=500):
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?_var=kline_dayhfq&param={sym},day,{start},{end},{count},qfq")
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=12) as r:
        raw = r.read(100_000).decode("utf-8")
    j = json.loads(raw[raw.index("=")+1:])
    key = list(j.get("data",{}).keys())[0]
    days = j["data"][key].get("day",[])
    rows = []
    for it in days:
        if len(it) < 6: continue
        rows.append({"date":it[0],"open":float(it[1]),"close":float(it[2]),
                     "high":float(it[3]),"low":float(it[4]),"vol":float(it[5])})
    rows.reverse()
    return rows

# ── 东方财富 API ────────────────────────────────────────
def fetch_emf(secid, start="20220101", end="20241231", limit=800):
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid={secid}&fields1=f1,f2,f3,f4,f5"
           f"&fields2=f51,f52,f53,f54,f55,f56"
           f"&klt=101&fqt=1&beg={start}&end={end}&lmt={limit}")
    req = urllib.request.Request(url, headers={
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer":"https://quote.eastmoney.com/",
    })
    with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
        raw = r.read(80_000).decode("utf-8")
    j = json.loads(raw)
    rows = []
    for kl in j.get("data",{}).get("klines",[]):
        p = kl.split(",")
        if len(p) < 6: continue
        rows.append({"date":p[0],"open":float(p[1]),"close":float(p[2]),
                     "high":float(p[3]),"low":float(p[4]),"vol":float(p[5])})
    return rows

# ── Stooq ────────────────────────────────────────────────
def fetch_stooq(sym, n=300):
    url = f"https://stooq.com/q/d/l/?s={sym}&d1=20230101&d2=20241231&i=d"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
        raw = r.read(5000).decode()
    rows = []
    for line in raw.strip().split("\r\n")[1:]:
        p = line.split(",")
        if len(p) < 5: continue
        rows.append({"date":p[0],"close":float(p[4])})
    rows.reverse()
    return rows[:n]

# ════════════════════════════════════════════════════════════
# 数据获取汇总
# ════════════════════════════════════════════════════════════

def get_data():
    results = {}
    errors = []

    # ① 沪深300（腾讯）
    try:
        rows = fetch_tx("sh000300", "2022-01-01", "2024-12-31")
        if rows:
            cps = [r["close"] for r in rows]
            print(f"  CSI300: {len(rows)}天 {(cps[-1]/cps[0]-1)*100:+.1f}%")
            results["CSI300"] = cps
    except Exception as e:
        errors.append(f"CSI300: {e}")

    # ② 港股（腾讯）
    hk_map = [
        ("hk09988","阿里巴巴"),("hk03690","京东物流"),("hk02020","理想汽车"),
        ("hk02628","中国人寿"),("hk00941","中国移动"),("hk00939","建设银行H"),
        ("hk06160","百济神州"),("hk02382","舜宇光学"),
    ]
    for sym, name in hk_map:
        try:
            rows = fetch_tx(sym, "2022-01-01", "2024-12-31")
            if rows and len(rows) >= 200:
                cps = [r["close"] for r in rows]
                bh = (cps[-1]/cps[0]-1)*100
                print(f"  HK/{name}: {len(rows)}天 {bh:+.1f}%")
                results[f"HK_{name}"] = cps
        except Exception as e:
            errors.append(f"HK/{name}: {e}")

    # ③ A股个股（东方财富）
    a_map = [
        ("0.300750","宁德时代"),("1.600036","招商银行"),
        ("0.000001","平安银行"),("1.512690","酒ETF"),
    ]
    for secid, name in a_map:
        try:
            rows = fetch_emf(secid)
            if rows and len(rows) >= 200:
                cps = [r["close"] for r in rows]
                bh = (cps[-1]/cps[0]-1)*100
                print(f"  AShare/{name}: {len(rows)}天 {bh:+.1f}%")
                results[f"A_{name}"] = cps
        except Exception as e:
            errors.append(f"AShare/{name}: {e}")

    # ④ 加密+黄金（Stooq）
    stooq_map = [("btc.v","BTC"),("eth.v","ETH"),("gld.US","GLD")]
    for sym, name in stooq_map:
        try:
            rows = fetch_stooq(sym, 300)
            if rows and len(rows) >= 200:
                cps = [r["close"] for r in rows]
                bh = (cps[-1]/cps[0]-1)*100
                print(f"  {name}: {len(rows)}天 {bh:+.1f}%")
                results[name] = cps
        except Exception as e:
            errors.append(f"{name}: {e}")

    if errors:
        print(f"\n[警告] {len(errors)} 个标的获取失败:")
        for e in errors:
            print(f"  ✗ {e}")
    print(f"\n共获取 {len(results)} 个标的")
    return results

if __name__ == "__main__":
    print("="*60)
    print("  Data Loader — multi_expert v3.5")
    print("="*60)
    data = get_data()
    print(f"\n标的列表: {list(data.keys())}")
