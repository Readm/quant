"""
xb_tier1_binance.py — 邢不行策略 · 第一级（Binance 可跑）
============================================================
数据：Binance 公开 API，无需 Key
覆盖：BTC/ETH/SOL 等主流币 + 全市场小币扫描

策略列表（8个）：
  T1-01  10年400倍模拟     小市值（选最近涨幅最小/市值最小币）
  T1-02  定投策略          每周/每月等额定投
  T1-03  动量轮动          月度动量最强币轮动
  T1-04  双均线共振        MA5>MA20 AND MA20>MA60 金叉
  T1-05 布林带加强版       多参数布林带 + 成交量确认
  T1-06  MACD多周期        日线+4H MACD共振
  T1-07  RSI超卖抄底       RSI<30 超卖区域买入
  T1-08  跳空过滤策略     过滤假跳空，趋势确认后入场
"""

import sys, math, json, ssl, urllib.request
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Callable

sys.path.insert(0, str(Path(__file__).parent.parent))
from strategies.backtest_engine import backtest_signal

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# ═══════════════════════════════════════════════════════════════
# 数据获取
# ═══════════════════════════════════════════════════════════════

def _simulate_price_data(symbol: str, start: str, end: str,
                          interval: str = "1d",
                          base_price: float = 50000) -> List[dict]:
    """当 Binance 无法访问时，使用几何布朗运动生成模拟数据"""
    import random, math
    rows = []
    try:
        s = datetime.strptime(start, "%Y%m%d")
        e = datetime.strptime(end, "%Y%m%d")
    except:
        s = datetime(2020, 1, 1)
        e = datetime(2024, 12, 31)

    price = base_price
    vol_year = 0.80   # 年化波动率 80%（BTC 典型值）
    dt_days = 1 if interval in ("1d", "1m") else (4/96 if interval == "4h" else 0.125)
    dt_yr = dt_days / 365
    drift = 0.20      # 年化漂移 20%（长期牛市假设）

    current = s
    while current <= e:
        if current.weekday() < 5:  # 跳过周末（币圈不休，但降低数据量）
            if interval == "1d":
                z = random.gauss(0, 1)
                ret = drift * dt_yr + vol_year * math.sqrt(dt_yr) * z
                price *= math.exp(ret)
                o = price * (1 + random.uniform(-0.005, 0.005))
                h = price * (1 + random.uniform(0, 0.015))
                l = price * (1 - random.uniform(0, 0.015))
                v = random.uniform(1e9, 5e10)
                rows.append({
                    "date":   current.strftime("%Y-%m-%d"),
                    "open":   round(o, 2), "high": round(h, 2),
                    "low":    round(l, 2), "close": round(price, 2),
                    "volume": round(v, 0),
                    "symbol": symbol,
                })
        if interval == "1d":
            current += timedelta(days=1)
        elif interval == "4h":
            current += timedelta(hours=4)
        else:
            current += timedelta(days=1)

        if len(rows) >= 1500:
            break

    return rows


def fetch_binance(symbol: str, interval: str = "1d",
                  start: str = "20200101", end: str = "20251231",
                  limit: int = 1000) -> List[dict]:
    """Binance K线 → OHLCV list（网络不可用时自动回退到模拟数据）"""
    start_ms = int(datetime.strptime(start, "%Y%m%d").timestamp() * 1000)
    end_ms   = int(datetime.strptime(end,   "%Y%m%d").timestamp() * 1000)
    url = (f"https://api.binance.com/api/v3/klines"
           f"?symbol={symbol}&interval={interval}"
           f"&startTime={start_ms}&endTime={end_ms}&limit={limit}")

    _fetched = False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=CTX, timeout=8) as r:
            data = json.loads(r.read().decode())
        if data:
            rows = []
            for it in data:
                rows.append({
                    "date":   datetime.fromtimestamp(it[0] / 1000).strftime("%Y-%m-%d"),
                    "open":   float(it[1]), "high":   float(it[2]),
                    "low":    float(it[3]), "close":  float(it[4]),
                    "volume": float(it[5]),
                    "symbol": symbol,
                })
            if rows:
                _fetched = True
                print(f"  🌐 Binance 获取 {symbol} 成功: {len(rows)} 条")
                return rows
    except Exception:
        pass

    # 回退：使用模拟数据
    base_prices = {"BTCUSDT": 50000, "ETHUSDT": 3000, "SOLUSDT": 100,
                   "BNBUSDT": 300, "XRPUSDT": 1.0, "ADAUSDT": 1.5}
    base = base_prices.get(symbol, 1000)
    rows = _simulate_price_data(symbol, start, end, interval, base)
    print(f"  🎭 [模拟] {symbol}: {len(rows)} 条 {rows[0]['date']} → {rows[-1]['date']}")
    return rows


