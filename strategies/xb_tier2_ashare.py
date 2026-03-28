"""
xb_tier2_ashare.py — 邢不行策略 · 第二级（A股数据）
================================================================
数据来源：
  腾讯证券 HTTP API（免费，无需 Token，已验证可用）
  - 个股日线：sh600519 格式（前缀 sh/sz + 6位代码）
  - 覆盖：每日 OHLCV，复权后价格

TuShare Token 接入状态：
  Token: 已配置（但积分=0，仅基础权限，建议累积积分后解锁更多字段）
  备选：腾讯证券 API（当前主力数据源，无限制）

策略列表（10个）：
  T2-01  小市值选股      每月选市值最小 Top10% A股（需市值数据）
  T2-02  低价股选股      股价 < 5元 月度轮动
  T2-03  量价相关性选股  选量价相关性最高的股票
  T2-04  反过度自信选股  换手率异常放大后逆势操作
  T2-05  资产有息负债率  选财务最健康的股票（需财务数据）
  T2-06  低估值高分红    PE<30 + 股息率>3%
  T2-07  伽利略五行选股  五维度因子综合评分
  T2-08  定风波择时      大跌后偏离MA20>10%+地量→买入
  T2-09  黑色星期四      周四收盘买/周开盘卖
  T2-10  Fama-French三因子  市值+价值+动量
"""

import sys, math, ssl, urllib.request, json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# ═══════════════════════════════════════════════════════════════
# 腾讯证券数据层（主力，无限制）
# ═══════════════════════════════════════════════════════════════

def _tencent_req(code: str, start: str, end: str,
                 limit: int = 500, fq: bool = True) -> List[dict]:
    """腾讯证券 HTTP API → [{date, open, high, low, close, volume}]"""
    suf = "qfqday" if fq else "day"
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?_var=kline_{suf}&param={code},day,{start},{end},{limit},{suf}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=CTX, timeout=10) as r:
            raw = r.read().decode()
        j = json.loads(raw.split("=", 1)[1])
        key = "qfqday" if fq else "day"
        days = j["data"][code].get(key) or j["data"][code].get("day", [])
        return [{"date":   d[0],
                 "open":   float(d[1]),
                 "close":  float(d[2]),
                 "high":   float(d[3]),
                 "low":    float(d[4]),
                 "volume": float(d[5]),
                 "code":   code}
                for d in days]
    except Exception:
        return []


def fetch_ashare(code: str, year: int) -> List[dict]:
    """
    获取A股个股全年日线数据（腾讯证券）
    code: 如 'sh600519'（上证）或 'sz000858'（深证）
    """
    quarters = [("01-01","03-31"), ("04-01","06-30"),
                ("07-01","09-30"), ("10-01","12-31")]
    all_d = []
    for s, e in quarters:
        all_d.extend(_tencent_req(code, f"{year}-{s}", f"{year}-{e}"))
    # 去重保留唯一日期
    seen, result = set(), []
    for d in sorted(all_d, key=lambda x: x["date"]):
        if d["date"] not in seen:
            seen.add(d["date"])
            result.append(d)
    return result


def fetch_index_by_code(code: str, year: int) -> List[dict]:
    """
    获取指数日线（腾讯证券不支持部分指数，优先用个股近似）
    code格式：sh000001=上证指数，sz399001=深证成指
    """
    return _tencent_req(code, f"{year}-01-01", f"{year}-12-31", limit=1000, fq=False)


# ═══════════════════════════════════════════════════════════════
# TuShare 层（Token 已配置但积分=0，仅作占位备用）
# ═══════════════════════════════════════════════════════════════

TU_TOKEN = "7a0b3f1c248e650a50db0d722af19cbe61cd67bb3df44939a9744b31"
TUSHARE_READY = False  # Token积分=0，暂无法调用

def _tushare_call(api: str, params: dict, fields: str) -> Optional[dict]:
    """TuShare REST API（积分足够时使用）"""
    if not TUSHARE_READY:
        return None
    payload = json.dumps({
        "api_name": api, "token": TU_TOKEN,
        "params": params, "fields": fields
    }).encode()
    req = urllib.request.Request(
        "http://api.tushare.pro", data=payload,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=10) as r:
            resp = json.loads(r.read().decode())
        if resp["code"] == 0:
            return resp["data"]
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════
# 指标计算
# ═══════════════════════════════════════════════════════════════

def ma(arr: List[float], n: int) -> List[float]:
    return [sum(arr[max(0,i-n+1):i+1])/min(n,i+1) for i in range(len(arr))]

def ema(arr: List[float], n: int) -> List[float]:
    if not arr: return []
    k = 2/(n+1)
    out = [arr[0]]
    for i in range(1, len(arr)):
        out.append(arr[i]*k + out[-1]*(1-k))
    return out

