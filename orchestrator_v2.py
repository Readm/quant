#!/usr/bin/env python3
"""
orchestrator_v2.py — 多专家量化系统 v3.0 最终版

修复内容：
  1. 数据源：Stooq 真实数据（替代合成数据）
  2. _load_data：使用相对导入，兼容 quant.experts 结构
  3. _make_snapshot：使用传入参数而非 rp.*
  4. run()：rp=None 时跳过继续
  5. _build_portfolio：weight 正确设为 float
  6. 5 轮迭代 + Walk-Forward 对比

运行：
  python3 quant/orchestrator_v2.py
"""
import sys, json, random, math, ssl, urllib.request, concurrent.futures
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Literal

sys.path.insert(0, str(Path(__file__).parent))
ctx = ssl.create_default_context()
ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE

# ═══════════════════════════════════════════════════════
# 数据获取（Stooq 真实数据）
# ═══════════════════════════════════════════════════════

STOOQ = {
    "BTCUSDT": ("btc.v",   "crypto"),
    "ETHUSDT": ("eth.v",   "crypto"),
    "SOLUSDT": ("sol.v",   "crypto"),
    "AAPL":    ("aapl.US",  "stock"),
    "NVDA":    ("nvda.US",  "stock"),
    "TSLA":    ("tsla.US",  "stock"),
}

def fetch_stooq(sym, n=300):
    code = STOOQ.get(sym.upper(), [None])[0]
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

def gen_synthetic(sym, n, seed=2026):
    rng = random.Random(seed + hash(sym.upper()) % 9999)
    phases = [(0,80,0.0009,0.016),(80,160,-0.0004,0.020),(160,n,0.0012,0.017)]
    events = {50:0.06,110:-0.05,170:0.07,230:-0.04}
    rets = [0.0]*n
    for i in range(1,n):
        d = next((db for s,e,db,_ in phases if s<=i<e), 0.0002)
        if i in events: d += events[i]
        rets[i] = rng.gauss(d, 0.018)
    base = 50000 if "BTC" in sym.upper() else (5000 if "ETH" in sym.upper() else 200)
    closes = [base]
    for r in rets[1:]: closes.append(closes[-1]*(1+r))
    dates = [f"2023-{12*(i//30)+1:02d}-{i%30+1:02d}" for i in range(n)]
    return {"dates": dates, "closes": closes, "source": "Synthetic"}

# ═══════════════════════════════════════════════════════
# 技术指标
# ═══════════════════════════════════════════════════════

def ma(cps, p):
    n=len(cps); out=[0.0]*n
    for i in range(p-1,n): out[i]=sum(cps[i-p+1:i+1])/p
    return out

def ema(cps, p):
    n=len(cps); k=2/(p+1); out=[cps[0]]*n
    for i in range(1,n): out[i]=cps[i]*k+out[i-1]*(1-k)
    return out

def rsi(cps, p=14):
    n=len(cps); out=[50.0]*n
    for i in range(p,n):
        ag=sum(max(0,cps[j]-cps[j-1]) for j in range(p,i+1))/p
        al=sum(max(0,cps[j-1]-cps[j]) for j in range(p,i+1))/p
        out[i]=100-100/(1+ag/(al+1e-9))
    return out

def macd(cps):
    n=len(cps); e12=ema(cps,12); e26=ema(cps,26)
    md=[0.0]*n
    for i in range(26,n): md[i]=e12[i]-e26[i]
    k=2/(9+1); sig=[md[0]]*n
    for i in range(9,n): sig[i]=md[i]*k+sig[i-1]*(1-k)
    return md,sig

def bbands(cps,p=20,mult=2.0):
    n=len(cps); mid=ma(cps,p); std=[0.0]*n
    for i in range(p-1,n):
        v=cps[i-p+1:i+1]; m=mid[i]
        std[i]=math.sqrt(sum((x-m)**2 for x in v)/p)
    upper=[0.0]*n; lower=[0.0]*n
    for i in range(p-1,n):
        upper[i]=mid[i]+mult*std[i]; lower[i]=mid[i]-mult*std[i]
    return upper,mid,lower

