"""
coordinator.py — 双专家协调器（纯Python版）
"""

import json, random, math, copy
from datetime import datetime
from experts.expert1_generator import (
    BacktestReport, generate_candidates, run_iteration, TEMPLATES
)
from experts.evaluator import Evaluator


class Coordinator:
    def __init__(self, symbols_data, max_rounds=2, top_n=3):
        """
        symbols_data: list of (symbol_name, closes_list, highs_list, lows_list)
        """
        self.symbols_data = symbols_data
        self.max_rounds   = max_rounds
        self.top_n        = top_n
        self.feedback     = []
        self.global_top   = []
        self.rounds_log   = []

    def run(self):
        print("=" * 65)
        print("  双专家量化策略迭代系统 v2.0（纯Python）")
        print("=" * 65)
        print(f"\n标的数量: {len(self.symbols_data)}")
        for s, _, _, _ in self.symbols_data:
            print(f"  - {s}（{len(self.symbols_data[0][1])}个交易日）")

        for rnd in range(1, self.max_rounds + 1):
            print(f"\n{'━' * 65}")
            print(f"  ▶ 第 {rnd} 轮迭代{'（有反馈优化）' if self.feedback and rnd > 1 else ''}")
            print(f"{'━' * 65}")

            # Expert1
            iter_result = run_iteration(self.symbols_data, feedback=self.feedback if rnd > 1 else None)
            iter_result["round"] = rnd

            # Expert2
            eval_result = run_evaluation(iter_result)
            eval_result["round"] = rnd
            print_evaluation_report(eval_result)

            # 更新全局Top
            top_reports = [e.original for e in eval_result.get("top3", [])]
            if not self.global_top:
                self.global_top = top_reports
            else:
                combined = self.global_top + top_reports
                evaled = evaluate_batch(combined)
                evaled.sort(key=lambda x: x.composite_score, reverse=True)
                self.global_top = [e.original for e in evaled[:self.top_n]]

            self.rounds_log.append({
                "round"   : rnd,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "top3"    : [
                    {"name": e.original.strategy_name,
                     "params": e.original.params,
                     "score": e.composite_score,
                     "return": e.original.total_return,
                     "sharpe": e.original.sharpe_ratio,
                     "drawdown": e.original.max_drawdown_pct,
                     "winrate": e.original.win_rate,
                     "pf": e.original.profit_factor,
                     "decision": e.decision}
                    for e in eval_result.get("top3", [])
                ],
                "feedback_used": len(self.feedback),
            })

            # 更新反馈
            self.feedback = eval_result.get("feedback", [])

        return self._final_report()

    def _final_report(self) -> dict:
        # 全局Top重新评估
        evaled = evaluate_batch(self.global_top)
        evaled.sort(key=lambda x: x.composite_score, reverse=True)

        final_strats = []
        for i, e in enumerate(evaled):
            r = e.original
            final_strats.append({
                "rank"              : i + 1,
                "name"              : r.strategy_name,
                "tags"              : r.tags,
                "params"            : r.params,
                "composite_score"   : e.composite_score,
                "total_return"      : r.total_return,
                "annualized_return" : r.annualized_return,
                "sharpe_ratio"      : r.sharpe_ratio,
                "max_drawdown_pct"  : r.max_drawdown_pct,
                "win_rate"          : r.win_rate,
                "profit_factor"     : r.profit_factor,
                "calmar_ratio"      : r.calmar_ratio,
                "sortino_ratio"     : r.sortino_ratio,
                "total_trades"      : r.total_trades,
                "avg_holding_days"  : r.avg_holding_days,
                "decision"          : e.decision,
                "feedback"          : e.feedback_for_expert1,
            })

        # 收敛分析
        convergence = {}
        if len(self.rounds_log) >= 2:
            r1 = self.rounds_log[0]["top3"][0]["score"] if self.rounds_log[0]["top3"] else 0
            r2 = self.rounds_log[-1]["top3"][0]["score"]  if self.rounds_log[-1]["top3"] else 0
            delta = r2 - r1
            convergence = {
                "round1_top_score": r1,
                "final_top_score" : r2,
                "delta"           : round(delta, 1),
                "direction"        : "↑改善" if delta > 2 else ("↓下降" if delta < -2 else "→平稳"),
                "interpretation"  : (
                    "策略质量显著提升，评估专家反馈有效。"
                    if delta > 5 else
                    "策略小幅改善，可继续迭代。"
                    if delta > 0 else
                    "已收敛，建议增加策略多样性。"
                )
            }

        report = {
            "generated_at"       : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_rounds"        : len(self.rounds_log),
            "symbols"            : [s[0] for s in self.symbols_data],
            "rounds_log"         : self.rounds_log,
            "final_top_strategies": final_strats,
            "convergence_analysis": convergence,
            "investment_suggestion": _make_suggestion(evaled),
        }
        return report


def _make_suggestion(evaled):
    if not evaled:
        return {"best_score": 0, "suggestions": []}
    best = evaled[0]
    r = best.original
    sg = []
    if best.composite_score >= 70 and r.max_drawdown_pct < 15:
        sg.append({
            "risk_level"   : "进取型",
            "strategy"     : r.strategy_name,
            "params"       : {k: v for k, v in r.params.items() if k != "market"},
            "expected_return": f"约{r.total_return * 2:.0f}%（年化）",
            "max_loss_risk" : f"约{r.max_drawdown_pct:.0f}%",
            "sharpe"        : r.sharpe_ratio,
            "action"        : "可考虑实盘小资金验证（5~10%）",
        })
    if best.composite_score >= 55:
        sg.append({
            "risk_level"   : "稳健型",
            "strategy"     : r.strategy_name,
            "params"       : {k: v for k, v in r.params.items() if k != "market"},
            "expected_return": f"约{r.annualized_return:.0f}%（年化）",
            "max_loss_risk" : f"约{r.max_drawdown_pct:.0f}%",
            "action"        : "建议先做模拟盘验证3个月",
        })
    return {"best_score": best.composite_score, "suggestions": sg}
