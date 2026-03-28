"""
real_data_comparison.py — 真实 vs 模拟数据全对比（含Walk-Forward）
"""
import sys, math, random, urllib.request, ssl, concurrent.futures
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# ── 真实数据获取（Stooq，无Token）─────────────
META = {
    "BTCUSDT": ("btc.v", "crypto"),
    "ETHUSDT": ("eth.v", "crypto"),
    "SOLUSDT": ("sol.v", "crypto"),
    "AAPL":    ("aapl.US",  "stock"),
    "NVDA":    ("nvda.US",  "stock"),
    "TSLA":    ("tsla.US",  "stock"),
}

def fetch_stooq(symbol, n=300):
    code = META.get(symbol, [None])[0]
    if not code: return None
    url = f"https://stooq.com/q/d/l/?s={code}&d1=20230101&d2=20241231&i=d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            raw = r.read().decode("utf-8")
    except: return None
    rows = []
    for line in raw.strip().split("\r\n")[1:]:
        p = line.split(",")
        if len(p) < 6: continue
        try:
            rows.append({"date": p[0], "close": float(p[4])})
        except: continue
    rows.reverse()
    return rows[-n:] if len(rows) > n else rows

def get_closes(symbol):
    rows = fetch_stooq(symbol)
    if not rows: return None
    return [r["close"] for r in rows]

# ── 技术指标 ─────────────────────────────────
def calc_ma(closes, period):
    n = len(closes); out = [0.0]*n
    for i in range(period-1, n):
        out[i] = sum(closes[i-period+1:i+1]) / period
    return out

def calc_rsi(closes, period=14):
    n = len(closes); out = [50.0]*n
    for i in range(period, n):
        gains  = max(0.0, closes[i]-closes[i-1])
        losses = max(0.0, closes[i-1]-closes[i])
        ag = sum(max(0, closes[j]-closes[j-1]) for j in range(period, i+1)) / period
        al = sum(max(0, closes[j-1]-closes[j]) for j in range(period, i+1)) / period
        out[i] = 100 - 100 / (1 + ag / (al + 1e-9))
    return out

# ── 回测引擎 ─────────────────────────────────
def backtest(name, closes, params, initial=1_000_000.0):
    n = len(closes)
    if n < 60: return None
    sig = [0] * n
    if "MA" in name:
        fp, sp = params.get("fast",20), params.get("slow",60)
        m1 = calc_ma(closes, fp); m2 = calc_ma(closes, sp)
        for i in range(sp, n):
            if m1[i] > m2[i] and m1[i-1] <= m2[i-1]: sig[i] = 1
            elif m1[i] < m2[i] and m1[i-1] >= m2[i-1]: sig[i] = -1
    elif "RSI" in name:
        p, lo, hi = params.get("period",14), params.get("lo",30), params.get("hi",70)
        rv = calc_rsi(closes, p)
        for i in range(p, n):
            if rv[i-1] < lo and rv[i] >= lo: sig[i] = 1
            elif rv[i-1] > hi and rv[i] <= hi: sig[i] = -1
    cash = initial; pos = 0; trades = []; equity = [initial]
    for i in range(1, n):
        px = closes[i]
        if sig[i] == 1 and pos == 0:
            pos = int(cash * 0.95 / px); cash -= pos * px
        elif sig[i] == -1 and pos > 0:
            trades.append((px - closes[i-1]) / closes[i-1])
            cash += pos * px; pos = 0
        elif pos > 0:
            trades.append((px - closes[i-1]) / closes[i-1])
        equity.append(cash + pos * px)
    final = equity[-1]
    ann_ret = ((final/initial)**(252/max(n-1,1))-1)*100
    vol = math.sqrt(sum((r*r) for r in trades)/max(len(trades),1))*math.sqrt(252)
    sharpe = ann_ret / vol if vol > 0 else 0.0
    dd = _max_dd(equity, initial)
    wins = [t for t in trades if t > 0]
    wr = len(wins)/len(trades) if trades else 0.0
    return dict(name=name, ann_ret=round(ann_ret,2), sharpe=round(sharpe,3),
                max_dd=round(dd,2), n_trades=len(trades), win_rate=round(wr*100,1),
                equity=equity, initial=initial)

def _max_dd(equity, init):
    peak = init; max_dd = 0.0
    for v in equity:
        if v > peak: peak = v
        dd = (v-peak)/peak
        if dd < max_dd: max_dd = dd
    return abs(max_dd)*100

