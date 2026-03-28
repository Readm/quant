"""
market_data.py — 纯实盘数据层（已移除合成数据 fallback）
=======================================================
数据优先级：
  1. Stooq.com（日频，A股/港股/美股/加密货币）
  2. akshare（A股实时 + 期货 + 黄金）

⚠️ 彻底移除 generate_synthetic()，数据不可用时直接报错，不降级。
"""

import math, ssl, time, random
import urllib.request
from typing import Optional, Dict, List

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


# ══════════════════════════════════════════════════════
#  数据源 1：Stooq.com（日频 OHLCV，真实市场数据）
# ══════════════════════════════════════════════════════

STOOQ_MAP = {
    # Crypto
    "BTCUSDT":  ("btc.v",   "crypto"),
    "ETHUSDT":  ("eth.v",   "crypto"),
    "SOLUSDT":  ("sol.v",   "crypto"),
    # US stocks
    "AAPL":     ("aapl.us", "stock"),
    "NVDA":     ("nvda.us", "stock"),
    "TSLA":     ("tsla.us", "stock"),
    "MSFT":     ("msft.us", "stock"),
    "GOOGL":    ("googl.us","stock"),
    "AMZN":     ("amzn.us", "stock"),
    "SPY":      ("spy.us",  "etf"),
    "QQQ":      ("qqq.us",  "etf"),
    # HK stocks
    "00700.HK": ("700.hk",  "stock"),
    "09988.HK": ("9988.hk", "stock"),
    # China A-shares (需要 .SH / .SZ 后缀)
    "000001.SH":("000001.sh","stock"),
    "000300.SH":("000300.sh","stock"),  # 沪深300
    "510300.SH":("510300.sh","etf"),
    "600519.SH":("600519.sh","stock"),  # 贵州茅台
}


