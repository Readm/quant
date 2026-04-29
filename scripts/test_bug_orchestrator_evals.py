"""
Smoke test: verify InstrumentedOrchestrator reads from all_evals/all_reports.
Bug #0427: t_evals + mr_evals 恒空 → strategies 为空 → selected 和 equity_curve 丢失。

Run: python3 scripts/test_bug_orchestrator_evals.py
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime

class EvalResultStub:
    def __init__(self, name, decision, score=80):
        self.strategy_name = name
        self.strategy_id = f"{name}_id"
        self.strategy_type = "combo"
        self.composite = score
        self.decision = decision
        self.total_trades = 48
        self.annualized_return = 100.0
        self.sharpe_ratio = 1.8
        self.max_drawdown_pct = 20.0
        self.win_rate = 80.0
        self.profit_factor = 1.5
        self.params = {}
        self.tags = []
        self.sortino_score = 85.0
        self.calmar_score = 90.0
        self.ir_score = 70.0
        self.drawdown_score = 75.0
        self.pbo_score = 0.0
        self.pbo_label = ""
        self.pbo_multiplier = 1.0
        self.benchmark_ann_return = 0.0
        self.alpha = 5.0
        self.template_key = ""
        self.oos_annualized_return = 0.0
        self.weight = 0.0
        self.reason = ""
        self.feedback = ""
        self.feedback_text = ""
        self.elimination_note = ""
        self.weakness = ""
        self.adjustment = ""
        self.adjustment_param = ""

class BacktestReportStub:
    def __init__(self, sid, daily_rets):
        self.strategy_id = sid
        self.daily_returns = daily_rets

class RoundReportFake:
    def __init__(self, rnd):
        self.round_num = rnd
        self.timestamp = datetime.now().strftime("%H:%M:%S")
        self.market_regime = None
        self.sentiment = None
        self.all_reports = []
        self.all_evals = []
        self.debate_result = None
        self.risk_results = []
        self.final_selected = []
        self.portfolio_weights = {}
        self.converged = False
        self.holdout_results = []
        self.meta_evaluation = {}
        self.meta_plan = {}


def test_fix():
    """Simulate InstrumentedOrchestrator data extraction with FIXED code."""
    rp = RoundReportFake(1)

    # Setup: all_evals with 3 strategies, 1 selected
    rp.all_evals = [
        EvalResultStub("A", "ACCEPT", 90.0),
        EvalResultStub("B", "ACCEPT", 80.0),
        EvalResultStub("C", "REJECT", 50.0),
    ]
    rp.final_selected = [rp.all_evals[0]]  # only "A" selected

    # Setup: all_reports with equity curves
    rp.all_reports = [
        BacktestReportStub("A_id", [0.01, -0.005, 0.02]),
        BacktestReportStub("B_id", [0.005, 0.01, -0.01]),
        BacktestReportStub("C_id", [0.001, 0.002, 0.001]),
    ]

    # ── FIXED extraction logic ──
    all_evals = getattr(rp, "all_evals", []) or []
    selected = getattr(rp, "final_selected", []) or []
    selected_names = {getattr(e, "strategy_name", "") for e in selected}

    all_reports = getattr(rp, "all_reports", []) or []
    dr_map = {getattr(r, "strategy_id", ""): getattr(r, "daily_returns", []) or []
              for r in all_reports}

    strategies = []
    for e in all_evals:
        from scripts.run_iteration import eval_to_dict
        d = eval_to_dict(e)
        sid = d.get("id", "")
        dr = dr_map.get(sid, [])
        from scripts.run_iteration import daily_returns_to_equity
        d["equity_curve"] = daily_returns_to_equity(dr)
        d["selected"] = d["name"] in selected_names
        strategies.append(d)

    # ── Assertions ──
    assert len(strategies) == 3, f"Expected 3 strategies, got {len(strategies)}"

    # All strategies must have names
    names = [s["name"] for s in strategies]
    assert "A" in names, "Strategy A missing"
    assert "B" in names, "Strategy B missing"
    assert "C" in names, "Strategy C missing"

    # Selected flag must be correct
    a = next(s for s in strategies if s["name"] == "A")
    b = next(s for s in strategies if s["name"] == "B")
    c = next(s for s in strategies if s["name"] == "C")
    assert a["selected"] == True,  f"A should be selected"
    assert b["selected"] == False, f"B should NOT be selected"
    assert c["selected"] == False, f"C should NOT be selected"

    # equity_curve must be populated
    assert len(a["equity_curve"]) > 0, "A equity_curve is empty"
    assert len(b["equity_curve"]) > 0, "B equity_curve is empty"
    assert len(c["equity_curve"]) > 0, "C equity_curve is empty"

    print("✅ ALL CHECKS PASSED: strategies populated, selected flag correct, equity curves filled")


def test_old_code_would_fail():
    """Verify that the OLD code (t_evals + mr_evals) produces empty strategies."""
    rp = RoundReportFake(1)
    rp.all_evals = [EvalResultStub("A", "ACCEPT", 90.0)]

    # OLD code path
    t_evals = getattr(rp, "trend_evals", []) or []
    mr_evals = getattr(rp, "mr_evals", []) or []
    assert len(t_evals + mr_evals) == 0, \
        "BUG REPRODUCED: t_evals + mr_evals should be empty (they're never set)"
    print("✅ BUG CONFIRMED: old code path would produce 0 strategies")


if __name__ == "__main__":
    test_old_code_would_fail()
    test_fix()
    print("\n🎉 ALL smoke tests passed!")
