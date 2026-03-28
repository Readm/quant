"""
data_fetcher.py — Stooq 真实历史数据获取器

数据源：Stooq.com（免费，无需Token，日本市场数据）
覆盖：加密货币（BTC/ETH/SOL）、美股（AAPL/NVDA/TSLA等）

说明：
  Stooq 数据有2~3天延迟，适合回测，不适合实时。
  A股暂不支持（stooq对中国股票覆盖有限）。
  数据格式：Date,Open,High,Low,Close,Volume
"""

import urllib.request, ssl, math, random
from typing import Literal

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode    = ssl.CERT_NONE

# Stooq 代码映射
SYMBOL_MAP = {
    # 加密货币
    "BTCUSDT": ("btc.v",   "BTC/USD"),
    "ETHUSDT": ("eth.v",   "ETH/USD"),
    "SOLUSDT": ("sol.v",   "SOL/USD"),
    # 美股（.US后缀）
    "AAPL":    ("aapl.US",  "Apple"),
    "NVDA":    ("nvda.US",  "NVIDIA"),
    "TSLA":    ("tsla.US",  "Tesla"),
    "MSFT":    ("msft.US",  "Microsoft"),
    "GOOGL":   ("googl.US", "Google"),
    "META":    ("meta.US",  "Meta"),
    "AMZN":    ("amzn.US",  "Amazon"),
    "SPY":     ("spy.US",   "S&P500 ETF"),
    "QQQ":     ("qqq.US",   "Nasdaq ETF"),
}

DATE_RANGE = "20230101"  # 可改为更长区间


def fetch_real(symbol: str, end: str = "20241231",
               n_days: int = 500) -> dict | None:
    """
    获取真实历史数据。
    返回 dict: {
        "symbol", "asset_type", "dates", "closes", "highs", "lows",
        "opens", "volumes", "returns", "source", "fetched_at"
    }
    """
    stooq_code = _get_code(symbol)
    if not stooq_code:
        return None

    url = (f"https://stooq.com/q/d/l/?s={stooq_code}"
            f"&d1={DATE_RANGE}&d2={end}&i=d")

    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    })
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            raw = r.read().decode("utf-8")
    except Exception:
        return None

    rows = _parse_csv(raw)
    if not rows:
        return None

    # 取最近 n_days 条（stooq是最新的在前）
    rows = rows[-n_days:]

    closes = [r["close"] for r in rows]
    opens  = [r["open"]  for r in rows]
    highs  = [r["high"]  for r in rows]
    lows   = [r["low"]   for r in rows]
    volumes= [r["volume"] for r in rows]
    dates  = [r["date"]  for r in rows]
    returns= [(closes[i]-closes[i-1])/closes[i-1] for i in range(1, len(closes))]

    asset = _asset_type(symbol)

    return {
        "symbol"   : symbol,
        "asset_type": asset,
        "dates"     : dates,
        "closes"    : closes,
        "opens"     : opens,
        "highs"     : highs,
        "lows"      : lows,
        "volumes"   : volumes,
        "returns"   : returns,
        "source"    : "Stooq.com",
        "n_days"    : len(closes),
    }


def _parse_csv(raw: str) -> list:
    rows = []
    lines = raw.strip().split("\r\n")
    for line in lines[1:]:   # 跳过表头
        parts = line.split(",")
        if len(parts) < 6:
            continue
        try:
            rows.append({
                "date"  : parts[0],
                "open"  : float(parts[1]),
                "high"  : float(parts[2]),
                "low"   : float(parts[3]),
                "close" : float(parts[4]),
                "volume": float(parts[5]),
            })
        except ValueError:
            continue
    # stooq最新日期在前 → 反转
    rows.reverse()
    return rows


def _get_code(symbol: str) -> str | None:
    s = symbol.upper()
    if s in SYMBOL_MAP:
        return SYMBOL_MAP[s][0]
    # 通用尝试
    for key in SYMBOL_MAP:
        if key.upper() == s:
            return SYMBOL_MAP[key][0]
    return None


