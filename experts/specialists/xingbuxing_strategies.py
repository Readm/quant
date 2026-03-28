"""
xingbuxing_strategies.py — 邢不行量化小讲堂·核心策略复刻
============================================================
数据来源：
  Binance K线 API → 加密货币（无API Key）
  Stooq → BTC/ETH 日线
  TuShare Pro Token → A股（待接入）

策略列表（共16个）：
  [已实现] Turtle         海龟交易法则     20日高低点突破
  [已实现] BollingerBB   布林带均值回归   价格触及布林带上下轨
  [已实现] KDJ_Xing      KDJ金叉死叉      J值穿越0/100信号
  [已实现] EMV_Strategy  简易波动指标     成交量加权价格变化率
  [已实现] ADX_Strategy  平均趋向指标     ADX>25趋势确认
  [已实现] GapFill       跳空缺口策略     向上跳空买、向下跳空卖
  [已实现] SmallCap400   小市值选股(模拟) 月末选最小市值持有一月
  [已实现] TurtleCrypto  海龟加密版       20日突破做多/做空
  [待A股]  FamaFrench3   Fama-French三因子 需市值+PB数据
  [待A股]  NewFortuneAnalyst 新财富分析师   需分析师评级数据
  [加密]   DollarCostAveraging 定投策略     BTC定期等额定投
  [加密]   MACD_Crypto   MACD择时          MACD金叉买死叉卖
  [加密]   RSI40_80      RSI超买超卖       RSI<40买 RSI>80卖
  [加密]   Grid4Ever     永远网格          等比例挂单持有加密
  [加密]   Momentum轮动  动量轮动          选动量最强币持有一个月
  [加密]   ComboMulti    多周期均线组合     MA5>MA20+MA60多周期共振
"""
import sys, math, json, ssl, urllib.request, time
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# ═══════════════════════════════════════════════════
#  数据获取
# ═══════════════════════════════════════════════════

def fetch_binance(symbol="BTCUSDT", interval="1d", start="20200101", end="20241231", limit=1000) -> List[dict]:
    """Binance K线 → [{date, open, high, low, close, volume}]"""
    start_ms = int(datetime.strptime(start, "%Y%m%d").timestamp() * 1000)
    end_ms   = int(datetime.strptime(end,   "%Y%m%d").timestamp() * 1000)
    url = (f"https://api.binance.com/api/v3/klines"
           f"?symbol={symbol}&interval={interval}"
           f"&startTime={start_ms}&endTime={end_ms}&limit={limit}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=CTX, timeout=15) as r:
            data = json.loads(r.read().decode())
        rows = []
        for it in data:
            rows.append({
                "date":   datetime.fromtimestamp(it[0] / 1000).strftime("%Y-%m-%d"),
                "open":   float(it[1]), "high":   float(it[2]),
                "low":    float(it[3]), "close":  float(it[4]),
                "volume": float(it[5]),
            })
        return rows
    except Exception as e:
        print(f"  [Binance] {symbol} 获取失败: {e}")
        return []

def fetch_stooq(sym, n=500) -> List[dict]:
    """Stooq → [{date, close}]"""
    url = f"https://stooq.com/q/d/l/?s={sym}&d1=20200101&d2=20241231&i=d"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=CTX, timeout=10) as r:
            raw = r.read().decode()
        rows = []
        for line in raw.strip().split("\r\n")[1:]:
            p = line.split(",")
            if len(p) >= 5:
                try:
                    rows.append({"date": p[0], "close": float(p[4])})
                except: pass
        rows.reverse()
        return rows[-n:]
    except Exception as e:
        return []

# ═══════════════════════════════════════════════════
#  指标计算
# ═══════════════════════════════════════════════════

def ma(arr, n):
    """简单移动平均"""
    out = []
    for i in range(len(arr)):
        if i < n - 1:
            out.append(sum(arr[:i+1])/(i+1))
        else:
            out.append(sum(arr[i-n+1:i+1])/n)
    return out

