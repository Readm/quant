#!/usr/bin/env python3
"""
multi_expert_v35.py — 多专家量化系统 v3.5
数据源：
  腾讯API：沪深300(sh000300) + 港股(腾讯控股/阿里/理想/移动/银行等)
  东方财富：A股个股(宁德时代/招商银行/酒ETF等)
  Stooq：BTC/ETH/GLD

运行：python3 quant/multi_expert_v35.py
"""
import sys, math, random, ssl, urllib.request, concurrent.futures, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
ctx = ssl.create_default_context()
ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE

# ════════════════════════════════════════════════════════════
# 数据获取
# ════════════════════════════════════════════════════════════

# ① 腾讯证券 API（指数 + 港股）
def fetch_tx(sym, start, end, count=500):
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?_var=kline_dayhfq&param={sym},day,{start},{end},{count},qfq")
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=12) as r:
            raw = r.read(100_000).decode("utf-8")
        j = json.loads(raw[raw.index("=")+1:])
        key = list(j.get("data",{}).keys())[0]
        days = j["data"][key].get("day",[])
    except: return []
    rows = []
    for it in days:
        if len(it) < 6: continue
        try: rows.append({"date":it[0],"open":float(it[1]),"close":float(it[2]),
                          "high":float(it[3]),"low":float(it[4]),"vol":float(it[5])})
        except: pass
    rows.reverse()  # oldest→newest
    return rows

# ② 东方财富 API（A股个股）
def fetch_emf(secid, start="20220101", end="20241231", limit=800):
    url = (f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
           f"?secid={secid}&fields1=f1,f2,f3,f4,f5"
           f"&fields2=f51,f52,f53,f54,f55,f56"
           f"&klt=101&fqt=1&beg={start}&end={end}&lmt={limit}")
    req = urllib.request.Request(url, headers={
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer":"https://quote.eastmoney.com/",
    })
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            raw = r.read(80_000).decode("utf-8")
        j = json.loads(raw)
        rows = []
        for kl in j.get("data",{}).get("klines",[]):
            p = kl.split(",")
            if len(p) < 6: continue
            try: rows.append({"date":p[0],"open":float(p[1]),"close":float(p[2]),
                              "high":float(p[3]),"low":float(p[4]),"vol":float(p[5])})
            except: pass
        return rows
    except: return []

# ③ Stooq（加密 + 黄金）
def fetch_stooq(sym, n=300):
    url = f"https://stooq.com/q/d/l/?s={sym}&d1=20230101&d2=20241231&i=d"
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            raw = r.read(5000).decode()
    except: return []
    rows = []
    for line in raw.strip().split("\r\n")[1:]:
        p = line.split(",")
        if len(p) < 5: continue
        try: rows.append({"date":p[0],"close":float(p[4])})
        except: pass
    rows.reverse()
    return rows[:n]

# ════════════════════════════════════════════════════════════
# 指标
# ════════════════════════════════════════════════════════════

def ma(cps,p):
    n=len(cps);out=[0.0]*n
    for i in range(p-1,n): out[i]=sum(cps[i-p+1:i+1])/p
    return out

def ema(cps,p):
    n=len(cps);k=2/(p+1);out=[cps[0]]*n
    for i in range(1,n): out[i]=cps[i]*k+out[i-1]*(1-k)
    return out

def rsi(cps,p=14):
    n=len(cps);out=[50.0]*n
    for i in range(p,n):
        ag=sum(max(0,cps[j]-cps[j-1]) for j in range(p,i+1))/p
        al=sum(max(0,cps[j-1]-cps[j]) for j in range(p,i+1))/p
        out[i]=100-100/(1+ag/(al+1e-9))
    return out

def macd(cps):
    n=len(cps);e12=ema(cps,12);e26=ema(cps,26)
    md=[0.0]*n
    for i in range(26,n): md[i]=e12[i]-e26[i]
    k=2/10;sig=[md[0]]*n
    for i in range(9,n): sig[i]=md[i]*k+sig[i-1]*(1-k)
    return md,sig