def atr(cps, highs, lows, p=14):
    n=len(cps); trs=[0.0]*n
    for i in range(1,n):
        trs[i]=max(highs[i]-lows[i],abs(highs[i]-cps[i-1]),abs(lows[i]-cps[i-1]))
    out=[trs[0]]*n
    for i in range(p,n): out[i]=sum(trs[i-p+1:i+1])/p
    return out

def compute_indicators(closes):
    return {
        "ma5": ma(closes,5), "ma10": ma(closes,10),
        "ma20": ma(closes,20), "ma60": ma(closes,60),
        "ma120": ma(closes,120),
        "ema12": ema(closes,12), "ema26": ema(closes,26),
        "rsi14": rsi(closes,14), "rsi6": rsi(closes,6),
        "macd": macd(closes)[0],
        "macd_sig": macd(closes)[1],
        "bb_upper": bbands(closes,20,2.0)[0],
        "bb_mid": bbands(closes,20,2.0)[1],
        "bb_lower": bbands(closes,20,2.0)[2],
    }

# ═══════════════════════════════════════════════════════
# Regime 检测（无前瞻）
# ═══════════════════════════════════════════════════════

def detect_regime(closes, t):
    if t < 120:
        return {"label":"中性","score":0.0,"rec":["RSI均值回归"],
                "pos_cap":0.30,"vol_ratio":1.0,"trend":"SIDEWAYS"}
    vol20=_rolling_vol(closes,20,t-1)
    vol60=_rolling_vol(closes,60,max(0,t-60))
    vol_ratio=vol20/(vol60+1e-9)
    ma20=sum(closes[t-20:t])/20
    ma60=sum(closes[t-60:t])/60
    ma120=sum(closes[t-120:t])/120
    price=closes[t-1]
    ret20=(closes[t-1]/(closes[t-21]+1e-9)-1) if t>20 else 0.0
    vol_high=vol_ratio>1.1
    trend_up=ma20>ma60 and price>ma120
    trend_down=ma20<ma60 and price<ma120
    if vol_high and trend_down:
        return {"label":"熊市/恐慌","score":-40.0,"rec":["布林带均值回归"],"pos_cap":0.25,"vol_ratio":round(vol_ratio,3),"trend":"DOWNTREND"}
    elif vol_high and not trend_up:
        return {"label":"震荡高波","score":-10.0,"rec":["RSI超卖","布林带"],"pos_cap":0.30,"vol_ratio":round(vol_ratio,3),"trend":"SIDEWAYS"}
    elif not vol_high and trend_up:
        return {"label":"慢牛","score":+35.0,"rec":["趋势追踪","均线多头"],"pos_cap":0.60,"vol_ratio":round(vol_ratio,3),"trend":"UPTREND"}
    elif trend_down:
        return {"label":"偏空","score":-25.0,"rec":["防御配置"],"pos_cap":0.20,"vol_ratio":round(vol_ratio,3),"trend":"DOWNTRAND"}
    else:
        return {"label":"震荡整理","score":+5.0,"rec":["RSI均值回归","布林带"],"pos_cap":0.40,"vol_ratio":round(vol_ratio,3),"trend":"SIDEWAYS"}

def _rolling_vol(cps, window, end_idx):
    if end_idx<window: return 0.0
    rets=[math.log(cps[i]/cps[i-1]) for i in range(end_idx-window+1,end_idx+1) if i>0]
    if len(rets)<2: return 0.0
    mu=sum(rets)/len(rets)
    return math.sqrt(sum((r-mu)**2 for r in rets)/len(rets)*252)

# ═══════════════════════════════════════════════════════
# 信号函数
# ═══════════════════════════════════════════════════════

def sig_ma_cross(cps,fp,sp):
    n=len(cps); m1=ma(cps,fp); m2=ma(cps,sp); s=[0]*n
    for i in range(sp,n):
        if m1[i]>m2[i] and m1[i-1]<=m2[i-1]: s[i]=1
        elif m1[i]<m2[i] and m1[i-1]>=m2[i-1]: s[i]=-1
    return s

