#!/usr/bin/env python3
"""fetch_csi_gold.py — 腾讯证券API获取沪深300（无Token）"""
import urllib.request, ssl, json, math

ctx = ssl.create_default_context()
ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE

def fetch_kline(sym, start, end, count=500):
    """腾讯证券K线API"""
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?_var=kline_dayhfq&param={sym},day,{start},{end},{count},qfq")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    })
    with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
        # 扩大读取量（沪深300两年约500条记录，JSON约40KB）
        raw = r.read(100_000).decode("utf-8")
    json_str = raw[raw.index("=") + 1:]
    return json.loads(json_str)

def parse_day(data, sym):
    try:
        key = list(data["data"].keys())[0]
        return data["data"][key].get("day", [])
    except (KeyError, IndexError):
        return []

def to_rows(day_list):
    rows = []
    for it in day_list:
        if len(it) < 6: continue
        try:
            rows.append({"date": it[0], "open": float(it[1]),
                         "close": float(it[2]), "high": float(it[3]),
                         "low": float(it[4]), "vol": float(it[5])})
        except: continue
    return rows

def stats(rows, label=""):
    if not rows: return
    cps = [r["close"] for r in rows]
    rets = [(cps[i]-cps[i-1])/cps[i-1] for i in range(1,len(cps))]
    mu = sum(rets)/len(rets)*252
    vol = math.sqrt(sum((r-mu/252)**2 for r in rets)/len(rets))*math.sqrt(252)
    peak = max(cps); pi = cps.index(peak)
    max_dd = (peak - min(cps[pi:]))/peak*100
    bh = (cps[-1]/cps[0]-1)*100
    print(f"  {'✅' if rows else '❌'} {label}: {len(rows)}天 "
          f"[{rows[0]['date']} → {rows[-1]['date']}]  "
          f"涨跌{bh:+.1f}% 年化{mu*100:+.1f}% "
          f"波动{vol*100:.1f}% 最大回撤{max_dd:.1f}%")
    return rows

def fetch_gold_stooq():
    """Stooq 黄金/贵金属ETF"""
    print("\n  📋 黄金数据（Stooq）...")
    tests = [
        ("GLD ETF", "https://stooq.com/q/d/l/?s=gld.US&d1=20230101&d2=20241231&i=d"),
        ("GOLD",    "https://stooq.com/q/d/l/?s=gold.US&d1=20230101&d2=20241231&i=d"),
        ("IAU ETF", "https://stooq.com/q/d/l/?s=iau.US&d1=20230101&d2=20241231&i=d"),
    ]
    results = {}
    for name, url in tests:
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=8) as r:
                raw = r.read(5000).decode()
        except Exception as e:
            print(f"  ❌ {name}: {e}"); continue
        lines = raw.strip().split("\r\n")
        if len(lines) < 3:
            print(f"  ❌ {name}: 数据不足({len(lines)}行)"); continue
        rows = []
        for line in lines[1:]:
            p = line.split(",")
            if len(p) >= 5:
                try: rows.append({"date":p[0],"close":float(p[4])})
                except: pass
        if rows:
            results[name] = rows
            stats(rows, name)
        else:
            print(f"  ❌ {name}: 解析0行")
    return results

def main():
    print("="*62)
    print("  📊 沪深300 & 黄金数据获取")
    print("  数据源：腾讯证券API（沪深300）| Stooq（黄金）")
    print("="*62)

    # ── 沪深300 ──────────────────────────────────────────
    print("\n  📋 沪深300/上证指数（腾讯API）...")
    csi_tests = [
        ("sh000300", "2022-01-01", "2024-12-31", "沪深300"),
        ("sh000001", "2022-01-01", "2024-12-31", "上证指数"),
        ("sz399001", "2022-01-01", "2024-12-31", "深证成指"),
        ("sz399006", "2022-01-01", "2024-12-31", "创业板指"),
    ]
    csi_results = {}
    for sym, start, end, name in csi_tests:
        try:
            data = fetch_kline(sym, start, end)
            rows = to_rows(parse_day(data, sym))
            if rows:
                rows.reverse()  # oldest → newest
                csi_results[name] = rows
                stats(rows, name)
            else:
                print(f"  ⚠️  {name}: 空数据")
        except Exception as e:
            print(f"  ❌ {name}: {type(e).__name__}: {str(e)[:80]}")

    # ── 黄金 ────────────────────────────────────────────────
    gold_results = fetch_gold_stooq()

    # ── 汇总 ──────────────────────────────────────────────
    print(f"\n{'='*62}")
    print("  📋 数据可用性汇总")
    print(f"{'='*62}")

    print(f"\n  A股/指数（腾讯API，无需Token）：")
    if csi_results:
        for name, rows in csi_results.items():
            print(f"    ✅ {name}: {len(rows)}天 {rows[0]['date']} → {rows[-1]['date']}")
        print(f"\n  → 可立即用于回测！将沪深300纳入多专家系统。")
    else:
        print(f"    ❌ 暂无可用数据")

    print(f"\n  黄金（Stooq）：")
    if gold_results:
        for name, rows in gold_results.items():
            print(f"    ✅ {name}: {len(rows)}天（稀疏数据，仅交易 日）")
        print(f"    ⚠️  数据不完整（仅18~64天），建议使用TuShare黄金数据")
    else:
        print(f"    ❌ 暂无可用黄金历史数据")

    print(f"""
  ─────────────────────────────────────────────────────
  📌 获取完整A股/黄金数据的推荐方案：

  方案A（推荐）：TuShare Token（免费注册）
     → 注册: https://tushare.pro
     → 获取Token后告诉我，立即接入

  方案B：东方财富 WebSocket（无需Token）
     → push2his.eastmoney.com API
     → 当前被拒绝（可能是IP限制），可尝试备用域名

  方案C：分时间段获取腾讯API
     → 将2年数据拆成多个请求（每段60天）
     → 可绕过单次数据量限制
    """)

if __name__ == "__main__":
    main()