def bbands(cps,p=20,mult=2.0):
    n=len(cps);mid=ma(cps,p);std=[0.0]*n
    for i in range(p-1,n):
        v=cps[i-p+1:i+1];m=mid[i]
        std[i]=math.sqrt(sum((x-m)**2 for x in v)/p)
    upper=[0.0]*n;lower=[0.0]*n
    for i in range(p-1,n):
        upper[i]=mid[i]+mult*std[i];lower[i]=mid[i]-mult*std[i]
    return upper,mid,lower

def _vol(cps,window,end):
    if end<window: return 0.0
    rets=[math.log(cps[i]/cps[i-1]) for i in range(end-window+1,end+1) if i>0]
    if len(rets)<2: return 0.0
    mu=sum(rets)/len(rets)
    return math.sqrt(sum((r-mu)**2 for r in rets)/len(rets)*252)

# ════════════════════════════════════════════════════════════
# 信号
# ════════════════════════════════════════════════════════════

def sig_ma(cps,fp,sp):
    n=len(cps);m1=ma(cps,fp);m2=ma(cps,sp);s=[0]*n
    for i in range(sp,n):
        if m1[i]>m2[i] and m1[i-1]<=m2[i-1]: s[i]=1
        elif m1[i]<m2[i] and m1[i-1]>=m2[i-1]: s[i]=-1
    return s

def sig_rsi(cps,period,lo,hi):
    n=len(cps);rv=rsi(cps,period);s=[0]*n
    for i in range(period,n):
        if rv[i-1]<lo and rv[i]>=lo: s[i]=1
        elif rv[i-1]>hi and rv[i]<=hi: s[i]=-1
    return s

def sig_bb(cps,period,n_std):
    n=len(cps);upper,mid,lower=bbands(cps,period,n_std);s=[0]*n
    for i in range(period,n):
        if cps[i]<lower[i] and cps[i-1]>=lower[i]: s[i]=1
        elif cps[i]>upper[i] and cps[i-1]<=upper[i]: s[i]=-1
    return s

def sig_macd(cps):
    n=len(cps);md,sig=macd(cps);s=[0]*n
    for i in range(26,n):
        if md[i]>sig[i] and md[i-1]<=sig[i-1]: s[i]=1
        elif md[i]<sig[i] and md[i-1]>=sig[i-1]: s[i]=-1
    return s

SIGNALS = {
    "MA(5,20)":     (lambda c: sig_ma(c,5,20),   "trend"),
    "MA(10,60)":    (lambda c: sig_ma(c,10,60),  "trend"),
    "MA(20,120)":   (lambda c: sig_ma(c,20,120), "trend"),
    "RSI(14,30,70)":(lambda c: sig_rsi(c,14,30,70), "mean_reversion"),
    "RSI(6,20,80)": (lambda c: sig_rsi(c,6,20,80),  "mean_reversion"),
    "MACD":          (lambda c: sig_macd(c),         "trend"),
    "布林带":         (lambda c: sig_bb(c,20,2.0),      "mean_reversion"),
}

# ════════════════════════════════════════════════════════════
# Regime（无前瞻）
# ════════════════════════════════════════════════════════════

