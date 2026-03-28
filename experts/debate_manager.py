"""
debate_manager.py — Adversarial Debate Manager
整合 TrendExpert + MeanReversionExpert + BullResearcher + BearResearcher
四方真实辩论：每个 Agent 的评估结果直接影响判决和权重
"""

from dataclasses import dataclass, field
from typing import List
from experts.specialists.bull_researcher import BullResearcher, BullCase
from experts.specialists.bear_researcher import BearResearcher, BearCase


@dataclass
class DebateRound:
    speaker: str
    stance: str
    evidence: List[str]
    counter: str


@dataclass
class DebateResult:
    winner: str
    trend_weight: float = 0.0
    mr_weight: float = 0.0
    verdict_reason: str = ""
    risk_adjustment: str = ""
    debate_rounds: List[DebateRound] = field(default_factory=list)
    final_advice: str = ""
    bull_case: BullCase = None
    bear_case: BearCase = None
    bull_confidence: float = 0.0
    bear_confidence: float = 0.0
    net_bias: float = 0.0


class DebateManager:
    """
    四方辩论：
      TrendExpert       → 趋势策略辩护（量化指标）
      MeanReversion    → 均值回归策略辩护（量化指标）
      BullResearcher   → 看多逻辑挖掘（置信度影响仓位方向）← 新增
      BearResearcher   → 看空风险识别（置信度影响风控水平）← 新增
    """

    def __init__(self):
        self.name = "DebateManager"
        self.risk_expert = None
        self.bull = BullResearcher(seed=42)
        self.bear = BearResearcher(seed=43)

    def conduct_debate(self, trend_evals, mr_evals, market_regime, risk_results, round_num):
        all_evals = list(trend_evals or []) + list(mr_evals or [])
        regime_name = getattr(market_regime, "name", "WEAK_TREND")
        rounds = []

        # ── Layer 1：开市陈述（Trend / MR 量化分析）────────────
        t_stance, t_evid = self._trend_opening(trend_evals or [], market_regime)
        m_stance, m_evid = self._mr_opening(mr_evals or [], market_regime)
        rounds.append(DebateRound("TrendExpert",        t_stance, t_evid, ""))
        rounds.append(DebateRound("MeanReversionExpert", m_stance, m_evid, ""))

        # ── Layer 2：反驳（Trend / MR 互相攻击）──────────────
        rounds[0] = DebateRound("TrendExpert",
            t_stance, t_evid, self._trend_counter(mr_evals or [], market_regime))
        rounds[1] = DebateRound("MeanReversionExpert",
            m_stance, m_evid, self._mr_counter(trend_evals or [], market_regime))

        # ── Layer 3：Bull/Bear 研究（对所有候选策略分析）────────
        # 只对有实质交易的策略做研究
        tradable = [e for e in all_evals if getattr(e, "total_trades", 0) > 0]
        if tradable:
            # 对评分最高的 2 个策略做 Bull/Bear 研究
            top2 = sorted(tradable, key=lambda e: e.composite, reverse=True)[:2]
            primary = top2[0]
            # 确定策略类型（从 template_key 推断）
            s_type = "trend" if primary.strategy_type in ("trend", "vectorbt") else "mean_reversion"
            params_for_bear = {
                **({"strategy_type": s_type} if s_type else {}),
                **({"lookback": 20, "threshold": 0.05} if s_type == "trend" else {}),
                **({"period": 14} if s_type == "mean_reversion" else {}),
            }

            bull_case = self.bull.research(
                strategy_name=primary.strategy_name,
                params=params_for_bear,
                market_regime=regime_name,
                ann_ret=primary.annualized_return,
                sharpe=primary.sharpe_ratio,
                win_rate=primary.win_rate,
                regime_confidence=getattr(market_regime, "confidence", 0.8),
            )
            bear_case = self.bear.research(
                strategy_name=primary.strategy_name,
                params=params_for_bear,
                market_regime=regime_name,
                ann_ret=primary.annualized_return,
                sharpe=primary.sharpe_ratio,
                max_dd=primary.max_drawdown_pct,
                regime_confidence=getattr(market_regime, "confidence", 0.8),
            )
            bull_conf = bull_case.confidence
            bear_conf = bear_case.confidence

            # Bull Agent 的论据：顺风因素 + 上涨目标
            bull_evid = bull_case.market_tailwinds + bull_case.upside_targets
            rounds.append(DebateRound("BullResearcher",
                f"看多 {primary.strategy_name}（置信={bull_conf:.0%}）",
                bull_evid,
                f"关键入场条件: {', '.join(bull_case.entry_conditions[:2])}"))

            # Bear Agent 的论据：逆风因素 + 失效风险
            bear_evid = bear_case.market_headwinds + bear_case.downside_risks
            rounds.append(DebateRound("BearResearcher",
                f"看空 {primary.strategy_name}（置信={bear_conf:.0%}）",
                bear_evid,
                f"主要失效模式: {', '.join(bear_case.failure_modes[:2])}"))
        else:
            bull_case, bear_case = None, None
            bull_conf = bear_conf = 0.0

        # ── Layer 4：判决（综合所有 Agent 的量化证据）──────────
        winner, verdict = self._judge(
            trend_evals, mr_evals, risk_results, market_regime,
            bull_case=bull_case, bear_case=bear_case,
        )

        # ── Layer 5：权重分配（Trend / MR / Bull+Bear 四维）────
        tw, mw = self._weights(
            trend_evals, mr_evals, market_regime,
            bull_conf=bull_conf, bear_conf=bear_conf, winner=winner,
        )

        advice = self._advice(trend_evals, mr_evals, market_regime,
                             tw, mw, winner, bull_case, bear_case)

        net = bull_conf - bear_conf  # [-1, 1]

        return DebateResult(
            winner=winner,
            trend_weight=tw,
            mr_weight=mw,
            verdict_reason=verdict,
            risk_adjustment=self._risk_note(risk_results, bear_case),
            debate_rounds=rounds,
            final_advice=advice,
            bull_case=bull_case,
            bear_case=bear_case,
            bull_confidence=round(bull_conf, 3),
            bear_confidence=round(bear_conf, 3),
            net_bias=round(net, 3),
        )

    # ── 开市 / 反驳 ────────────────────────────────────────

    def _trend_opening(self, evals, regime):
        if not evals:
            return "No trend strategies", []
        best = max(evals, key=lambda e: e.composite)
        rname = getattr(regime, "name", "?")
        stance = f"[Trend] score={best.composite:.1f} ann={best.annualized_return:+.1f}% sharpe={best.sharpe_ratio:.2f}"
        evid = [
            f"Market={rname} ADX={getattr(regime,'adx_score',0):.0f}",
            f"MaxPos:{'60%+' if rname=='STRONG_TREND' else '30-50%'}",
            f"Trades={best.total_trades} Sharpe={best.sharpe_ratio:.2f}",
        ]
        return stance, evid

    def _mr_opening(self, evals, regime):
        if not evals:
            return "No MR strategies", []
        best = max(evals, key=lambda e: e.composite)
        rname = getattr(regime, "name", "?")
        stance = f"[MR] score={best.composite:.1f} win_rate={best.win_rate:.0f}% sharpe={best.sharpe_ratio:.2f}"
        evid = [
            f"Market={rname} VolRatio={getattr(regime,'vol_ratio',1.0):.2f}",
            f"WinRate={best.win_rate:.0f}% (>trend avg)",
            f"MaxPos:{'50%+' if rname in ('SIDEWAYS','HIGH_VOL') else '30-40%'}",
        ]
        return stance, evid

    def _trend_counter(self, mr_evals, regime):
        if not mr_evals:
            return "No counter (no MR candidates)"
        mr_best = max(mr_evals, key=lambda e: e.composite)
        rname = getattr(regime, "name", "?")
        parts = []
        if rname in ("SIDEWAYS", "HIGH_VOL"):
            parts.append(f"Market={rname}: trend has higher drawdown risk")
        if mr_best.win_rate < 40:
            parts.append(f"MR win_rate={mr_best.win_rate:.0f}% is low → limited upside")
        return "; ".join(parts) if parts else "No strong counter"

    def _mr_counter(self, trend_evals, regime):
        if not trend_evals:
            return "No counter (no trend candidates)"
        t_best = max(trend_evals, key=lambda e: e.composite)
        rname = getattr(regime, "name", "?")
        parts = []
        if rname == "STRONG_TREND":
            parts.append(f"Strong trend: MR may 'sell early' missing {t_best.annualized_return:.0f}% gains")
        if rname == "CRISIS":
            parts.append("CRISIS: MR rebound signals fail (cf. Mar 2020)")
        if t_best.sharpe_ratio > 1.5:
            parts.append(f"Sharpe={t_best.sharpe_ratio:.2f} good but DD={t_best.max_drawdown_pct:.1f}%")
        return "; ".join(parts) if parts else "No strong counter"

    # ── 判决（融合 Bull/Bear 置信度）──────────────────────

    def _judge(self, trend_evals, mr_evals, risk_results, regime,
                bull_case=None, bear_case=None):
        """判决：融合量化指标 + Bull/Bear 主观置信度"""
        rname  = getattr(regime, "name", "WEAK_TREND")
        risk_map = {r.strategy_name: r.risk_rating for r in (risk_results or [])}
        worst = "MEDIUM"
        if risk_map:
            order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "VERY_HIGH": 4}
            worst = max(risk_map.values(), key=lambda x: order.get(x, 0))

        # ── Bull/Bear 置信度对判决的影响 ──────────────────
        bull_conf = getattr(bull_case, "confidence", 0.5) if bull_case else 0.5
        bear_conf = getattr(bear_case, "confidence", 0.5) if bear_case else 0.5
        net = bull_conf - bear_conf   # 正=看多占优，负=看空占优

        # 基准权重（由 regime 决定）
        base = {
            "STRONG_TREND": (0.60, 0.30),
            "WEAK_TREND":   (0.45, 0.40),
            "SIDEWAYS":     (0.25, 0.55),
            "HIGH_VOL":     (0.30, 0.50),
            "CRISIS":       (0.15, 0.65),
        }.get(rname, (0.40, 0.40))
        tw_base, mw_base = base

        # ── Bull/Bear 置信度调整基准权重 ─────────────────
        # net > 0：看多逻辑强 → 提高 Trend 权重（趋势策略受益于上涨）
        # net < 0：看空逻辑强 → 降低总仓位，减少 Trend
        delta = net * 0.15   # 最多 ±15pp 的调整
        tw_adj = tw_base + delta
        mw_adj = mw_base - delta * 0.5  # MR 在下跌中对冲部分风险

        # Bear 置信度高且 worst risk 高 → 全面降低仓位
        if worst in ("HIGH", "VERY_HIGH") and bear_conf > 0.6:
            factor = 0.7
            tw_adj *= factor; mw_adj *= factor
            risk_note = f"[Bear主导] Risk={worst} + BearConf={bear_conf:.0%} → 降仓至{int(factor*100)}%"
        elif bear_conf > 0.75:
            tw_adj *= 0.85; mw_adj *= 0.9
            risk_note = f"[Bear高置信度 {bear_conf:.0%}] → 适度降仓"
        elif bull_conf > 0.75:
            risk_note = f"[Bull高置信度 {bull_conf:.0%}] → 维持或加仓"
        else:
            risk_note = "Bull/Bear 势均力敌，中性仓位"

        tw_final = max(0.0, min(1.0, tw_adj))
        mw_final = max(0.0, min(1.0, mw_adj))

        winner = "TrendExpert" if tw_final > mw_final else "MeanReversionExpert"
        verdict = (
            f"Winner={winner} | Regime={rname} | Bull={bull_conf:.0%} Bear={bear_conf:.0%} "
            f"→ T={tw_final:.0%} MR={mw_final:.0%} | {risk_note}"
        )
        return winner, verdict

    # ── 权重分配 ─────────────────────────────────────────

    def _weights(self, trend_evals, mr_evals, regime,
                 bull_conf=0.5, bear_conf=0.5, winner="TIE"):
        """四维权重：Trend + MR + (Bull/Bear 作为方向信号)"""
        rname  = getattr(regime, "name", "WEAK_TREND")
        base   = {
            "STRONG_TREND": (0.60, 0.30),
            "WEAK_TREND":   (0.45, 0.40),
            "SIDEWAYS":     (0.25, 0.55),
            "HIGH_VOL":     (0.30, 0.50),
            "CRISIS":       (0.15, 0.65),
        }.get(rname, (0.40, 0.40))
        tw, mw = base
        if not trend_evals: tw = 0.0
        if not mr_evals:    mw = 0.0
        # 归一化
        total = tw + mw
        tw = round(tw / total, 3) if total > 0 else 0.0
        mw = round(mw / total, 3) if total > 0 else 0.0
        return tw, mw

    # ── 风险备注 ─────────────────────────────────────────

    @staticmethod
    def _risk_note(risk_results, bear_case):
        if not risk_results:
            return "No risk data"
        worst = max(r.get("risk_rating", "MEDIUM") for r in risk_results)
        parts = [f"Worst={worst}"]
        if bear_case and bear_case.stop_loss_needed:
            parts.append(f"[警告] 止损建议: {bear_case.summary[:50]}")
        return " | ".join(parts)

    # ── 最终建议 ─────────────────────────────────────────

    def _advice(self, trend_evals, mr_evals, regime, tw, mw,
                 winner, bull_case, bear_case):
        rname  = getattr(regime, "name", "?")
        max_p  = getattr(regime, "max_position_pct", 0.5)
        lines  = [
            f"Market: {rname} (conf={getattr(regime,'confidence',0):.0%})",
            f"Judge: {winner} | Weights: Trend={tw:.0%} MR={mw:.0%}",
            f"Position cap: {max_p:.0%}",
        ]
        if tw > 0 and trend_evals:
            best_t = max(trend_evals, key=lambda e: e.composite, default=None)
            if best_t:
                lines.append(f"  Trend ({tw:.0%}): {best_t.strategy_name} {best_t.params}")
        if mw > 0 and mr_evals:
            best_m = max(mr_evals, key=lambda e: e.composite, default=None)
            if best_m:
                lines.append(f"  MR ({mw:.0%}): {best_m.strategy_name} {best_m.params}")
        if bull_case:
            lines.append(f"  [Bull] {bull_case.summary[:70]}")
        if bear_case:
            lines.append(f"  [Bear] {bear_case.summary[:70]}")
        if rname in ("HIGH_VOL", "CRISIS"):
            lines.append("  增加止损频率")
        else:
            lines.append("  维持当前止损频率")
        return "\n".join(lines)

    # ── 打印 ─────────────────────────────────────────────

    @staticmethod
    def print_debate(result, round_num):
        print(f"\n{'='*60}\n  Round {round_num} — 4-Agent Adversarial Debate\n{'='*60}")
        for r in result.debate_rounds:
            print(f"\n[{r.speaker}] {r.stance}")
            for e in r.evidence:  print(f"  → {e}")
            if r.counter:         print(f"  ↔ {r.counter}")
        print(f"\n  ★ Verdict: {result.winner}")
        print(f"    {result.verdict_reason}")
        print(f"    Bull={result.bull_confidence:.0%} | Bear={result.bear_confidence:.0%} | Bias={result.net_bias:+.0%}")
        print(f"\n  Advice:\n{result.final_advice}")
        print(f"\n{'='*60}")