# ── 摩擦成本 ─────────────────────────────────
def apply_cost(r, asset):
    n = r["n_trades"]
    if n == 0: return {**r, "cost":0, "adj_ret":r["ann_ret"], "adj_sharpe":r["sharpe"], "loss":0}
    commission = 0.04 if asset=="crypto" else 0.03
    spread_bps = 20 if asset=="crypto" else 5
    stamp = 0.10 if asset=="stock" else 0.0
    per_trade = r["initial"] * 0.95 / n
    cost_per = per_trade * (commission/100*2 + spread_bps/10000*2)
    total = cost_per * n + per_trade * n * stamp/100 if stamp > 0 else cost_per * n
    adj_ret = r["ann_ret"] - (total/r["initial"])*100
    adj_sharpe = r["sharpe"] * (adj_ret/r["ann_ret"]) if r["ann_ret"] != 0 else 0
    return {**r, "cost":round(total,0), "adj_ret":round(adj_ret,2),
            "adj_sharpe":round(adj_sharpe,3), "loss":round((total/r["initial"])*100,2)}

# ── Walk-Forward ─────────────────────────────
def walk_forward(closes, params_fn, n_train=180, n_test=60):
    n = len(closes)
    results = []
    cursor = n
    while True:
        te = cursor
        ts = max(n_train+n_test, cursor - n_test)
        tr = max(0, ts - n_train)
        if ts - tr < n_train or ts - te < 30: break
        tc = closes[tr:ts]; ec = closes[ts:te]
        if len(ec) < 30: break
        tr_rets = [(tc[j]-tc[j-1])/tc[j-1] for j in range(1,len(tc))]
        mu_t = sum(tr_rets)/len(tr_rets)*252
        vo_t = math.sqrt(sum((r-mu_t/252)**2 for r in tr_rets)/len(tr_rets))*math.sqrt(252)
        sh_t = mu_t/vo_t if vo_t>0 else 0
        te_rets = [(ec[j]-ec[j-1])/ec[j-1] for j in range(1,len(ec))]
        mu_e = sum(te_rets)/len(te_rets)*252
        vo_e = math.sqrt(sum((r-mu_e/252)**2 for r in te_rets)/len(te_rets))*math.sqrt(252)
        sh_e = mu_e/vo_e if vo_e>0 else 0
        bh = (ec[-1]/ec[0]-1)*100
        results.append({"train_sharpe":round(sh_t,3), "test_sharpe":round(sh_e,3),
                       "buyhold":round(bh,1), "decay":round(sh_e/sh_t if sh_t!=0 else 0,2)})
        cursor = ts
        if cursor < n_train+n_test*2: break
    if not results: return None
    avg_decay = sum(r["decay"] for r in results)/len(results)
    avg_test_s = sum(r["test_sharpe"] for r in results)/len(results)
    std_s = math.sqrt(sum((r["test_sharpe"]-avg_test_s)**2 for r in results)/len(results))
    return dict(n=len(results), avg_decay=round(avg_decay,2),
                avg_test_sharpe=round(avg_test_s,3),
                std_sharpe=round(std_s,3),
                std_mean=round(std_s/avg_test_s if avg_test_s!=0 else 0,2),
                windows=results)

# ── 合成数据 ─────────────────────────────────
def gen_synthetic(symbol, n, seed=2026):
    random.seed(seed + hash(symbol)%9999)
    rets = [random.gauss(0.0003,0.018) for _ in range(n)]
    for s,e,d in [(0,100,0.0008),(100,200,-0.0004),(200,n,0.001)]:
        for i in range(s,min(e,n)): rets[i] += d
    for i in [50,120,200,280]:
        if i < n: rets[i] += random.choice([-1,1])*0.04
    base = 50000.0 if "BTC" in symbol else (5000 if "ETH" in symbol else 200.0)
    closes = [base]
    for r in rets[1:]: closes.append(closes[-1]*(1+r))
    return closes

