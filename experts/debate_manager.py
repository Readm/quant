"""
debate_manager.py — 策略级 LLM 辩论 v5
========================================
每个通过门槛的策略单独经过 LLM 评审（优缺点 + 仓位建议），
整体 Trend vs MR 阵营权重也由 LLM 裁决。
无规则引擎，无降级。
"""

from dataclasses import dataclass, field
from typing import List

MAX_DEBATE_STRATEGIES = 5   # 每轮最多辩论 N 个策略
MIN_SCORE_FOR_DEBATE  = 35  # 综合分低于此值跳过


@dataclass
class DebateRound:
    speaker:  str
    stance:   str
    evidence: List[str]
    counter:  str


@dataclass
class StrategyVerdict:
    """单策略的 LLM 评审结论"""
    strategy_id:   str
    strategy_name: str
    composite:     float
    pros:          List[str] = field(default_factory=list)
    cons:          List[str] = field(default_factory=list)
    verdict:       str   = "HOLD"   # STRONG_BUY / BUY / HOLD / SELL
    confidence:    float = 0.5
    weight_advice: float = 0.0
    analysis:      str   = ""


@dataclass
class DebateResult:
    winner:            str
    trend_weight:      float = 0.5
    mr_weight:         float = 0.5
    verdict_reason:    str   = ""
    final_advice:      str   = ""
    debate_rounds:     List[DebateRound]     = field(default_factory=list)
    strategy_verdicts: List[StrategyVerdict] = field(default_factory=list)


