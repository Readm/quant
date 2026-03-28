"""
evaluator.py — Expert2 评估专家（含结构化反馈输出）
=====================================================
职责：
  1. 硬性过滤（年化 < 10% / 夏普 < 0.3 / 交易 < 3 / 回撤 > 35%）
  2. 多维打分 → 综合分 composite
  3. 输出结构化反馈（StructuredFeedback）+ 自然语言反馈
  4. 检测候选多样性（若某种类型连续被拒，提供 diversify 信号）
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional
from experts.structured_feedback import (
    StructuredFeedback, Weakness, AdjustmentDirection,
    FeedbackHistory
)

# ── 硬过滤门槛 ─────────────────────────────
MIN_ANNUAL_RETURN = 0.0   # 年化低于此 → REJECT
MIN_SHARPE        = 0.0    # 夏普低于此 → REJECT
MIN_TRADES        = 0        # 0 = 不淘汰（低频策略也有价值）
                     # 若需过滤极端情况，改用 SOFT_MIN_TRADES
SOFT_MIN_TRADES   = 3       # 仅作标记，不淘汰（低频=潜在高置信度）
MAX_DRAWDOWN      = 35.0   # 回撤高于此 → REJECT

# ── 打分权重 ────────────────────────────────
W_SHARPE   = 0.40   # 夏普权重
W_DRAWDOWN = 0.30   # 回撤权重
W_RETURN   = 0.30   # 年化权重


@dataclass
class EvalResult:
    # 身份
    strategy_id:   str;  strategy_name: str;  strategy_type: str
    params: dict;  tags: list

    # 原始指标
    total_return:      float;  annualized_return: float
    sharpe_ratio:      float;  max_drawdown_pct: float
    win_rate:          float;  profit_factor:     float
    total_trades:      int

    # 维度分（0~100）
    sharpe_score:      float;  drawdown_score: float
    return_score:      float;  composite:        float

    # 决策
    decision:  str           # ACCEPT / REJECT / CONDITIONAL
    reason:    str           # 人类可读原因
    feedback:  str           # 人类可读反馈（给生成专家）
    elimination_note: str = ""   # REJECT 时的淘汰说明
    weight: float = 0.0           # 组合权重（由 _build_portfolio 填充）

    # ── PBO 过拟合评估（新增）──────────────
    pbo_score: float = 0.0        # PBO 值 [0,1]，越高越稳健
    pbo_label: str = ""            # 标签：稳健/轻度过拟合/中度过拟合/严重过拟合
    sharpe_after_pbo: float = 0.0 # PBO 调整后的夏普（用于 composite）

    # ── 新增：结构化反馈 ───────────────
    structured_feedback: Optional[StructuredFeedback] = None


class Evaluator:
    """
    Expert2：策略评估 + 结构化反馈输出。
    新增：feedback_history 用于多样性检测。
    """

    def __init__(self):
        self.name = "Evaluator"
        self.history: List[dict]       = []
        self.fb_history: FeedbackHistory = FeedbackHistory()

    def evaluate(self, report, template_key: str = "") -> EvalResult:
        """
        评估单个 BacktestReport。
        同步输出结构化反馈（供 Expert1 直接使用）。
        """
        r          = report
        ann_ret    = getattr(r, "annualized_return", 0.0)
        sharpe     = getattr(r, "sharpe_ratio",     0.0)
        dd         = getattr(r, "max_drawdown_pct", 0.0)
        wr         = getattr(r, "win_rate",          0.0)
        pf         = getattr(r, "profit_factor",     0.0)
        n_trades   = getattr(r, "total_trades",      0)
        params     = getattr(r, "params",            {})
        tags       = getattr(r, "tags",               [])
        sid        = getattr(r, "strategy_id",        "")
        sname      = getattr(r, "strategy_name",      "")
        stype      = getattr(r, "strategy_type",     "unknown")

        # ── 1. 硬性过滤 ────────────────────────
        elim_reasons = []
        if ann_ret < MIN_ANNUAL_RETURN:
            elim_reasons.append(f"年化{ann_ret:.1f}% < {MIN_ANNUAL_RETURN}%目标线")
        if sharpe < MIN_SHARPE:
            elim_reasons.append(f"夏普{sharpe:.2f} < {MIN_SHARPE}门槛")
        if n_trades < MIN_TRADES:
            elim_reasons.append(f"交易{n_trades}次 < {MIN_TRADES}次（下数据不足）")
        if dd > MAX_DRAWDOWN:
            elim_reasons.append(f"回撤{dd:.1f}% > {MAX_DRAWDOWN}%上限")

        is_rejected = bool(elim_reasons)
        elim_note   = "【淘汰】" + "；".join(elim_reasons)

        # ── 2. 多维打分 ────────────────────────
        sharpe_s = self._s_sharpe(sharpe)
        dd_s     = self._s_dd(dd)
        ret_s    = self._s_ret(ann_ret)
        composite = sharpe_s * W_SHARPE + dd_s * W_DRAWDOWN + ret_s * W_RETURN

        # ── PBO 过拟合惩罚（新增）────────────────
        pbo_penalty_ratio, pbo_label, sharpe_after_pbo = self._pbo_penalty(r)
        # 用 PBO 调整后的夏普计算 composite
        sharpe_pbo_s = max(0.0, sharpe_s - pbo_penalty_ratio * 100)
        composite = sharpe_pbo_s * W_SHARPE + dd_s * W_DRAWDOWN + ret_s * W_RETURN
        composite = round(composite, 1)

        # ── 3. 决策 ────────────────────────────
        if is_rejected:
            decision = "REJECT"
            reason   = elim_note
        elif composite >= 60:
            decision = "ACCEPT"
            reason   = f"✅ 纳入（综合分={composite}，年化={ann_ret:.1f}%，夏普={sharpe:.2f}）"
        else:
            decision = "CONDITIONAL"
            reason   = f"⚠️ 待观察（综合分={composite}，建议优化参数）"

        # ── 4. 生成结构化反馈 ─────────────────
        fb_text   = self._make_feedback(ann_ret, sharpe, dd, wr, pf, n_trades)
        raw_note  = elim_note if is_rejected else reason

        # 手动构建结构化反馈（不依赖 from_eval_result）
        weakness, adj_dir, adj_param, adj_mag, adj_unit = self._diagnose_and_prescribe(
            ann_ret, sharpe, dd, wr, pf, n_trades, is_rejected
        )

        regime_map   = {"trend": "STRONG_TREND", "mean_reversion": "SIDEWAYS"}
        rec_regime  = regime_map.get(stype, "WEAK_TREND")
        pos_advice  = ("低配" if dd > 20 else "标配" if dd > 10 else "高配")
        alternatives = {
            "trend":          ["RSI均值回归", "布林带回归"],
            "mean_reversion": ["动量突破", "ADX趋势确认"],
        }.get(stype, [])

        sfb = StructuredFeedback(
            strategy_id    = sid,
            strategy_name   = sname,
            strategy_type   = stype,
            template_key    = template_key,
            weakness        = weakness,
            weakness_desc   = raw_note,
            ann_return      = ann_ret,
            sharpe_ratio    = sharpe,
            max_drawdown    = dd,
            win_rate        = wr,
            profit_factor   = pf,
            total_trades    = n_trades,
            composite       = composite,
            adjustment       = adj_dir,
            adjustment_param = adj_param,
            adjustment_magnitude = adj_mag,
            adjustment_unit  = adj_unit,
            recommended_regime = rec_regime,
            position_advice  = pos_advice,
            alternative_strategies = alternatives,
            raw_reason       = raw_note,
            feedback_text    = fb_text,
        )

        # 记录到历史
        self.history.append({"strategy_id": sid, "composite": composite,
                              "decision": decision, "ann_ret": ann_ret})
        self.fb_history.add(sfb)

        return EvalResult(
            strategy_id=sid, strategy_name=sname, strategy_type=stype,
            params=params, tags=tags,
            total_return=getattr(r, "total_return", 0.0),
            annualized_return=ann_ret, sharpe_ratio=sharpe,
            max_drawdown_pct=dd, win_rate=wr, profit_factor=pf,
            total_trades=n_trades,
            sharpe_score=round(sharpe_s, 1),
            drawdown_score=round(dd_s, 1),
            return_score=round(ret_s, 1),
            composite=composite,
            decision=decision, reason=reason,
            feedback=fb_text,
            elimination_note=elim_note,
            structured_feedback=sfb,
            pbo_score=round(sharpe_after_pbo / max(sharpe, 0.01)), pbo_label=pbo_label, sharpe_after_pbo=round(sharpe_after_pbo, 3),
        )

    def evaluate_batch(self, reports: list) -> List[EvalResult]:
        """批量评估并按综合分降序排列"""
        results = [self.evaluate(r) for r in reports]
        results.sort(key=lambda x: x.composite, reverse=True)
        return results

    # ── 弱点诊断 + 处方 ────────────────────
    @staticmethod
    def _diagnose_and_prescribe(ann, sharpe, dd, wr, pf, n_trades,
                                 is_rejected) -> tuple:
        """精确诊断弱点 → 生成可执行参数调整指令"""
        weakness_map = [
            (lambda: sharpe < MIN_SHARPE,
             Weakness.LOW_SHARPE,
             AdjustmentDirection.TIGHTEN_STOP_LOSS,  "atr_mult",   0.5,  "倍"),
            (lambda: dd > MAX_DRAWDOWN,
             Weakness.HIGH_DRAWDOWN,
             AdjustmentDirection.DECREASE_POSITION,    "position",   0.7,  "%"),
            (lambda: ann < MIN_ANNUAL_RETURN,
             Weakness.LOW_RETURN,
             AdjustmentDirection.INCREASE_LOOKBACK,   "lookback",   5,    "天"),
            (lambda: wr < 40,
             Weakness.LOW_WIN_RATE,
             AdjustmentDirection.DECREASE_LOOKBACK,   "period",    -5,    "天"),
            (lambda: pf < 1.3,
             Weakness.LOW_PROFIT_FACTOR,
             AdjustmentDirection.TIGHTEN_STOP_LOSS,   "atr_mult",   0.7,  "倍"),
            (lambda: n_trades < MIN_TRADES,
             Weakness.FEW_TRADES,
             AdjustmentDirection.ADD_FILTER,           "threshold", -0.2,  "%"),
        ]

        for check_fn, w, adj, param, mag, unit in weakness_map:
            if check_fn():
                return w, adj, param, mag, unit

        if is_rejected:
            return Weakness.OVERFITTED, AdjustmentDirection.DIVERSIFY, "", 0, ""
        return Weakness.NONE, AdjustmentDirection.NONE, "", 0, ""

    # ── 打分函数 ───────────────────────────
    @staticmethod
    def _s_sharpe(s):
        if s >= 2.0: return 100.0
        if s >= 1.0: return 80 + (s - 1.0) * 20
        if s >= 0.5: return 50 + (s - 0.5) * 60
        if s >= 0.0: return 30 + s * 40
        return max(0.0, 20 + s * 30)

    @staticmethod
    def _s_dd(d):
        if d <=  5: return 100.0
        if d <= 10: return 90.0
        if d <= 15: return 75.0
        if d <= 20: return 60.0
        if d <= 30: return 40.0
        return max(0.0, 30 - (d - 30) * 2)

    @staticmethod
    def _s_ret(a):
        if a >= 50: return 100.0
        if a >= 30: return 80 + (a - 30) * 1.0
        if a >= 10: return 50 + (a - 10) * 1.5
        if a >=  0: return max(0.0, a * 3)
        return 0.0

    # ── PBO 过拟合惩罚（新增）────────────────
    def _pbo_penalty(self, report) -> tuple:
        """计算 PBO 过拟合惩罚，返回 (penalty_ratio, pbo_label, adjusted_sharpe)"""
        try:
            from experts.modules.pbo_analysis import compute_pbo, pbo_score_adjustment
            from experts.specialists.expert1a_trend import TrendExpert
            from experts.specialists.expert1b_mean_reversion import MeanReversionExpert

            closes = getattr(report, "daily_returns", None)
            if closes is None or len(closes) < 60:
                return 0.0, "", 0.0

            s_type  = getattr(report, "strategy_type", "trend")
            params  = getattr(report, "params", {})
            sharpe  = getattr(report, "sharpe_ratio", 0.0)

            # 用真实收盘价重算信号（需要closes），PBO用模拟收益序列
            rets   = closes
            if len(rets) < 120:
                return 0.0, "", sharpe

            # 构建参数网格
            if "period" in params:
                grid = {
                    "period":   [max(7, params["period"]-3), params["period"], params["period"]+3],
                    "lower":    [25, 30],
                    "upper":    [70, 75],
                }
            elif "lookback" in params:
                grid = {
                    "lookback":  [max(10, params.get("lookback",20)-5), params.get("lookback",20), params.get("lookback",20)+5],
                    "threshold": [0.03, 0.05, 0.08],
                }
            elif "fast" in params:
                grid = {
                    "fast": [params["fast"]//2, params["fast"], params["fast"]*2],
                    "slow": [params["slow"]//2, params["slow"], params["slow"]*2],
                }
            else:
                return 0.0, "", sharpe

            result = compute_pbo(rets, lambda c, **kw: [0]*len(c), grid, n_windows=6, train_ratio=0.6)
            adj_sharpe, reason = pbo_score_adjustment(result, sharpe)
            pbo_val = result.pbo

            if pbo_val >= 0.80:   label = "🟢稳健"
            elif pbo_val >= 0.60: label = "🟡可接受"
            elif pbo_val >= 0.40: label = "🟠轻度过拟合"
            elif pbo_val >= 0.20: label = "🔴中度过拟合"
            else:                  label = "⚫严重过拟合"

            penalty = sharpe - adj_sharpe
            return penalty, label, adj_sharpe
        except Exception:
            return 0.0, "", getattr(report, "sharpe_ratio", 0.0)

    @staticmethod
    def _make_feedback(ann, sharpe, dd, wr, pf, n_trades) -> str:
        tips = []
        if sharpe < 0.5:  tips.append("收紧出场条件减少假信号")
        if dd > 20:        tips.append("降低单笔仓位至≤10%")
        if wr < 40:       tips.append("缩短持仓周期或加入趋势过滤")
        if pf < 1.3:      tips.append("优化止盈止损比，减少赢转亏")
        if n_trades < 5:  tips.append("放宽入场条件增加交易频率")
        if not tips:      tips.append("指标良好，可适度扩大仓位")
        return "；".join(tips)

    # ── 多样性检测 ────────────────────────
    def need_diversify(self) -> bool:
        """若某策略类型连续被拒绝 3 次以上，返回 True"""
        return self.fb_history.suggest_diversify()

    def get_structured_feedback_for(self, strategy_type: str) -> List[dict]:
        """获取某类型所有结构化反馈（简化 dict）"""
        fbs = self.fb_history.get_for_type(strategy_type)
        return [fb.to_simple_dict() for fb in fbs]

    # ── 报告打印 ───────────────────────────
    @staticmethod
    def print_batch_report(results: List[EvalResult], round_num: int):
        accepted    = [r for r in results if r.decision == "ACCEPT"]
        conditional = [r for r in results if r.decision == "CONDITIONAL"]
        rejected    = [r for r in results if r.decision == "REJECT"]

        print(f"\n{'='*68}")
        print(f"  Expert2 评估报告 — 第 {round_num} 轮（结构化反馈已启用）")
        print(f"{'='*68}")
        print(f"\n📊 结果：纳入 {len(accepted)} | 待观察 {len(conditional)} | 淘汰 {len(rejected)}")
        print(f"   硬过滤：年化<{MIN_ANNUAL_RETURN}% | 夏普<{MIN_SHARPE} | 交易<{MIN_TRADES}次 | 回撤>{MAX_DRAWDOWN}%\n")

        if accepted:
            print("✅ 纳入策略：")
            for r in accepted:
                sf = r.structured_feedback
                print(f"   · {r.strategy_name}（{r.strategy_type}）| "
                      f"年化{r.annualized_return:.1f}% | 夏普{r.sharpe_ratio:.3f} | "
                      f"回撤{r.max_drawdown_pct:.1f}% | 综合分={r.composite}")
                if sf:
                    print(f"     → 结构化反馈: 弱点={sf.weakness.value} | "
                          f"调整方向={sf.adjustment.value} | "
                          f"参数={sf.adjustment_param} {sf.adjustment_magnitude:+.1f}{sf.adjustment_unit}")
                print(f"     反馈：{r.feedback}")

        if conditional:
            print("\n⚠️ 待观察：")
            for r in conditional:
                print(f"   · {r.strategy_name} | 综合分={r.composite} | {r.reason}")

        if rejected:
            print(f"\n❌ 淘汰（{len(rejected)}个）：")
            for r in rejected[:5]:
                print(f"   · {r.strategy_name} | {r.elimination_note}")
                sf = r.structured_feedback
                if sf:
                    print(f"     → 需调整: {sf.adjustment.value} "
                          f"参数={sf.adjustment_param} "
                          f"幅度={sf.adjustment_magnitude:+.1f}{sf.adjustment_unit}")

        print(f"\n{'='*68}")


# ══════════════════════════════════════════════════════════════
#  PBO 集成（新增）
# ══════════════════════════════════════════════════════════════

def _pbo_penalty(report) -> tuple:
    """对候选报告计算 PBO 过拟合惩罚，返回 (penalty, reason)"""
    try:
        from experts.modules.pbo_analysis import compute_pbo, pbo_score_adjustment
        from experts.specialists.expert1a_trend import TrendExpert
        from experts.specialists.expert1b_mean_reversion import MeanReversionExpert

        closes = getattr(report, "closes", None) if hasattr(report, "closes") else None
        if closes is None or len(closes) < 120:
            return 0.0, "PBO: 数据不足，跳过"

        # 根据策略类型选择信号函数
        s_type = getattr(report, "strategy_type", "trend")
        params = getattr(report, "params", {})

        if s_type == "mean_reversion":
            fn = MeanReversionExpert()._signal_series
        else:
            fn = TrendExpert()._signal_series

        # 参数网格（从 params 推断 3 个变体）
        if "period" in params:
            grid = {"period": [max(7, params["period"]-3), params["period"], params["period"]+3],
                    "lower": [25, 30], "upper": [70, 75]}
        elif "lookback" in params:
            grid = {"lookback": [max(10, params["lookback"]-5), params["lookback"], params["lookback"]+5],
                    "threshold": [0.03, 0.05, 0.08]}
        elif "fast" in params:
            grid = {"fast": [params["fast"]//2, params["fast"], params["fast"]*2],
                    "slow": [params["slow"]//2, params["slow"], params["slow"]*2]}
        else:
            return 0.0, "PBO: 未知参数，跳过"

        result = compute_pbo(closes, fn, grid, n_windows=8, train_ratio=0.6)
        adj, reason = pbo_score_adjustment(result, getattr(report, "sharpe_ratio", 0.0))
        penalty = (getattr(report, "sharpe_ratio", 0.0) - adj)
        return penalty, reason

    except Exception as e:
        return 0.0, f"PBO: 异常({e})，跳过"