def fetch_binance_all_symbols() -> List[str]:
    """获取 Binance 所有 USDT 现货币对"""
    url = "https://api.binance.com/api/v3/exchangeInfo"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=CTX, timeout=15) as r:
            data = json.loads(r.read().decode())
        return [s["symbol"] for s in data["symbols"]
                if s["status"] == "TRADING" and s["quoteAsset"] == "USDT"]
    except:
        return []


def fetch_multi_timeframe(symbol: str, start: str, end: str) -> Dict[str, List[dict]]:
    """获取多时间周期数据：日线 + 4H"""
    d1 = fetch_binance(symbol, "1d", start, end, 1000)
    h4 = fetch_binance(symbol, "4h", start, end, 1000)
    return {"1d": d1, "4h": h4}


# ═══════════════════════════════════════════════════════════════
# 指标计算
# ═══════════════════════════════════════════════════════════════

def ma(arr: List[float], n: int) -> List[float]:
    out = []
    for i in range(len(arr)):
        out.append(sum(arr[max(0,i-n+1):i+1]) / min(n, i+1))
    return out

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
        subset = closes[max(0,i-n+1):i+1]
        m = sum(subset)/len(subset)
        std.append(math.sqrt(sum((x-m)**2 for x in subset)/len(subset)))
    mid = ma(closes, n)
    upper = [m + mult*s for m, s in zip(mid, std)]
    lower = [m - mult*s for m, s in zip(mid, std)]
    return upper, mid, lower

def macd(closes: List[float], f: int = 12, s: int = 26, sig: int = 9):
    ef = ema(closes, f)
    es = ema(closes, s)
    dif = [ef[i]-es[i] for i in range(len(ef))]
    dea = [sum(dif[max(0,i-sig+1):i+1])/min(sig,i+1) for i in range(len(dif))]
    return dif, dea

def rsi(closes: List[float], n: int = 14):
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    avg_g = ma(gains, n); avg_l = ma(losses, n)
    return [100-100/(1+a/b) if b>0 else 50 for a,b in zip(avg_g, avg_l)]

def atr(highs, lows, closes, n: int = 14):
    trs = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
           for i in range(1, len(highs))]
    return ma([0.0]+trs, n)

def top_momentum_rank(symbols: List[str], end: str, days: int = 30) -> List[tuple]:
    """
    返回：[(symbol, momentum_return), ...]，按动量排序
    用于月度动量轮动选币
    """
    results = []
    for sym in symbols[:30]:  # 限制数量避免慢
        rows = fetch_binance(sym, "1d",
                             (datetime.strptime(end,"%Y%m%d")-timedelta(days=days+5)).strftime("%Y%m%d"),
                             end, 100)
        if not rows or len(rows) < days//2:
            continue
        ret = (rows[-1]["close"] - rows[0]["close"]) / rows[0]["close"]
        results.append((sym, ret))
    return sorted(results, key=lambda x: x[1], reverse=True)


# ═══════════════════════════════════════════════════════════════
# T1-01  10年400倍模拟策略（小市值/低估值币版）
# ================================================================
# 原理：邢不行10年400倍策略 = 每月选市值最小10只股等额买入
# 币圈版：每7天选流通量最小或价格最低的币，等额配置
# 说明：币圈无"市值"概念，用 price * supply 有误差，用"历史低币"替代
# ═══════════════════════════════════════════════════════════════