def boll_bands(closes: List[float], n: int = 20, mult: float = 2.0):
    std = []
    for i in range(len(closes)):
        s = closes[max(0,i-n+1):i+1]
        m = sum(s)/len(s)
        std.append(math.sqrt(sum((x-m)**2 for x in s)/len(s)))
    mid = ma(closes, n)
    return [m+mult*s for m,s in zip(mid,std)], mid, [m-mult*s for m,s in zip(mid,std)]

def rsi(closes: List[float], n: int = 14) -> List[float]:
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i]-closes[i-1]
        gains.append(max(d,0)); losses.append(max(-d,0))
    avg_g = ma(gains, n); avg_l = ma(losses, n)
    return [100-100/(1+a/b) if b>0 else 50 for a,b in zip(avg_g,avg_l)]

def macd(closes: List[float], f: int = 12, s: int = 26, sig: int = 9):
    ef = ema(closes, f); es = ema(closes, s)
    dif = [ef[i]-es[i] for i in range(len(ef))]
    dea = [sum(dif[max(0,i-sig+1):i+1])/min(sig,i+1) for i in range(len(dif))]
    return dif, dea


# ═══════════════════════════════════════════════════════════════
# T2-08  定风波择时策略
# ═══════════════════════════════════════════════════════════════

def signal_dingfengbo(closes: List[float], highs: List[float],
                       lows: List[float], opens: List[float],
                       volumes: List[float],
                       ma_period: int = 20,
                       vol_lookback: int = 30,
                       dev_threshold: float = 0.10) -> List[int]:
    """
    定风波择时（邢不行2024年末提出）：
    - 市场超跌（偏离MA20 > threshold%）且成交量萎缩至均值30%以下 → 买入
    - 市场反弹至MA5以上 → 卖出
    """
    if len(closes) < ma_period + vol_lookback:
        return [0] * len(closes)

    m20 = ma(closes, ma_period)
    avg_vol = [sum(volumes[max(0,i-vol_lookback+1):i+1])/min(vol_lookback,i+1)
               for i in range(len(volumes))]

    sig = [0] * len(closes)
    in_pos = False

    for i in range(ma_period, len(closes)):
        dev = (closes[i] - m20[i]) / m20[i] if m20[i] != 0 else 0
        vol_ratio = volumes[i] / max(avg_vol[i], 1e-9)

        if not in_pos:
            # 买入：大幅偏离均线 + 极度缩量（恐慌极点）
            if dev < -dev_threshold and vol_ratio < 0.35:
                sig[i] = 1
                in_pos = True
        else:
            # 卖出：反弹至MA5以上
            ma5 = sum(closes[max(0,i-4):i+1]) / 5
            ma5_prev = sum(closes[max(0,i-5):i-1]) / 5 if i >= 6 else ma5
            if closes[i] > ma5 and ma5_prev <= (sum(closes[max(0,i-6):i])/5 if i >= 6 else ma5):
                sig[i] = -1
                in_pos = False

    return sig


# ═══════════════════════════════════════════════════════════════
# T2-09  黑色星期四择时策略
# ═══════════════════════════════════════════════════════════════

def signal_black_thursday(closes: List[float], highs: List[float],
                           lows: List[float], opens: List[float],
                           volumes: List[float],
                           hold_over_weekend: bool = True) -> List[int]:
    """
    黑色星期四（A股周内效应）：
    - 每周四收盘前买入（周四是一周中下跌概率最大的交易日）
    - 周一开盘卖出
    - 注意：仅适用于指数ETF，不适合个股
    """
    sig = [0] * len(closes)
    for i in range(1, len(closes)):
        days_since_start = i % 5  # 模拟星期
        if days_since_start == 3:   # 周四
            sig[i] = 1
        elif days_since_start == 0 and hold_over_weekend:  # 周一
            sig[i] = -1
    return sig


# ═══════════════════════════════════════════════════════════════
# T2-10  布林带均值回归（A股指数择时）
# ═══════════════════════════════════════════════════════════════

def signal_boll_ashare(closes: List[float], highs: List[float],
                        lows: List[float], opens: List[float],
                        volumes: List[float],
                        n: int = 20, k: float = 2.0) -> List[int]:
    """
    布林带均值回归（A股权证/指数）：
    - 价格触及下轨 → 买入（超卖）
    - 价格触及上轨 → 卖出（超买）
    """
    if len(closes) < n + 5:
        return [0] * len(closes)
    upper, mid, lower = boll_bands(closes, n, k)
    sig = [0] * len(closes)
    for i in range(n, len(closes)):
        if closes[i] <= lower[i] and closes[i-1] > lower[i-1]:
            sig[i] = 1
        elif closes[i] >= upper[i] and closes[i-1] < upper[i-1]:
            sig[i] = -1
    return sig


# ═══════════════════════════════════════════════════════════════
# T2-11  MACD 择时（A股指数）
# ═══════════════════════════════════════════════════════════════

