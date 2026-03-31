"""
expert1a_trend.py — 趋势专家 Expert1A v4（信号去抖版）
修复内容：
  - _debounce_signals: 信号连续2天确认 + 平仓后3天冷却期
  - _simulate: 正确 equity=cash+pos*close，daily_rets与trades互斥
  - _ema: 静态方法正确调用
"""
import math, random, uuid
from dataclasses import dataclass
from typing import List

@dataclass
class BacktestReport:
    strategy_id: str; strategy_name: str
    strategy_type: str = "trend"
    tags: List[str] = None; params: dict = None
    total_return: float = 0.0; sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0; annualized_return: float = 0.0
    volatility: float = 0.0; total_trades: int = 0
    win_rate: float = 0.0; profit_factor: float = 0.0
    avg_holding_days: float = 0.0; calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0; daily_returns: list = None
    def __post_init__(self):
        if self.tags is None: self.tags = []
        if self.params is None: self.params = {}
        if self.daily_returns is None: self.daily_returns = []


class TrendExpert:
    TEMPLATES = [
        {"key": "ma_cross",          "name": "双均线交叉",    "params": {"fast": 20,  "slow": 60}},
        {"key": "macd",              "name": "MACD趋势",       "params": {"fp": 12,   "sp": 26, "sig": 9}},
        {"key": "momentum",          "name": "动量突破",       "params": {"lookback": 20, "threshold": 0.05}},
        {"key": "adx_trend",         "name": "ADX趋势确认",    "params": {"adx_thr": 25,  "atr_mult": 2.0}},
        {"key": "ichimoku_signal",   "name": "Ichimoku云图",   "params": {"tenkan": 9, "kijun": 26}},
        {"key": "kst",               "name": "KST动量",        "params": {"r1": 10, "r2": 13}},
        {"key": "trix",              "name": "TRIX三重指数",   "params": {"period": 14}},
        {"key": "donchian_breakout", "name": "Donchian突破",   "params": {"period": 20}},
        {"key": "aroon_signal",      "name": "Aroon交叉",      "params": {"period": 25}},
    ]

    def __init__(self, seed: int = 42):
        self.name = "TrendExpert"
        self._rng = random.Random(seed)

    def generate_candidates(self, count: int = 4, feedback: list = None) -> List[dict]:
        candidates = []
        templates = self.TEMPLATES * 2
        for i in range(count):
            fb  = (feedback[i] if (feedback and i < len(feedback)) else None) or {}
            tpl = templates[i % len(templates)]
            params = self._tune_from_feedback(tpl, fb)
            candidates.append({
                "strategy_id":   f"trend_{uuid.uuid4().hex[:8]}",
                "strategy_type": "trend",
                "strategy_name": tpl["name"],
                "template_key":  tpl["key"],
                "params":        params,
                "tags":          ["趋势跟踪", tpl["name"]],
                "feedback_note": self._fb_summary(fb),
            })
        return candidates

    def _tune_from_feedback(self, tpl: dict, fb: dict) -> dict:
        params = dict(tpl["params"])
        adj    = (fb.get("adjustment") or "").lower()
        pname  = fb.get("param", ""); mag = fb.get("magnitude", 0)
        unit   = fb.get("unit", "")
        if not adj or adj in ("none", "diversify"): return params
        if "increase_lookback" in adj:
            for k in ("lookback","fast","slow","period"):
                if k in params and pname in ("", k):
                    params[k] = max(5, params.get(k, 10) + (int(mag) if unit=="天" else 5))
        elif "decrease_lookback" in adj:
            for k in ("lookback","fast","period"):
                if k in params and pname in ("", k):
                    params[k] = max(3, params.get(k, 10) - 5)
        elif "tighten_stop_loss" in adj:
            for k in ("atr_mult","threshold"):
                if k in params and pname in ("", k):
                    params[k] = max(0.5, params.get(k, 2.0) * (mag if unit=="倍" else 0.7))
        elif "add_filter" in adj or "remove_filter" in adj:
            if "threshold" in params:
                delta = mag/100 if unit=="%" else -0.2
                params["threshold"] = round(params["threshold"] * (1+delta), 4)
        return params

    @staticmethod
    def _fb_summary(fb: dict) -> str:
        if not fb: return "首轮生成，无反馈"
        adj = fb.get("adjustment", "none")
        if adj in ("none", ""): return "无结构化指令"
        return (f"指令={adj}，参数={fb.get('param','?')}，"
                f"幅度={fb.get('magnitude',0):+.1f}{fb.get('unit','')}")

    def backtest(self, data: dict, ind: dict, params: dict, template_key: str,
                 initial_cash: float = 1_000_000.0, strategy_id: str = None) -> BacktestReport:
        closes = data["closes"]
        n = len(closes)
        if n < 60: return BacktestReport(strategy_id="", strategy_name="", params=params)
        signals = self._signal_series(closes, ind, params, template_key, data)
        equity, trades, daily_rets = self._simulate(signals, closes, initial_cash)
        sid = strategy_id or f"trend_{uuid.uuid4().hex[:6]}"
        return TrendExpert._build_report(sid, params, template_key, equity, trades, daily_rets, n, initial_cash)

    @staticmethod
    def _debounce_signals(signals, min_consecutive=2, cooldown_days=3):
        """
        信号去抖：解决日频翻牌问题
        - min_consecutive: 信号需连续出现 N 天才确认
        - cooldown_days: 平仓后等待 N 天才能重新开仓
        """
        n = len(signals)
        # Step 1: 连续 N 天确认
        confirmed = [0] * n
        streak = 0; pending = 0
        for i in range(n):
            if signals[i] == pending:
                streak += 1
            else:
                streak = 1; pending = signals[i]
            if streak >= min_consecutive and pending != 0:
                confirmed[i] = pending; streak = 0
        # Step 2: 冷却期
        cooldown = 0; result = [0] * n; pos_open = False
        for i in range(n):
            if cooldown > 0:
                cooldown -= 1
                if confirmed[i] == -1 and pos_open:
                    pos_open = False  # 冷却期内仍允许平仓
                result[i] = 0
            elif confirmed[i] == 1 and not pos_open:
                result[i] = 1; pos_open = True
            elif confirmed[i] == -1 and pos_open:
                result[i] = -1; pos_open = False; cooldown = cooldown_days
            else:
                result[i] = 0
        return result

    def _signal_series(self, closes, ind, params, key, data=None):
        n = len(closes)
        adx_v = ind.get("adx", [0]*n)
        if key == "ma_cross":
            ma20=ind["ma20"]; ma60=ind["ma60"]
            # Level-based: hold 1 while MA20>MA60, -1 while MA20<MA60
            # Debounce then filters brief whipsaws (needs 2 consecutive days)
            raw = [0 if i<60 or ma20[i] is None or ma60[i] is None else
                    1 if ma20[i]>ma60[i] else -1
                    for i in range(n)]
            return self._debounce_signals(raw, min_consecutive=2, cooldown_days=2)
        elif key == "macd":
            fp_i=int(params.get("fp",12)); sp_i=int(params.get("sp",26)); sig_i=int(params.get("sig",9))
            macd_line=[TrendExpert._ema(closes,fp_i)[j]-TrendExpert._ema(closes,sp_i)[j] for j in range(n)]
            sig_line=TrendExpert._ema(macd_line,sig_i)
            # Level-based: hold 1 while MACD>signal, -1 while MACD<signal
            raw = [0 if i<sp_i+sig_i else
                    1 if macd_line[i]>sig_line[i] else -1
                    for i in range(n)]
            return self._debounce_signals(raw, min_consecutive=2, cooldown_days=2)
        elif key == "momentum":
            lb_i=int(params.get("lookback",20)); thr=float(params.get("threshold",0.05))
            raw = [0 if i<lb_i else
                    1 if (closes[i]-closes[i-lb_i])/closes[i-lb_i]>thr else
                   -1 if (closes[i]-closes[i-lb_i])/closes[i-lb_i]<-thr else 0
                    for i in range(n)]
            return self._debounce_signals(raw, min_consecutive=2, cooldown_days=2)
        elif key == "adx_trend":
            adx_thr=float(params.get("adx_thr",25))
            raw = [0 if i<20 else
                    1 if adx_v[i]>adx_thr and closes[i]>closes[i-1] else
                   -1 if adx_v[i]>adx_thr and closes[i]<closes[i-1] else 0
                    for i in range(n)]
            # ADX=100 导致翻牌：冷却期3天，连续2天确认
            return self._debounce_signals(raw, min_consecutive=2, cooldown_days=3)
        elif key in ("ichimoku_signal", "kst", "trix", "donchian_breakout", "aroon_signal"):
            highs_d = data.get("highs", closes) if data else closes
            lows_d  = data.get("lows",  closes) if data else closes
            try:
                from factors.trend import (
                    ichimoku_signal as _ichi, kst_signal as _kst,
                    trix_signal as _trix, donchian_breakout as _don,
                    aroon_signal as _aroon
                )
                if key == "ichimoku_signal":
                    raw = _ichi(closes, highs_d, lows_d,
                                tenkan=int(params.get("tenkan", 9)),
                                kijun=int(params.get("kijun", 26)))
                elif key == "kst":
                    from factors.trend import kst as _kst_fn
                    import math as _math
                    kst_line, kst_sig = _kst_fn(closes,
                                                roc1=int(params.get("r1", 10)),
                                                roc2=int(params.get("r2", 15)))
                    raw = [1 if kst_line[i] > kst_sig[i] and not _math.isnan(kst_line[i])
                           else -1 if kst_line[i] < kst_sig[i] and not _math.isnan(kst_line[i])
                           else 0 for i in range(len(closes))]
                elif key == "trix":
                    from factors.trend import trix as _trix_fn
                    import math as _math
                    trix_vals, trix_sig = _trix_fn(closes, period=int(params.get("period", 15)))
                    raw = [1 if not _math.isnan(trix_vals[i]) and trix_vals[i] > trix_sig[i]
                           else -1 if not _math.isnan(trix_vals[i]) and trix_vals[i] < trix_sig[i]
                           else 0 for i in range(len(closes))]
                elif key == "donchian_breakout":
                    raw = _don(closes, highs_d, lows_d, period=int(params.get("period", 20)))
                elif key == "aroon_signal":
                    raw = _aroon(closes, highs_d, lows_d, period=int(params.get("period", 25)))
                else:
                    raw = [0] * n
                raw = list(raw)
                if len(raw) < n: raw += [0] * (n - len(raw))
                return self._debounce_signals(raw[:n], min_consecutive=2, cooldown_days=2)
            except Exception:
                return [0] * n
        return [0]*n

    @staticmethod
    def _ema(data, period):
        k=2/(period+1); out=[data[0]]*len(data)
        for i in range(1,len(data)): out[i]=data[i]*k+out[i-1]*(1-k)
        return out

    # ── 交易成本参数（A股/美股混合场景）───────────────────────────────
    # 佣金：0.03% 双向 | 印花税：0.10% 仅卖出(A股) | 滑点：0.05% 双向
    BUY_COST  = 0.0003 + 0.0005   # 佣金+滑点 = 0.08%
    SELL_COST = 0.0003 + 0.0005 + 0.0010  # 佣金+滑点+印花税 = 0.18%

    @staticmethod
    def _simulate(signals, closes, initial_cash):
        """
        正确金融模拟（含交易成本）：
        - 买入：扣除 0.08%（佣金+滑点）
        - 卖出：扣除 0.18%（佣金+滑点+印花税）
        equity = cash + pos*close（每日净值）
        daily_rets = 每日净值变化百分比（与trades互斥）
        """
        cash=initial_cash; pos=0.0; entry_price=0.0
        equity=[initial_cash]; trades=[]; daily_rets=[]
        for i in range(1,len(closes)):
            prev_eq=equity[-1]; sig=signals[i]
            if sig==1 and pos==0:
                target_pos=prev_eq*0.95
                # 实际买入：扣除佣金+滑点（0.08%）
                actual_pos=target_pos*(1-TrendExpert.BUY_COST)/closes[i]
                cost=target_pos*TrendExpert.BUY_COST
                pos=actual_pos; cash=prev_eq-cost-actual_pos*closes[i]
                entry_price=closes[i]
            elif sig==-1 and pos>0:
                # 实际卖出：扣除佣金+滑点+印花税（0.18%）
                gross=pos*closes[i]; cost=gross*TrendExpert.SELL_COST
                net=gross-cost; trade_ret=(net/initial_cash-1) if initial_cash>0 else 0.0
                trades.append(trade_ret); cash+=net; pos=0.0
            eq_today=cash+pos*closes[i]; equity.append(eq_today)
            daily_rets.append((eq_today-prev_eq)/prev_eq if prev_eq>0 else 0.0)
        return equity, trades, daily_rets

    @staticmethod
    def _build_report(strategy_id, params, key, equity, trades, daily_rets, n, cash):
        final=equity[-1]; tr=(final/cash-1)
        ann=((final/cash)**(252/max(n-1,1))-1)
        vol=TrendExpert._std(daily_rets)*math.sqrt(252) if daily_rets else 0.0
        s=ann/vol if vol>0 else 0.0
        sortino_v=TrendExpert._sortino(daily_rets); max_dd_v=TrendExpert._max_dd(daily_rets)
        calmar=ann/(max_dd_v/100) if max_dd_v>0 else 0.0
        wins=[t for t in trades if t>0]; loss=[t for t in trades if t<0]
        wr=len(wins)/len(trades) if trades else 0.0
        avg_win=sum(wins)/len(wins) if wins else 0.0
        avg_loss=abs(sum(loss)/len(loss)) if loss else 1.0
        pf=avg_win/avg_loss if avg_loss>1e-9 else 0.0
        name={
            "ma_cross":"双均线交叉","macd":"MACD趋势","momentum":"动量突破","adx_trend":"ADX趋势确认",
            "ichimoku_signal":"Ichimoku云图","kst":"KST动量","trix":"TRIX三重指数",
            "donchian_breakout":"Donchian突破","aroon_signal":"Aroon交叉",
        }.get(key,key)
        return BacktestReport(
            strategy_id=strategy_id, strategy_name=name, strategy_type="trend",
            tags=["趋势跟踪",name], params=params,
            total_return=round(tr*100,2), sharpe_ratio=round(s,3),
            max_drawdown_pct=round(max_dd_v,2), annualized_return=round(ann*100,2),
            volatility=round(vol*100,2), total_trades=len(trades),
            win_rate=round(wr*100,2), profit_factor=round(pf,2),
            avg_holding_days=round(len(trades)/max(n/252,1),1),
            calmar_ratio=round(calmar,3), sortino_ratio=round(sortino_v,3),
            daily_returns=[round(r,4) for r in daily_rets])

    @staticmethod
    def _std(vals):
        n=len(vals); m=sum(vals)/n if n>1 else 0.0
        return math.sqrt(sum((v-m)**2 for v in vals)/(n-1)) if n>1 else 0.0
    @staticmethod
    def _sortino(rets,target=0.0):
        d=[r for r in rets if r<target]
        if not d: return 0.0
        return (sum(rets)/len(rets)*252)/(TrendExpert._std(d)*math.sqrt(252)+1e-9)
    @staticmethod
    def _max_dd(rets):
        eq=1.0;peak=1.0;max_dd=0.0
        for r in rets:
            eq*=(1+r)
            if eq>peak: peak=eq
            dd=(eq-peak)/peak
            if dd<max_dd: max_dd=dd
        return abs(max_dd)*100


# 别名供 _signal_series 中 EMA._ema 调用
EMA = TrendExpert