def detect_regime(cps, t):
    if t<120: return {"label":"中性","score":0.0,"rec":["RSI均值回归"],"pos_cap":0.30,"trend":"SIDEWAYS"}
    vol20=_vol(cps,20,t-1); vol60=_vol(cps,60,max(0,t-60))
    vr=vol20/(vol60+1e-9)
    ma20=sum(cps[t-20:t])/20; ma60=sum(cps[t-60:t])/60; ma120=sum(cps[t-120:t])/120
    price=cps[t-1]
    t_up=ma20>ma60 and price>ma120; t_dn=ma20<ma60 and price<ma120
    if vr>1.1 and t_dn:   return {"label":"熊市/恐慌","score":-40.0,"rec":["布林带均值回归"],"pos_cap":0.25,"trend":"DOWNTREND"}
    if vr>1.1 and not t_up: return {"label":"震荡高波","score":-10.0,"rec":["RSI超卖","布林带"],"pos_cap":0.30,"trend":"SIDEWAYS"}
    if vr<=1.1 and t_up: return {"label":"慢牛","score":+35.0,"rec":["趋势追踪","均线多头"],"pos_cap":0.60,"trend":"UPTREND"}
    if t_dn: return {"label":"偏空","score":-25.0,"rec":["防御配置"],"pos_cap":0.20,"trend":"DOWNTREND"}
    return {"label":"震荡整理","score":+5.0,"rec":["RSI均值回归","布林带"],"pos_cap":0.40,"trend":"SIDEWAYS"}

# ════════════════════════════════════════════════════════════
# 回测
# ════════════════════════════════════════════════════════════

def backtest(name, cps, sig_fn, initial=1_000_000.0, commission=0.03, spread=5, stamp=0.10):
    n=len(cps)
    if n<30: return None
    sig=sig_fn(cps); cash=initial; pos=0; entry_px=0.0
    equity=[initial]; trades=[]; cost=0.0
    for i in range(1,n):
        px=cps[i]
        if sig[i]==1 and pos==0:
            cp=px*(1+0.0003); comm=cp*(commission/100+spread/10000)
            pos=int(cash*0.99/cp); cash-=cp*pos+comm*pos; cost+=comm*pos; entry_px=px
        elif sig[i]==-1 and pos>0:
            pp=px*(1-0.0003); tc=pp*(commission/100+spread/10000+stamp/100)
            net=pp*pos-tc; trades.append({"ret":round((px-entry_px)/entry_px*100,2)})
            cash+=net; pos=0; cost+=tc
        equity.append(cash+pos*px)
    final=equity[-1]
    ann=((final/initial)**(252/max(n-1,1))-1)*100
    rets=[(equity[i]-equity[i-1])/equity[i-1] for i in range(1,len(equity))]
    vol=math.sqrt(sum(r*r for r in rets)/max(len(rets),1)*252)
    sh=ann/vol if vol>0 else 0.0
    peak=initial; mdd=0.0
    for v in equity:
        if v>peak: peak=v
        dd=(v-peak)/peak
        if dd<mdd: mdd=dd
    wins=[t for t in trades if t["ret"]>0]
    wr=len(wins)/len(trades) if trades else 0.0
    adj=ann-(cost/initial)*100
    adj_sh=adj/vol if vol>0 else 0.0
    return dict(name=name,ann=round(ann,1),adj_ann=round(adj,1),
                sh=round(sh,2),adj_sh=round(adj_sh,2),
                mdd=round(abs(mdd)*100,1),n=len(trades),wr=round(wr*100,0),
                cost=round(cost,0),equity=equity,final=round(final,0))

def score_it(r):
    if not r or r["n"]<2: return -999.0,False,"交易不足"
    sh=r["adj_sh"]; ann=r["adj_ann"]; mdd=r["mdd"]; wr=r["wr"]
    sc=min(max(sh/2.0*35,-35),35)+max(0,(35-mdd)/35*25 if mdd<35 else 0)+wr/100*15+min(r["n"]/10*15,15)
    sc=round(sc,1)
    if ann<-30: return sc,False,f"年化{ann:.1f}%<-30%"
    if mdd>45: return sc,False,f"回撤{mdd:.1f}%>45%"
    if ann<0 and sh<0: return sc,False,f"双负"
    return sc,True,"纳入"

# ════════════════════════════════════════════════════════════
# 辩论 + 组合
# ════════════════════════════════════════════════════════════