class DebateManager:
    def __init__(self):
        self.name        = "DebateManager"
        self.risk_expert = None   # 由 orchestrator 注入，当前版本未使用

    # ── 主入口 ───────────────────────────────────────────────────

    def conduct_debate(self, trend_evals, mr_evals, market_regime,
                       risk_results, round_num):
        from experts.modules.llm_proxy import llm_analyze

        # v5: 统一处理 — trend_evals 可能包含全部策略, mr_evals 可能为空
        all_evals   = list(trend_evals or []) + list(mr_evals or [])
        regime_name = getattr(market_regime, "name", "UNKNOWN")
        rounds      = []

        # ── 筛选参与辩论的策略 ────────────────────────────────
        debate_pool = [
            e for e in all_evals
            if getattr(e, "total_trades", 0) > 0
            and getattr(e, "composite",   0) >= MIN_SCORE_FOR_DEBATE
        ]
        debate_pool.sort(key=lambda e: e.composite, reverse=True)
        debate_pool = debate_pool[:MAX_DEBATE_STRATEGIES]

        print(f"\n  [辩论] 参与策略 {len(debate_pool)} 个（门槛分={MIN_SCORE_FOR_DEBATE}，上限={MAX_DEBATE_STRATEGIES}）")

        # ── 逐策略 LLM 评审 ───────────────────────────────────
        strategy_verdicts: List[StrategyVerdict] = []
        for e in debate_pool:
            prompt = self._strategy_prompt(e, regime_name)
            result = llm_analyze(prompt, task="strategy_verdict",
                                 temperature=0.6, timeout_ms=25000)
            sv = StrategyVerdict(
                strategy_id   = e.strategy_id,
                strategy_name = e.strategy_name,
                composite     = e.composite,
                pros          = list(result.get("pros", [])),
                cons          = list(result.get("cons", [])),
                verdict       = str(result.get("verdict", "HOLD")),
                confidence    = min(1.0, max(0.0, float(result.get("confidence",    0.5)))),
                weight_advice = min(0.5, max(0.0, float(result.get("weight_advice", 0.0)))),
                analysis      = str(result.get("analysis", "")),
            )
            strategy_verdicts.append(sv)
            rounds.append(DebateRound(
                speaker  = e.strategy_name,
                stance   = f"{sv.verdict}（置信={sv.confidence:.0%}，仓位={sv.weight_advice:.0%}）",
                evidence = sv.pros[:3],
                counter  = "; ".join(sv.cons[:2]),
            ))

        # ── 阵营裁决 LLM ─────────────────────────────────────
        camp_prompt = self._camp_prompt(
            trend_evals, mr_evals, strategy_verdicts, regime_name, round_num)
        camp = llm_analyze(camp_prompt, task="camp_verdict",
                           temperature=0.5, timeout_ms=20000)

        winner = str(camp.get("winner", "TIE"))
        tw     = min(1.0, max(0.0, float(camp.get("trend_weight", 0.5))))
        mw     = min(1.0, max(0.0, float(camp.get("mr_weight",    0.5))))
        reason = str(camp.get("reason", ""))
        advice = str(camp.get("advice", ""))
        total  = tw + mw
        if total > 0:
            tw = round(tw / total, 3)
            mw = round(mw / total, 3)

        return DebateResult(
            winner            = winner,
            trend_weight      = tw,
            mr_weight         = mw,
            verdict_reason    = reason,
            final_advice      = advice,
            debate_rounds     = rounds,
            strategy_verdicts = strategy_verdicts,
        )

    # ── Prompt 构建 ──────────────────────────────────────────────

    @staticmethod
    def _strategy_prompt(e, regime_name: str) -> str:
        return (
            f"你是量化策略分析师，请评估以下回测策略并给出投资决策建议：\n\n"
            f"策略名: {e.strategy_name}\n"
            f"策略类型: {e.strategy_type}\n"
            f"参数: {getattr(e, 'params', {})}\n"
            f"年化收益: {e.annualized_return:+.2f}%\n"
            f"夏普比率: {e.sharpe_ratio:.3f}\n"
            f"最大回撤: {e.max_drawdown_pct:.2f}%\n"
            f"胜率: {e.win_rate:.1f}%\n"
            f"总交易次数: {e.total_trades}\n"
            f"综合评分: {e.composite:.1f}/100\n"
            f"当前市场状态: {regime_name}\n\n"
            f"请以JSON格式输出（直接返回JSON，不要有任何其他文字）：\n"
            f"{{\n"
            f'  "pros": ["优点1", "优点2", ...],\n'
            f'  "cons": ["缺点1", "缺点2", ...],\n'
            f'  "verdict": "STRONG_BUY 或 BUY 或 HOLD 或 SELL",\n'
            f'  "confidence": 0.0~1.0之间的数字,\n'
            f'  "weight_advice": 建议组合仓位比例0.0~0.5,\n'
            f'  "analysis": "一句话总结不超过60字"\n'
            f"}}"
        )

    @staticmethod
    def _camp_prompt(trend_evals, mr_evals, verdicts: List[StrategyVerdict],
                     regime_name: str, round_num: int) -> str:
        def best_stats(evals):
            if not evals: return "无候选"
            b = max(evals, key=lambda e: e.composite)
            return (f"{b.strategy_name} 年化={b.annualized_return:+.1f}%"
                    f" 夏普={b.sharpe_ratio:.2f} 综合分={b.composite:.1f}")

        verdict_lines = "\n".join(
            f"  {v.strategy_name}: {v.verdict} 仓位建议={v.weight_advice:.0%} 置信={v.confidence:.0%}"
            for v in verdicts
        ) or "  无策略通过辩论门槛"

        return (
            f"你是量化投资组合配置专家（第 {round_num} 轮迭代）。\n\n"
            f"市场状态: {regime_name}\n"
            f"趋势策略阵营最优 — {best_stats(trend_evals)}\n"
            f"均值回归阵营最优 — {best_stats(mr_evals)}\n\n"
            f"各策略 LLM 评审结论:\n{verdict_lines}\n\n"
            f"请综合以上信息，输出阵营权重分配（直接返回JSON，不要有任何其他文字）：\n"
            f"{{\n"
            f'  "winner": "TrendExpert 或 MeanReversionExpert 或 TIE",\n'
            f'  "trend_weight": 趋势阵营权重0.0~1.0,\n'
            f'  "mr_weight": 均值回归阵营权重0.0~1.0,\n'
            f'  "reason": "一句话裁决理由",\n'
            f'  "advice": "给交易员的2-3句具体建议"\n'
            f"}}"
        )

    # ── 打印 ─────────────────────────────────────────────────────

    @staticmethod
    def print_debate(result, round_num):
        print(f"\n{'='*60}\n  Round {round_num} — 策略级 LLM 辩论\n{'='*60}")
        if result.strategy_verdicts:
            print(f"\n  策略评审（{len(result.strategy_verdicts)} 个）：")
            for sv in result.strategy_verdicts:
                print(f"  [{sv.verdict}] {sv.strategy_name}"
                      f" 置信={sv.confidence:.0%} 仓位={sv.weight_advice:.0%}")
                if sv.analysis:
                    print(f"    → {sv.analysis}")
        else:
            print("  （无策略达到辩论门槛）")
        print(f"\n  ★ 阵营裁决: {result.winner}")
        print(f"    {result.verdict_reason}")
        print(f"    Trend={result.trend_weight:.0%} | MR={result.mr_weight:.0%}")
        if result.final_advice:
            print(f"\n  建议:\n    {result.final_advice}")
        print(f"{'='*60}")