def sig_rsi(cps,period,lo,hi):
    n=len(cps); rv=rsi(cps,period); s=[0]*n
    for i in range(period,n):
        if rv[i-1]<lo and rv[i]>=lo: s[i]=1
        elif rv[i-1]>hi and rv[i]<=hi: s[i]=-1
    return s

def sig_bollinger(cps,period,n_std):
    n=len(cps); upper,mid,lower=bbands(cps,period,n_std); s=[0]*n
    for i in range(period,n):
        if cps[i]<lower[i] and cps[i-1]>=lower[i]: s[i]=1
        elif cps[i]>upper[i] and cps[i-1]<=upper[i]: s[i]=-1
    return s

def sig_regime_aware(cps, t, regime):
    recs=regime.get("rec",["RSI均值回归"])
    for rec in recs:
        if "布林带" in rec:
            s=sig_bollinger(cps,20,2.0); return s[t] if t<len(s) else 0
        elif "RSI" in rec:
            s=sig_rsi(cps,14,30,70); return s[t] if t<len(s) else 0
        elif "趋势" in rec or "均线" in rec:
            s=sig_ma_cross(cps,20,60); return s[t] if t<len(s) else 0
        elif "防御" in rec:
            return 0  # 空仓
    return 0

# ═══════════════════════════════════════════════════════
# 回测引擎
# ═══════════════════════════════════════════════════════

def backtest(name, cps, params, sig_fn,
             initial=1_000_000.0, commission=0.04,
             spread_bps=20, stamp=0.10, verbose=False):
    n=len(cps)
    if n<30: return None
    sig=sig_fn(cps, params) if callable(sig_fn) else sig_fn(cps)
    cash=initial; pos=0; entry_px=0.0; entry_idx=0
    equity=[initial]; trades=[]; cost=0.0
    for i in range(1,n):
        px=cps[i]
        if sig[i]==1 and pos==0:
            cost_px=px*(1+0.0005)
            comm=cost_px*(commission/100+spread_bps/10000)
            pos=int(cash*0.98/cost_px); cash-=cost_px*pos+comm*pos; cost+=comm*pos
            entry_px=px; entry_idx=i
        elif sig[i]==-1 and pos>0:
            px_px=px*(1-0.0005)
            tc=px_px*(commission/100+spread_bps/10000+stamp/100)
            net=px_px*pos-tc; ret=(px-entry_px)/entry_px*100
            trades.append({"ret":round(ret,2),"pnl":round(cash+net-initial,0)})
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
    return dict(name=name, ann=round(ann,2), adj_ann=round(adj,2),
                sh=round(sh,3), adj_sh=round(adj_sh,3),
                mdd=round(mdd,1), n=len(trades), wr=round(wr*100,1),
                cost=round(cost,0), equity=equity, final=round(final,0))

# ═══════════════════════════════════════════════════════
# 专家策略候选
# ═══════════════════════════════════════════════════════

CANDIDATES = [
    ("MA(5,20)",    "trend",       {"fp":5,"sp":20}),
    ("MA(10,60)",   "trend",       {"fp":10,"sp":60}),
    ("MA(20,120)",  "trend",       {"fp":20,"sp":120}),
    ("RSI(14,30,70)","mean_reversion",{"period":14,"lo":30,"hi":70}),
    ("RSI(6,20,80)", "mean_reversion",{"period":6,"lo":20,"hi":80}),
    ("MACD",        "trend",       {}),
    ("布林带(20,2σ)","mean_reversion",{"period":20,"std":2.0}),
]

