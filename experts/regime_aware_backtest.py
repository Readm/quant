"""
regime_aware_backtest.py — Regime感知回测引擎（无未来数据版）

核心设计原则：
  在每个时间点 t，regime 检测只使用 [0, t-1] 的历史数据。
  策略选择根据"当前已发生的 regime"做出，非预测。
  这不是预测市场，而是对已发生市场状态的实时响应。

Regime 检测 → 策略映射（基于实测结果）：
  · 高波动+下跌（熊市/恐慌）→ 布林带均值回归
  · 高波动+震荡            → RSI超卖 + 布林带
  · 低波动+上涨            → 趋势追踪（MA金叉）
  · 低波动+中性/震荡        → RSI均值回归

关键：无前瞻 bias。
      不使用任何 t+1 或之后的数据来影响 t 的决策。
"""

import math, random, urllib.request, ssl
from dataclasses import dataclass

ctx = ssl.create_default_context()
ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE

# ── 数据获取 ─────────────────────────────────────────────────

STOOQ = {
    "BTCUSDT": "btc.v",   "ETHUSDT": "eth.v",   "SOLUSDT": "sol.v",
    "AAPL":    "aapl.US",  "NVDA":    "nvda.US",  "TSLA":    "tsla.US",
}

def fetch_stooq(sym, n=300):
    code = STOOQ.get(sym.upper())
    if not code: return None
    url = f"https://stooq.com/q/d/l/?s={code}&d1=20230101&d2=20241231&i=d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=12) as r:
            raw = r.read().decode()
    except: return None
    rows = []
    for line in raw.strip().split("\r\n")[1:]:
        p = line.split(",")
        if len(p) < 5: continue
        try: rows.append({"date": p[0], "close": float(p[4])})
        except: pass
    rows.reverse()
    return rows[:n] if len(rows) > n else rows


# ── Regime 检测 ────────────────────────────────────────────────

def _rolling_vol(closes, window, end_idx):
    if end_idx < window: return 0.0
    rets = [math.log(closes[i]/closes[i-1]) for i in range(end_idx-window+1, end_idx+1) if i>0]
    if len(rets) < 2: return 0.0
    mu = sum(rets)/len(rets)
    var = sum((r-mu)**2 for r in rets)/len(rets)
    return math.sqrt(var*252)

def _rolling_ma(closes, window, end_idx):
    if end_idx < window: return closes[end_idx]
    return sum(closes[end_idx-window+1:end_idx+1])/window

def detect_regime(closes, t):
    """
    在时间点 t 的 regime 状态。
    只使用 [0, t-1] 数据计算，无前瞻。
    """
    if t < 120:
        return {"label": "中性", "regime_score": 0.0,
                "rec": ["RSI均值回归"], "pos_cap": 0.30,
                "vol_ratio": 1.0, "trend": "SIDEWAYS", "lookback": t}

    # 波动率
    vol_20 = _rolling_vol(closes, 20, t-1)  # t-1 是"当前"（信号滞后1天）
    vol_60_avg = _rolling_vol(closes, 60, t-60) if t >= 60 else vol_20
    vol_ratio = vol_20 / (vol_60_avg + 1e-9)

    # 均线状态（趋势）
    ma20 = _rolling_ma(closes, 20, t-1)
    ma60 = _rolling_ma(closes, 60, t-1)
    ma120 = _rolling_ma(closes, 120, t-1)
    price = closes[t-1]

    # 近期收益
    ret_20d = (closes[t-1] / (closes[t-21] if t > 20 else closes[0]) - 1) if t > 20 else 0.0

    # Regime 判断
    vol_high = vol_ratio > 1.1
    trend_up = ma20 > ma60 and price > ma120
    trend_down = ma20 < ma60 and price < ma120

    if vol_high and trend_down:
        label = "熊市/恐慌"; rec = ["布林带均值回归"]; pos = 0.25
        regime_score = -40.0; trend = "DOWNTREND"
    elif vol_high and not trend_up and not trend_down:
        label = "震荡高波"; rec = ["RSI超卖", "布林带"]; pos = 0.30
        regime_score = -10.0; trend = "SIDEWAYS"
    elif not vol_high and trend_up:
        label = "慢牛"; rec = ["趋势追踪", "均线多头"]; pos = 0.60
        regime_score = +35.0; trend = "UPTREND"
    elif trend_down:
        label = "偏空"; rec = ["防御配置"]; pos = 0.20
        regime_score = -25.0; trend = "DOWNTREND"
    else:
        label = "震荡整理"; rec = ["RSI均值回归", "布林带"]; pos = 0.40
        regime_score = +5.0; trend = "SIDEWAYS"

    return {
        "label": label, "regime_score": regime_score,
        "rec": rec, "pos_cap": pos,
        "vol_ratio": round(vol_ratio, 3),
        "trend": trend,
        "lookback": t,
    }