def ema(arr, n):
    """指数移动平均"""
    if not arr: return []
    k = 2/(n+1)
    out = [arr[0]]
    for i in range(1, len(arr)):
        out.append(arr[i]*k + out[-1]*(1-k))
    return out

def atr(highs, lows, closes, n=14):
    """Average True Range"""
    trs = [0.0]
    for i in range(1, len(highs)):
        tr = max(highs[i]-lows[i],
                 abs(highs[i]-closes[i-1]),
                 abs(lows[i]-closes[i-1]))
        trs.append(tr)
    return ma(trs, n)

def boll_bands(closes, n=20, mult=2.0):
    """布林带: (upper, mid, lower)"""
    std = []
    for i in range(len(closes)):
        if i < n-1:
            subset = closes[:i+1]
            m = sum(subset)/len(subset)
            v = sum((x-m)**2 for x in subset)/len(subset)
        else:
            subset = closes[i-n+1:i+1]
            m = sum(subset)/n
            v = sum((x-m)**2 for x in subset)/n
        std.append(math.sqrt(v))
    mid = ma(closes, n)
    upper = [m + mult*s for m, s in zip(mid, std)]
    lower = [m - mult*s for m, s in zip(mid, std)]
    return upper, mid, lower

def kdj(highs, lows, closes, n=9, m1=3, m2=3):
    """KDJ 指标"""
    k = [50.0] * n
    d = [50.0] * n
    for i in range(n, len(closes)):
        rsv = (closes[i]-min(lows[max(0,i-n):i+1])) / \
              (max(highs[max(0,i-n):i+1])-min(lows[max(0,i-n):i+1])+1e-9) * 100
        k.append(k[-1]*2/3 + rsv/3)
        d.append(d[-1]*2/3 + k[-1]/3)
    j = [3*k[i]-2*d[i] for i in range(len(k))]
    return k, d, j

def adx(highs, lows, closes, n=14):
    """ADX 平均趋向指数"""
    p_dm, m_dm, tr_arr = [], [], []
    for i in range(1, len(highs)):
        hp, hm = highs[i]-highs[i-1], lows[i-1]-lows[i]
        p_dm.append(hp if hp > hm and hp > 0 else 0)
        m_dm.append(hm if hm > hp and hm > 0 else 0)
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        tr_arr.append(tr)
    p_dm = [0.0]*n + p_dm
    m_dm = [0.0]*n + m_dm
    tr_arr = [0.0]*n + tr_arr
    p_di = [a/b*100 if b>0 else 0 for a, b in zip(ma(p_dm,n), ma(tr_arr,n))]
    m_di = [a/b*100 if b>0 else 0 for a, b in zip(ma(m_dm,n), ma(tr_arr,n))]
    dx = [abs(p_di[i]-m_di[i])/(p_di[i]+m_di[i]+1e-9)*100 for i in range(len(p_di))]
    adx_series = ma(dx, n)
    return adx_series, p_di, m_di

def emv(highs, lows, volumes, n=14):
    """EMV 简易波动指标"""
    emv = [0.0]
    for i in range(1, len(highs)):
        dm = (highs[i]+lows[i])/2 - (highs[i-1]+lows[i-1])/2
        br = volumes[i] / (highs[i]-lows[i]+1e-9)
        emv.append(dm/br if abs(br)>1e-9 else 0)
    emv_ma = ma(emv, n)
    return emv_ma

def macd(closes, fast=12, slow=26, signal=9):
    """MACD: (dif, dea, macd_hist)"""
    e_fast = ema(closes, fast)
    e_slow = ema(closes, slow)
    dif = [e_fast[i]-e_slow[i] for i in range(len(e_fast))]
    dea = ma(dif[-signal:], signal)
    # 简化：直接用EMA差值
    return dif, [0.0]*max(0, len(closes)-slow) + dif[slow:]

def rsi(closes, n=14):
    """RSI 相对强弱指标"""
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = ma(gains, n)
    avg_loss = ma(losses, n)
    rs = [a/b if b>0 else 0 for a, b in zip(avg_gain, avg_loss)]
    return [100 - 100/(1+r) if r>0 else 50 for r in rs]