def debate(evals, regime):
    t_ev=[e for e in evals if e["type"]=="trend"]
    m_ev=[e for e in evals if e["type"]=="mean_reversion"]
    best_t=max(t_ev,key=lambda x:x["score"],default=None)
    best_m=max(m_ev,key=lambda x:x["score"],default=None)
    recs=regime.get("rec",[])
    tr_rec=any("趋势" in r or "均线" in r for r in recs)
    mr_rec=any("RSI" in r or "布林" in r for r in recs)
    if tr_rec and not mr_rec: w_t,w_m=0.70,0.30;win="TrendExpert"
    elif mr_rec and not tr_rec: w_t,w_m=0.30,0.70;win="MeanReversionExpert"
    elif best_t and best_m:
        if best_t["score"]>best_m["score"]+10: w_t,w_m=0.65,0.35;win="TrendExpert"
        elif best_m["score"]>best_t["score"]+10: w_t,w_m=0.35,0.65;win="MeanReversionExpert"
        else: w_t,w_m=0.50,0.50;win="TIE"
    elif best_t: w_t,w_m=0.80,0.20;win="TrendExpert"
    elif best_m: w_t,w_m=0.20,0.80;win="MeanReversionExpert"
    else: w_t,w_m=0.50,0.50;win="TIE"
    return {"winner":win,"w_t":w_t,"w_m":w_m}

def build_portfolio(db, evals, max_pos):
    w_t,w_m=db["w_t"],db["w_m"]
    all_w={e["name"]:max(e["score"]*(w_t if e["type"]=="trend" else w_m),0.0) for e in evals}
    tot=sum(all_w.values()) or 1.0
    norm={k:v/tot*max_pos for k,v in all_w.items()}
    for e in evals: e["weight"]=norm.get(e["name"],0.0)
    return evals

def walk_forward(cps, sig_fn, n_train=180, n_test=60):
    n=len(cps); wins=[]; cursor=n
    while True:
        te=cursor; ts=max(n_train+n_test,cursor-n_test); tr=max(0,ts-n_train)
        if ts-tr<n_train or te-ts<30: break
        tc=cps[tr:ts]; ec=cps[ts:te]
        if len(ec)<30: break
        rt=backtest("t",tc,sig_fn); re=backtest("e",ec,sig_fn)
        if rt and re:
            dec=re["adj_sh"]/abs(rt["adj_sh"]) if rt["adj_sh"]!=0 else 0
            wins.append({"tr_sh":rt["adj_sh"],"te_sh":re["adj_sh"],
                        "decay":round(dec,2),
                        "verdict":"PASS" if dec>=0.5 and re["adj_sh"]>0.3 else "FAIL"})
        cursor=ts
        if cursor<n_train+n_test*2: break
    if not wins: return {}
    avg_d=sum(w["decay"] for w in wins)/len(wins)
    passes=sum(1 for w in wins if w["verdict"]=="PASS")
    overall="PASS" if passes>=len(wins)*0.6 else "WEAK" if passes>=1 else "FAIL"
    return {"n":len(wins),"avg_decay":round(avg_d,2),"overall":overall}

# ════════════════════════════════════════════════════════════
# 加载数据
# ════════════════════════════════════════════════════════════

