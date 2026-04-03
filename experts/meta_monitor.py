"""
meta_monitor.py — 迭代元监控专家（Meta Monitor Expert）

职责：
  1. 收集每轮迭代的状态快照
  2. 判断策略质量趋势（改善/平稳/退化）
  3. 评估专家系统结构本身是否有优化空间
  4. 每 N 轮（默认5）生成结构化报告，向用户汇报
  5. 触发实时预警条件时立即预警

触发预警条件（任一满足即预警）：
  - 连续 2 轮 Top 策略综合分下降
  - 某专家连续 5 轮胜出（多样性枯竭）
  - Expert2 淘汰率 > 80%（候选质量差）
  - 新闻置信度连续 3 轮为 0（传感器失灵）
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


# ─────────────────────────────────────────────
#  数据结构
# ─────────────────────────────────────────────

@dataclass
class RoundSnapshot:
    """单轮迭代快照"""
    round_num       : int

    # 策略质量
    top_score       : float   # 本轮最高综合分
    avg_score       : float   # 本轮平均综合分
    total_candidates: int     # 本轮候选总数
    accepted_count  : int     # Expert2 纳入数
    rejected_count  : int     # Expert2 淘汰数
    trend_count     : int     # 趋势类入选数
    mr_count        : int     # 均值回归类入选数

    # 辩论
    debate_winner   : str     # "TrendExpert" / "MeanReversionExpert" / "TIE"
    trend_win_streak: int     # 趋势专家连续胜出轮次
    mr_win_streak   : int     # 均值回归专家连续胜出轮次

    # 新闻情绪
    sentiment_label : str     # POSITIVE / NEUTRAL / NEGATIVE
    sentiment_score : float
    sentiment_conf  : float

    # 市场状态
    market_regime   : str

    # 风险
    avg_var99       : float   # 平均 VaR99

    # 淘汰原因分布
    elimination_causes: dict  # {"低夏普": 2, "年化不足": 1, ...}

    sentiment_enabled: bool = False  # True when news_sentiment module is active

    timestamp        : str = field(
        default_factory=lambda: datetime.now().strftime("%H:%M:%S")
    )


@dataclass
class QualityTrend:
    """策略质量趋势"""
    direction        : str   # IMPROVING / STABLE / DEGRADING / UNKNOWN
    delta            : float  # 相邻轮次变化量
    confidence      : float  # 判断置信度
    explanation      : str   # 人类可读说明


@dataclass
class ExpertContribution:
    """各专家贡献度评分"""
    expert           : str
    usefulness_score : float  # 0~100，有用程度
    diversity_score  : float  # 0~100，多样性贡献
    reliability_score: float  # 0~100，稳定性
    suggestion       : str    # 对该专家的优化建议


@dataclass
class MetaReport:
    """元监控报告（每5轮或预警时生成）"""
    rounds_analyzed  : int
    from_round       : int
    to_round         : int

    # 质量趋势
    quality_trend    : QualityTrend

    # 收敛分析
    converged        : bool
    convergence_round: int    # 若收敛，则在第几轮收敛

    # 专家表现
    expert_scores    : List[ExpertContribution]

    # 策略多样性
    diversity_index : float   # 0~1（1=完全不同类型，0=全同类）
    type_balance    : dict    # {"trend": 0.6, "mean_reversion": 0.4}

    # 系统结构问题
    structural_issues: List[str]  # 发现的问题列表
    optimization_suggestions: List[str]  # 优化建议

    # 预警（若有）
    alerts          : List[str]  # 触发预警的原因

    # 全局Top策略
    best_strategies : List[dict]  # [{"name": ..., "avg_score": ..., "count": ...}]

    timestamp       : str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M")
    )


# ─────────────────────────────────────────────
#  淘汰原因映射（归一化）
# ─────────────────────────────────────────────

def _normalize_cause(cause: str) -> str:
    """将具体原因归一化为大类"""
    cause = cause.lower()
    if any(w in cause for w in ["夏普", "sharpe", "sr<"]):
        return "低夏普比率"
    if any(w in cause for w in ["年化", "annual"]):
        return "年化收益率不足"
    if any(w in cause for w in ["回撤", "drawdown", "dd>"]):
        return "最大回撤超限"
    if any(w in cause for w in ["交易", "trade", "<2", "<3"]):
        return "交易次数不足"
    if any(w in cause for w in ["胜率", "win", "wr<"]):
        return "胜率过低"
    if any(w in cause for w in ["盈亏", "pf<", "profit"]):
        return "盈亏比不足"
    return "其他"


# ─────────────────────────────────────────────
#  MetaMonitor 主类
# ─────────────────────────────────────────────

from experts.llm_prompts import LLM_META_PROMPT, LLM_PLAN_PROMPT, LLM_ARCH_PROMPT

class MetaMonitor:
    """
    迭代元监控专家。

    使用方式：
      monitor = MetaMonitor(report_every=5)

      # 每轮迭代结束后调用：
      monitor.record_round(snapshot)

      # 需要汇报时调用：
      if monitor.should_report():
          report = monitor.generate_report()
          print(report)
    """

    def __init__(self, report_every: int = 5):
        self.report_every = report_every
        self.snapshots: List[RoundSnapshot] = []

        # 胜出连续计数
        self._trend_streak = 0
        self._mr_streak    = 0

        # 预警状态
        self._alerts_triggered: List[str] = []

    # ── 记录单轮快照 ─────────────────────────

    def record_round(self, snapshot: RoundSnapshot):
        """每轮迭代结束时调用，记录快照"""
        # 更新辩论连续胜出次数
        if snapshot.debate_winner == "TrendExpert":
            self._trend_streak += 1
            self._mr_streak = 0
        elif snapshot.debate_winner == "MeanReversionExpert":
            self._mr_streak += 1
            self._trend_streak = 0
        else:
            self._trend_streak = 0
            self._mr_streak = 0

        snapshot.trend_win_streak = self._trend_streak
        snapshot.mr_win_streak   = self._mr_streak
        self.snapshots.append(snapshot)

        # 触发预警检查
        alerts = self._check_alerts()
        if alerts:
            self._alerts_triggered.extend(alerts)

    # ── 预警检测 ─────────────────────────────

    def _check_alerts(self) -> List[str]:
        """检查是否触发预警条件"""
        alerts = []
        n = len(self.snapshots)
        if n < 2:
            return alerts

        # 条件1：连续2轮质量下降
        recent = self.snapshots[-2:]
        if (len(recent) >= 2 and
            recent[0].top_score > recent[1].top_score and
            (n < 3 or self.snapshots[-3].top_score > recent[0].top_score)):
            alerts.append(
                f"⚠️ 【预警】策略质量连续2轮下降："
                f"第{n-2}轮={recent[0].top_score:.1f} → "
                f"第{n-1}轮={recent[1].top_score:.1f}。"
                f"建议检查：市场状态是否突变，或硬过滤条件是否过严。"
            )

        # 条件2：某专家连续5轮胜出
        if self._trend_streak >= 5:
            alerts.append(
                f"⚠️ 【预警】趋势专家已连续胜出{self._trend_streak}轮，"
                f"辩论多样性枯竭。策略池可能过度集中于趋势类，"
                f"建议：①降低趋势类基础权重；②引入新策略类型（如统计套利）。"
            )
        if self._mr_streak >= 5:
            alerts.append(
                f"⚠️ 【预警】均值回归专家已连续胜出{self._mr_streak}轮，"
                f"策略同质化风险。建议增加事件驱动/宏观因子专家。"
            )

        # 条件3：淘汰率过高
        last = self.snapshots[-1]
        if last.total_candidates > 0:
            reject_rate = last.rejected_count / last.total_candidates
            if reject_rate > 0.80 and last.total_candidates >= 5:
                alerts.append(
                    f"⚠️ 【预警】第{last.round_num}轮淘汰率={reject_rate:.0%}（{last.rejected_count}/{last.total_candidates}）"
                    f"，候选质量持续低迷。建议：①放宽夏普门槛（当前<0.3）；"
                    f"②检查市场数据质量；③增加策略模板多样性。"
                )

        # 条件4：新闻置信度连续3轮为0（仅在模块启用时检查）
        enabled_snaps = [s for s in self.snapshots if getattr(s, "sentiment_enabled", False)]
        if len(enabled_snaps) >= 3:
            recent_3 = enabled_snaps[-3:]
            if all(s.sentiment_conf == 0.0 for s in recent_3):
                alerts.append(
                    "⚠️ 【预警】新闻情绪置信度连续3轮为0，传感器失灵。"
                    "可能原因：①网络不可用；②关键词未命中。影响：情绪模块决策权重应降为0，"
                    "改由市场状态专家主导适配。"
                )

        return alerts

    # ── 是否该汇报 ────────────────────────────

    def should_report(self) -> bool:
        """判断是否应生成汇报"""
        n = len(self.snapshots)
        if n == 0:
            return False
        # 每 N 轮汇报一次
        if n % self.report_every == 0:
            return True
        # 或者有新的预警
        if len(self._alerts_triggered) > 0:
            return True
        return False

    def get_pending_alerts(self) -> List[str]:
        """获取未读的预警"""
        return list(self._alerts_triggered)

    def clear_alerts(self):
        """预警已读后清除"""
        self._alerts_triggered.clear()

    # ── 生成元报告 ────────────────────────────

    def generate_report(self, rounds: List) -> MetaReport:
        """
        生成元监控报告。
        rounds: 所有轮次的 Orchestrator RoundReportFake 对象列表
        """
        n = len(self.snapshots)
        if n == 0:
            raise ValueError("No snapshots to analyze")

        # 质量趋势
        trend = self._analyze_quality_trend()

        # 收敛判断
        converged, conv_round = self._check_convergence()

        # 专家贡献度
        expert_scores = self._score_experts()

        # 多样性
        div_idx, type_bal = self._diversity_index()

        # 系统结构问题
        issues, suggestions = self._structural_analysis(expert_scores, div_idx)

        # 收集预警
        alerts = list(self._alerts_triggered)
        self._alerts_triggered.clear()

        # 全局Top策略
        best_strats = self._top_strategies(rounds)

        return MetaReport(
            rounds_analyzed  = n,
            from_round       = self.snapshots[0].round_num,
            to_round         = self.snapshots[-1].round_num,
            quality_trend    = trend,
            converged       = converged,
            convergence_round = conv_round,
            expert_scores   = expert_scores,
            diversity_index = div_idx,
            type_balance    = type_bal,
            structural_issues = issues,
            optimization_suggestions = suggestions,
            alerts          = alerts,
            best_strategies = best_strats,
        )

    # ── LLM 元专家评估（每轮调用）────────────────────────────


    def llm_evaluate_round(self, round_strategies: list, best_score_ever: float, no_improve_count: int) -> dict:
        """每轮结束后调用 LLM 元专家评估本轮数据质量和收敛真实性。

        round_strategies: 本轮所有策略的 dict 列表（含 name, score, trades, ann_return, sharpe, decision）
        best_score_ever: 历史最高冠军分
        no_improve_count: 当前无提升轮数计数
        """
        from experts.modules.llm_proxy import llm_analyze

        n = len(self.snapshots)
        snap = self.snapshots[-1] if self.snapshots else None

        # 构造送给 LLM 的数据概要
        strat_summary = []
        for s in round_strategies[:20]:  # 最多20条避免 token 超限
            strat_summary.append({
                "name":     s.get("name", ""),
                "type":     s.get("type", ""),
                "decision": s.get("decision", ""),
                "score":    round(s.get("score", 0), 1),
                "trades":   s.get("total_trades", 0),
                "ann":      round(s.get("ann_return", 0), 1),
                "sharpe":   round(s.get("sharpe", 0), 2),
            })

        score_history = [round(s.top_score, 1) for s in self.snapshots]

        data = {
            "round_num":        n,
            "best_score_ever":  round(best_score_ever, 1),
            "no_improve_count": no_improve_count,
            "score_history":    score_history,
            "this_round": {
                "top_score":        round(snap.top_score, 1) if snap else 0,
                "accepted":         snap.accepted_count if snap else 0,
                "rejected":         snap.rejected_count if snap else 0,
                "total_candidates": snap.total_candidates if snap else 0,
                "trend_accepted":   snap.trend_count if snap else 0,
                "mr_accepted":      snap.mr_count if snap else 0,
            },
            "strategies": strat_summary,
        }

        import json as _json
        prompt = LLM_META_PROMPT.replace("{data_json}", _json.dumps(data, ensure_ascii=False, indent=2))

        MAX_RETRIES = 3
        last_error  = ""
        for attempt in range(1, MAX_RETRIES + 1):
            result = llm_analyze(
                prompt, task="meta_evaluate",
                temperature=0.3, timeout_ms=60000, max_tokens=10240,
            )
            if "error" not in result:
                result["_llm_available"] = True
                return result
            last_error = result["error"]
            print(f"  [元专家] 第{attempt}次调用失败: {last_error[:120]}"
                  + ("，重试…" if attempt < MAX_RETRIES else "，已达最大重试次数"))

        # 所有重试耗尽 —— 显式标注失败，不静默降级
        return {
            "data_validity":      "UNKNOWN",
            "invalidity_reasons": [f"[LLM_FAILED×{MAX_RETRIES}] {last_error[:200]}"],
            "convergence_is_real": True,
            "should_continue":    False,
            "continue_reason":    f"元专家 LLM 连续 {MAX_RETRIES} 次失败，本轮收敛判断由规则主导",
            "round_summary":      f"⚠️ 第{n}轮 · 元专家LLM失败({MAX_RETRIES}次重试)",
            "key_insight":        f"元专家不可用，错误: {last_error[:100]}",
            "suggestions":        ["检查 MiniMax API Key 和网络连通性"],
            "_llm_available":     False,
            "_llm_failed":        True,   # 区分"未调用"和"调用失败"
        }

    # ── 元专家：动态规划下一轮参数 ─────────────────────────

    def llm_plan_next_round(self, round_data: dict, history: dict) -> dict:
        """调用 LLM 元专家规划下一轮参数。"""
        from experts.modules.llm_proxy import llm_analyze
        import json as _json

        # 检测陷阱
        traps = []
        total_cands = history.get("total_candidates", 0)
        total_accepted = history.get("total_accepted", 0)
        total_rejected = history.get("total_rejected", 0)
        accept_rate = total_accepted / max(total_cands, 1)

        if accept_rate < 0.10:
            traps.append(f"接受率极低 ({accept_rate:.1%})，大量策略被淘汰")
        if round_data.get("zero_trade_count", 0) > total_cands * 0.3:
            traps.append(f"超过30%策略零交易，可能是数据窗口或信号生成问题")
        if round_data.get("avg_trades", 0) < 5:
            traps.append(f"平均交易次数过低 ({round_data['avg_trades']:.1f})，统计不可靠")

        # 构造 round_summary
        round_summary = _json.dumps(round_data, ensure_ascii=False, indent=2)

        import json as _json
        prompt = LLM_PLAN_PROMPT
        prompt = prompt.replace("{round_summary}", round_summary)
        prompt = prompt.replace("{best_score}", str(round(history.get("best_score", 0), 1)))
        prompt = prompt.replace("{no_improve}", str(history.get("no_improve", 0)))
        prompt = prompt.replace("{completed_rounds}", str(history.get("completed_rounds", 0)))
        prompt = prompt.replace("{total_candidates}", str(total_cands))
        prompt = prompt.replace("{total_accepted}", str(total_accepted))
        prompt = prompt.replace("{total_rejected}", str(total_rejected))
        prompt = prompt.replace("{accept_rate}", f"{accept_rate:.1%}")
        prompt = prompt.replace("{traps}", "\n".join(f"- {t}" for t in traps) if traps else "- 无明显陷阱")

        # 默认参数（LLM 失败时使用）
        defaults = {
            "next_round_params": {
                "trend_candidates": 30,
                "mr_candidates": 25,
                "accept_threshold": 45,
                "conditional_threshold": 25,
                "n_stocks_min": 2,
                "n_stocks_max": 5,
                "rebalance_options": [5, 10, 20, 60],
            },
            "reasoning": "LLM 不可用，使用默认参数",
            "traps_detected": traps,
            "suggestions": ["检查 MiniMax API 连接"],
            "_llm_available": False,
        }

        try:
            result = llm_analyze(prompt, task="plan_next_round",
                                 temperature=0.3, timeout_ms=60000, max_tokens=2048)
            if "error" in result:
                print(f"  [元专家-规划] ❌ LLM失败: {result['error'][:100]}")
                return defaults

            result["_llm_available"] = True

            # 解析并验证参数
            params = result.get("next_round_params", {})
            params["trend_candidates"] = max(10, min(60, int(params.get("trend_candidates", 30))))
            params["mr_candidates"] = max(10, min(40, int(params.get("mr_candidates", 25))))
            params["accept_threshold"] = max(30, min(70, float(params.get("accept_threshold", 45))))
            params["conditional_threshold"] = max(15, min(45, float(params.get("conditional_threshold", 25))))
            if params["conditional_threshold"] >= params["accept_threshold"]:
                params["conditional_threshold"] = params["accept_threshold"] - 10
            params["n_stocks_min"] = max(2, min(3, int(params.get("n_stocks_min", 2))))
            params["n_stocks_max"] = max(params["n_stocks_min"], min(5, int(params.get("n_stocks_max", 5))))

            result["next_round_params"] = params
            return result

        except Exception as e:
            print(f"  [元专家-规划] ❌ 异常: {e}")
            return defaults

    # ── 元专家：架构全局评估 ─────────────────────────────────────

    def llm_architecture_review(self, architecture_desc: str, iteration_result: dict) -> dict:
        """迭代终止后，让元专家对整个系统做架构评审。"""
        from experts.modules.llm_proxy import llm_analyze
        import json as _json

        import json as _json2
        prompt = LLM_ARCH_PROMPT
        prompt = prompt.replace("{architecture}", architecture_desc)
        prompt = prompt.replace("{iteration_result}", _json2.dumps(iteration_result, ensure_ascii=False, indent=2))

        defaults = {
            "overall_rating": "N/A",
            "strengths": ["LLM 不可用，无法评估"],
            "weaknesses": ["MiniMax API 连接失败"],
            "critical_issues": ["元专家 LLM 不可用"],
            "improvement_priorities": [],
            "architecture_suggestions": [],
            "next_iteration_focus": "修复 LLM 连接",
            "estimated_improvement": "N/A",
            "_llm_available": False,
        }

        try:
            result = llm_analyze(prompt, task="architecture_review",
                                 temperature=0.5, timeout_ms=120000, max_tokens=4096)
            if "error" in result:
                print(f"  [元专家-架构评审] ❌ LLM失败: {result['error'][:100]}")
                return defaults
            result["_llm_available"] = True
            return result
        except Exception as e:
            print(f"  [元专家-架构评审] ❌ 异常: {e}")
            return defaults

    # ── 质量趋势分析 ────────────────────────

    def _analyze_quality_trend(self) -> QualityTrend:
        if len(self.snapshots) < 2:
            return QualityTrend(
                direction="UNKNOWN",
                delta=0.0, confidence=0.0,
                explanation="数据不足，无法判断趋势"
            )

        recent = self.snapshots[-3:] if len(self.snapshots) >= 3 else self.snapshots
        scores = [s.top_score for s in recent]

        if len(scores) >= 2:
            delta = scores[-1] - scores[0]
        else:
            delta = 0.0

        if len(scores) >= 3:
            slopes = [scores[i+1] - scores[i] for i in range(len(scores)-1)]
            improving_count = sum(1 for s in slopes if s > 0)
            if improving_count >= 2:
                direction = "IMPROVING"
                explanation = (f"连续{len(scores)}轮中{improving_count}轮上升，"
                             f"从{scores[0]:.1f}→{scores[-1]:.1f}，策略质量持续改善。"
                             f"专家反馈机制有效，继续当前迭代方向。"
                             if delta > 2 else
                             f"整体平稳，局部波动（±{delta:.1f}分），无明显趋势。"
                             f"建议关注市场状态是否进入新阶段。"
                )
            elif all(s < 0 for s in slopes):
                direction = "DEGRADING"
                explanation = (f"连续{len(scores)}轮下降（{scores[0]:.1f}→{scores[-1]:.1f}），"
                             f"策略质量退化。可能是市场状态变化或候选多样性不足。"
                             f"建议：①检查市场状态是否改变；②引入新策略类型；③放宽过滤条件。"
                )
            else:
                direction = "STABLE"
                explanation = f"策略质量基本平稳（{scores[0]:.1f}→{scores[-1]:.1f}），无显著趋势。"

            confidence = min(1.0, len(slopes) * 0.4)
        else:
            direction = "STABLE"
            explanation = f"数据点不足，以首轮得分{scores[0]:.1f}为基准。"
            confidence = 0.3

        return QualityTrend(
            direction=direction, delta=round(delta, 1),
            confidence=round(confidence, 2), explanation=explanation
        )

    # ── 收敛判断 ────────────────────────────

    def _check_convergence(self):
        """判断是否收敛：连续2轮Top名单相同"""
        # 简化判断：Top分数差<1分即认为收敛
        if len(self.snapshots) < 3:
            return False, 0
        recent = self.snapshots[-3:]
        if all(abs(recent[i].top_score - recent[i+1].top_score) < 1.0
               for i in range(len(recent)-1)):
            return True, recent[0].round_num
        return False, 0

    # ── 专家贡献度评分 ────────────────────────

    def _score_experts(self) -> List[ExpertContribution]:
        if not self.snapshots:
            return []

        trend_wins = sum(1 for s in self.snapshots if s.debate_winner == "TrendExpert")
        mr_wins    = sum(1 for s in self.snapshots if s.debate_winner == "MeanReversionExpert")
        total      = len(self.snapshots)

        def streak(name):
            if name == "TrendExpert":
                return max(s.trend_win_streak for s in self.snapshots)
            return max(s.mr_win_streak for s in self.snapshots)

        expert_names = ["TrendExpert", "MeanReversionExpert", "RiskExpert",
                        "NewsSentiment", "MarketRegime"]

        scores = []
        for name in expert_names:
            if name == "TrendExpert":
                use_s  = min(100, 60 + (trend_wins / total) * 40)
                div_s  = max(0, 100 - abs(trend_wins - mr_wins) / total * 100)
                rel_s  = max(30, 80 - streak(name) * 8)
                sugg   = ("表现强势，但长期独占可能导致策略同质化。"
                        if trend_wins > mr_wins * 2 else
                        "正常，建议持续监控多样性。")
            elif name == "MeanReversionExpert":
                use_s  = min(100, 60 + (mr_wins / total) * 40)
                div_s  = max(0, 100 - abs(mr_wins - trend_wins) / total * 100)
                rel_s  = max(30, 80 - streak(name) * 8)
                sugg   = ("近期胜出频繁，若极端市场（CRISIS）到来需关注回撤风险。"
                        if mr_wins > trend_wins * 2 else "正常。")
            elif name == "RiskExpert":
                # VaR99持续稳定 → 高可靠
                avg_var = sum(s.avg_var99 for s in self.snapshots) / total if total else 5.0
                use_s  = 65.0
                div_s  = 50.0
                rel_s  = max(40, 90 - avg_var * 5)
                sugg   = "VaR稳定，低误报率，建议保留。"
            elif name == "NewsSentiment":
                conf_avg = sum(s.sentiment_conf for s in self.snapshots) / total if total else 0.0
                use_s  = conf_avg * 80
                div_s  = 40.0
                rel_s  = conf_avg * 70 if conf_avg > 0 else 20.0
                sugg   = ("置信度持续为0，建议降低其在组合决策中的权重，"
                        "或检查网络连接。") if conf_avg == 0 else "表现正常。"
            else:  # MarketRegime
                use_s = 70.0
                div_s = 55.0
                rel_s = 75.0
                sugg  = "市场状态检测稳定，对辩论裁决贡献显著。"

            scores.append(ExpertContribution(
                expert=name,
                usefulness_score=round(use_s, 1),
                diversity_score=round(div_s, 1),
                reliability_score=round(rel_s, 1),
                suggestion=sugg
            ))

        return scores

    # ── 策略多样性指数 ─────────────────────

    def _diversity_index(self):
        if not self.snapshots:
            return 0.0, {}

        total_trend = sum(s.trend_count for s in self.snapshots)
        total_mr    = sum(s.mr_count for s in self.snapshots)
        total       = total_trend + total_mr or 1

        t_ratio = total_trend / total
        # 香农多样性指数
        if t_ratio == 0 or t_ratio == 1:
            div_idx = 0.0
        else:
            div_idx = 2 * t_ratio * (1 - t_ratio)  # 简单二分类熵

        # 最新一轮的类型分布
        last = self.snapshots[-1]
        last_total = (last.trend_count + last.mr_count) or 1
        type_balance = {
            "趋势类": round(last.trend_count / last_total, 2),
            "均值回归类": round(last.mr_count / last_total, 2),
        }

        return round(div_idx, 3), type_balance

    # ── 系统结构分析 ────────────────────────

    def _structural_analysis(self, expert_scores, div_idx) -> tuple:
        issues = []
        suggestions = []

        # 问题1：多样性枯竭
        if div_idx < 0.15:
            issues.append(f"策略多样性严重不足（指数={div_idx:.2f}），"
                         f"入选策略同质化，组合风险集中。")
            suggestions.append("建议立即引入新策略类型：统计套利、事件驱动、机器学习因子。"
                              "或降低评分中夏普的权重，增加策略类型多样性奖励。")

        # 问题2：淘汰率趋势
        if len(self.snapshots) >= 2:
            recent = self.snapshots[-2:]
            rates = [s.rejected_count / max(s.total_candidates,1)
                    for s in recent]
            if all(r > 0.5 for r in rates):
                issues.append(f"连续2轮淘汰率>50%，候选生成质量差或硬过滤条件过严。")
                suggestions.append("建议：①适当放宽夏普门槛（0.3→0.2）；"
                                 "②Expert1每个模板至少生成2个不同参数版本；"
                                 "③加入基于规则的预过滤，减少Expert2压力。")

        # 问题3：某专家过度主导
        for e in expert_scores:
            if e.usefulness_score > 90 and e.diversity_score < 20:
                issues.append(f"专家{e.expert}过度主导（有用度={e.usefulness_score}%，"
                           f"多样性={e.diversity_score}%），系统平衡被打破。")
                suggestions.append(f"{e.expert}：{e.suggestion}")

        # 问题4：无预警但质量平稳
        if (len(self.snapshots) >= 3 and
            all(s.direction == "STABLE"
                for s in [self._snap_to_trend(s) for s in self.snapshots[-3:]])):
            issues.append("策略质量连续3轮无明显改善，可能已达到当前系统能力上限。")
            suggestions.append("建议：①增加策略模板多样性（当前仅趋势+均值回归）；"
                             "②扩大标的池（加入期货、外汇）；"
                             "③引入外部数据（宏观因子、另类数据）。")

        # 问题5：新闻传感器失灵（仅在模块启用时检查）
        enabled_snaps = [s for s in self.snapshots if getattr(s, "sentiment_enabled", False)]
        if enabled_snaps:
            no_signal = sum(1 for s in enabled_snaps if s.sentiment_conf == 0.0)
            if no_signal >= len(enabled_snaps) * 0.6:
                issues.append(f"{no_signal}轮新闻置信度为0，情绪模块形同虚设。")
                suggestions.append("建议：在情绪模块恢复前，默认使用NEUTRAL状态，"
                                 "同时加大MarketRegimeExpert在决策中的权重。")

        return issues, suggestions

    def _snap_to_trend(self, snap) -> QualityTrend:
        return QualityTrend(
            direction="STABLE", delta=0.0, confidence=0.0,
            explanation=""
        )

    # ── 全局Top策略 ────────────────────────

    def _top_strategies(self, rounds: List) -> List[dict]:
        """汇总所有轮次的Top策略"""
        strat_scores: dict = {}
        for rp in rounds:
            for e in (rp.trend_evals + rp.mr_evals):
                key = e.strategy_name
                if key not in strat_scores:
                    strat_scores[key] = {"name": key, "type": e.strategy_type,
                                       "scores": [], "count": 0}
                strat_scores[key]["scores"].append(e.composite)
                strat_scores[key]["count"] += 1

        result = []
        for name, info in strat_scores.items():
            avg_s = sum(info["scores"]) / len(info["scores"])
            result.append({
                "name"       : name,
                "type"       : info["type"],
                "avg_score"  : round(avg_s, 1),
                "rounds_seen": info["count"],
                "scores"     : [round(s, 1) for s in info["scores"]],
            })

        result.sort(key=lambda x: x["avg_score"], reverse=True)
        return result[:8]  # 最多返回8个

    # ── 打印报告 ───────────────────────────

    @staticmethod
    def print_report(report: MetaReport):
        """格式化打印元监控报告"""
        trend_icon = {"IMPROVING": "📈", "STABLE": "➡️",
                     "DEGRADING": "📉", "UNKNOWN": "❓"}.get(
                         report.quality_trend.direction, "➡️")

        print("\n" + "=" * 70)
        print(f"  🧠 迭代元监控报告（第 {report.from_round}~{report.to_round} 轮）")
        print("=" * 70)

        # 预警
        if report.alerts:
            print("\n🚨 实时预警：")
            for a in report.alerts:
                print(f"  {a}")

        # 质量趋势
        print(f"\n{trend_icon} 策略质量趋势：{report.quality_trend.direction}")
        print(f"   变化量：{report.quality_trend.delta:+.1f} 分")
        print(f"   置信度：{report.quality_trend.confidence:.0%}")
        print(f"   {report.quality_trend.explanation}")

        # 收敛
        if report.converged:
            print(f"\n✅ 系统已收敛（第 {report.convergence_round} 轮）")
        else:
            print(f"\n⚙️ 系统尚未收敛，继续迭代...")

        # 专家贡献度
        print(f"\n🔬 专家贡献度评估：")
        print(f"   {'专家':<20} {'有用度':>8} {'多样性':>8} {'稳定性':>8}  评价")
        print(f"   {'─'*60}")
        for e in report.expert_scores:
            flag = "⚠️" if e.diversity_score < 30 else ("🏆" if e.usefulness_score > 80 else "  ")
            print(f"   {flag}{e.expert:<18} {e.usefulness_score:>7.1f} "
                  f"{e.diversity_score:>8.1f} {e.reliability_score:>8.1f}")
            if e.suggestion:
                print(f"                            → {e.suggestion}")

        # 策略多样性
        bal = report.type_balance
        print(f"\n🔀 策略多样性指数：{report.diversity_index:.2f}（0=全同类，1=完全多样）")
        print(f"   当前分布：趋势类={bal.get('趋势类',0):.0%}，均值回归={bal.get('均值回归类',0):.0%}")

        # 结构问题
        if report.structural_issues:
            print(f"\n⚠️ 系统结构问题：")
            for issue in report.structural_issues:
                print(f"  · {issue}")
        if report.optimization_suggestions:
            print(f"\n💡 优化建议：")
            for sg in report.optimization_suggestions:
                print(f"  · {sg}")

        # 全局Top策略
        if report.best_strategies:
            print(f"\n🏅 跨轮全局Top策略：")
            print(f"   {'策略名':<20} {'类型':<12} {'平均分':>8} {'出现轮次':>8} {'近期得分'}")
            print(f"   {'─'*65}")
            for s in report.best_strategies[:5]:
                print(f"   {s['name']:<20} {s['type']:<12} "
                      f"{s['avg_score']:>8.1f} {s['rounds_seen']:>8}轮  "
                      f"{s['scores']}")

        print("\n" + "=" * 70)