# ═══════════════════════════════════════════════════
#  回测引擎
# ═══════════════════════════════════════════════════

def backtest(name, rows, signals_fn, commission=0.001, slippage=0.0005,
             initial=1_000_000.0, position_pct=0.98):
    """
    rows: [{date, open, high, low, close, volume}]
    signals_fn: (closes, highs, lows, open, volume) → [0=持有, 1=买入, -1=卖出]
    返回: 回测报告 dict
    """
    if len(rows) < 30:
        return None
    closes = [r["close"] for r in rows]
    highs  = [r["high"]  for r in rows]
    lows   = [r["low"]   for r in rows]
    opens  = [r["open"]  for r in rows]
    volumes= [r["volume"] for r in rows]

    sigs = signals_fn(closes, highs, lows, opens, volumes)
    cash = initial; pos = 0; entry_px = 0.0
    equity = [initial]; trades = []; cost = 0.0

    for i in range(1, len(rows)):
        px = closes[i]
        sig = sigs[i] if i < len(sigs) else 0

        if sig == 1 and pos == 0:
            # 买入
            buy_px = px * (1 + slippage)
            pos = int(cash * position_pct / buy_px)
            comm = pos * buy_px * commission
            cash -= pos * buy_px + comm
            cost += comm; entry_px = px
        elif sig == -1 and pos > 0:
            # 卖出
            sell_px = px * (1 - slippage)
            comm = pos * sell_px * commission
            trades.append({"entry": entry_px, "exit": sell_px,
                            "ret": (sell_px-entry_px)/entry_px,
                            "ret_pct": round((sell_px-entry_px)/entry_px*100, 2)})
            cash += pos * sell_px - comm
            cost += comm; pos = 0

        equity.append(cash + pos * px)

    # 空仓时不持有
    final = equity[-1]
    ann = ((final/initial)**(365/max(len(rows)-1,1))-1) * 100
    rets = [(equity[i]-equity[i-1])/max(equity[i-1],1) for i in range(1,len(equity))]
    vol = math.sqrt(sum(r*r for r in rets)/max(len(rets),1)*365) if rets else 0
    sh = ann/vol if vol > 0 else 0

    peak = initial; mdd = 0.0
    for v in equity:
        if v > peak: peak = v
        dd = (v-peak)/peak
        if dd < mdd: mdd = dd

    wins = [t for t in trades if t["ret"] > 0]
    wr = len(wins)/len(trades)*100 if trades else 0
    pf = sum(t["ret"] for t in wins)/abs(sum(t["ret"] for t in trades if t["ret"]<0)+1e-9) if wins and trades else 0

    return {
        "strategy": name, "symbol": rows[0].get("symbol",""),
        "period_days": len(rows),
        "start": rows[0]["date"], "end": rows[-1]["date"],
        "initial": initial, "final": round(final, 0),
        "ann_return_pct": round(ann, 2), "sharpe": round(sh, 3),
        "max_drawdown_pct": round(abs(mdd)*100, 2),
        "total_trades": len(trades),
        "win_rate_pct": round(wr, 1),
        "profit_factor": round(pf, 2),
        "commission_cost": round(cost, 0),
        "equity_curve": equity,
    }


# ═══════════════════════════════════════════════════
#  策略实现
# ═══════════════════════════════════════════════════