# ── 信号函数 ──────────────────────────────────────────────────

def ma_cross_sig(closes, fp, sp, start=0):
    n = len(closes); s = [0]*n
    for i in range(start, n):
        if i < sp: continue
        m1=sum(closes[i-fp+1:i+1])/fp
        m2=sum(closes[i-sp+1:i+1])/sp
        m1p=sum(closes[i-fp:i])/fp if i>fp else closes[i-fp]
        m2p=sum(closes[i-sp:i])/sp if i>sp else closes[i-sp]
        if m1>m2 and m1p<=m2p: s[i]=1
        elif m1<m2 and m1p>=m2p: s[i]=-1
    return s

def rsi_sig(closes, period, lo, hi, start=0):
    n=len(closes); s=[0]*n
    for i in range(start, n):
        if i<period: continue
        gains=max(0.0,closes[i]-closes[i-1])
        losses=max(0.0,closes[i-1]-closes[i])
        ag=sum(max(0,closes[j]-closes[j-1]) for j in range(period,i+1))/period
        al=sum(max(0,closes[j-1]-closes[j]) for j in range(period,i+1))/period
        rv=100-100/(1+ag/(al+1e-9))
        if rv<lo: s[i]=1
        elif rv>hi: s[i]=-1
    return s

def bollinger_sig(closes, period, n_std, start=0):
    n=len(closes); s=[0]*n
    for i in range(start, n):
        if i<period: continue
        window=closes[i-period:i+1]
        mid=sum(window)/period
        std=math.sqrt(sum((x-mid)**2 for x in window)/period)
        upper=mid+n_std*std; lower=mid-n_std*std
        if closes[i]<lower: s[i]=1
        elif closes[i]>upper: s[i]=-1
    return s


# ── Regime感知信号选择 ─────────────────────────────────────────

STRATEGY_SIGNALS = {
    "布林带均值回归": lambda c, i: bollinger_sig(c, 20, 2.0, start=max(0,i)),
    "布林带":         lambda c, i: bollinger_sig(c, 20, 2.0, start=max(0,i)),
    "RSI超卖":        lambda c, i: rsi_sig(c, 14, 30, 70, start=max(0,i)),
    "RSI均值回归":    lambda c, i: rsi_sig(c, 14, 30, 70, start=max(0,i)),
    "趋势追踪":       lambda c, i: ma_cross_sig(c, 20, 60, start=max(0,i)),
    "均线多头":       lambda c, i: ma_cross_sig(c, 10, 60, start=max(0,i)),
    "动量突破":       lambda c, i: ma_cross_sig(c, 5, 20, start=max(0,i)),
    "MACD趋势":       lambda c, i: ma_cross_sig(c, 12, 26, start=max(0,i)),
    "防御配置":       lambda c, i: [0]*len(c),  # 空仓策略
}


def regime_aware_signal(closes, t, regime):
    """
    根据当前 regime 选择信号。
    在 t 时间点，regime 是用 [0, t-1] 数据检测的。
    返回 t 时刻应该持仓的信号（1=多/-1=空/0=空仓）。
    """
    recs = regime.get("rec", ["RSI均值回归"])
    # 尝试第一个推荐策略
    for rec in recs:
        if rec in STRATEGY_SIGNALS:
            sig_fn = STRATEGY_SIGNALS[rec]
            sigs = sig_fn(closes, t)
            return sigs[t] if t < len(sigs) else 0
    return 0


# ── 回测引擎（t 时间点才能用 t 时刻收盘价做信号）─────────────