def signal_small_cap_crypto(closes: List[float], highs: List[float],
                              lows: List[float], opens: List[float],
                              volumes: List[float],
                              lookback: int = 20,
                              entry_pct: float = 0.3) -> List[int]:
    """
    小市值（低价）模拟策略：
    - 每天计算过去 N 日收益率，收益率最小的币被视为"低估值/落后币"
    - 买入后持有固定天数，用动量作为 proxy
    - 这模拟了"买最便宜资产"的思想
    """
    if len(closes) < lookback + 5:
        return [0] * len(closes)

    momentum = []
    for i in range(lookback, len(closes)):
        ret = (closes[i] - closes[i-lookback]) / closes[i-lookback]
        momentum.append(ret)

    sig = [0] * len(closes)
    hold_days = 5  # 持有5天后强制平仓
    position_open = False
    hold_counter = 0

    for i in range(lookback, len(closes)):
        idx = i - lookback

        if not position_open:
            if momentum[idx] < -0.05:  # 跌幅超过5%视为被错杀的"低估值"
                sig[i] = 1
                position_open = True
                hold_counter = hold_days
        else:
            hold_counter -= 1
            if hold_counter <= 0:
                sig[i] = -1
                position_open = False

    return sig


# ═══════════════════════════════════════════════════════════════
# T1-02  定投策略（Dollar Cost Averaging）
# ═══════════════════════════════════════════════════════════════

def signal_dca(closes: List[float], highs: List[float],
                lows: List[float], opens: List[float],
                volumes: List[float],
                dca_interval_days: int = 7,
                dca_amount_pct: float = 0.1) -> List[int]:
    """
    定投策略：每 N 天投入固定金额买币
    - 无论价格高低，定期买入（等额）
    - RSI(14) > 75 且年度收益 > 50% → 止盈卖出
    - 持仓超过 90 天 → 强制平仓（防套牢）
    """
    if len(closes) < 30:
        return [0] * len(closes)

    rv = rsi(closes, 14)
    sig = [0] * len(closes)
    in_pos = False
    entry_prices = []     # 历次买入价
    days_held = 0

    for i in range(1, len(closes)):
        # RSI 对应 closes[i] → 用 rv[i-1]
        rvi = rv[i-1] if i-1 < len(rv) else 50
        annual_ret = 0.0
        if entry_prices:
            avg_entry = sum(entry_prices) / len(entry_prices)
            annual_ret = (closes[i] - avg_entry) / avg_entry

        # 买入：每 N 天定投一次，且未持仓
        if (i % dca_interval_days == 0) and not in_pos:
            sig[i] = 1
            in_pos = True
            entry_prices.append(closes[i])
            days_held = 0

        elif in_pos:
            days_held += 1
            # 卖出：RSI超买 或 年度收益>50% 或 持有超过90天
            if rvi > 75 or annual_ret > 0.5 or days_held > 90:
                sig[i] = -1
                in_pos = False
                entry_prices = []

    return sig


# ═══════════════════════════════════════════════════════════════
# T1-03  动量轮动（月度动量最强币）
# ═══════════════════════════════════════════════════════════════

def signal_momentum_rotation(closes: List[float], highs: List[float],
                               lows: List[float], opens: List[float],
                               volumes: List[float],
                               fast: int = 5, slow: int = 20,
                               mom_days: int = 30) -> List[int]:
    """
    动量轮动策略（邢不行课程内容）：
    - 每月计算各币动量（近N日收益率）
    - 选动量最强币买入
    - 动量转负时切换
    信号：MA5 上穿 MA20 且近 mom_days 日收益率为正 → 买入
    """
    if len(closes) < slow + 5:
        return [0] * len(closes)

    m1 = ma(closes, fast)
    m2 = ma(closes, slow)
    sig = [0] * len(closes)

    for i in range(slow, len(closes)):
        mom = (closes[i] - closes[i-mom_days]) / closes[i-mom_days] if i >= mom_days else 0

        # 金叉 + 动量为正
        if (m1[i-1] <= m2[i-1] and m1[i] > m2[i]) and mom > 0:
            sig[i] = 1
        # 死叉 → 平仓
        elif m1[i-1] >= m2[i-1] and m1[i] < m2[i]:
            sig[i] = -1
        # 动量转负 → 止损
        elif mom < -0.1:
            sig[i] = -1

    return sig