def load_all_data():
    print("\n📥 加载多市场数据...")
    all_data = {}
    errors = []

    # ── 沪深300（腾讯API）──
    try:
        rows = fetch_tx("sh000300", "2022-01-01", "2024-12-31")
        if rows:
            cps = [r["close"] for r in rows]
            print(f"  ✅ 沪深300(sh000300): {len(rows)}天")
            all_data["CSI300"] = cps
    except Exception as e:
        errors.append(f"沪深300: {e}")

    # ── 港股（腾讯API）──
    hk_stocks = [
        ("hk09988", "阿里巴巴"),
        ("hk03690", "京东物流"),
        ("hk02020", "理想汽车"),
        ("hk02628", “中国人寿”"),
        ("hk00941", "中国移动"),
        ("hk00939", "建设银行(港)"),
        ("hk06160", "百济神州"),
        ("hk02382", "舜宇光学"),
    ]
    for sym, name in hk_stocks:
        try:
            rows = fetch_tx(sym, "2022-01-01", "2024-12-31")
            if rows and len(rows) >= 200:
                cps = [r["close"] for r in rows]
                bh = (cps[-1]/cps[0]-1)*100
                print(f"  ✅ {name}（{sym}）: {len(rows)}天 涨跌{bh:+.1f}%")
                all_data[f"HK_{name}"] = cps
        except Exception as e:
            pass

    # ── A股个股（东方财富API）──
    a_stocks = [
        ("0.300750", "宁德时代"),
        ("1.600036", "招商银行"),
        ("0.000001", "平安银行"),
        ("1.512690", "酒ETF"),
    ]
    for secid, name in a_stocks:
        try:
            rows = fetch_emf(secid)
            if rows and len(rows) >= 200:
                cps = [r["close"] for r in rows]
                bh = (cps[-1]/cps[0]-1)*100
                print(f"  ✅ {name}: {len(rows)}天 涨跌{bh:+.1f}%")
                all_data[f"A_{name}"] = cps
        except Exception as e:
            pass

    # ── 加密 + 黄金（Stooq）──
    for sym, name, label in [
        ("btc.v","BTC","crypto"), ("eth.v","ETH","crypto"),
        ("gld.US","GLD","etf"),
    ]:
        try:
            rows = fetch_stooq(sym, 300)
            if rows and len(rows) >= 200:
                cps = [r["close"] for r in rows]
                bh = (cps[-1]/cps[0]-1)*100
                print(f"  ✅ {name}（{label}）: {len(rows)}天 涨跌{bh:+.1f}%")
                all_data[name] = cps
        except Exception as e:
            pass

    print(f"\n  共加载 {len(all_data)} 个标的")
    for sym, cps in all_data.items():
        print(f"     {sym}: {len(cps)}天")
    return all_data

# ════════════════════════════════════════════════════════════
# 主程序
# ════════════════════════════════════════════════════════════

def sentiment(cps):
    if len(cps)<20: return "NEUTRAL",0.0
    ret20=cps[-1]/cps[-20]-1
    if ret20>0.08: return "POSITIVE",min(ret20*100,100)
    if ret20<-0.08: return "NEGATIVE",max(-ret20*100,100)
    return "NEUTRAL",0.0

def run(symbols=None, rounds=5):
    print("\n"+"="*68)
    print("  🌡️  多专家量化系统 v3.5 — 多市场版")
    print("  数据：沪深300 + 港股 + A股个股 + 加密 + 黄金ETF")
    print("="*68)

    all_data = load_all_data()
    if not all_data:
        print("❌ 无可用数据"); return

    # 按市场分组
    csi   = {k:v for k,v in all_data.items() if "CSI" in k}
    hk    = {k:v for k,v in all_data.items() if k.startswith("HK_")}
    a     = {k:v for k,v in all_data.items() if k.startswith("A_")}
    other = {k:v for k,v in all_data.items() if not any(x in k for x in ["CSI","HK_","A_"])}

    all_markets = {**csi, **hk, **a, **other}
    prev_top = None
    all_rounds = []

    for rnd in range(1, rounds+1):
        print(f"\n{'='*65}\n  ▶ 第 {rnd} 轮\n{'='*65}")

        # 汇总多市场评估
        market_results = {}
        for mkt_name, mkt_data in [("沪深300",csi),("港股",hk),("A股",a),("其他",other)]:
            if not mkt_data: continue
            sym = list(mkt_data.keys())[0]
            cps = list(mkt_data.values())[0]
            n = len(cps)
            t_idx = min(120+rnd*30, n-1)
            regime = detect_regime(cps, t_idx)
            sent_label, sent_score = sentiment(cps[:t_idx+1])

            evals = []
            for name,(sig_fn,stype) in SIGNALS.items():
                r = backtest(name, cps, sig_fn)
                if not r: continue
                score,ok,reason = score_it(r)
                wf = {}
                if n>=250: wf = walk_forward(cps, sig_fn)
                if wf.get("overall")=="FAIL":
                    score *= 0.7; ok=False; reason=f"WF:{wf['avg_decay']:.0%}"
                evals.append(dict(name=name,type=stype,sig=sig_fn,
                                 ann=r["ann"],adj_ann=r["adj_ann"],
                                 sh=r["sh"],adj_sh=r["adj_sh"],
                                 mdd=r["mdd"],n=r["n"],wr=r["wr"],
                                 score=score,ok=ok,reason=reason,
                                 weight=0.0,wf=wf))

            evals.sort(key=lambda x:x["score"],reverse=True)
            accepted = [e for e in evals if e["ok"]]
            db = debate(accepted if accepted else evals, regime)
            portfolio = build_portfolio(db, accepted if accepted else evals,
                                     regime.get("pos_cap",0.40))
            top = sorted(portfolio, key=lambda x:x["score"], reverse=True)[:4]
            top0 = top[0] if top else None

            ico = "✅" if accepted else "⚠️无纳入"
            print(f"\n  📊 {mkt_name}（{sym}）— Regime={regime['label']}({regime['score']:+.0f}) "
                  f"辩论={db['winner']} {ico}")
            for e in top[:3]:
                wf_s = f" WF:{e['wf'].get('overall','—')}({e['wf'].get('avg_decay',0):.0%})" if e.get("wf") else ""
                print(f"    {e['name']:<18} {e['type']:<14} "
                      f"分={e['score']:>5.1f} 夏普={e['adj_sh']:>5.2f} "
                      f"年化={e['adj_ann']:>+6.1f}%{wf_s}")

            market_results[mkt_name] = {
                "regime":regime,"debate":db,
                "top":top,"accepted":accepted,
                "sentiment":sent_label
            }

        # 全市场汇总
        all_top = []
        for mrd in market_results.values():
            all_top.extend(mrd["top"][:2])
        all_top.sort(key=lambda x:x["score"],reverse=True)
        global_top = all_top[:5]
        top_ids = {e["name"] for e in global_top}
        converged = (top_ids==prev_top) if prev_top else False
        prev_top = top_ids

        print(f"\n  🏆 第{rnd}轮 全球Top5：")
        for e in global_top[:3]:
            print(f"    {e['name']}（{e['type']}）分={e['score']:.1f} "
                  f"夏普={e['adj_sh']:.2f} 年化={e['adj_ann']:+.1f}%")

        if rnd>=2 and converged:
            print(f"\n  ✅ 连续2轮名单一致，已收敛！")
            break

        all_rounds.append({"round":rnd,"markets":market_results,
                          "global_top":global_top})

    # 最终汇总
    print(f"\n{'='*68}")
    print("  🏁 最终汇总")
    print(f"{'='*68}")
    print(f"\n  {'市场':<10} {'轮次':<4} {'Regime':<10} {'辩论胜出':<20} {'最佳策略':<16} {'分数':>5}")
    print(f"  {'─'*60}")
    for rd in all_rounds:
        for mkt, mrd in rd["markets"].items():
            t1 = mrd["top"][0] if mrd["top"] else {"name":"—","score":0}
            print(f"  {mkt:<10} 第{rd['round']}轮 {mrd['regime']['label']:<10} "
                  f"{mrd['debate']['winner']:<20} {t1.get('name','—'):<16} {t1.get('score',0):>5.1f}")

    # 推荐汇总
    from collections import Counter
    pool = []
    for rd in all_rounds:
        for t in rd["global_top"][:2]: pool.append(t["name"])
    cnt = Counter(pool)
    print(f"\n  💡 跨市场推荐（按入选次数）：")
    for name, c in cnt.most_common(6):
        print(f"     {name}: {c}次入选")

    print(f"\n{'='*68}")
    return all_rounds

if __name__ == "__main__":
    run()