STRATEGY_SIGNALS = {
    "MA(5,20)":      lambda cps,p: sig_ma_cross(cps,p["fp"],p["sp"]),
    "MA(10,60)":     lambda cps,p: sig_ma_cross(cps,p["fp"],p["sp"]),
    "MA(20,120)":    lambda cps,p: sig_ma_cross(cps,p["fp"],p["sp"]),
    "RSI(14,30,70)": lambda cps,p: sig_rsi(cps,p["period"],p["lo"],p["hi"]),
    "RSI(6,20,80)":  lambda cps,p: sig_rsi(cps,p["period"],p["lo"],p["hi"]),
    "MACD":          lambda cps,p: _sig_macd(cps),
    "布林带(20,2σ)": lambda cps,p: sig_bollinger(cps,p["period"],p["std"]),
}

def _sig_macd(cps):
    n=len(cps); md,sig=macd(cps); s=[0]*n
    for i in range(26,n):
        if md[i]>sig[i] and md[i-1]<=sig[i-1]: s[i]=1
        elif md[i]<sig[i] and md[i-1]>=sig[i-1]: s[i]=-1
    return s

# ═══════════════════════════════════════════════════════
# Expert2 评估
# ═══════════════════════════════════════════════════════

@dataclass
class EvalResult:
    strategy_id: str
    strategy_name: str
    strategy_type: str
    params: dict
    ann_ret: float; sh: float; mdd: float; n_trades: int
    win_rate: float; cost: float; adj_sh: float; adj_ann: float
    composite: float = 0.0
    decision: str = "REJECT"
    feedback: str = ""

def evaluate(name, sname, stype, params, cps, commission=0.04, stamp=0.0):
    sig_fn = STRATEGY_SIGNALS.get(sname)
    if not sig_fn: return None
    r = backtest(name, cps, params, sig_fn, commission=commission, stamp=stamp)
    if not r: return None

    # 评分（无前瞻）
    sharpe_sc   = min(r["adj_sh"] / 2.0 * 35, 35) if r["adj_sh"] > 0 else max(r["adj_sh"]/2.0*35, -35)
    dd_sc      = max(0, (35 - r["mdd"])/35*25) if r["mdd"] < 35 else 0
    wr_sc      = r["wr"]/100 * 15
    trades_sc  = min(r["n"]/10*15, 15) if r["n"] >= 3 else r["n"]/3*15
    composite  = sharpe_sc + dd_sc + wr_sc + trades_sc

    # 决策
    decision = "ACCEPT"
    feedback = ""
    if r["adj_ann"] < 10.0:
        decision = "REJECT"; feedback = f"年化{round(r['adj_ann'],1)}%<10%阈值"
    elif r["adj_sh"] < 0.3:
        decision = "REJECT"; feedback = f"夏普{round(r['adj_sh'],2)}<0.3阈值"
    elif r["n_trades"] < 2:
        decision = "REJECT"; feedback = f"交易次数{r['n_trades']}<2"
    elif r["mdd"] > 35.0:
        decision = "REJECT"; feedback = f"回撤{r['mdd']:.1f}%>35%"

    e = EvalResult(
        strategy_id=name, strategy_name=sname, strategy_type=stype,
        params=params,
        ann_ret=r["ann"], sh=r["sh"], mdd=r["mdd"],
        n_trades=r["n"], win_rate=r["wr"], cost=r["cost"],
        adj_sh=r["adj_sh"], adj_ann=r["adj_ann"],
        composite=round(composite,1),
        decision=decision, feedback=feedback,
    )
    return e

# ═══════════════════════════════════════════════════════
# 辩论
# ═══════════════════════════════════════════════════════

@dataclass
class DebateResult:
    winner: str
    trend_weight: float
    mr_weight: float
    verdict_reason: str