# ═══════════════════════════════════════════════════════════════
# T1-04  双均线共振（多均线金叉）
# ═══════════════════════════════════════════════════════════════

def signal_ma_resonance(closes: List[float], highs: List[float],
                          lows: List[float], opens: List[float],
                          volumes: List[float],
                          ma1: int = 5, ma2: int = 20, ma3: int = 60,
                          require_both: bool = True) -> List[int]:
    """
    多均线共振策略：
    - MA5 > MA20 > MA60（三线多头排列）
    - MA5 上穿 MA20 → 买入
    - MA5 下穿 MA20 → 卖出
    require_both=True 时，要求三线多头才持仓
    """
    if len(closes) < ma3 + 5:
        return [0] * len(closes)

    m1 = ma(closes, ma1)
    m2 = ma(closes, ma2)
    m3 = ma(closes, ma3)
    sig = [0] * len(closes)

    in_position = False

    for i in range(ma3, len(closes)):
        golden_cross = (m1[i-1] <= m2[i-1] and m1[i] > m2[i])
        dead_cross   = (m1[i-1] >= m2[i-1] and m1[i] < m2[i])

        if not in_position:
            if golden_cross:
                if not require_both or (m2[i] > m3[i]):
                    sig[i] = 1
                    in_position = True
        else:
            if dead_cross or (m2[i] < m3[i] and require_both):
                sig[i] = -1
                in_position = False

    return sig


# ═══════════════════════════════════════════════════════════════
# T1-05  布林带加强版（多参数 + 成交量确认）
# ═══════════════════════════════════════════════════════════════

def signal_boll_enhanced(closes: List[float], highs: List[float],
                           lows: List[float], opens: List[float],
                           volumes: List[float],
                           n_list: List[int] = [10, 20, 30],
                           k: float = 2.0,
                           vol_threshold: float = 1.5) -> List[int]:
    """
    布林带加强版：
    - 三组布林带共振（10/20/30日）
    - 价格触及任意两组下轨且成交量放大 → 买入
    - 价格触及上轨 → 卖出
    """
    all_upper, all_lower = [], []
    for n in n_list:
        u, _, l = boll_bands(closes, n, k)
        all_upper.append(u)
        all_lower.append(l)

    avg_vol = ma(volumes, 20)
    sig = [0] * len(closes)

    for i in range(30, len(closes)):
        vol_ratio = volumes[i] / max(avg_vol[i], 1e-9)

        # 统计触及下轨的布林带数量
        lower_touches = sum(
            1 for n_idx in range(len(n_list))
            if i >= n_list[n_idx] and closes[i] <= all_lower[n_idx][i]
        )
        upper_touches = sum(
            1 for n_idx in range(len(n_list))
            if i >= n_list[n_idx] and closes[i] >= all_upper[n_idx][i]
        )

        # 买入：至少2组布林带触及下轨 + 成交量放大
        if lower_touches >= 2 and vol_ratio > vol_threshold:
            sig[i] = 1
        # 卖出：任意1组触及上轨
        elif upper_touches >= 1:
            sig[i] = -1

    return sig


# ═══════════════════════════════════════════════════════════════
# T1-06  MACD 多周期共振
# ═══════════════════════════════════════════════════════════════

