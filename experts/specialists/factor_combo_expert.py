"""
factor_combo_expert.py — 因子组合专家 v1
=========================================
合并 TrendExpert + MeanReversionExpert，统一 26 个策略模板。
候选 = 因子组合 (1~3 个因子 AND/OR/加权)，全因子库覆盖。

设计原则：
  - 不再区分"趋势"vs"均值回归"，所有因子平等竞争
  - 候选生成：从 26 个模板中随机组合 1-3 个因子
  - 信号生成：委托给 backtest/engine.py 的 _SCORE_REGISTRY
  - 回测执行：由 PortfolioBacktester 统一处理
"""
import math, random, uuid
from dataclasses import dataclass
from typing import List

@dataclass
class BacktestReport:
    strategy_id: str; strategy_name: str
    strategy_type: str = "combo"
    tags: List[str] = None; params: dict = None
    total_return: float = 0.0; sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0; annualized_return: float = 0.0
    volatility: float = 0.0; total_trades: int = 0
    win_rate: float = 0.0; profit_factor: float = 0.0
    avg_holding_days: float = 0.0; calmar_ratio: float = 0.0
    sortino_ratio: float = 0.0; daily_returns: list = None
    oos_annualized_return: float = 0.0
    execution_shortfall_median: float = 0.0
    execution_shortfall_mean: float = 0.0
    def __post_init__(self):
        if self.tags is None: self.tags = []
        if self.params is None: self.params = {}
        if self.daily_returns is None: self.daily_returns = []


