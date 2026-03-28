#!/usr/bin/env python3
"""
multi_expert_v3.py — 多专家量化系统 v3.0 最终版
5轮迭代 + Regime感知 + Stooq真实数据 + Walk-Forward验证
"""
import sys, math, random, ssl, urllib.request, concurrent.futures
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
ctx = ssl.create_default_context()
ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE

STOOQ = {
    "BTCUSDT":("btc.v","crypto"),"ETHUSDT":("eth.v","crypto"),
    "SOLUSDT":("sol.v","crypto"),"AAPL":("aapl.US","stock"),
    "NVDA":("nvda.US","stock"),  "TSLA":("tsla.US","stock"),
}

def fetch_stooq(sym, n=300):
    code=STOOQ.get(sym.upper(),[None])[0]
    if not code: return None
    url=f"https://stooq.com/q/d/l/?s={code}&d1=20230101&d2=20241231&i=d"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req,context=ctx,timeout=12) as r:
            raw=r.read().decode()
    except: return None
    rows=[]
    for line in raw.strip().split("\r\n")[1:]:
        p=line.split(",")
        if len(p)<5: continue
        try: rows.append({"date":p[0],"close":float(p[4])})
        except: pass
    rows.reverse()
    return rows[:n] if len(rows)>n else rows

def gen_synthetic(sym, n, seed=2026):
    rng=random.Random(seed+hash(sym.upper())%9999)
    phases=[(0,80,0.0009,0.016),(80,160,-0.0004,0.020),(160,n,0.0012,0.017)]
    events={50:0.06,110:-0.05,170:0.07,230:-0.04}
    rets=[0.0]*n
    for i in range(1,n):
        d=next((db for s,e,db,_ in phases if s<=i<e),0.0002)
        if i in events: d+=events[i]
        rets[i]=rng.gauss(d,0.018)
    base=50000 if "BTC" in sym.upper() else(5000 if "ETH" in sym.upper() else 200)
    closes=[base]
    for r in rets[1:]: closes.append(closes[-1]*(1+r))
    return closes

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

def macd_calc(cps):
    n=len(cps);e12=ema(cps,12);e26=ema(cps,26)
    md=[0.0]*n
    for i in range(26,n): md[i]=e12[i]-e26[i]
    k=2/(9+1);sig=[md[0]]*n
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
    n=len(cps);md,sig=macd_calc(cps);s=[0]*n
    for i in range(26,n):
        if md[i]>sig[i] and md[i-1]<=sig[i-1]: s[i]=1
        elif md[i]<sig[i] and md[i-1]>=sig[i-1]: s[i]=-1
    return s

SIGNALS = {
    "MA(5,20)":     (lambda cps: sig_ma(cps,5,20),   "trend"),
    "MA(10,60)":    (lambda cps: sig_ma(cps,10,60),  "trend"),
    "MA(20,120)":   (lambda cps: sig_ma(cps,20,120), "trend"),
    "RSI(14,30,70)":(lambda cps: sig_rsi(cps,14,30,70), "mean_reversion"),
    "RSI(6,20,80)": (lambda cps: sig_rsi(cps,6,20,80),  "mean_reversion"),
    "MACD":          (lambda cps: sig_macd(cps),     "trend"),
    "布林带":         (lambda cps: sig_bb(cps,20,2.0),   "mean_reversion"),
}

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

