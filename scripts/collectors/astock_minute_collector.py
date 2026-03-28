"""
astock_minute_collector.py — A股数据采集器
用法:
  python3 -m scripts.collectors.astock_minute_collector 000300 day 500 --force
  python3 -m scripts.collectors.astock_minute_collector 600519 day 500 --force
  python3 -m scripts.collectors.astock_minute_collector 510300 day 500 --force
  python3 -m scripts.collectors.astock_minute_collector 510500 day 500 --force
"""

import sys, os, json, ssl, time, re, argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
DATA_DIR = Path("/workspace/quant/data/raw")
DATA_DIR.mkdir(parents=True, exist_ok=True)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "*/*",
    "Referer": "https://finance.qq.com/",
}

def fetch(url, timeout=10):
    req = __import__("urllib.request").Request(url, headers=HEADERS)
    with __import__("urllib.request").urlopen(req, context=CTX, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# ════════════════════════════════
#  腾讯日K（已验证完全可用）
# ════════════════════════════════
def fetch_tencent_daily(symbol, num=500):
    """腾讯股票日K，已验证可用。返回 {"date":[],"open":[],"high":[],"low":[],"close":[],"vol":[]}"""
    sym = symbol.strip().lower()
    for p in ("sh", "sz"):
        sym = sym.lstrip(p)
    sym = f"sh{sym}"  # 默认沪市

    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?_var=kline_day&param={sym},day,,,{num},qfq")
    raw = fetch(url)
    m = re.search(r'=\s*(\{.+})', raw, re.DOTALL)
    if not m:
        return {}
    data = json.loads(m.group(1))
    inner = (data.get("data") or {}).get(sym, {}) or {}
    bars = inner.get("qfqday", inner.get("day", []))
    if not bars:
        return {}
    return {
        "date":  [b[0]  for b in bars],
        "open":  [float(b[1]) for b in bars],
        "high":  [float(b[2]) for b in bars],
        "low":   [float(b[3]) for b in bars],
        "close": [float(b[4]) for b in bars],
        "vol":   [float(b[5]) for b in bars],
    }


# ════════════════════════════════
#  东方财富分钟K（仅作备用）
# ════════════════════════════════
# secid: 1.XXXXXX(沪)  0.XXXXXX(深)
EM_SECID = {
    "600519": "1.600519", "000300": "1.000300",
    "000001": "0.000001", "510300": "1.510300",
    "510500": "1.510500", "510050": "1.510050",
}
EM_PERIOD = {"5minute": 5, "15minute": 15, "30minute": 30, "60minute": 60}

def fetch_eastmoney_minute(symbol, period=5, num=500):
    """东方财富分钟K，返回同上格式。失败返回{}"""
    secid = EM_SECID.get(symbol.strip().lstrip("sh").lstrip("sz").strip().zfill(6),
                      f"1.{symbol.strip().lstrip('sh').lstrip('sz').strip().zfill(6)}")
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
        f"secid={secid}&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt={period}&fqt=1&end=20500101&lmt={num}"
        f"&ut=fa5fd1943c7b386f172d6893dbfba10b"
    )
    try:
        raw = fetch(url, timeout=8)
        pkt = json.loads(raw)
        klines = (pkt.get("data") or {}).get("klines") or []
        if not klines:
            return {}
        result = {"date": [], "open": [], "high": [], "low": [], "close": [], "vol": []}
        for kl in klines:
            p = kl.split(",")
            result["date"].append(p[0])
            result["open"].append(float(p[1]))
            result["close"].append(float(p[2]))
            result["high"].append(float(p[3]))
            result["low"].append(float(p[4]))
            result["vol"].append(float(p[5]))
        return result
    except Exception:
        return {}


# ════════════════════════════════
#  Stooq（A/港/美股日线）
# ════════════════════════════════
STOOQ = {
    "AAPL": "aapl.us", "NVDA": "nvda.us", "TSLA": "tsla.us",
    "MSFT": "msft.us", "GOOGL": "googl.us", "AMZN": "amzn.us",
    "SPY": "spy.us", "QQQ": "qqq.us",
    "00700": "700.hk", "09988": "9988.hk",
    "600519": "600519.sh", "000300": "000300.sh", "000001": "000001.sz",
    "510300": "510300.sh", "510500": "510500.sh",
    "BTC": "btc.v", "ETH": "eth.v", "SOL": "sol.v",
}