class TurtleStrategy:
    """
    海龟交易法则（20日突破）
    买入规则：今日收盘价 > 过去20日最高价 → 买入
    卖出规则：今日收盘价 < 过去10日最低价 → 卖出
    做空规则：反向亦然（可做空）
    来源：邢不行量化小讲堂系列08
    """
    def __init__(self, long_exit=10, short_exit=20, long_entry=20, allow_short=False):
        self.long_exit = long_exit   # 做空平仓/做空开仓
        self.long_entry = long_entry # 做多开仓
        self.allow_short = allow_short

    def signals(self, closes, highs, lows, opens, volumes):
        sig = [0] * len(closes)
        for i in range(self.long_entry, len(closes)):
            highest_20 = max(highs[i-self.long_entry:i+1])
            lowest_10  = min(lows[i-self.short_exit:i+1])
            lowest_20  = min(lows[i-self.long_entry:i+1])
            highest_10 = max(highs[i-self.short_exit:i+1])
            if closes[i] > highest_20 and closes[i-1] <= highest_20:
                sig[i] = 1  # 买入开多
            elif closes[i] < lowest_10 and closes[i-1] >= lowest_10:
                sig[i] = -1 # 卖出平多
            if self.allow_short:
                if closes[i] < lowest_20 and closes[i-1] >= lowest_20:
                    sig[i] = -1
                elif closes[i] > highest_10 and closes[i-1] <= highest_10:
                    sig[i] = 1
        return sig

    def run(self, rows, initial=1_000_000):
        return backtest("海龟20日突破", rows, self.signals, initial=initial)


class BollingerBB:
    """
    布林带均值回归（邢不行系列16）
    规则：价格触及下轨买入，触及上轨卖出
    参数：周期n（默认20），标准差倍数k（默认2.0）
    来源：邢不行量化小讲堂系列16
    """
    def __init__(self, n=20, k=2.0):
        self.n = n; self.k = k

    def signals(self, closes, highs, lows, opens, volumes):
        upper, mid, lower = boll_bands(closes, self.n, self.k)
        sig = [0] * len(closes)
        for i in range(self.n, len(closes)):
            if closes[i] <= lower[i] and closes[i-1] > lower[i-1]:
                sig[i] = 1  # 价格接触下轨，买入
            elif closes[i] >= upper[i] and closes[i-1] < upper[i-1]:
                sig[i] = -1 # 价格接触上轨，卖出
        return sig

    def run(self, rows, initial=1_000_000):
        return backtest(f"布林带({self.n},{self.k})", rows, self.signals, initial=initial)


class KDJ_Xing:
    """
    KDJ 金叉死叉（邢不行量化小讲堂）
    规则：J值<0超卖买入，J值>100超买卖出
    参数：n=9, m1=3, m2=3
    """
    def __init__(self, n=9, m1=3, m2=3):
        self.n = n; self.m1 = m1; self.m2 = m2

    def signals(self, closes, highs, lows, opens, volumes):
        k, d, j = kdj(highs, lows, closes, self.n, self.m1, self.m2)
        sig = [0] * len(closes)
        for i in range(self.n+1, len(closes)):
            if j[i-1] < 0 and j[i] >= 0:
                sig[i] = 1  # J值从<0向上穿越，买入
            elif j[i-1] > 100 and j[i] <= 100:
                sig[i] = -1 # J值从>100向下穿越，卖出
        return sig

    def run(self, rows, initial=1_000_000):
        return backtest(f"KDJ({self.n},{self.m1},{self.m2})", rows, self.signals, initial=initial)


class EMVStrategy:
    """
    EMV 简易波动指标（邢不行系列17）
    规则：EMV上穿0轴买入，下穿0轴卖出
    参数：n=14
    """
    def __init__(self, n=14):
        self.n = n

    def signals(self, closes, highs, lows, opens, volumes):
        emv = emv(highs, lows, volumes, self.n)
        sig = [0] * len(closes)
        for i in range(self.n, len(closes)):
            if emv[i-1] < 0 and emv[i] >= 0:
                sig[i] = 1
            elif emv[i-1] > 0 and emv[i] <= 0:
                sig[i] = -1
        return sig

    def run(self, rows, initial=1_000_000):
        return backtest(f"EMV({self.n})", rows, self.signals, initial=initial)