def adversarial_debate(evals, regime, sentiment):
    trend_evals = sorted([e for e in evals if e.strategy_type=="trend"],
                         key=lambda x: x.composite, reverse=True)
    mr_evals    = sorted([e for e in evals if e.strategy_type!="trend"],
                         key=lambda x: x.composite, reverse=True)
    best_t = trend_evals[0] if trend_evals else None
    best_m = mr_evals[0] if mr_evals else None

    recs = regime.get("rec", [])
    t_rec = any("趋势" in r or "均线" in r or "动量" in r for r in recs)
    mr_rec = any("RSI" in r or "布林" in r for r in recs)

    if t_rec and not mr_rec:
        winner="TrendExpert"; tw=0.70; mw=0.30
    elif mr_rec and not t_rec:
        winner="MeanReversionExpert"; tw=0.30; mw=0.70
    elif best_t and best_m:
        if best_t.composite > best_m.composite + 10:
            winner="TrendExpert"; tw=0.65; mw=0.35
        elif best_m.composite > best_t.composite + 10:
            winner="MeanReversionExpert"; tw=0.35; mw=0.65
        else:
            winner="TIE"; tw=0.50; mw=0.50
    elif best_t:
        winner="TrendExpert"; tw=0.80; mw=0.20
    elif best_m:
        winner="MeanReversionExpert"; tw=0.20; mw=0.80
    else:
        winner="TIE"; tw=0.50; mw=0.50

    reason = f"{winner}推荐{winners_weight}" if winner!="TIE" else "双方均衡"
    return DebateResult(winner=winner, trend_weight=tw, mr_weight=mw,
                        verdict_reason=reason)

def _winners_weight(w):
    return "7:3" if abs(w-0.7)<0.01 else ("5:5" if abs(w-0.5)<0.01 else "3:7")

# ═══════════════════════════════════════════════════════
# 组合构建
# ═══════════════════════════════════════════════════════

def build_portfolio(debate, pass_evals, regime, max_pos=0.40):
    risk_map = {}
    tw=debate.trend_weight; mw=debate.mr_weight
    trend_evals=[e for e in pass_evals if e.strategy_type=="trend"]
    mr_evals=[e for e in pass_evals if e.strategy_type!="trend"]
    t_items=[(e,e.strategy_id) for e in trend_evals]
    mr_items=[(e,e.strategy_id) for e in mr_evals]

    # All weights dict
    all_w = {}
    for e, sid in t_items: all_w[sid] = e.composite * tw
    for e, sid in mr_items: all_w[sid] = e.composite * mw
    total = sum(all_w.values())
    if total <= 0:
        for e, sid in t_items: all_w[sid] = 1.0
        for e, sid in mr_items: all_w[sid] = 1.0
        total = sum(all_w.values())

    normed = {sid: w/total for sid,w in all_w.items()}
    cap = max_pos / (len(normed) if normed else 1)
    final_weights = {}
    for sid, w in normed.items():
        final_weights[sid] = min(w, cap)

    # Normalize again
    tw2 = sum(v for k,v in final_weights.items() if any(e.strategy_id==k and e.strategy_type=="trend" for e in pass_evals))
    mw2 = sum(v for k,v in final_weights.items() if any(e.strategy_id==k and e.strategy_type!="trend" for e in pass_evals))
    if tw2+mw2 > 0:
        for sid in final_weights:
            if any(e.strategy_id==sid and e.strategy_type=="trend" for e in pass_evals):
                final_weights[sid] *= (tw+mw) * max_pos / (tw2+mw2) if tw2+mw2 > 0 else final_weights[sid]
            else:
                final_weights[sid] *= (tw+mw) * max_pos / (tw2+mw2) if tw2+mw2 > 0 else final_weights[sid]

    # Assign weights to EvalResults
    weight_dict = {}
    for e in pass_evals:
        w = float(final_weights.get(e.strategy_id, 0.0))
        e.weight = w  # type: ignore — dataclass field added dynamically
        weight_dict[e.strategy_id] = w

    return weight_dict

# ═══════════════════════════════════════════════════════
# Walk-Forward 验证
# ═══════════════════════════════════════════════════════