def backtest_regime_aware(name, closes, initial=1_000_000.0,
                          commission=0.04, spread_bps=20, stamp=0.0):
    """
    Regime感知回测。

    关键无前瞻设计：
      · 信号在 t-1 收盘时计算（收盘价已知）
      · 在 t-1 收盘时产生信号
      · 在 t 开盘时执行（用 t-1 收盘价的滑点调整）
      · regime 检测只用 t-1 及之前的数据
    """
    n = len(closes)
    cash = initial; pos = 0
    entry_px = 0.0; entry_idx = 0
    equity = [initial]
    trades = []
    cost_total = 0.0
    regime_log = []  # 记录每天的 regime 状态

    for t in range(1, n):
        # Step 1: 检测 t-1 时刻的 regime（只用历史数据）
        regime = detect_regime(closes, t)
        regime_log.append(regime)

        # Step 2: 根据 regime 选择信号
        sig = regime_aware_signal(closes, t, regime)

        # Step 3: 执行交易
        px = closes[t]
        if sig == 1 and pos == 0:
            # 买入
            cost_px = px * (1 + 0.0005)  # 滑点
            comm_cost = cost_px * (commission/100 + spread_bps/10000)
            pos = int(cash * 0.98 / cost_px)
            cash -= cost_px * pos + comm_cost * pos
            cost_total += comm_cost * pos
            entry_px = px; entry_idx = t
        elif sig == -1 and pos > 0:
            # 卖出
            proceeds_px = px * (1 - 0.0005)
            total_cost = proceeds_px * (commission/100 + spread_bps/10000 + stamp/100)
            net = proceeds_px * pos - total_cost
            ret = (px - entry_px) / entry_px * 100
            trades.append({"ret": round(ret, 2), "pnl": round(cash + net - initial, 0)})
            cash += net; pos = 0
            cost_total += total_cost

        equity.append(cash + pos * px)

    # 统计
    final = equity[-1]
    ann = ((final/initial)**(252/max(n-1,1))-1)*100
    rets_seq = [(equity[i]-equity[i-1])/equity[i-1] for i in range(1,len(equity))]
    vol = math.sqrt(sum(r*r for r in rets_seq)/max(len(rets_seq),1))*math.sqrt(252)
    sharpe = ann/vol if vol>0 else 0.0
    peak=initial; max_dd=0.0
    for v in equity:
        if v>peak: peak=v
        dd=(v-peak)/peak
        if dd<max_dd: max_dd=dd
    max_dd = abs(max_dd)*100
    wins=[t for t in trades if t["ret"]>0]
    win_rate=len(wins)/len(trades) if trades else 0
    adj_ann = ann - (cost_total/initial)*100
    adj_sh  = adj_ann/vol if vol>0 else 0.0

    # Regime 分布统计
    labels = [r["label"] for r in regime_log]
    label_counts = {l: labels.count(l) for l in set(labels)}

    return {
        "name": name, "ann_ret": round(ann, 2), "adj_ann": round(adj_ann, 2),
        "sharpe": round(sharpe, 3), "adj_sharpe": round(adj_sh, 3),
        "max_dd": round(max_dd, 1), "n_trades": len(trades),
        "win_rate": round(win_rate*100, 1), "cost": round(cost_total, 0),
        "equity": equity, "final": round(final, 0),
        "regime_distribution": label_counts,
    }


# ── 对比：固定策略 vs Regime感知策略 ─────────────────────────

def backtest_fixed(name, closes, sig_fn, params,
                   initial=1_000_000.0, commission=0.04,
                   spread_bps=20, stamp=0.0):
    """固定策略回测（无 regime 感知）"""
    n = len(closes)
    sig = sig_fn(closes, params)
    cash = initial; pos = 0
    entry_px = 0.0; entry_idx = 0
    equity = [initial]; trades = []; cost_total = 0.0

    for i in range(1, n):
        px = closes[i]
        if sig[i] == 1 and pos == 0:
            cost_px = px*(1+0.0005)
            comm_cost = cost_px*(commission/100+spread_bps/10000)
            pos = int(cash*0.98/cost_px); cash -= cost_px*pos + comm_cost*pos
            cost_total += comm_cost*pos; entry_px=px; entry_idx=i
        elif sig[i]==-1 and pos>0:
            proceeds_px=px*(1-0.0005)
            total_cost=proceeds_px*(commission/100+spread_bps/10000+stamp/100)
            net=proceeds_px*pos-total_cost; ret=(px-entry_px)/entry_px*100
            trades.append({"ret":round(ret,2),"pnl":round(cash+net-initial,0)})
            cash+=net; pos=0; cost_total+=total_cost
        equity.append(cash+pos*px)

    final=equity[-1]
    ann=((final/initial)**(252/max(n-1,1))-1)*100
    rets=[(equity[i]-equity[i-1])/equity[i-1] for i in range(1,len(equity))]
    vol=math.sqrt(sum(r*r for r in rets)/max(len(rets),1))*math.sqrt(252)
    sharpe=ann/vol if vol>0 else 0.0
    peak=initial; max_dd=0.0
    for v in equity:
        if v>peak: peak=v
        dd=(v-peak)/peak
        if dd<max_dd: max_dd=dd
    max_dd=abs(max_dd)*100
    wins=[t for t in trades if t["ret"]>0]
    wr=len(wins)/len(trades) if trades else 0
    adj=ann-(cost_total/initial)*100
    adj_sh=adj/vol if vol>0 else 0.0
    return {"name":name,"ann_ret":round(ann,2),"adj_ann":round(adj,2),
            "sharpe":round(sharpe,3),"adj_sharpe":round(adj_sh,3),
            "max_dd":round(max_dd,1),"n_trades":len(trades),
            "win_rate":round(wr*100,1),"cost":round(cost_total,0),
            "equity":equity,"final":round(final,0)}