def signal_macd_ashare(closes: List[float], highs: List[float],
                        lows: List[float], opens: List[float],
                        volumes: List[float],
                        fast: int = 12, slow: int = 26, sig: int = 9) -> List[int]:
    """
    MACD 择时（A股权证/指数）：
    - DIF 上穿 DEA → 买入
    - DIF 下穿 DEA → 卖出
    """
    if len(closes) < slow + sig:
        return [0] * len(closes)
    dif, dea = macd(closes, fast, slow, sig)
    # dif/dea 从 fast 开始有值
    offset = slow
    sig_out = [0] * len(closes)
    for i in range(offset, len(closes)):
        di = dif[i]; dd = dea[i]
        di_p = dif[i-1]; dd_p = dea[i-1]
        if di_p <= dd_p and di > dd:
            sig_out[i] = 1
        elif di_p >= dd_p and di < dd:
            sig_out[i] = -1
    return sig_out


# ═══════════════════════════════════════════════════════════════
# 选股模拟器（用于演示，基于公开财务逻辑）
# ═══════════════════════════════════════════════════════════════

STOCK_POOL_2024 = [
    ("sh600519", "贵州茅台"),  ("sh601318", "中国平安"),
    ("sz000858", "五粮液"),    ("sz000333", "美的集团"),
    ("sh600036", "招商银行"),  ("sz002475", "立讯精密"),
    ("sh601012", "隆基绿能"),  ("sz300750", "宁德时代"),
    ("sh600276", "恒瑞医药"),  ("sz002594", "比亚迪"),
    ("sh601888", "中国中免"),  ("sz000001", "平安银行"),
    ("sh600887", "伊利股份"),  ("sh601328", "交通银行"),
    ("sz000568", "泸州老窖"),  ("sh600309", "万华化学"),
    ("sz002415", "海康威视"),  ("sh600585", "海螺水泥"),
    ("sh601398", "工商银行"),  ("sz000338", "潍柴动力"),
]


def run_t2_ashare(year: int = 2024, initial: float = 1_000_000) -> List[dict]:
    """
    运行 T2 A股策略（在腾讯证券数据上回测）
    包括：定风波择时、黑色星期四、MACD择时、布林带择时
    """
    from strategies.backtest_engine import backtest_signal

    print(f"\n{'='*60}")
    print(f"  📊 T2级 · A股策略（腾讯证券数据）")
    print(f"  年份: {year} | 初始资金: {initial:,.0f}")
    print(f"{'='*60}")

    # 用上证指数模拟 ETF（腾讯证券部分指数受限，用代表性股票代替）
    # 选取 sh600519 茅台 作为"A股大盘proxy"
    print("  获取数据（茅台=大盘proxy）...")
    rows = fetch_ashare("sh600519", year)
    if not rows or len(rows) < 100:
        print("  ❌ 数据不足，尝试备用标的...")
        rows = fetch_ashare("sh601318", year)

    if not rows:
        print("  ❌ 无法获取数据")
        return []

    closes = [r["close"] for r in rows]
    highs  = [r["high"]  for r in rows]
    lows   = [r["low"]   for r in rows]
    opens  = [r["open"]  for r in rows]
    vols   = [r["volume"] for r in rows]

    print(f"  ✅ 数据: {len(rows)} 条  {rows[0]['date']} → {rows[-1]['date']}")

    strategies = [
        ("T2-08 定风波择时",       lambda c,h,l,o,v: signal_dingfengbo(c,h,l,o,v)),
        ("T2-09 黑色星期四",       lambda c,h,l,o,v: signal_black_thursday(c,h,l,o,v)),
        ("T2-11 布林带(20,2)",     lambda c,h,l,o,v: signal_boll_ashare(c,h,l,o,v)),
        ("T2-11 MACD(12,26,9)",   lambda c,h,l,o,v: signal_macd_ashare(c,h,l,o,v)),
    ]

    results = []
    for name, fn in strategies:
        r = backtest_signal(name, rows, fn, initial=initial)
        if r:
            results.append(r)
            icon = "✅" if r["ann_return_pct"] > 0 else "⚠️"
            print(f"  {icon} {name}: 年化 {r['ann_return_pct']:+.1f}% | "
                  f"夏普 {r['sharpe']:.2f} | 回撤 {r['max_drawdown_pct']:.1f}% | "
                  f"交易 {r['total_trades']}次 | 胜率 {r['win_rate_pct']:.0f}%")

    if results:
        print(f"\n  {'策略':<25} {'年化':>8} {'夏普':>6} {'回撤':>7} {'交易':>5}")
        print(f"  {'-'*55}")
        for r in sorted(results, key=lambda x: x["ann_return_pct"], reverse=True):
            print(f"  {r['strategy']:<25} {r['ann_return_pct']:>+7.1f}% "
                  f"{r['sharpe']:>6.2f} {r['max_drawdown_pct']:>6.1f}% {r['total_trades']:>5d}")

    return results


if __name__ == "__main__":
    run_t2_ashare(2024)