def walk_forward(cps, sig_fn, params, n_train=180, n_test=60):
    n=len(cps); results=[]; cursor=n
    while True:
        te=cursor; ts=max(n_train+n_test, cursor-n_test)
        tr=max(0,ts-n_train)
        if ts-tr<n_train or te-ts<30: break
        tc=cps[tr:ts]; ec=cps[ts:te]
        if len(ec)<30: break
        rt=backtest("t","train",tc,params,sig_fn)
        re=backtest("e","test",ec,params,sig_fn)
        if rt and re:
            dec=re["adj_sh"]/abs(rt["adj_sh"]) if rt["adj_sh"]!=0 else 0
            results.append({"tr_sh":rt["adj_sh"],"te_sh":re["adj_sh"],
                          "decay":round(dec,2),"verdict":"PASS" if dec>=0.5 and re["adj_sh"]>0.3 else "FAIL"})
        cursor=ts
        if cursor<n_train+n_test*2: break
    if not results: return {}
    avg_d=sum(r["decay"] for r in results)/len(results)
    passes=sum(1 for r in results if r["verdict"]=="PASS")
    return {"n":len(results),"avg_decay":round(avg_d,2),
            "overall":"PASS" if passes>=len(results)*0.6 else "WEAK" if passes>=1 else "FAIL",
            "windows":results}

# ═══════════════════════════════════════════════════════
# 多专家迭代系统
# ═══════════════════════════════════════════════════════

@dataclass
class RoundReport:
    round_num: int
    regime_label: str; regime_score: float
    sentiment_label: str; sentiment_score: float
    accepted: list
    final_selected: list
    debate_winner: str
    top_score: float; avg_score: float
    convergence: bool = False