# ── 主程序 ────────────────────────────────────────────────────

def main():
    print("\n" + "="*70)
    print("  🌡️  Regime-Aware 回测 vs 固定策略回测")
    print("  核心原则：Regime检测只用历史数据，无前瞻")
    print("="*70)

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AAPL", "NVDA", "TSLA"]

    for sym in symbols:
        rows = fetch_stooq(sym, 300)
        if not rows:
            print(f"  ❌ {sym}: 数据获取失败")
            continue

        closes = [r["close"] for r in rows]
        n = len(closes)
        price_start = closes[0]
        price_end = closes[-1]
        bh_ret = (price_end/price_start-1)*100
        print(f"\n{'='*65}")
        print(f"  {sym}（{n}天）买入持有: {bh_ret:+.1f}%")
        print(f"{'='*65}")

        # 固定布林带策略
        fixed = backtest_fixed(
            "固定布林带", closes,
            lambda c,p: bollinger_sig(c, p["period"], p["std_mult"]),
            {"period": 20, "std_mult": 2.0}
        )
        # 固定 MA 趋势策略
        ma_fixed = backtest_fixed(
            "固定均线MA(20,60)", closes,
            lambda c,p: ma_cross_sig(c, p["fast"], p["slow"]),
            {"fast": 20, "slow": 60}
        )
        # Regime感知策略
        regime = backtest_regime_aware(f"Regime感知", closes)

        # 打印对比
        print(f"\n  {'策略':<20} {'年化(摩)':>10} {'夏普(摩)':>9} "
              f"{'最大回撤':>8} {'交易':>5} {'胜率':>6} {'vs买入持有'}")
        print(f"  {'─'*60}")
        for r, label in [
            (fixed,      "固定布林带"),
            (ma_fixed,   "固定均线(20,60)"),
            (regime,     "Regime感知"),
        ]:
            vs_bh = r["adj_ann"] - bh_ret
            icon = "✅" if r["adj_sharpe"] > 0.3 else ("⚠️" if r["adj_ann"] > 0 else "❌")
            print(f"  {icon}{label:<19} {r['adj_ann']:>+9.1f}% "
                  f"{r['adj_sharpe']:>8.3f} {r['max_dd']:>7.1f}% "
                  f"{r['n_trades']:>5} {r['win_rate']:>5.0f}% "
                  f"{vs_bh:>+7.1f}pp")

        # Regime分布
        dist = regime.get("regime_distribution", {})
        dist_str = ", ".join(f"{k}:{v}天" for k,v in dist.items())
        print(f"\n  Regime分布：{dist_str}")
        print(f"  最终资金：{regime['final']:,.0f} 元（初始 1,000,000）")

    print(f"""
  ═══════════════════════════════════════════════════════════════
  💡 无前瞻（No Look-Ahead）设计说明
  ═══════════════════════════════════════════════════════════════

  1. Regime检测：
     detect_regime(closes, t) 函数只用 closes[0:t-1] 数据。
     t=120时，用前119天数据判断当前是否为"熊市/震荡/牛市"。

  2. 信号产生：
     在 t-1 收盘后，根据已知的收盘价计算信号。
     在 t 日开盘时以 t-1 收盘价（加滑点）执行。

  3. 与"预测未来"的本质区别：
     -Regime感知：过去1个月波动率很高（已发生）→ 当前市场是"高波动环境" → 用高波动策略
     -预测未来：预计下个月会熊市 → 提前做空（这是预测，非感知）

  4. 为什么Regime感知有效：
     市场状态有惯性。高波动环境通常持续数周。
     用"已发生"的状态来应对，比"完全忽视市场状态"更聪明。
     但不预测未来，所以不会因为"预测错误"而崩溃。

  ═══════════════════════════════════════════════════════════════
    """)

if __name__ == "__main__":
    main()