class FactorComboExpert:
    """统一的因子组合专家，覆盖全部 26 个策略模板。"""

    # ── 全部模板（合并 Trend + MR）─────────────────────────────────
    # 趋势类
    _TREND = [
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

    # 均值回归类
    _MR = [
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

    # 创新策略（跨越传统分类）
    _INNOVATIVE = [
        {"key": "smart_money",       "name": "主力资金流",     "params": {"period": 20, "vol_weight": 1.5}},
        {"key": "gap_break",         "name": "跳空缺口突破",   "params": {"min_gap_pct": 0.02, "lookback": 10}},
        {"key": "limit_board",       "name": "涨停动能",       "params": {"gain_thr": 0.07, "lookback": 15}},
        {"key": "trend_composite",   "name": "趋势复合信号",   "params": {"ma_fast": 10, "ma_slow": 30, "mom_period": 15, "vol_period": 20}},
        {"key": "lanban_fade",       "name": "烂板反转",       "params": {"limit_thr": 0.08, "fade_days": 3, "confirm_days": 2}},
        {"key": "vol_price_diverge", "name": "量价背离",       "params": {"lookback": 20, "sensitivity": 1.0}},
        {"key": "multi_signal_combo","name": "多信号组合",     "params": {"rsi_period": 14, "rsi_lower": 35, "bb_period": 20, "vol_surge_thr": 1.5}},
        {"key": "mean_rev_composite","name": "均值回归复合",   "params": {"period": 20, "z_enter": 1.5, "z_exit": 0.5}},
    ]

    # v5: 补全因子（动量/量价/波幅/缠论）
    _EXTENDED = [
        {"key": "force_index",               "name": "强力指数",       "params": {"period": 13}},
        {"key": "ppo",                       "name": "PPO信号",        "params": {"fast": 12, "slow": 26, "sig": 9}},
        {"key": "accdist",                   "name": "A/D累积派发",    "params": {}},
        {"key": "accumulation_distribution_signal", "name": "A/D背离", "params": {}},
        {"key": "volume_price_trend",        "name": "VPT量价趋势",    "params": {}},
        {"key": "mass_index",                "name": "MassIndex梅斯",  "params": {}},
        {"key": "ergodic_oscillator",        "name": "Ergodic遍历",    "params": {"period": 14}},
        {"key": "signal_horizon",            "name": "信号水平线",     "params": {"period": 14}},
        {"key": "ultraspline",               "name": "波幅收缩爆发",   "params": {"period": 20}},
        {"key": "ultraband_signal",          "name": "UltraBand突破",  "params": {"period": 20}},
        {"key": "chanlun_bi",                "name": "缠论笔",         "params": {}},
        {"key": "chanlun_tao",               "name": "缠论套",         "params": {}},
    ]

    TEMPLATES = _TREND + _MR + _INNOVATIVE + _EXTENDED

    # ── 组合模式 ─────────────────────────────────────────────────
    COMBO_MODES = ["single", "and", "or", "weighted", "rank", "product", "hierarchical", "conditional"]

    # 概率分布对应 COMBO_MODES 索引
    COMBO_PROBS = [0.30, 0.20, 0.15, 0.15, 0.05, 0.05, 0.05, 0.05]

    def __init__(self, seed: int = 42):
        self.name = "FactorComboExpert"
        self._rng = random.Random(seed)
        self._tpl_keys = [t["key"] for t in self.TEMPLATES]
        self._tpl_map  = {t["key"]: t for t in self.TEMPLATES}

    # ── 候选生成 ──────────────────────────────────────────────────

    def _build_factor_entry(self, tpl_key: str, extra_params: dict = None) -> dict:
        """Build a factor entry dict for combo modes: key + all params."""
        tpl = self._tpl_map.get(tpl_key, {})
        entry = {"key": tpl_key}
        # Copy template default params
        for k, v in tpl.get("params", {}).items():
            entry[k] = v
        # Override with any extra params
        if extra_params:
            entry.update(extra_params)
        return entry

    def generate_candidates(self, count: int = 55, feedback: list = None) -> List[dict]:
        """
        生成 count 个候选策略，每个候选 = 1~3 个因子的组合。
        概率分布:
          30% single / 20% and(2因子) / 15% or(2因子) / 15% weighted(3因子)
           5% rank(2因子) / 5% product(2因子) / 5% hierarchical(2因子) / 5% conditional(2因子)
        """
        candidates = []
        for i in range(count):
            fb = (feedback[i] if (feedback and i < len(feedback)) else None) or {}

            # 决定组合模式
            roll = self._rng.random()
            cum = 0.0
            chosen_idx = 0
            for idx, p in enumerate(self.COMBO_PROBS):
                cum += p
                if roll < cum:
                    chosen_idx = idx
                    break
            mode = self.COMBO_MODES[chosen_idx]

            # 因子数和调参来源
            if mode == "single":
                n_factors = 1
            elif mode == "weighted":
                n_factors = 3
            else:
                n_factors = 2

            # 选因子
            factors = self._pick_factors(n_factors, fb)
            primary       = factors[0]
            combo_factors = factors[1:] if len(factors) > 1 else []
            tpl           = self._tpl_map[primary]
            params        = self._tune_params(tpl, fb)

            # 构建名字
            if n_factors == 1:
                name = tpl["name"]
            else:
                combo_names = [self._tpl_map[f]["name"] for f in combo_factors]
                name = f"{tpl['name']}+{'&'.join(combo_names)}"

            # 构建候选
            if mode == "single":
                cand = {
                    "strategy_id":   f"cmb_{uuid.uuid4().hex[:8]}",
                    "strategy_type": "combo",
                    "strategy_name": name,
                    "template_key":  primary,
                    "combo_factors": [],
                    "combo_mode":    mode,
                    "params":        params,
                    "tags":          [mode, primary],
                    "feedback_note": self._fb_summary(fb),
                }
            else:
                # 多因子组合: 构建 factors 数组
                all_factor_keys = [primary] + combo_factors
                factor_entries = [self._build_factor_entry(k) for k in all_factor_keys]

                # weighted 模式设不等权重
                if mode == "weighted":
                    weights = [0.5, 0.3, 0.2]
                    for j, entry in enumerate(factor_entries):
                        if j < len(weights):
                            entry["weight"] = weights[j]
                        else:
                            entry["weight"] = 1.0

                # hierarchical 模式标记分层
                combo_params = dict(params)
                if mode == "hierarchical":
                    combo_params["layer_split"] = 1

                # conditional 模式配置条件因子
                if mode == "conditional":
                    combo_params["condition"] = {
                        "key": primary,
                        "trend_threshold": params.get("adx_thr", 25),
                    }
                    # 条件因子作为判断依据，不参与打分
                    factor_entries = [self._build_factor_entry(f) for f in all_factor_keys[:2]]
                    for entry in factor_entries:
                        entry["weight_trend"] = 0.7 if entry["key"] == all_factor_keys[0] else 0.3
                        entry["weight_sideways"] = 0.3 if entry["key"] == all_factor_keys[0] else 0.7

                cand = {
                    "strategy_id":   f"cmb_{uuid.uuid4().hex[:8]}",
                    "strategy_type": "combo",
                    "strategy_name": name,
                    "template_key":  f"_combo_{mode}",
                    "combo_factors": combo_factors,
                    "combo_mode":    mode,
                    "params":        {**combo_params, "factors": factor_entries},
                    "tags":          [mode, primary] + combo_factors,
                    "feedback_note": self._fb_summary(fb),
                }

            candidates.append(cand)
        return candidates

    def _pick_factors(self, n: int, fb: dict) -> List[str]:
        """挑选 n 个不重复的因子，反馈驱动加权采样。"""
        available = list(self._tpl_keys)
        if fb:
            adj = (fb.get("adjustment") or "").lower()
            if "diversify" in adj or "add_factor" in adj:
                # 优先选不同类别的因子
                pass  # TODO: 根据因子类别做差异化采样

        picked = []
        for _ in range(n):
            # 简单随机选择（避免重复）
            remaining = [k for k in available if k not in picked]
            if not remaining:
                break
            picked.append(self._rng.choice(remaining))
        return picked

    def _tune_params(self, tpl: dict, fb: dict) -> dict:
        """从反馈中调参（复用 TrendExpert 的调参逻辑）。"""
        params = dict(tpl["params"])
        adj    = (fb.get("adjustment") or "").lower()
        pname  = fb.get("param", "")
        mag    = fb.get("magnitude", 0)
        unit   = fb.get("unit", "")
        if not adj or adj in ("none", "diversify"):
            return params

        if "increase_lookback" in adj:
            for k in ("lookback", "fast", "slow", "period", "r1", "r2", "p1", "p2", "p3"):
                if k in params and pname in ("", k):
                    params[k] = max(5, params.get(k, 10) + (int(mag) if unit == "天" else 5))
        elif "decrease_lookback" in adj:
            for k in ("lookback", "fast", "period", "r1", "p1"):
                if k in params and pname in ("", k):
                    params[k] = max(3, params.get(k, 10) - 5)
        elif "tighten_stop_loss" in adj or "tighten_filter" in adj:
            for k in ("atr_mult", "threshold", "std_mult"):
                if k in params and pname in ("", k):
                    params[k] = max(0.5, params.get(k, 2.0) * (mag if unit == "倍" else 0.7))
        elif "widen" in adj:
            for k in ("lower", "upper", "period"):
                if k in params and pname in ("", k):
                    params[k] = params.get(k, 14) + (int(mag) if unit == "天" else 5)
        elif "narrow" in adj:
            for k in ("lower", "upper", "period"):
                if k in params and pname in ("", k):
                    v = params.get(k, 14) - (int(mag) if unit == "天" else 5)
                    params[k] = max(3, v)
        elif "add_filter" in adj or "remove_filter" in adj:
            if "threshold" in params:
                delta = mag / 100 if unit == "%" else -0.2
                params["threshold"] = round(params["threshold"] * (1 + delta), 4)

        return params

    @staticmethod
    def _fb_summary(fb: dict) -> str:
        if not fb:
            return "首轮生成，无反馈"
        adj = fb.get("adjustment", "none")
        if adj in ("none", ""):
            return "无结构化指令"
        return (f"指令={adj}，参数={fb.get('param', '?')}，"
                f"幅度={fb.get('magnitude', 0):+.1f}{fb.get('unit', '')}")

    # ── 单标的回测（兼容旧接口，实际由 PortfolioBacktester 主导）───

    def backtest(self, data: dict, ind: dict, params: dict, template_key: str,
                 initial_cash: float = 1_000_000.0, strategy_id: str = None) -> BacktestReport:
        """
        单标的回测（兼容旧接口）。
        实际多标的组合回测由 PortfolioBacktester 执行。
        """
        closes = data["closes"]
        n = len(closes)
        if n < 60:
            return BacktestReport(strategy_id="", strategy_name="", params=params)

        signals = self._signal_series(closes, data, ind, params, template_key)
        equity, trades, daily_rets = self._simulate(signals, closes, initial_cash)
        sid = strategy_id or f"cmb_{uuid.uuid4().hex[:6]}"
        return self._build_report(sid, params, template_key, equity, trades, daily_rets, n, initial_cash)

    def _signal_series(self, closes, data, ind, params, key):
        """为单标的生成信号序列（委托给引擎已注册的因子函数）。"""
        n = len(closes)

        # ── 趋势类信号 ──
        if key == "ma_cross":
            ma20 = ind["ma20"]; ma60 = ind["ma60"]
            raw = [0 if i < 60 or ma20[i] is None or ma60[i] is None else
                   1 if ma20[i] > ma60[i] else -1
                   for i in range(n)]
            return self._debounce_signals(raw, min_consecutive=2, cooldown_days=2)
        elif key == "macd":
            fp_i = int(params.get("fp", 12)); sp_i = int(params.get("sp", 26)); sig_i = int(params.get("sig", 9))
            macd_line = [self._ema(closes, fp_i)[j] - self._ema(closes, sp_i)[j] for j in range(n)]
            sig_line  = self._ema(macd_line, sig_i)
            raw = [0 if i < sp_i + sig_i else
                   1 if macd_line[i] > sig_line[i] else -1
                   for i in range(n)]
            return self._debounce_signals(raw, min_consecutive=2, cooldown_days=2)
        elif key == "momentum":
            lb_i = int(params.get("lookback", 20)); thr = float(params.get("threshold", 0.05))
            raw = [0 if i < lb_i else
                   1 if (closes[i] - closes[i - lb_i]) / closes[i - lb_i] > thr else
                  -1 if (closes[i] - closes[i - lb_i]) / closes[i - lb_i] < -thr else 0
                   for i in range(n)]
            return self._debounce_signals(raw, min_consecutive=2, cooldown_days=2)
        elif key == "adx_trend":
            adx_v = ind.get("adx", [0] * n)
            adx_thr = float(params.get("adx_thr", 25))
            raw = [0 if i < 20 else
                   1 if adx_v[i] > adx_thr and closes[i] > closes[i - 1] else
                  -1 if adx_v[i] > adx_thr and closes[i] < closes[i - 1] else 0
                   for i in range(n)]
            return self._debounce_signals(raw, min_consecutive=2, cooldown_days=3)

        # ── 趋势因子库信号 ──
        elif key in ("ichimoku_signal", "kst", "trix", "donchian_breakout", "aroon_signal"):
            highs_d = data.get("highs", closes) if isinstance(data, dict) else closes
            lows_d  = data.get("lows",  closes) if isinstance(data, dict) else closes
            if key == "ichimoku_signal":
                from factors.trend import ichimoku_signal as _f
                raw = _f(closes, highs_d, lows_d,
                         tenkan=int(params.get("tenkan", 9)),
                         kijun=int(params.get("kijun", 26)))
            elif key == "kst":
                from factors.trend import kst as _f
                kst_line, kst_sig = _f(closes,
                                       roc1=int(params.get("r1", 10)),
                                       roc2=int(params.get("r2", 15)))
                raw = [1 if kst_line[i] > kst_sig[i] and not math.isnan(kst_line[i])
                       else -1 if kst_line[i] < kst_sig[i] and not math.isnan(kst_line[i])
                       else 0 for i in range(len(closes))]
            elif key == "trix":
                from factors.trend import trix as _f
                trix_vals, trix_sig = _f(closes, period=int(params.get("period", 15)))
                raw = [1 if not math.isnan(trix_vals[i]) and trix_vals[i] > trix_sig[i]
                       else -1 if not math.isnan(trix_vals[i]) and trix_vals[i] < trix_sig[i]
                       else 0 for i in range(len(closes))]
            elif key == "donchian_breakout":
                from factors.trend import donchian_breakout as _f
                raw = _f(closes, highs_d, lows_d, period=int(params.get("period", 20)))
            elif key == "aroon_signal":
                from factors.trend import aroon_signal as _f
                raw = _f(closes, highs_d, lows_d, period=int(params.get("period", 25)))
            else:
                raw = [0] * n
            raw = list(raw)
            if len(raw) < n: raw += [0] * (n - len(raw))
            return self._debounce_signals(raw[:n], min_consecutive=2, cooldown_days=2)

        # ── RSI ──
        elif key == "rsi":
            period = int(params.get("period", 14)); lower = float(params.get("lower", 30)); upper = float(params.get("upper", 70))
            gains, losses = [], []
            for i in range(1, n):
                d = closes[i] - closes[i-1]
                gains.append(max(d, 0)); losses.append(max(-d, 0))
            if len(gains) < period: return [0]*n
            avg_gain = sum(gains[:period]) / period; avg_loss = sum(losses[:period]) / period
            rsi_vals = [50.0]
            for j in range(period, len(gains)):
                avg_gain = (avg_gain * (period-1) + gains[j]) / period
                avg_loss = (avg_loss * (period-1) + losses[j]) / period
                rs = avg_gain / (avg_loss + 1e-10)
                rsi_vals.append(100 - 100/(1+rs))
            raw = [0]*period
            for j in range(len(rsi_vals)):
                i = j + period
                if rsi_vals[j] < lower: raw.append(1)
                elif rsi_vals[j] > upper: raw.append(-1)
                else: raw.append(0)
            return raw + [0]*(n - len(raw)) if len(raw) < n else raw[:n]

        # ── Bollinger ──
        elif key == "bollinger":
            period = int(params.get("period", 20)); std_mult = float(params.get("std_mult", 2.0))
            raw = [0]*n
            for i in range(period, n):
                mean = sum(closes[i-period:i]) / period
                std  = math.sqrt(sum((closes[j]-mean)**2 for j in range(i-period,i)) / period)
                if closes[i] < mean - std_mult*std: raw[i] = 1
                elif closes[i] > mean + std_mult*std: raw[i] = -1
            return raw

        # ── Volume Surge ──
        elif key == "vol_surge":
            vol_ma = int(params.get("vol_ma", 20)); thr = float(params.get("threshold", 2.0))
            vols = data.get("volumes", [1e9]*n)
            raw = [0]*n
            for i in range(vol_ma, n):
                avg_v = sum(vols[i-vol_ma:i]) / vol_ma
                if vols[i] > avg_v * thr: raw[i] = -1
            return raw

        # ── 均值回归因子库信号 ──
        elif key in ("mfi_signal", "rvi_signal", "kdwave", "multi_roc_signal", "obos_composite", "elder_ray_signal"):
            highs_d = data.get("highs", closes) if isinstance(data, dict) else closes
            lows_d  = data.get("lows", closes) if isinstance(data, dict) else closes
            vols_d  = data.get("volumes", [1e9]*n) if isinstance(data, dict) else [1e9]*n
            if key == "mfi_signal":
                from factors.mean_reversion import mfi_signal as _f
                sig_raw = _f(closes, highs_d, lows_d, vols_d, period=int(params.get("period", 14)))
            elif key == "rvi_signal":
                from factors.mean_reversion import rvi_signal as _f
                sig_raw = _f(closes, highs_d, lows_d, period=int(params.get("period", 10)))
            elif key == "kdwave":
                from factors.mean_reversion import kdwave as _f
                _, _, sig_raw = _f(highs_d, lows_d, closes,
                                   k_period=int(params.get("fastk", 9)),
                                   d_period=int(params.get("slowk", 3)))
            elif key == "multi_roc_signal":
                from factors.momentum import multi_roc_signal as _f
                sig_raw = _f(closes, periods=[int(params.get("p1", 5)), int(params.get("p2", 15)), int(params.get("p3", 30))])
            elif key == "obos_composite":
                from factors.mean_reversion import obos_composite as _f
                _, sig_raw = _f(closes, vols_d, rsi_period=int(params.get("period", 20)))
            elif key == "elder_ray_signal":
                from factors.momentum import elder_ray_signal as _f
                sig_raw = _f(closes, highs_d, lows_d, period=int(params.get("ema_period", 13)))
            else:
                sig_raw = [0] * n
            sig_raw = list(sig_raw)
            if len(sig_raw) < n: sig_raw += [0] * (n - len(sig_raw))
            return sig_raw[:n]

        return [0]*n

    # ── 信号去抖 ──────────────────────────────────────────────────
    @staticmethod
    def _debounce_signals(signals, min_consecutive=2, cooldown_days=3):
        n = len(signals)
        confirmed = [0] * n
        streak = 0; pending = 0
        for i in range(n):
            if signals[i] == pending:
                streak += 1
            else:
                streak = 1; pending = signals[i]
            if streak >= min_consecutive and pending != 0:
                confirmed[i] = pending; streak = 0
        cooldown = 0; result = [0] * n; pos_open = False
        for i in range(n):
            if cooldown > 0:
                cooldown -= 1
                if confirmed[i] == -1 and pos_open:
                    pos_open = False
                result[i] = 0
            elif confirmed[i] == 1 and not pos_open:
                result[i] = 1; pos_open = True
            elif confirmed[i] == -1 and pos_open:
                result[i] = -1; pos_open = False; cooldown = cooldown_days
            else:
                result[i] = 0
        return result

    @staticmethod
    def _ema(data, period):
        k = 2/(period+1); out = [data[0]]*len(data)
        for i in range(1, len(data)): out[i] = data[i]*k + out[i-1]*(1-k)
        return out

    # ── 交易模拟 ──────────────────────────────────────────────────
    from config.settings import TRADING_COST as _TC
    BUY_COST  = _TC["buy"]
    SELL_COST = _TC["sell"]

    @staticmethod
    def _simulate(signals, closes, initial_cash):
        cash = initial_cash; pos = 0.0; entry_price = 0.0
        equity = [initial_cash]; trades = []; daily_rets = []
        for i in range(1, len(closes)):
            prev_eq = equity[-1]; sig = signals[i]
            if sig == 1 and pos == 0:
                target_pos = prev_eq * 0.95
                actual_pos = target_pos * (1 - FactorComboExpert.BUY_COST) / closes[i]
                cost = target_pos * FactorComboExpert.BUY_COST
                pos = actual_pos; cash = prev_eq - cost - actual_pos * closes[i]
                entry_price = closes[i]
            elif sig == -1 and pos > 0:
                gross = pos * closes[i]; cost = gross * FactorComboExpert.SELL_COST
                net = gross - cost; trade_ret = (net / initial_cash - 1) if initial_cash > 0 else 0.0
                trades.append(trade_ret); cash += net; pos = 0.0
            eq_today = cash + pos * closes[i]; equity.append(eq_today)
            daily_rets.append((eq_today - prev_eq) / prev_eq if prev_eq > 0 else 0.0)
        return equity, trades, daily_rets

    @staticmethod
    def _build_report(strategy_id, params, key, equity, trades, daily_rets, n, cash):
        final = equity[-1]; tr = (final/cash - 1)
        ann = ((final/cash)**(252/max(n-1, 1)) - 1)
        vol = FactorComboExpert._std(daily_rets) * math.sqrt(252) if daily_rets else 0.0
        s = ann/vol if vol > 0 else 0.0
        sortino_v = FactorComboExpert._sortino(daily_rets)
        max_dd_v  = FactorComboExpert._max_dd(daily_rets)
        calmar = ann/(max_dd_v/100) if max_dd_v > 0 else 0.0
        name_map = {t["key"]: t["name"] for t in FactorComboExpert.TEMPLATES}
        name = name_map.get(key, key)
        wins = [t for t in trades if t > 0]; loss = [t for t in trades if t < 0]
        wr = len(wins)/len(trades) if trades else 0.0
        avg_win = sum(wins)/len(wins) if wins else 0.0
        avg_loss = abs(sum(loss)/len(loss)) if loss else 1.0
        pf = avg_win/avg_loss if avg_loss > 1e-9 else 0.0
        return BacktestReport(
            strategy_id=strategy_id, strategy_name=name, strategy_type="combo",
            tags=["因子组合", name], params=params,
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
    def _sortino(rets, target=0.0):
        d = [r for r in rets if r < target]
        if not d: return 0.0
        return (sum(rets)/len(rets)*252)/(FactorComboExpert._std(d)*math.sqrt(252)+1e-9)
    @staticmethod
    def _max_dd(rets):
        eq=1.0; peak=1.0; max_dd=0.0
        for r in rets: eq*=(1+r)
        if eq>peak: peak=eq
        dd=(eq-peak)/peak
        if dd<max_dd: max_dd=dd
        return abs(max_dd)*100
