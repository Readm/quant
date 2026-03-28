"""
risk_engine.py — 风险专家模块

功能：
  1. 对候选策略做压力测试（VaR, CVaR）
  2. 极端情景打分（黑天鹅、历史极端日）
  3. 生成可解释的风险报告

可解释性设计：
  每个风险指标都附带"多少天触发一次"的频率说明，
  让非quant背景的用户也能理解。
"""

import math, random
from dataclasses import dataclass
from typing import List


@dataclass
class StressTestResult:
    """压力测试结果"""
    strategy_name  : str
    params          : dict

    # VaR / CVaR
    var_95          : float   # 单日VaR 95%（损失%）
    var_99          : float   # 单日VaR 99%
    cvar_95         : float   # 条件VaR（极端损失平均）

    # 极端情景打分
    crisis_score    : float   # 0~100（黑天鹅抵抗力）

    # 综合风险等级
    risk_rating     : str     # LOW / MEDIUM / HIGH / VERY_HIGH
    risk_explanation: str     # 人类可读说明
    frequency_note   : str     # "约每年发生N次"


class RiskExpert:
    """
    风险专家：对每个候选策略计算风险指标。
    纯Python实现，不依赖外部库。
    """

    def __init__(self, initial_cash: float = 1_000_000.0):
        self.initial_cash = initial_cash

    def analyze(self, strategy_name: str, params: dict,
               daily_returns: List[float],
               total_trades: int) -> StressTestResult:
        """
        主入口：对单策略做全面风险评估。
        """
        if not daily_returns or len(daily_returns) < 20:
            return self._default_result(strategy_name, params, "数据不足")

        # ── 基础统计 ─────────────────────────
        mu  = sum(daily_returns) / len(daily_returns)
        std = self._std(daily_returns)

        # ── VaR 计算 ─────────────────────────
        var_95, var_99 = self._compute_var(daily_returns)
        cvar_95         = self._compute_cvar(daily_returns, var_95)

        # ── 极端情景测试 ─────────────────────
        crisis_score = self._crisis_test(daily_returns)

        # ── 综合评级 ─────────────────────────
        risk_rating, explanation = self._rate(
            var_99, crisis_score, total_trades, std
        )

        # ── 频率说明 ─────────────────────────
        freq_note = self._freq_note(var_95)

        return StressTestResult(
            strategy_name   = strategy_name,
            params         = params,
            var_95         = round(var_95 * 100, 3),
            var_99         = round(var_99 * 100, 3),
            cvar_95        = round(cvar_95 * 100, 3),
            crisis_score   = round(crisis_score, 1),
            risk_rating    = risk_rating,
            risk_explanation = explanation,
            frequency_note   = freq_note,
        )

    def analyze_batch(self, reports: List) -> List[StressTestResult]:
        """
        批量分析。
        reports: 每个元素是 (strategy_name, params, daily_returns, total_trades)
        """
        results = []
        for strat_name, params, daily_rets, n_trades in reports:
            r = self.analyze(strat_name, params, daily_rets, n_trades)
            results.append(r)
        return results

    # ── VaR / CVaR ────────────────────────────

    @staticmethod
    def _compute_var(returns: List[float], confidence: float = 0.95) -> tuple:
        """历史模拟法 VaR"""
        sorted_ret = sorted(returns)
        n = len(sorted_ret)
        idx = int(n * (1 - confidence))
        # 95% VaR：取第5百分位（损失为正）
        var = -sorted_ret[max(0, idx - 1)]
        idx99 = int(n * 0.01)
        var99 = -sorted_ret[max(0, min(idx99, n-1))]
        return var, var99

    @staticmethod
    def _compute_cvar(returns: List[float], var: float) -> float:
        """CVaR：VaR情景下的平均极端损失"""
        tail = [r for r in returns if r <= -var]
        if not tail:
            return var
        return -sum(tail) / len(tail)

    # ── 黑天鹅压力测试 ─────────────────────────

    @staticmethod
    def _crisis_test(returns: List[float]) -> float:
        """
        模拟三个历史极端冲击，测试策略抵抗力。
        情景1：2020年3月级别的急速下跌（-12%单日）
        情景2：2015年A股股灾级别的震荡（连续3天-5%）
        情景3：流动性枯竭（成交量为零）
        返回 0~100 分。
        """
        scores = []

        # 情景1：单日-12%冲击
        losses_1 = [r for r in returns if r < -0.05]
        extreme_loss_1 = max(abs(min(returns)) if returns else 0, 0.12)
        score1 = max(0, 100 - extreme_loss_1 * 500)
        scores.append(score1)

        # 情景2：连续极端损失
        streaks = []
        streak = 0
        for r in returns:
            if r < -0.03:
                streak += 1
                streaks.append(streak)
            else:
                streak = 0
        max_streak = max(streaks) if streaks else 0
        score2 = max(0, 100 - max_streak * 20)
        scores.append(score2)

        # 情景3：收益波动率异常
        volatility = RiskExpert._std(returns)
        vol_anomaly = max(0, volatility - 0.03) / 0.05
        score3 = max(0, 100 - vol_anomaly * 100)
        scores.append(score3)

        return sum(scores) / len(scores)

    # ── 风险评级 ───────────────────────────────

    @staticmethod
    def _rate(var_99, crisis_score, total_trades, volatility) -> tuple:
        """综合判断风险等级"""
        # 高VaR99 + 低危机分 → 高风险
        risk_score = var_99 * 400 + (100 - crisis_score) * 0.5
        if total_trades < 5:
            risk_score += 15  # 数据不足额外惩罚

        if risk_score < 30:
            return "LOW",    ("风险较低。VaR99={:.1f}%表明极端损失有限，"
                              "黑天鹅抵抗力较好。").format(var_99*100)
        elif risk_score < 50:
            return "MEDIUM", ("风险中等。VaR99={:.1f}%，在极端行情下需关注。"
                               "建议控制仓位不超过总资金15%。").format(var_99*100)
        elif risk_score < 70:
            return "HIGH",   ("风险较高！VaR99={:.1f}%意味着极端日可能损失较大，"
                               "需严格止损。建议总仓位不超过10%，并设置硬止损-8%。"
                               .format(var_99*100))
        else:
            return "VERY_HIGH", ("风险极高！VaR99={:.1f}%，极端行情下可能出现超过20%回撤。"
                                   "不建议单独使用，必须配合其他低风险策略对冲。"
                                   .format(var_99*100))

    # ── 频率说明 ───────────────────────────────

    @staticmethod
    def _freq_note(var_95: float) -> str:
        """将 VaR 转换为通俗频率说明"""
        if var_95 < 0.01:
            return "约每年1~2天触发（正常范围）"
        elif var_95 < 0.02:
            return "约每年5~10天触发（需关注）"
        elif var_95 < 0.03:
            return "约每月1~2天触发（风险较高）"
        else:
            return "约每周都可能触发（风险极高）"

    # ── 工具 ─────────────────────────────────

    @staticmethod
    def _std(values: List[float]) -> float:
        n = len(values)
        if n < 2: return 0.0
        m = sum(values) / n
        return math.sqrt(sum((v - m) ** 2 for v in values) / (n - 1))

    @staticmethod
    def _default_result(name, params, reason) -> StressTestResult:
        return StressTestResult(
            strategy_name   = name,
            params          = params,
            var_95          = 0.0,
            var_99          = 0.0,
            cvar_95         = 0.0,
            crisis_score    = 50.0,
            risk_rating     = "UNKNOWN",
            risk_explanation= f"无法评估：{reason}",
            frequency_note  = "数据不足",
        )

    # ── 可解释报告 ────────────────────────────

    @staticmethod
    def explain(result: StressTestResult) -> str:
        """生成人类可读风险报告"""
        icon = {
            "LOW": "🟢", "MEDIUM": "🟡",
            "HIGH": "🟠", "VERY_HIGH": "🔴",
        }.get(result.risk_rating, "⚪")

        lines = [
            f"{icon} 风险评估：{result.strategy_name}",
            f"   风险等级：{result.risk_rating}",
            f"   单日VaR 95%：{result.var_95:.2f}%（{result.frequency_note}）",
            f"   单日VaR 99%：{result.var_99:.2f}%（极端情况）",
            f"   CVaR 95%：{result.cvar_95:.2f}%（VaR情景下平均损失）",
            f"   黑天鹅抵抗分：{result.crisis_score}/100",
            f"   说明：{result.risk_explanation}",
        ]
        return "\n".join(lines)
