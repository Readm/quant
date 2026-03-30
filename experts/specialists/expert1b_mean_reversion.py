"""
expert1b_mean_reversion.py — 均值回归专家 v4（含交易成本）
"""
import math, random, uuid
from dataclasses import dataclass
from typing import List

@dataclass
class BacktestReport:
    strategy_id: str; strategy_name: str
    strategy_type: str = "mean_reversion"
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


class MeanReversionExpert:
    TEMPLATES = [
        {"key": "rsi",              "name": "RSI均值回归",    "params": {"period": 14, "lower": 30, "upper": 70}},
        {"key": "bollinger",        "name": "布林带回归",      "params": {"period": 20, "std_mult": 2.0}},
        {"key": "vol_surge",        "name": "成交量异常",      "params": {"vol_ma": 20, "threshold": 2.0}},
        {"key": "mfi_signal",       "name": "MFI资金流",       "params": {"period": 14, "lower": 20, "upper": 80}},
        {"key": "rvi_signal",       "name": "RVI相对活力",     "params": {"period": 10}},
        {"key": "kdwave",           "name": "KDJ波形",         "params": {"fastk": 9, "slowk": 3}},
        {"key": "multi_roc_signal", "name": "ROC多周期",       "params": {"p1": 10, "p2": 20, "p3": 40}},
        {"key": "obos_composite",   "name": "OBOS超买超卖",    "params": {"period": 20}},
        {"key": "elder_ray_signal", "name": "Elder Ray信号",   "params": {"ema_period": 13}},
    ]

    def __init__(self, seed: int = 42):
        self.name = "MeanReversionExpert"
        self._rng = random.Random(seed)

    def generate_candidates(self, count: int = 4, feedback: list = None) -> List[dict]:
        candidates = []
        templates = self.TEMPLATES * 2
        for i in range(count):
            fb  = (feedback[i] if (feedback and i < len(feedback)) else None) or {}
            tpl = templates[i % len(templates)]
            params = self._tune_from_feedback(tpl, fb)
            candidates.append({
                "strategy_id":   f"mr_{uuid.uuid4().hex[:8]}",
                "strategy_type": "mean_reversion",
                "strategy_name": tpl["name"],
                "template_key":  tpl["key"],
                "params":        params,
                "tags":          ["均值回归", tpl["name"]],
                "feedback_note": self._fb_summary(fb),
            })
        return candidates

    def _tune_from_feedback(self, tpl, fb):
        params = dict(tpl["params"])
        adj = (fb.get("adjustment") or "").lower()
        pname = fb.get("param", ""); mag = fb.get("magnitude", 0)
        unit = fb.get("unit", "")
        if not adj or adj in ("none", "diversify"): return params
        if "widen" in adj:
            for k in ("lower", "upper", "period"):
                if k in params and pname in ("", k):
                    params[k] = params.get(k, 14) + (int(mag) if unit=="天" else 5)
        elif "narrow" in adj:
            for k in ("lower", "upper", "period"):
                if k in params and pname in ("", k):
                    v = params.get(k, 14) - (int(mag) if unit=="天" else 5)
                    params[k] = max(3, v)
        elif "tighten_filter" in adj:
            for k in ("std_mult", "threshold"):
                if k in params and pname in ("", k):
                    params[k] = max(0.5, params.get(k, 2.0) * (mag/100.0 if unit=="%" else 0.8))
        return params

    @staticmethod
    def _fb_summary(fb):
        if not fb: return "首轮生成，无反馈"
        adj = fb.get("adjustment", "none")
        if adj in ("none", ""): return "无结构化指令"
        return f"指令={adj}，参数={fb.get('param','?')}，幅度={fb.get('magnitude',0):+.1f}{fb.get('unit','')}"

    def backtest(self, data, ind, params, template_key, initial_cash=1_000_000.0, strategy_id=None):
        """接口与 TrendExpert 保持一致：backtest(data, ind_dict, params, template_key)"""
        closes = [float(c) for c in data["closes"]]
        n = len(closes)
        if n < 60:
            return BacktestReport(strategy_id="", strategy_name="", params=params)
        signals = self._signal_series(closes, data, params, template_key)
        equity, trades, daily_rets = self._simulate(signals, closes, initial_cash)
        sid = strategy_id or f"mr_{uuid.uuid4().hex[:6]}"
        return self._build_report(sid, params, template_key, equity, trades, daily_rets, n, initial_cash)

    def _signal_series(self, closes, data, params, key):
        n = len(closes)
        if key == "rsi":
            period = int(params.get("period", 14))
            lower  = float(params.get("lower", 30))
            upper  = float(params.get("upper", 70))
            gains, losses = [], []
            for i in range(1, n):
                d = closes[i] - closes[i-1]
                gains.append(max(d, 0)); losses.append(max(-d, 0))
            if len(gains) < period: return [0]*n
            avg_gain = sum(gains[:period]) / period
            avg_loss = sum(losses[:period]) / period
            rsi_vals = [50.0]
            for j in range(period, len(gains)):
                avg_gain = (avg_gain * (period-1) + gains[j]) / period
                avg_loss = (avg_loss * (period-1) + losses[j]) / period
                rs = avg_gain / (avg_loss + 1e-10)
                rsi_vals.append(100 - 100/(1+rs))
            raw = [0]*period
            for j in range(len(rsi_vals)):
                i = j + period
                if rsi_vals[j] < lower:  raw.append(1)
                elif rsi_vals[j] > upper: raw.append(-1)
                else: raw.append(0)
            return raw + [0]*(n - len(raw)) if len(raw) < n else raw[:n]
        elif key == "bollinger":
            period   = int(params.get("period", 20))
            std_mult = float(params.get("std_mult", 2.0))
            raw = [0]*n
            for i in range(period, n):
                mean = sum(closes[i-period:i]) / period
                std  = math.sqrt(sum((closes[j]-mean)**2 for j in range(i-period,i)) / period)
                if   closes[i] < mean - std_mult*std: raw[i] = 1
                elif closes[i] > mean + std_mult*std: raw[i] = -1
            return raw
        elif key == "vol_surge":
            vol_ma = int(params.get("vol_ma", 20))
            thr    = float(params.get("threshold", 2.0))
            vols   = data.get("volumes", [1e9]*n)
            raw = [0]*n
            for i in range(vol_ma, n):
                avg_v = sum(vols[i-vol_ma:i]) / vol_ma
                if vols[i] > avg_v * thr: raw[i] = -1
            return raw
        elif key == "alpha158":
            alpha_name = params.get("alpha_name", "roc_20")
            highs  = data.get("highs",  closes) if isinstance(data, dict) else closes
            lows   = data.get("lows",   closes) if isinstance(data, dict) else closes
            vols   = data.get("volumes", [1e9]*n) if isinstance(data, dict) else [1e9]*n
            try:
                from experts.modules.alpha158 import alpha158_features, alpha158_signal
                sig_raw = alpha158_signal(closes, highs, lows, vols, alpha_name)
                return sig_raw  # mean_reversion already has its own debounce
            except Exception:
                return [0]*n
        elif key in ("mfi_signal", "rvi_signal", "kdwave", "multi_roc_signal", "obos_composite", "elder_ray_signal"):
            highs_d = data.get("highs",   closes) if isinstance(data, dict) else closes
            lows_d  = data.get("lows",    closes) if isinstance(data, dict) else closes
            vols_d  = data.get("volumes", [1e9]*n) if isinstance(data, dict) else [1e9]*n
            try:
                from factors.signals import generate_signal
                sig_raw = list(generate_signal(key, closes, highs_d, lows_d, vols_d))
                if len(sig_raw) < n: sig_raw += [0] * (n - len(sig_raw))
                return sig_raw[:n]
            except Exception:
                return [0] * n
        return [0]*n


    # ── 交易成本参数（与 expert1a 保持一致）─────────────────────────
    BUY_COST  = 0.0003 + 0.0005   # 佣金+滑点 = 0.08%
    SELL_COST = 0.0003 + 0.0005 + 0.0010  # 佣金+滑点+印花税 = 0.18%

    @staticmethod
    def _simulate(signals, closes, initial_cash):
        """
        含交易成本模拟：
        - 买入：扣除佣金+滑点（0.08%）
        - 卖出：扣除佣金+滑点+印花税（0.18%）
        """
        cash = float(initial_cash)
        pos  = 0.0
        entry_price = 0.0
        equity = [cash]; trades = []; daily_rets = []

        for i in range(1, len(closes)):
            c = float(closes[i])
            prev_eq = float(equity[-1])
            sig = signals[i]

            if sig == 1 and pos == 0:
                target_pos = prev_eq * 0.95
                # 买入：佣金+滑点 0.08%
                actual_pos = target_pos * (1 - MeanReversionExpert.BUY_COST) / c
                cost       = target_pos * MeanReversionExpert.BUY_COST
                pos        = actual_pos
                cash       = prev_eq - cost - actual_pos * c
                entry_price = c

            elif sig == -1 and pos > 0:
                # 卖出：佣金+滑点+印花税 0.18%
                gross = pos * c
                cost  = gross * MeanReversionExpert.SELL_COST
                net   = gross - cost
                trade_ret = (net / initial_cash - 1.0) if initial_cash > 0 else 0.0
                trades.append(trade_ret)
                cash += net
                pos   = 0.0

            eq_today = cash + pos * c
            equity.append(eq_today)
            daily_rets.append((eq_today - prev_eq) / prev_eq if prev_eq > 0 else 0.0)

            if pos > 0 and entry_price == 0.0:
                entry_price = c

        return equity, trades, daily_rets

    def _build_report(self, strategy_id, params, key, equity, trades, daily_rets, n, cash):
        final = float(equity[-1])
        tr    = (final / cash - 1)
        ann   = ((final / cash) ** (252 / max(n - 1, 1)) - 1)
        vol   = self._std(daily_rets) * math.sqrt(252) if daily_rets else 0.0
        s     = ann / vol if vol > 0 else 0.0
        sortino_v  = self._sortino(daily_rets)
        max_dd_v   = self._max_dd(daily_rets)
        calmar     = ann / (max_dd_v / 100) if max_dd_v > 0 else 0.0
        wins  = [t for t in trades if t > 0]
        loss  = [t for t in trades if t < 0]
        wr    = len(wins) / len(trades) if trades else 0.0
        avg_w = sum(wins) / len(wins)   if wins  else 0.0
        avg_l = abs(sum(loss) / len(loss)) if loss else 1e-9
        pf    = avg_w / avg_l if avg_l > 1e-9 else 0.0
        name  = {
            "rsi": "RSI均值回归", "bollinger": "布林带回归", "vol_surge": "成交量异常",
            "mfi_signal": "MFI资金流", "rvi_signal": "RVI相对活力", "kdwave": "KDJ波形",
            "multi_roc_signal": "ROC多周期", "obos_composite": "OBOS超买超卖",
            "elder_ray_signal": "Elder Ray信号",
        }.get(key, key)
        return BacktestReport(
            strategy_id = strategy_id,
            strategy_name = name,
            strategy_type = "mean_reversion",
            tags = ["均值回归", name],
            params = params,
            total_return       = round(tr * 100, 2),
            sharpe_ratio        = round(s, 3),
            max_drawdown_pct    = round(max_dd_v, 2),
            annualized_return   = round(ann * 100, 2),
            volatility          = round(vol * 100, 2),
            total_trades       = len(trades),
            win_rate            = round(wr * 100, 2),
            profit_factor       = round(pf, 2),
            avg_holding_days    = round(len(trades) / max(n / 252, 1), 1),
            calmar_ratio        = round(calmar, 3),
            sortino_ratio       = round(sortino_v, 3),
            daily_returns       = [round(r, 4) for r in daily_rets],
        )

    @staticmethod
    def _std(vals):
        n = len(vals); m = sum(vals) / n if n > 1 else 0.0
        return math.sqrt(sum((v-m)**2 for v in vals) / (n-1)) if n > 1 else 0.0

    @staticmethod
    def _sortino(rets, target=0.0):
        d = [r for r in rets if r < target]
        if not d: return 0.0
        return (sum(rets)/len(rets)*252) / (MeanReversionExpert._std(d)*math.sqrt(252) + 1e-9)

    @staticmethod
    def _max_dd(rets):
        eq = 1.0; peak = 1.0; max_dd = 0.0
        for r in rets:
            eq *= (1 + r)
            if eq > peak: peak = eq
            dd = (eq - peak) / peak
            if dd < max_dd: max_dd = dd
        return abs(max_dd) * 100