def backtest(name, cps, sig_fn, initial=1_000_000.0, commission=0.04, spread=20, stamp=0.10):
    n=len(cps)
    if n<30: return None
    sig=sig_fn(cps); cash=initial; pos=0; entry_px=0.0
    equity=[initial]; trades=[]; cost=0.0
    for i in range(1,n):
        px=cps[i]
        if sig[i]==1 and pos==0:
            cp=px*(1+0.0005); comm=cp*(commission/100+spread/10000)
            pos=int(cash*0.98/cp); cash-=cp*pos+comm*pos; cost+=comm*pos
            entry_px=px
        elif sig[i]==-1 and pos>0:
            pp=px*(1-0.0005); tc=pp*(commission/100+spread/10000+stamp/100)
            net=pp*pos-tc
            trades.append({"ret":round((px-entry_px)/entry_px*100,2),"pnl":round(cash+net-initial,0)})
            cash+=net; pos=0; cost+=tc
        equity.append(cash+pos*px)
    final=equity[-1]
    ann=((final/initial)**(252/max(n-1,1))-1)*100
    rets=[(equity[i]-equity[i-1])/equity[i-1] for i in range(1,len(equity))]
    vol=math.sqrt(sum(r*r for r in rets)/max(len(rets),1))*math.sqrt(252)
    sh=ann/vol if vol>0 else 0.0
    peak=initial; mdd=0.0
    for v in equity:
        if v>peak: peak=v
        dd=(v-peak)/peak
        if dd<mdd: mdd=dd
    mdd=abs(mdd)*100
    wins=[t for t in trades if t["ret"]>0]
    wr=len(wins)/len(trades) if trades else 0.0
    adj=ann-(cost/initial)*100
    adj_sh=adj/vol if vol>0 else 0.0
    return dict(name=name,ann=round(ann,1),adj_ann=round(adj,1),
                sh=round(sh,2),adj_sh=round(adj_sh,2),
                mdd=round(mdd,1),n=len(trades),wr=round(wr*100,0),
                cost=round(cost,0),equity=equity,final=round(final,0))

def score_evals(r):
    if not r or r["n"]<2: return -999.0,False,"交易次数不足"
    sh=r["adj_sh"]; ann=r["adj_ann"]; mdd=r["mdd"]; wr=r["wr"]
    sharpe_sc=min(max(sh/2.0*35,-35),35)
    dd_sc=max(0,(35-mdd)/35*25) if mdd<35 else 0
    wr_sc=wr/100*15; trades_sc=min(r["n"]/10*15,15)
    composite=round(sharpe_sc+dd_sc+wr_sc+trades_sc,1)
    if ann<-30: return composite,False,f"年化{ann:.1f}%<-30%"
    if ann<5 and sh<0.3: return composite,False,f"夏普{sh:.2f}+年化{ann:.1f}%双低"
    if mdd>40: return composite,False,f"回撤{mdd:.1f}%>40%"
    if r["n"]<3: return composite,False,f"交易{r['n']}<3"
    return composite,True,"纳入"

def debate(evals, regime):
    t_evals=sorted([e for e in evals if e["type"]=="trend"],key=lambda x:x["score"],reverse=True)
    m_evals=sorted([e for e in evals if e["type"]=="mean_reversion"],key=lambda x:x["score"],reverse=True)
    best_t=t_evals[0] if t_evals else None
    best_m=m_evals[0] if m_evals else None
    recs=regime.get("rec",[])
    t_rec=any("趋势" in r or "均线" in r or "动量" in r for r in recs)
    m_rec=any("RSI" in r or "布林" in r for r in recs)
    if t_rec and not m_rec: w_t,w_m=0.70,0.30;winner="TrendExpert"
    elif m_rec and not t_rec: w_t,w_m=0.30,0.70;winner="MeanReversionExpert"
    elif best_t and best_m:
        if best_t["score"]>best_m["score"]+10: w_t,w_m=0.65,0.35;winner="TrendExpert"
        elif best_m["score"]>best_t["score"]+10: w_t,w_m=0.35,0.65;winner="MeanReversionExpert"
        else: w_t,w_m=0.50,0.50;winner="TIE"
    elif best_t: w_t,w_m=0.80,0.20;winner="TrendExpert"
    elif best_m: w_t,w_m=0.20,0.80;winner="MeanReversionExpert"
    else: w_t,w_m=0.50,0.50;winner="TIE"
    return {"winner":winner,"w_t":w_t,"w_m":w_m}

def build_portfolio(debate, evals, regime, max_pos=0.40):
    w_t=debate["w_t"]; w_m=debate["w_m"]
    all_w={}
    for e in evals:
        w=e["score"]*(w_t if e["type"]=="trend" else w_m)
        all_w[e["name"]]=max(w,0.0)
    total=sum(all_w.values()) or 1.0
    norm={k:v/total*max_pos for k,v in all_w.items()}
    for e in evals:
        e["weight"]=norm.get(e["name"],0.0)
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
    return {"n":len(wins),"avg_decay":round(avg_d,2),"overall":overall,"windows":wins}