def fetch_stooq_daily(symbol, days=500):
    code = STOOQ.get(symbol.upper(), f"{symbol}.sh")
    end   = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days*2)).strftime("%Y%m%d")
    url = f"https://stooq.com/q/d/l/?s={code}&d1={start}&d2={end}&i=d"
    try:
        raw = fetch(url, timeout=10)
        rows = []
        for line in raw.strip().split("\n"):
            if not line or "Date" in line:
                continue
            p = line.split(",")
            if len(p) >= 6:
                rows.append({"date": p[0], "open": float(p[1]),
                             "high": float(p[2]), "low": float(p[3]),
                             "close": float(p[4]), "vol": float(p[5])})
        rows.reverse()
        if not rows:
            return {}
        return {k: [r[k] for r in rows] for k in ("date", "open", "high", "low", "close", "vol")}
    except Exception:
        return {}


# ════════════════════════════════
#  统一采集入口
# ════════════════════════════════

def collect(symbol, period="day", num=500, force=False):
    """
    采集并缓存数据。
    period: "day" | "5minute" | "15minute" | "30minute" | "60minute"
    返回保存路径，失败返回""。
    """
    sym = symbol.strip().lstrip("sh").lstrip("sz").strip()
    cache = DATA_DIR / f"{sym.upper()}_{period}_{num}.json"

    if cache.exists() and not force:
        print(f"  📋 缓存命中: {cache.name}")
        return str(cache)

    result = {}
    source = ""

    if period == "day":
        # 优先腾讯 → 备用Stooq
        result = fetch_tencent_daily(sym, num)
        source = "tencent_daily"
        if not result.get("date"):
            result = fetch_stooq_daily(sym, num)
            source = "stooq_daily"

    else:
        # 分钟K：东方财富 → 备用Stooq(非真实)
        p = EM_PERIOD.get(period, 5)
        result = fetch_eastmoney_minute(sym, period=p, num=num)
        source = "eastmoney_minute"
        if not result.get("date"):
            # 尝试Stooq（仅日线，分钟数据用日K重采样+警告）
            sd = fetch_stooq_daily(sym, num * 5)
            if sd.get("date"):
                result = _resample(sd, period)
                source = f"stooq_resampled_to_{period}"
                print(f"  ⚠️  {sym} {period}: 东方财富不可用，用日K重采样（不真实！）")
            else:
                result = {}

    if result.get("date"):
        cache_data = {
            "symbol": sym.upper(),
            "period": period,
            "source": source,
            "fetched_at": datetime.now().isoformat(),
            "count": len(result["date"]),
            **{k: result[k] for k in result}
        }
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        closes = result["close"]
        chg = (closes[-1]/closes[0]-1)*100 if len(closes) >= 2 else 0
        print(f"  💾 {cache.name} | {len(closes)} 条 | 来源:{source} | {chg:+.1f}%")
        return str(cache)
    else:
        print(f"  ❌ {sym} {period}: 所有数据源失败")
        return ""


def _resample(daily, period):
    """日K重采样为模拟分钟（数据不真实，仅用于架构演示）"""
    n_map = {"5minute": 5, "15minute": 15, "30minute": 30, "60minute": 60}
    n = n_map.get(period, 5)
    out = {k: [] for k in daily}
    for i in range(0, len(daily["date"]) - n, n):
        out["date"].append(daily["date"][i])
        out["open"].append(daily["open"][i])
        out["high"].append(max(daily["high"][i:i+n]))
        out["low"].append(min(daily["low"][i:i+n]))
        out["close"].append(daily["close"][i+n-1])
        out["vol"].append(sum(daily["vol"][i:i+n]))
    return out


# ════════════════════════════════
#  CLI
# ════════════════════════════════

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("symbol", help="代码，如 000300 / 600519")
    p.add_argument("period", default="day")
    p.add_argument("num", type=int, default=500)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    print(f"\n📡 采集 {args.symbol} {args.period} × {args.num}")
    print("=" * 55)
    t0 = time.time()
    path = collect(args.symbol, args.period, args.num, force=args.force)
    print(f"\n✅ 完成（{time.time()-t0:.1f}s）: {path}")