def fetch_stooq(symbol: str, start_date: str = "20230101",
                end_date: str = "20241231", n: int = 500) -> Optional[dict]:
    """
    从 Stooq 获取真实 OHLCV 数据。
    成功返回标准 dict，失败返回 None（不再降级）。
    """
    code, _ = STOOQ_MAP.get(symbol.upper(), (None, None))
    if not code:
        return None

    url = (f"https://stooq.com/q/d/l/?s={code}&d1={start_date}"
           f"&d2={end_date}&i=d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            raw = r.read().decode("utf-8")
    except Exception as e:
        print(f"  [Stooq] {symbol} fetch failed: {e}")
        return None

    rows = []
    for line in raw.strip().split("\n"):
        if not line or line.startswith("Date"):
            continue
        p = line.split(",")
        if len(p) < 6:
            continue
        try:
            rows.append({
                "date":  p[0].strip(),
                "open":  float(p[1]),
                "high":  float(p[2]),
                "low":   float(p[3]),
                "close": float(p[4]),
                "vol":   float(p[5]),
            })
        except ValueError:
            continue

    rows.reverse()  # oldest → newest
    if len(rows) < 30:
        print(f"  [Stooq] {symbol}: 仅获取 {len(rows)} 天数据，数据不足")
        return None

    if n > 0 and len(rows) > n:
        rows = rows[-n:]

    return {
        "symbol":  symbol,
        "dates":   [r["date"]  for r in rows],
        "opens":   [r["open"]  for r in rows],
        "highs":   [r["high"]  for r in rows],
        "lows":    [r["low"]   for r in rows],
        "closes":  [r["close"] for r in rows],
        "volumes": [r["vol"]   for r in rows],
        "source":  "Stooq.com",
    }


# ══════════════════════════════════════════════════════
#  数据源 2：akshare（A 股 + 期货 + 黄金）
# ══════════════════════════════════════════════════════

def fetch_akshare(symbol: str, period: str = "daily",
                  adjust: str = "qfq", n: int = 500) -> Optional[dict]:
    """
    用 akshare 获取 A 股实时数据。
    支持沪深主板、创业板、科创板。
    """
    try:
        import akshare as ak
    except ImportError:
        print(f"  [akshare] 未安装，跳过 {symbol}")
        return None

    # 期货/黄金
    futures = {"AU2404.SHF": "gold", "CU2404.SMF": "copper"}
    if symbol.upper() in futures:
        try:
            df = ak.futures_zh_spot(symbol="AF")
            return _parse_ak_df(df, symbol)
        except Exception as e:
            print(f"  [akshare] {symbol} futures failed: {e}")
            return None

    # A 股：转换格式
    stype, codes = _resolve_akshare_code(symbol)
    if not codes:
        return None

    try:
        if stype == "stock":
            df = ak.stock_zh_a_hist(symbol=codes, period=period,
                                     start_date="20230101",
                                     end_date="20241231",
                                     adjust=adjust)
        elif stype == "index":
            df = ak.stock_zh_index_daily(symbol=codes)
        else:
            return None
        return _parse_ak_df(df, symbol)
    except Exception as e:
        print(f"  [akshare] {symbol} failed: {e}")
        return None


def _resolve_akshare_code(symbol: str) -> tuple:
    """将常见代码映射为 akshare 需要的格式"""
    mapping = {
        "000001.SH": ("stock", "000001"),
        "000001.SZ": ("stock", "000001"),
        "600519.SH": ("stock", "600519"),
        "000300.SH": ("index", "000300"),
        "399001.SZ": ("index", "399001"),
        "399006.SZ": ("index", "399006"),
    }
    return mapping.get(symbol.upper(), (None, None))


def _parse_ak_df(df, symbol: str) -> Optional[dict]:
    """将 akshare DataFrame 解析为标准格式"""
    try:
        import pandas as pd
        if df is None or (hasattr(df, "empty") and df.empty):
            return None
        df = df.tail(500)
        return {
            "symbol":  symbol,
            "dates":   df["日期"].astype(str).tolist() if "日期" in df.columns else [],
            "opens":   df["开盘"].tolist()    if "开盘" in df.columns else [],
            "highs":   df["最高"].tolist()    if "最高" in df.columns else [],
            "lows":    df["最低"].tolist()    if "最低" in df.columns else [],
            "closes":  df["收盘"].tolist()    if "收盘" in df.columns else [],
            "volumes": df["成交量"].tolist() if "成交量" in df.columns else [],
            "source":  "akshare",
        }
    except Exception:
        return None


# ══════════════════════════════════════════════════════
#  技术指标计算（基于真实数据）
# ══════════════════════════════════════════════════════

def compute_indicators(closes, highs=None, lows=None) -> dict:
    """
    计算完整技术指标集（无合成数据依赖）。
    输入：真实 OHLC 序列
    """
    n = len(closes)
    if highs is None: highs = closes
    if lows  is None: lows  = closes

    # ── 简单移动平均 ───────────────────────
    def ma(p):
        out = [0.0] * n
        for i in range(p - 1, n):
            out[i] = sum(closes[i - p + 1:i + 1]) / p
        return out

    # ── EMA ──────────────────────────────
    def ema(p):
        k = 2 / (p + 1)
        out = [closes[0]] * n
        for i in range(1, n):
            out[i] = closes[i] * k + out[i - 1] * (1 - k)
        return out

    # ── RSI ──────────────────────────────
    def rsi(p=14):
        out = [50.0] * n
        for i in range(p, n):
            gains  = sum(max(0.0, closes[j] - closes[j-1]) for j in range(i-p+1, i+1))
            losses = sum(max(0.0, closes[j-1] - closes[j]) for j in range(i-p+1, i+1))
            ag = gains / p
            al = losses / p
            out[i] = 100 - 100 / (1 + ag / (al + 1e-9))
        return out

    # ── ATR ──────────────────────────────
    def atr(p=14):
        trs = [0.0] * n
        for i in range(1, n):
            trs[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i]  - closes[i - 1]),
            )
        out = [trs[0]] * n
        for i in range(p, n):
            out[i] = sum(trs[i - p + 1:i + 1]) / p
        return out

    # ── ADX（简化趋势强度）────────────────
    def adx(p=14):
        ma_p  = ma(p)
        adx_v = [0.0] * n
        for i in range(p * 2, n):
            run = abs(ma_p[i] - ma_p[i - p * 2])
            tr  = (highs[i] - lows[i]) + 1e-9
            pdi = max(0.0, highs[i] - highs[i-p]) / tr * 100
            mdi = max(0.0, lows[i-p]  - lows[i])  / tr * 100
            dx  = abs(pdi - mdi) / (pdi + mdi + 1e-9) * 100
            adx_v[i] = adx_v[i-1] * 0.7 + dx * 0.3  # 平滑
        return adx_v

    # ── MACD ─────────────────────────────
    e12  = ema(12);  e26  = ema(26)
    macd = [0.0] * n
    for i in range(26, n):
        macd[i] = e12[i] - e26[i]
    sig_k  = 2 / (9 + 1)
    macd_s = [macd[0]] * n
    for i in range(9, n):
        macd_s[i] = macd[i] * sig_k + macd_s[i-1] * (1 - sig_k)
    macd_h = [0.0] * n
    for i in range(26, n):
        macd_h[i] = macd[i] - macd_s[i]

    # ── 布林带 ───────────────────────────
    def bbands(p=20, mult=2.0):
        mid = ma(p)
        std = [0.0] * n
        for i in range(p - 1, n):
            vals = closes[i-p+1:i+1]
            m    = mid[i]
            std[i] = math.sqrt(sum((v - m) ** 2 for v in vals) / p)
        upper = [mid[i] + mult * std[i] for i in range(n)]
        lower = [mid[i] - mult * std[i] for i in range(n)]
        return upper, mid, lower

    # ── 历史波动率 ───────────────────────
    log_rets = [0.0] * n
    for i in range(1, n):
        log_rets[i] = math.log(max(closes[i], 0.001) / max(closes[i-1], 0.001))
    hist_vol = [0.0] * n
    for i in range(20, n):
        vals  = log_rets[i-19:i+1]
        mu    = sum(vals) / 20
        hist_vol[i] = math.sqrt(sum((v - mu) ** 2 for v in vals) / 20) * math.sqrt(252)

    b_upper, b_mid, b_lower = bbands(20, 2.0)

    return {
        "ma5":       ma(5),
        "ma10":      ma(10),
        "ma20":      ma(20),
        "ma60":      ma(60),
        "ma120":     ma(120),
        "ema12":     e12,
        "ema26":     e26,
        "macd":      macd,
        "macd_signal": macd_s,
        "macd_hist": macd_h,
        "rsi14":     rsi(14),
        "rsi6":      rsi(6),
        "atr14":     atr(14),
        "adx":       adx(14),
        "bb_upper":  b_upper,
        "bb_mid":    b_mid,
        "bb_lower":  b_lower,
        "hist_vol":  hist_vol,
    }