def signal_macd_multi_timeframe(
        closes: List[float], highs: List[float],
        lows: List[float], opens: List[float],
        volumes: List[float],
        d1_rows: List[dict],
        fast: int = 12, slow: int = 26, sig: int = 9) -> List[int]:
    """
    MACD 多周期共振：
    - 日线 DIF 上穿 DEA → 买入
    - 4H DIF 下穿 DEA → 降仓/止损参考
    - 只在两周期同向时重仓
    d1_rows: 日线数据（用于计算日线MACD）
    """
    if not d1_rows or len(d1_rows) < slow + sig:
        return [0] * len(closes)

    d1_closes = [r["close"] for r in d1_rows]

    dif_d1, dea_d1 = macd(d1_closes, fast, slow, sig)
    dif_h4, dea_h4 = macd(closes, fast, slow, sig)

    # 对齐4H数据到日线（简化处理：取每根日线的最后一条4H）
    # 实际应用需要更精确的对齐，这里用索引映射
    d1_len = len(d1_closes)
    ratio = max(len(closes) // max(d1_len, 1), 1)

    sig_out = [0] * len(closes)
    in_pos = False

    for i in range(slow+sig, len(closes)):
        d1_idx = min(i // ratio, len(dif_d1) - 1)

        dif_d = dif_d1[d1_idx] if d1_idx < len(dif_d1) else 0
        dea_d = dea_d1[d1_idx] if d1_idx < len(dea_d1) else 0
        dif_h = dif_h4[i]
        dea_h = dea_h4[i]

        d1_golden = (dif_d > dea_d)
        d1_dead   = (dif_d < dea_d)
        h4_golden = (dif_h > dea_h)
        h4_dead   = (dif_h < dea_h)

        if not in_pos:
            if d1_golden and h4_golden:
                sig_out[i] = 1
                in_pos = True
        else:
            if d1_dead and h4_dead:
                sig_out[i] = -1
                in_pos = False

    return sig_out


# ═══════════════════════════════════════════════════════════════
# T1-07  RSI 超卖抄底策略
# ═══════════════════════════════════════════════════════════════

def signal_rsi_oversold(closes: List[float], highs: List[float],
                           lows: List[float], opens: List[float],
                           volumes: List[float],
                           rsi_n: int = 14,
                           oversold: float = 35,
                           overbought: float = 70,
                           confirm_bars: int = 2) -> List[int]:
    """
    RSI 超卖抄底策略：
    - RSI < oversold 区域连续 N 根K线 → 买入
    - RSI > overbought → 卖出
    - 配合价格创 N 日新低过滤假信号
    原理：邢不行课程中"反过度自信"在币圈的应用
    """
    if len(closes) < rsi_n + 5:
        return [0] * len(closes)

    rv = rsi(closes, rsi_n)
    sig = [0] * len(closes)
    consecutive_oversold = 0
    # rv[i-1] 对应 closes[i] 的RSI（RSI从closes[1]开始计算）
    rv_offset = 1

    for i in range(rsi_n, len(closes)):
        rvi = rv[i - rv_offset] if (i - rv_offset) >= 0 else 50
        lowest_n = min(lows[max(0, i-confirm_bars):i+1])
        price_low = lows[i] <= lowest_n

        if rvi < oversold:
            consecutive_oversold += 1
        else:
            consecutive_oversold = 0

        # RSI超卖 + 价格创新低（恐慌极点）
        if consecutive_oversold >= confirm_bars and price_low:
            sig[i] = 1
            consecutive_oversold = 0
        # RSI超买 → 卖出
        elif rvi > overbought:
            sig[i] = -1

    return sig


# ═══════════════════════════════════════════════════════════════
# T1-08  跳空过滤策略（假跳空识别）
# ═══════════════════════════════════════════════════════════════

def signal_gap_filter(closes: List[float], highs: List[float],
                         lows: List[float], opens: List[float],
                         volumes: List[float],
                         gap_threshold: float = 0.02,
                         confirm_ma: int = 20) -> List[int]:
    """
    跳空过滤策略：
    - 识别超过 threshold% 的跳空
    - 假跳空：价格3日内回补缺口 → 逆势买入
    - 真跳空：顺势突破 → 跟势
    - 用 MA20 趋势过滤
    来源：邢不行量化小讲堂系列，跳空策略升级版
    """
    if len(closes) < 10:
        return [0] * len(closes)

    m20 = ma(closes, confirm_ma)
    sig = [0] * len(closes)

    for i in range(1, len(closes)):
        gap = (opens[i] - closes[i-1]) / closes[i-1]
        trend_up = m20[i] > m20[i-1] if i >= confirm_ma else True

        # 向上跳空（高开）
        if gap > gap_threshold:
            # 是否在3日内回补？
            filled = any(closes[i+j] <= closes[i-1] for j in range(1, min(4, len(closes)-i)))
            if filled:
                # 假跳空（高开低走）→ 卖出
                sig[i] = -1
            elif trend_up:
                # 真跳空 → 顺势买入
                sig[i] = 1

        # 向下跳空（低开）
        elif gap < -gap_threshold:
            filled = any(closes[i+j] >= closes[i-1] for j in range(1, min(4, len(closes)-i)))
            if filled:
                # 假跳空（下探回升）→ 买入
                sig[i] = 1
            elif not trend_up:
                # 真跳空 → 顺势做空
                sig[i] = -1

    return sig


# ═══════════════════════════════════════════════════════════════
# 运行器
# ═══════════════════════════════════════════════════════════════

STRATEGY_T1 = [
    ("T1-01 小市值模拟(400倍)",      signal_small_cap_crypto,     {"lookback": 20}),
    ("T1-02 定投策略(DCA)",          signal_dca,                  {"dca_interval_days": 7}),
    ("T1-03 动量轮动(月度)",          signal_momentum_rotation,    {"fast": 5, "slow": 20, "mom_days": 30}),
    ("T1-04 多均线共振(5/20/60)",    signal_ma_resonance,         {"ma1": 5, "ma2": 20, "ma3": 60}),
    ("T1-05 布林带加强版(多参数)",    signal_boll_enhanced,        {"n_list": [10, 20, 30], "k": 2.0}),
    ("T1-06 MACD多周期共振",          signal_macd_multi_timeframe, {"fast": 12, "slow": 26, "sig": 9}),
    ("T1-07 RSI超卖抄底",            signal_rsi_oversold,         {"rsi_n": 14, "oversold": 35, "overbought": 70}),
    ("T1-08 跳空过滤策略",            signal_gap_filter,           {"gap_threshold": 0.02}),
]


def run_tier1(symbol: str = "BTCUSDT", start: str = "20200101",
              end: str = "20251231",
              tf: str = "1d",
              initial: float = 1_000_000) -> List[dict]:
    """下载数据并运行所有 T1 策略"""
    print(f"\n{'='*60}")
    print(f"  🏛️  邢不行策略 T1级（Binance 可跑）")
    print(f"  标的: {symbol} | 时间: {start} → {end} | 周期: {tf}")
    print(f"{'='*60}")

    rows = fetch_binance(symbol, tf, start, end)
    if not rows:
        print("  ❌ 数据获取失败"); return []

    closes = [r["close"] for r in rows]
    highs  = [r["high"]  for r in rows]
    lows   = [r["low"]   for r in rows]
    opens  = [r["open"]  for r in rows]
    vols   = [r["volume"] for r in rows]

    # T1-06 需要多周期数据（先获取日线备用）
    d1_rows = fetch_binance(symbol, "1d", start, end, 1500)

    results = []
    for name, fn, params in STRATEGY_T1:

        def make_signal(c, h, l, o, v, _fn=fn, _p=params, _d1=d1_rows):
            # T1-06 特殊处理：注入日线数据
            if _fn.__name__ == "signal_macd_multi_timeframe":
                return _fn(c, h, l, o, v, d1_rows=_d1, **_p)
            return _fn(c, h, l, o, v, **_p)

        try:
            r = backtest_signal(name, rows, make_signal, initial=initial)
            if r:
                results.append(r)
                print(f"  ✅ {name}: 年化 {r['ann_return_pct']:+.1f}% | "
                      f"夏普 {r['sharpe']:.2f} | 回撤 {r['max_drawdown_pct']:.1f}% | "
                      f"交易 {r['total_trades']}次 | 胜率 {r['win_rate_pct']:.0f}%")
        except Exception as e:
            print(f"  ❌ {name}: {e}")

    if results:
        print(f"\n  📊 策略排序（按年化收益）：")
        print(f"  {'策略':<30} {'年化':>8} {'夏普':>6} {'回撤':>7} {'交易':>5}")
        print(f"  {'-'*58}")
        for r in sorted(results, key=lambda x: x["ann_return_pct"], reverse=True):
            print(f"  {r['strategy']:<30} {r['ann_return_pct']:>+7.1f}% "
                  f"{r['sharpe']:>6.2f} {r['max_drawdown_pct']:>6.1f}% {r['total_trades']:>5d}")

    return results


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    run_tier1(sym, "20200101", "20251231", "1d")