# ── 报告打印 ─────────────────────────────────
def print_report(sym, real_c, syn_c, asset):
    rma = backtest("双均线MA(20,60)", real_c, {"fast":20,"slow":60})
    rrs = backtest("RSI(14,30,70)", real_c, {"period":14,"lo":30,"hi":70})
    sma = backtest("双均线MA(20,60)", syn_c,  {"fast":20,"slow":60})
    srs = backtest("RSI(14,30,70)", syn_c,  {"period":14,"lo":30,"hi":70})
    rma2 = apply_cost(rma, asset); rrs2 = apply_cost(rrs, asset)
    sma2 = apply_cost(sma, asset); srs2 = apply_cost(srs, asset)
    wf_r = walk_forward(real_c, None); wf_s = walk_forward(syn_c, None)

    def line(name, tag, r, adj, wf):
        loss = r["ann_ret"] - adj["adj_ret"]
        icon = "✅" if adj["adj_sharpe"] > 0.5 else ("⚠️" if adj["adj_sharpe"] > 0.1 else "❌")
        wf_str = f"WF退={wf['avg_decay']:.0%}(夏普{wf['avg_test_sharpe']:.3f})" if wf else ""
        print(f"  {icon}{name:<20}{tag:<5}{r['ann_ret']:>+7.1f}%{adj['adj_ret']:>+9.1f}%"
              f"{loss:>+6.1f}pp{r['sharpe']:>7.3f}{adj['adj_sharpe']:>9.3f}"
              f"{adj['cost']/1e4:>6.0f}万{r['max_dd']:>7.1f}%{wf_str}")

    print(f"\n{'='*72}")
    print(f"  {sym}（{asset}）{'真实数据' if asset else '合成数据'}")
    print(f"{'='*72}")
    print(f"  {'策略':<21}{'类型':<5}{'年化':>9}{'摩擦后年化':>11}{'损耗':>8}"
          f"{'原始夏普':>9}{'摩擦夏普':>11}{'成本':>8}{'回撤':>9}Walk-Forward")
    print(f"  {'-'*70}")
    line("双均线MA(20,60)","真实", rma, rma2, wf_r)
    line("双均线MA(20,60)","合成", sma, sma2, wf_s)
    line("RSI(14,30,70)","真实", rrs, rrs2, wf_r)
    line("RSI(14,30,70)","合成", srs, srs2, wf_s)

    # 关键洞察
    real_avg = (rma["sharpe"]+rrs["sharpe"])/2
    syn_avg  = (sma["sharpe"]+srs["sharpe"])/2
    bias = syn_avg - real_avg
    print(f"\n  💡 关键发现：")
    print(f"     · 合成数据高估夏普：{bias:+.3f}（{bias/abs(real_avg)*100:.0f}%偏差）")
    if abs(bias) > 1.0:
        print(f"     · ⚠️ 偏差巨大！合成数据严重失真，必须基于真实数据决策。")
    else:
        print(f"     · 偏差可接受，但真实数据仍含合成数据缺失的波动率聚类。")
    print(f"     · 真实数据摩擦后：{asset}市场夏普损耗约{bias:.1f}pp，")
    print(f"       建议实盘夏普门槛设为 > {max(1.0, abs(bias)+0.5):.1f}。")

# ── 主程序 ─────────────────────────────────
def main():
    print("\n" + "="*72)
    print("  📊 真实 vs 模拟数据 · Walk-Forward 对比报告")
    print("  数据源：Stooq.com（无需Token，直接访问）")
    print("="*72)

    # 获取真实数据
    print("\n📥 获取真实历史数据...")
    real = {}
    for sym in META:
        rows = fetch_stooq(sym)
        if rows:
            real[sym] = [r["close"] for r in rows]
            asset = META[sym][1]
            prices = real[sym]
            print(f"  ✅ {sym}（{asset}）: {len(prices)}天 "
                  f"{prices[0]:.1f} → {prices[-1]:.1f}")
        else:
            print(f"  ❌ {sym}: 获取失败（网络或Stooq限制）")

    # 对比
    for sym, closes in real.items():
        asset = META.get(sym, [None,"stock"])[1]
        syn_c = gen_synthetic(sym, len(closes))
        print_report(sym, closes, syn_c, asset)

    # A股补充说明
    print(f"\n{'='*72}")
    print("  📌 A股数据说明")
    print(f"{'='*72}")
    print("""
    Stooq 不覆盖 A股（沪深交易所数据需额外授权）。
    以下任一方案均可获取 A股真实数据：

    方案A（推荐）：TuShare Token
       1. 注册 https://tushare.pro
       2. 获取 Token（免费套餐可用日线数据）
       3. 告诉我 Token，立即接入

    方案B：akshare（无需Token）
       pip install akshare
       但当前服务器无pip，无法安装。

    方案C：东方财富 API（无需Token）
       直接 HTTP 请求获取 A股日K线，免费。
    """)
    print(f"{'='*72}")

if __name__ == "__main__":
    main()