# ══════════════════════════════════════════════════════
#  主数据生成器（纯实盘，不降级）
# ══════════════════════════════════════════════════════

class MarketDataGenerator:
    """
    统一实盘数据接口。
    ⚠️ 数据不可用时：打印错误，不降级到合成数据。
    """

    def __init__(self, days: int = 500, symbols: list = None):
        self.days    = days
        self.symbols = symbols or []
        self._cache: Dict[str, dict] = {}

    def get(self, symbol: str) -> Optional[dict]:
        """
        获取单个标的数据（优先 Stooq → akshare）。
        返回 None 表示数据不可用，系统应终止而非降级。
        """
        if symbol in self._cache:
            return self._cache[symbol]

        raw = None

        # 1. 优先 Stooq
        raw = fetch_stooq(symbol, n=self.days)

        # 2. Fallback akshare（A 股、期货）
        if raw is None:
            raw = fetch_akshare(symbol, n=self.days)

        # 3. 最终失败：不再降级
        if raw is None:
            print(f"  [错误] {symbol}: 无法获取实盘数据（已尝试 Stooq + akshare）")
            print(f"          请检查网络，或在 STOOQ_MAP / akshare 中添加该标的")
            self._cache[symbol] = None
            return None

        # 4. 计算指标
        closes = raw["closes"]
        highs  = raw.get("highs",  closes)
        lows   = raw.get("lows",   closes)

        if len(closes) < 60:
            print(f"  [错误] {symbol}: 仅 {len(closes)} 天数据，不足 60 天，无法计算指标")
            self._cache[symbol] = None
            return None

        ind        = compute_indicators(closes, highs, lows)
        returns    = [0.0] + [
            (closes[i] - closes[i-1]) / closes[i-1]
            for i in range(1, len(closes))
        ]

        result = {
            **raw,
            "returns":    returns,
            "indicators": ind,
        }
        self._cache[symbol] = result
        print(f"  [数据] {symbol}: ✅ {raw['source']} {len(closes)} 天真实数据")
        return result

    def get_multiple(self, symbols: list) -> Dict[str, dict]:
        """并发获取多标的，至少一个成功才继续"""
        results  = {}
        failures = []

        for sym in symbols:
            data = self.get(sym)
            if data is not None:
                results[sym] = data
            else:
                failures.append(sym)

        if failures:
            print(f"\n  [警告] 以下标的获取失败: {failures}")
            print(f"         这些标的将不参与后续回测\n")

        if not results:
            raise RuntimeError(
                "【致命错误】所有标的均无法获取实盘数据。"
                "请检查：\n"
                "  1. 网络连接是否正常\n"
                "  2. 标的代码是否在 STOOQ_MAP 中\n"
                "  3. akshare 是否已安装：pip install akshare\n"
                "已强制终止，不使用任何合成数据替代。"
            )

        return results

    def print_summary(self, results: dict):
        print(f"\n{'='*68}")
        print(f"  📊 实盘数据摘要（已移除合成数据）")
        print(f"{'='*68}")
        for sym, data in results.items():
            c = data["closes"]
            r = data["returns"]
            n = len(c)
            mu  = sum(r) / max(len(r), 1) * 252 * 100
            vol = math.sqrt(sum((x - mu/252)**2 for x in r) / max(len(r),1)) * math.sqrt(252) * 100
            peak    = max(c)
            trough_i = c.index(peak)
            trough  = min(c[trough_i:])
            max_dd  = (peak - trough) / peak * 100
            change  = (c[-1] / c[0] - 1) * 100
            print(f"  {sym:<14} {n:>3}天 {data['source']:<9} "
                  f"CPR {c[0]:>10.2f}→{c[-1]:>10.2f}  "
                  f"{change:>+7.1f}%  "
                  f"年化{mu:>+7.1f}%  波幅{vol:>5.1f}%  回撤{max_dd:>5.1f}%")
        print(f"{'='*68}\n")