def _asset_type(symbol: str) -> str:
    s = symbol.upper()
    if any(x in s for x in ["BTC","ETH","SOL","USDT"]):
        return "crypto"
    if s in ["SPY","QQQ"]:
        return "etf"
    return "stock"


def fetch_multiple(symbols: list) -> dict:
    """并发获取多标的"""
    import concurrent.futures
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(fetch_real, sym): sym for sym in symbols}
        for fut in concurrent.futures.as_completed(futures, timeout=30):
            sym = futures[fut]
            try:
                data = fut.result()
                if data:
                    results[sym] = data
            except Exception:
                pass
    return results


def compute_realistic_indicators(data: dict) -> dict:
    """在真实数据上计算技术指标"""
    closes = data["closes"]
    highs  = data["highs"]
    lows   = data["lows"]
    n = len(closes)

    def ma(period):
        out = [0.0]*n
        for i in range(period-1, n):
            out[i] = sum(closes[i-period+1:i+1])/period
        return out

    def ema(period):
        k = 2/(period+1)
        out = [closes[0]]*n
        for i in range(1, n):
            out[i] = closes[i]*k + out[i-1]*(1-k)
        return out

    def rsi(period=14):
        out = [50.0]*n
        for i in range(period, n):
            gains = max(0.0, closes[i]-closes[i-1])
            losses= max(0.0, closes[i-1]-closes[i])
            ag = sum(max(0, closes[j]-closes[j-1]) for j in range(period, i+1))/period
            al = sum(max(0, closes[j-1]-closes[j]) for j in range(period, i+1))/period
            out[i] = 100 - 100/(1+ag/(al+1e-9))
        return out

    def atr(period=14):
        trs = []
        for i in range(1, n):
            tr = max(highs[i]-lows[i],
                     abs(highs[i]-closes[i-1]),
                     abs(lows[i]-closes[i-1]))
            trs.append(tr)
        out = [trs[0]]*n
        for i in range(period, n):
            out[i] = sum(trs[i-period+1:i+1])/period
        return out

    # ADX 简化版
    ma14 = ma(14)
    slope = [0.0]*n
    for i in range(20, n):
        slope[i] = abs((ma14[i]-ma14[i-10])/(ma14[i-10]+1e-9))*100

    return {
        "ma5"   : ma(5),
        "ma10"  : ma(10),
        "ma20"  : ma(20),
        "ma60"  : ma(60),
        "ema12" : ema(12),
        "ema26" : ema(26),
        "rsi"   : rsi(14),
        "atr"   : atr(14),
        "adx"   : slope,
    }


def print_data_summary(results: dict):
    """打印数据获取汇总"""
    print(f"\n{'='*60}")
    print(f"  📊 Stooq 真实数据获取报告")
    print(f"{'='*60}")
    for sym, data in results.items():
        closes = data["closes"]
        rets   = data["returns"]
        n = len(closes)
        mu  = sum(rets)/len(rets)*252
        vol = math.sqrt(sum((r-mu/252)**2 for r in rets)/len(rets))*math.sqrt(252)
        cum_max = max(closes)
        peak_idx = closes.index(cum_max)
        trough_after_peak = min(closes[peak_idx:])
        max_dd = (cum_max-trough_after_peak)/cum_max*100

        print(f"\n  {sym}（{data['asset_type']}）：{data['n_days']}天真实交易日")
        print(f"    价格区间：{min(closes):.2f} ~ {max(closes):.2f}")
        print(f"    年化收益率：{mu*100:.1f}%  | 年化波动率：{vol*100:.1f}%")
        print(f"    最大回撤：-{max_dd:.1f}%  | 偏峰度（最后20天）：{sum(rets[-20:])/20*100:.1f}%/天")
        print(f"    数据范围：{data['dates'][0]} → {data['dates'][-1]}")
    print(f"\n{'='*60}")