class OrchestratorV2:
    def __init__(self, symbols, days=300, seed=2026, rounds=5, top_n=5):
        self.symbols = symbols
        self.n_days = days
        self.seed = seed
        self.rounds = rounds
        self.top_n = top_n
        self.prev_ids = None
        self.round_reports = []

    def run(self):
        print("\n"+"="*68)
        print("  🌡️  多专家量化系统 v3.0 — Regime感知迭代版")
        print("  Pipeline(A) + Adversarial(B) + Stooq真实数据")
        print("="*68)

        # 加载数据
        symbols_data = self._load_data()
        self._print_data_summary(symbols_data)

        for rnd in range(1, self.rounds + 1):
            print(f"\n{'='*68}\n  ▶ 第 {rnd} 轮\n{'='*68}")
            rp = self._run_round(rnd, symbols_data)
            if rp is None:
                print(f"  ❌ 第{rnd}轮失败（数据不足）"); continue
            self.round_reports.append(rp)

            top_ids = {e.strategy_id for e in rp.final_selected}
            converged = (top_ids == self.prev_ids) if self.prev_ids else False
            self.prev_ids = top_ids

            # 元监控
            print(f"\n  📊 本轮结果：")
            for e in rp.final_selected:
                w = float(getattr(e, "weight", 0.0))
                print(f"    {e.strategy_name}({e.strategy_type}) "
                      f"分={e.composite:.1f} 夏普={e.adj_sh:.2f} 年化={e.adj_ann:+.1f}% 权重={w:.1%}")

            regime = rp.regime_label
            sentiment = rp.sentiment_label
            print(f"\n  🌡️ 市场状态：{regime} | 📰 情绪：{sentiment}")
            print(f"  🏆 辩论胜出：{rp.debate_winner}")

            if rnd >= 2 and converged:
                print(f"\n  ✅ 第{rnd}轮名单与第{rnd-1}轮相同，已收敛（连续一致）")
                break

        self._print_final_summary()
        return self.round_reports

    def _load_data(self):
        results = {}
        for sym in self.symbols:
            rows = fetch_stooq(sym, self.n_days)
            if rows:
                cps = [r["close"] for r in rows]
                dts = [r["date"]  for r in rows]
                source = "Stooq"
            else:
                syn = gen_synthetic(sym, self.n_days, self.seed)
                cps = syn["closes"]; dts = syn["dates"]; source = "Synthetic"
            ind = compute_indicators(cps)
            results[sym] = {"closes": cps, "dates": dts,
                           "indicators": ind, "source": source}
        return results

    def _print_data_summary(self, data):
        print(f"\n📥 数据加载：")
        for sym, d in data.items():
            cps = d["closes"]
            ret = (cps[-1]/cps[0]-1)*100
            vol = math.sqrt(sum((cps[i]-cps[i-1])**2 for i in range(1,len(cps)))/len(cps)*math.sqrt(252)*100
            print(f"  {sym:<10} {d['source']:<8} {len(cps)}天 涨跌{ret:>+6.1f}% 波动{vol:>5.1f}%")

    def _run_round(self, rnd, symbols_data):
        # 使用主标的（第一个）
        sym = self.symbols[0]
        d = symbols_data[sym]
        cps = d["closes"]
        ind = d["indicators"]
        n = len(cps)

        # Step1: 情绪（用Stooq数据本身作为价格序列代理）
        sent = self._analyze_sentiment(cps)

        # Step2: Regime检测
        regime = detect_regime(cps, n-1)
        print(f"\n[Step2] 🌡️ Regime={regime['label']} 评分={regime['score']:+.0f} "
              f"推荐={regime['rec']} 仓位≤{regime['pos_cap']:.0%}")

        # Step3: 专家评估
        evals = []
        for name, stype, params in CANDIDATES:
            e = evaluate(name, name, stype, params, cps)
            if e:
                # Walk-Forward 验证
                sig_fn = STRATEGY_SIGNALS.get(name)
                if sig_fn and n >= 250:
                    wf = walk_forward(cps, sig_fn, params)
                    if wf.get("overall") == "FAIL":
                        e.decision = "REJECT"
                        e.feedback = f"Walk-Forward FAIL(退={wf['avg_decay']:.0%})"
                        e.composite *= 0.7  # 降权
                evals.append(e)

        evals.sort(key=lambda x: x.composite, reverse=True)
        accepted = [e for e in evals if e.decision == "ACCEPT"]
        rejected = [e for e in evals if e.decision == "REJECT"]

        print(f"\n[Step3] 候选策略：{len(evals)} | 纳入：{len(accepted)} | 淘汰：{len(rejected)}")
        for e in evals[:5]:
            icon = "✅" if e.decision=="ACCEPT" else "❌"
            print(f"  {icon} {e.strategy_name:<18} 分={e.composite:>5.1f} "
                  f"夏普={e.adj_sh:>6.2f} 年化={e.adj_ann:>+7.1f}% {e.feedback}")

        # Step4: 辩论
        debate = adversarial_debate(accepted, regime, sent)

        # Step5: 组合
        max_pos = regime.get("pos_cap", 0.40)
        weights = build_portfolio(debate, accepted, regime, max_pos)
        final = sorted(accepted, key=lambda x: x.composite, reverse=True)[:self.top_n]
        # Assign weights properly
        for e in final:
            w = float(weights.get(e.strategy_id, 0.0))
            e.weight = w  # type: ignore

        top_score = max([e.composite for e in evals]+[0.0])
        avg_score = sum([e.composite for e in evals])/max(len(evals),1)

        print(f"\n[Step4] 辩论胜出：{debate.winner}（趋势={debate.trend_weight:.0%} | 均值={debate.mr_weight:.0%}）")
        print(f"[Step5] 组合构建：{len(final)}个策略，最大仓位{max_pos:.0%}")

        rp = RoundReport(
            round_num=rnd,
            regime_label=regime.get("label","UNKNOWN"),
            regime_score=regime.get("score",0.0),
            sentiment_label=sent.get("sentiment_label","NEUTRAL"),
            sentiment_score=sent.get("sentiment_score",0.0),
            accepted=accepted,
            final_selected=final,
            debate_winner=debate.winner,
            top_score=top_score,
            avg_score=avg_score,
        )
        return rp

    def _analyze_sentiment(self, cps):
        """用价格动量作为情绪代理（无前瞻）"""
        if len(cps) < 20:
            return {"sentiment_label":"NEUTRAL","sentiment_score":0.0,"confidence":0.0}
        ret20 = (cps[-1]/cps[-20]-1) if len(cps)>=20 else 0.0
        if ret20 > 0.05