class ADXStrategy:
    """
    ADX 平均趋向指标（邢不行系列18）
    规则：ADX>25确认趋势成立，顺势交易
    +DI上穿-DI买入，+DI下穿-DI卖出
    参数：n=14
    """
    def __init__(self, n=14):
        self.n = n

    def signals(self, closes, highs, lows, opens, volumes):
        adx_series, p_di, m_di = adx(highs, lows, closes, self.n)
        sig = [0] * len(closes)
        for i in range(self.n*2, len(closes)):
            if adx_series[i] < 25:
                continue  # 无趋势，不操作
            if p_di[i] > m_di[i] and p_di[i-1] <= m_di[i-1]:
                sig[i] = 1  # 上升趋势中
            elif p_di[i] < m_di[i] and p_di[i-1] >= m_di[i-1]:
                sig[i] = -1
        return sig

    def run(self, rows, initial=1_000_000):
        return backtest(f"ADX({self.n})", rows, self.signals, initial=initial)


class GapFillStrategy:
    """
    跳空缺口策略（邢不行系列46）
    验证A股名言"跳空必回补"
    策略：跳空高开>1%则次日卖出，跳空低开<1%则次日买入
    仅适用于日线数据
    """
    def __init__(self, threshold=0.01):
        self.threshold = threshold  # 1%

    def signals(self, closes, highs, lows, opens, volumes):
        sig = [0] * len(closes)
        for i in range(1, len(closes)):
            open_pct = (opens[i] - closes[i-1]) / closes[i-1]
            if open_pct > self.threshold:
                # 向上跳空：次日开盘卖出（若持有）
                sig[i] = -1
            elif open_pct < -self.threshold:
                # 向下跳空：次日开盘买入
                sig[i] = 1
        return sig

    def run(self, rows, initial=1_000_000):
        return backtest(f"跳空(threshold={self.threshold:.0%})", rows, self.signals, initial=initial)


class SmallCapStrategy:
    """
    小市值选股（模拟版）（邢不行系列19"10年400倍"）
    规则：每月末选市值最小N只股票，等额买入，月末再平衡
    注意：真实实现需要A股market cap数据，这里用随机模拟演示逻辑
    参数：top_n=10, holding_days=30
    """
    def __init__(self, top_n=10, holding_days=30):
        self.top_n = top_n
        self.holding_days = holding_days

    def signals(self, closes, highs, lows, opens, volumes):
        """用成交量变化率模拟市值大小"""
        # 模拟：成交量低+价格低的股票=小市值
        sig = [0] * len(closes)
        if len(closes) < 60:
            return sig
        vol_ma = ma(volumes, 20)
        for i in range(60, len(closes)):
            # 每月换仓（假设交易日约20天/月）
            if i % self.holding_days == 0:
                # 用vol排名（越小越像小市值）
                window = volumes[i-60:i]
                min_v = min(window)
                max_v = max(window)
                # 越小市值越大
                vol_rank = (volumes[i] - min_v) / (max_v - min_v + 1e-9)
                if vol_rank < 0.3:  # 成交量低=小市值
                    sig[i] = 1
        return sig

    def run(self, rows, initial=1_000_000):
        return backtest(f"小市值({self.top_n}只)", rows, self.signals, initial=initial)


class MACDCrypto:
    """
    MACD 择时策略（邢不行加密货币系列）
    规则：DIF上穿DEA买入，DIF下穿DEA卖出
    """
    def __init__(self, fast=12, slow=26, sig=9):
        self.fast=fast; self.slow=slow; self.sig=sig

    def signals(self, closes, highs, lows, opens, volumes):
        dif, dea = macd(closes, self.fast, self.slow, self.sig)
        sig = [0] * len(closes)
        for i in range(self.slow, len(closes)):
            if i >= len(dif) or i >= len(dea): continue
            if dif[i] > dea[i] and dif[i-1] <= dea[i-1]:
                sig[i] = 1
            elif dif[i] < dea[i] and dif[i-1] >= dea[i-1]:
                sig[i] = -1
        return sig

    def run(self, rows, initial=1_000_000):
        return backtest(f"MACD({self.fast},{self.slow},{self.sig})", rows, self.signals, initial=initial)