def sentiment_proxy(cps):
    if len(cps)<20: return "NEUTRAL",0.0,0.0
    ret20=(cps[-1]/cps[-20]-1)
    if ret20>0.08: return "POSITIVE",min(ret20*100,100),min(ret20*100,100)
    if ret20<-0.08: return "NEGATIVE",max(ret20*100,-100),max(-ret20*100,100)
    return "NEUTRAL",0.0,50.0

def run(symbols, n_days=300, rounds=5, seed=2026):
    print("\n"+"="*68)
    print("  🌡️  多专家量化系统 v3.0 — 5轮迭代 + Regime感知 + 真实数据")
    print("="*68)

    # 加载数据
    data={}
    for sym in symbols:
        rows=fetch_stooq(sym,n_days)
        if rows:
            cps=[r["close"] for r in rows]
            bh_ret=(cps[-1]/cps[0]-1)*100
            print(f"  ✅ {sym}: {len(cps)}天 Stooq 涨跌{bh_ret:+.1f}%")
            data[sym]=cps
        else:
            cps=gen_synthetic(sym,n_days,seed)
            print(f"  ⚠️  {sym}: {len(cps)}天 合成数据")
            data[sym]=cps

    if not data: return
    main_sym=list(data.keys())[0]
    cps_main=data[main_sym]
    n=len(cps_main)

    prev_top=None
    all_rounds=[]

    for rnd in range(1,rounds+1):
        print(f"\n{'='*65}\n  ▶ 第 {rnd} 轮\n{'='*65}")

        # Step1: 情绪
        sent_label,sent_score,sent_conf=sentiment_proxy(cps_main)
        print(f"[Step1] 📰 情绪={sent_label}({sent_score:+.1f}) 置信={sent_conf:.0f}%")

        # Step2: Regime（用第rnd轮对应的数据切片来模拟逐步向前）
        t_idx = min(120+rnd*30, n-1)
        regime_r=detect_regime(cps_main, t_idx)
        print(f"[Step2] 🌡️ Regime={regime_r['label']} 评分={regime_r['score']:+.0f} "
              f"推荐={regime_r['rec']} 仓位≤{regime_r['pos_cap']:.0%}")

        # Step3: 专家评估
        results=[]
        for name,(sig_fn,stype) in SIGNALS.items():
            r=backtest(name,cps_main,sig_fn)
            if not r: continue
            score,ok,reason=score_evals(r)
            wf={}
            if n>=250: wf=walk_forward(cps_main,sig_fn)
            if wf.get("overall")=="FAIL":
                score=score*0.7; ok=False; reason=f"WF FAIL(退={wf['avg_decay']:.0%})"
            results.append(dict(name=name,type=stype,sig=sig_fn,
                     ann=r["ann"],adj_ann=r["adj_ann"],
                     sh=r["sh"],adj_sh=r["adj_sh"],
                     mdd=r["mdd"],n=r["n"],wr=r["wr"],
                     score=score,ok=ok,reason=reason,
                     weight=0.0,wf=wf))

        results.sort(key=lambda x:x["score"],reverse=True)
        accepted=[r for r in results if r["ok"]]
        print(f"\n[Step3] Expert2 评估：候选{len(results)} | 纳入{len(accepted)} | 淘汰{len(results)-len(accepted)}")
        for r in results[:7]:
            icon="✅" if r["ok"] else "❌"
            wf_s=f" WF:{r['wf'].get('overall','—')}({r['wf'].get('avg_decay',0):.0%})" if r.get("wf") else ""
            print(f"  {icon} {r['name']:<18} 分={r['score']:>5.1f} "
                  f"夏普={r['adj_sh']:>5.2f} 年化={r['adj_ann']:>+6.1f}% "
                  f"回撤={r['mdd']:>5.1f}% {r['reason']}{wf_s}")

        # Step4: 辩论
        db=debate(accepted if accepted else results,regime_r)
        print(f"\n[Step4] 辩论胜出：{db['winner']} "
              f"（趋势={db['w_t']:.0%} | 均值回归={db['w_m']:.0%}）")

        # Step5: 组合
        max_pos=regime_r.get("pos_cap",0.40)
        portfolio=build_portfolio(db,accepted if accepted else results,regime_r,max_pos)
        top=sorted(portfolio,key=lambda x:x["score"],reverse=True)[:5]

        top0_score = top[0]["score"] if top else 0.0
        print(f"\n[Step5] 最终入选 {len(top)} 个策略（仓位≤{max_pos:.0%}）：")
        for r in top:
            wf_s=f" WF:{r['wf'].get('overall','—')}" if r.get("wf") else ""
            print(f"  ✅ {r['name']:<18} {r['type']:<14} "
                  f"分={r['score']:>5.1f} 夏普={r['adj_sh']:>5.2f} "
                  f"年化={r['adj_ann']:>+6.1f}% 权重={r['weight']:.1%}{wf_s}")

        # 收敛
        top_ids={r["name"] for r in top}
        converged=(top_ids==prev_top) if prev_top else False
        prev_top=top_ids

        print(f"\n  📊 第{rnd}轮：Regime={regime_r['label']} | 情绪={sent_label} | "
              f"辩论={db['winner']} | Top分数={top0_score:.1f}")
        if rnd>=2 and converged:
            print(f"\n  ✅ 第{rnd}轮名单与第{rnd-1}轮相同，已收敛！")
            break

        all_rounds.append({"round":rnd,"regime":regime_r,"sentiment":sent_label,
                          "debate":db,"top":top,"accepted":accepted})

    # 最终汇报
    print(f"\n{'='*68}")
    print("  🏁 5轮迭代最终汇总")
    print(f"{'='*68}")
    print(f"\n  {'轮':<3} {'Regime':<10} {'情绪':<8} {'辩论胜出':<20} "
          f"{'最佳策略':<16} {'分':>5} {'年化':>8}")
    print(f"  {'─'*60}")
    for rd in all_rounds:
        top1=rd["top"][0] if rd["top"] else {"name":"—","score":0,"adj_ann":0}
        print(f"  第{rd['round']}轮 {rd['regime']['label']:<10} {rd['sentiment']:<8} "
              f"{rd['debate']['winner']:<20} "
              f"{top1.get('name','—'):<16} {top1.get('score',0):>5.1f} "
              f"{top1.get('adj_ann',0):>+7.1f}%")

    # 跨轮稳定性
    if len(all_rounds)>=2:
        regimes=[r["regime"]["label"] for r in all_rounds]
        winners=[r["debate"]["winner"] for r in all_rounds]
        r_stab=1-len(set(regimes))/len(regimes)
        w_stab=1-len(set(winners))/len(winners)
        print(f"\n  📈 跨轮稳定性：")
        print(f"     Regime变化率：{r_stab:.0%}（0%=完全稳定，100%=完全变化）")
        print(f"     辩论胜出变化率：{w_stab:.0%}")

    # 推荐汇总
    print(f"\n  💡 最终策略推荐（按5轮平均分数）：")
    from collections import Counter
    pool=[]
    for rd in all_rounds:
        for t in rd["top"][:3]: pool.append(t)
    score_sum={}
    cnt={}
    for r in pool:
        score_sum[r["name"]]=score_sum.get(r["name"],0)+r["score"]
        cnt[r["name"]]=cnt.get(r["name"],0)+1
    avg={k:score_sum[k]/cnt[k] for k in score_sum}
    top_strats=sorted(avg.items(),key=lambda x:x[1],reverse=True)[:6]
    for name,avg_sc in top_strats:
        c=cnt[name]
        top1=next((r["name"] for r in pool if r["name"]==name),"—")
        stype=next((r["type"] for r in pool if r["name"]==name),"—")
        print(f"     {name:<18} [{stype}] 平均分={avg_sc:.1f} 出现{c}次/5轮")

    print(f"\n{'='*68}")
    return all_rounds

if __name__=="__main__":
    syms=["BTCUSDT","ETHUSDT","AAPL","NVDA"]
    rnd=5
    if len(sys.argv)>1: syms=sys.argv[1].split(",")
    if len(sys.argv)>2: rnd=int(sys.argv[2])
    run(syms,rounds=rnd)