class RSI4080:
    """
    RSI 超买超卖（类邢不行RSI策略）
    规则：RSI<40超卖买入，RSI>80超买卖出
    """
    def __init__(self, period=14):
        self.period = period

    def signals(self, closes, highs, lows, opens, volumes):
        rv = rsi(closes, self.period)
        sig = [0] * len(closes)
        for i in range(self.period, len(closes)):
            if rv[i-1] < 40 and rv[i] >= 40:
                sig[i] = 1
            elif rv[i-1] > 80 and rv[i] <= 80:
                sig[i] = -1
        return sig

    def run(self, rows, initial=1_000_000):
        return backtest(f"RSI({self.period},40,80)", rows, self.signals, initial=initial)


class GridStrategy:
    """
    永远网格策略（类邢不行网格策略）
    规则：将价格区间等分，在每个网格点挂买单和卖单
    每格间距固定（如2%），价格上涨触上轨卖出，跌破下轨买入
    """
    def __init__(self, grid_pct=0.02, initial_price=None):
        self.grid_pct = grid_pct  # 每格2%
        self.initial_price = initial_price

    def signals(self, closes, highs, lows, opens, volumes):
        if self.initial_price is None:
            self.initial_price = closes[0]
        base = self.initial_price
        upper = base * (1 + self.grid_pct)
        lower = base * (1 - self.grid_pct)
        sig = [0] * len(closes)
        for i in range(1, len(closes)):
            if closes[i] >= upper:
                sig[i] = -1  # 触及上格，卖出
            elif closes[i] <= lower:
                sig[i] = 1   # 触及下格，买入
        return sig

    def run(self, rows, initial=1_000_000):
        if rows:
            self.initial_price = rows[0]["close"]
        return backtest(f"网格({self.grid_pct:.0%})", rows, self.signals, initial=initial)


class MomentumRotation:
    """
    动量轮动策略（类邢不行币圈多空择时）
    规则：比较过去N日收益率，选动量最强的币做多，最弱的做空
    这里单币版本：MA5>MA20做多，MA5<MA20做空
    """
    def __init__(self, fast=5, slow=20):
        self.fast = fast; self.slow = slow

    def signals(self, closes, highs, lows, opens, volumes):
        ma_f = ma(closes, self.fast)
        ma_s = ma(closes, self.slow)
        sig = [0] * len(closes)
        for i in range(self.slow, len(closes)):
            if ma_f[i] > ma_s[i] and ma_f[i-1] <= ma_s[i-1]:
                sig[i] = 1
            elif ma_f[i] < ma_s[i] and ma_f[i-1] >= ma_s[i-1]:
                sig[i] = -1
        return sig

    def run(self, rows, initial=1_000_000):
        return backtest(f"动量轮动({self.fast},{self.slow})", rows, self.signals, initial=initial)


class TurtleCrypto(TurtleStrategy):
    """海龟交易法则·加密货币专用版（允许做空）"""
    def __init__(self, long_exit=10, short_exit=20, long_entry=20):
        super().__init__(long_exit, short_exit, long_entry, allow_short=True)


class DollarCostAveraging:
    """
    定期定投策略（类邢不行指数定投验证）
    规则：每周/每月等额定投一次，不择时
    """
    def __init__(self, freq="monthly"):
        self.freq = freq  # "weekly" | "monthly"

    def signals(self, closes, highs, lows, opens, volumes):
        sig = [0] * len(closes)
        if self.freq == "monthly":
            for i in range(1, len(closes)):
                d = closes[i]["date"] if isinstance(closes[i], dict) else closes[i]
                # 月底买
                if i < len(closes)-1:
                    d_next = closes[i+1]["date"] if isinstance(closes[i+1], dict) else closes[i+1]
                    if d[5:7] != d_next[5:7]:
                        sig[i] = 1
        elif self.freq == "weekly":
            for i in range(1, len(closes)):
                d = closes[i]["date"] if isinstance(closes[i], dict) else closes[i]
                # 每周一买
                from datetime import datetime as dt
                weekday = dt.strptime(d, "%Y-%m-%d").weekday()
                if weekday == 0:
                    sig[i] = 1
        return sig

    def run(self, rows, initial=1_000_000):
        return backtest(f"定投({self.freq})", rows, self.signals, initial=initial)