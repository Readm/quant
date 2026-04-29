"""
test_combo_engine.py — 因子组合引擎单元测试

覆盖:
  1. 候选生成随机性 — 所有 8 种组合模式都被随机到
  2. 候选生成格式 — 每种模式的 template_key / factors 格式正确
  3. 打分行为 — AND/OR/weighted/rank/product/hierarchical/conditional 各场景
"""

import sys, os, random, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backtest.engine import (
    _combo_score_and, _combo_score_or, _combo_score_weighted,
    _combo_score_product, _combo_score_rank,
    _combo_score_hierarchical, _combo_score_conditional,
    _SCORE_REGISTRY,
)
from experts.specialists.factor_combo_expert import FactorComboExpert

# ── Mock data for scoring tests ────────────────────────────────────
_CLOSES = [100.0 + i for i in range(200)]  # steady uptrend
_DATA = {"volumes": [1.0] * 200, "highs": [v + 1 for v in _CLOSES],
         "lows": [v - 1 for v in _CLOSES]}
_INDICATORS = {}


# ═══════════════════════════════════════════════════════════════════
# 测试 1: 候选生成随机性
# ═══════════════════════════════════════════════════════════════════

def test_all_modes_are_generated():
    """Run 500 candidates, verify all 8 combo modes appear."""
    fce = FactorComboExpert(seed=42)
    cands = fce.generate_candidates(500)

    modes_seen = set(c["combo_mode"] for c in cands)
    expected = {"single", "and", "or", "weighted", "rank", "product", "hierarchical", "conditional"}
    missing = expected - modes_seen
    assert not missing, f"Missing modes: {missing}"


def test_single_mode_format():
    """Single mode: normal template_key, no params.factors."""
    fce = FactorComboExpert(seed=42)
    # Force single by generating many candidates then filtering
    cands = fce.generate_candidates(500)
    singles = [c for c in cands if c["combo_mode"] == "single"]
    assert len(singles) > 0, "No single-mode candidates generated"

    for c in singles:
        assert not c["template_key"].startswith("_combo_"), \
            f"Single mode should not use _combo_ prefix, got {c['template_key']}"
        assert "factors" not in c["params"] or c["params"]["factors"] == [], \
            "Single mode should not have params.factors"


def test_combo_mode_format():
    """Multi-factor modes: _combo_<mode> template_key, params.factors populated."""
    fce = FactorComboExpert(seed=42)
    cands = fce.generate_candidates(500)

    multi = [c for c in cands if c["combo_mode"] != "single"]
    assert len(multi) > 0, "No multi-factor candidates generated"

    for c in multi:
        assert c["template_key"].startswith("_combo_"), \
            f"Multi-factor mode should use _combo_ prefix, got {c['template_key']}"
        assert "factors" in c["params"], "Multi-factor mode must have params.factors"

        factors = c["params"]["factors"]
        assert len(factors) >= 2, f"Multi-factor mode needs ≥2 factors, got {len(factors)}"

        # Each factor entry must have 'key'
        for f in factors:
            assert "key" in f, f"Factor entry missing 'key': {f}"


def test_weighted_mode_weights():
    """Weighted mode weights should sum to approximately 1.0."""
    fce = FactorComboExpert(seed=42)
    cands = fce.generate_candidates(500)
    weighted = [c for c in cands if c["combo_mode"] == "weighted"]
    assert len(weighted) > 0, "No weighted candidates generated"

    for c in weighted:
        factors = c["params"].get("factors", [])
        if len(factors) < 2:
            continue
        total_w = sum(float(f.get("weight", 1.0)) for f in factors)
        assert abs(total_w - 1.0) < 0.01, \
            f"Weighted mode weights should sum to 1.0, got {total_w}"


def test_hierarchical_mode_has_layer_split():
    """Hierarchical mode: params must have layer_split."""
    fce = FactorComboExpert(seed=42)
    cands = fce.generate_candidates(500)
    hier = [c for c in cands if c["combo_mode"] == "hierarchical"]
    assert len(hier) > 0, "No hierarchical candidates generated"

    for c in hier:
        assert "layer_split" in c["params"], \
            "Hierarchical mode must have layer_split in params"


def test_conditional_mode_has_condition():
    """Conditional mode: params must have condition config."""
    fce = FactorComboExpert(seed=42)
    cands = fce.generate_candidates(500)
    cond = [c for c in cands if c["combo_mode"] == "conditional"]
    assert len(cond) > 0, "No conditional candidates generated"

    for c in cond:
        assert "condition" in c["params"], \
            "Conditional mode must have condition in params"
        assert "key" in c["params"]["condition"], \
            "Condition must specify a condition factor key"


def test_low_prob_modes_appear():
    """Low probability modes (5% each) must appear in a large enough sample."""
    fce = FactorComboExpert(seed=42)
    cands = fce.generate_candidates(1000)

    low_prob_modes = {"rank", "product", "hierarchical", "conditional"}
    counts = {}
    for c in cands:
        m = c["combo_mode"]
        counts[m] = counts.get(m, 0) + 1

    for mode in low_prob_modes:
        assert counts.get(mode, 0) >= 5, \
            f"Mode '{mode}' only appeared {counts.get(mode, 0)} times in 1000 candidates (expected ~50)"


# ═══════════════════════════════════════════════════════════════════
# 测试 2: 组合打分函数
# ═══════════════════════════════════════════════════════════════════

def test_and_mode_both_positive():
    """AND: both factors positive → positive score."""
    params = {
        "factors": [
            {"key": "momentum", "lookback": 3, "threshold": 0.001},
            {"key": "ma_cross", "fast": 5, "slow": 15},
        ]
    }
    t = 30
    score = _combo_score_and(_CLOSES, _DATA, _INDICATORS, params, t)
    assert score > 0, f"AND mode should be positive in uptrend, got {score}"


def test_and_mode_one_negative():
    """AND: one factor negative → zero.
    Use a factor that generates negative signal (ma_cross with fast > slow).
    """
    params = {
        "factors": [
            {"key": "momentum", "lookback": 3, "threshold": 0.001},  # positive
            {"key": "ma_cross", "fast": 80, "slow": 10},  # negative (fast > slow in uptrend)
        ]
    }
    t = 30
    score = _combo_score_and(_CLOSES, _DATA, _INDICATORS, params, t)
    assert score == 0, f"AND should be 0 when factor condition blocks, got {score}"


def test_or_mode():
    """OR: at least one positive → non-zero score."""
    params = {
        "factors": [
            {"key": "gap_break", "min_gap_pct": 99.0, "lookback": 3},  # =0, won't trigger
            {"key": "ma_cross", "fast": 5, "slow": 15},
        ]
    }
    t = 30
    score = _combo_score_or(_CLOSES, _DATA, _INDICATORS, params, t)
    assert score > 0, f"OR should be positive when any factor fires, got {score}"


def test_or_mode_all_negative():
    """OR: all negative → zero or negative score."""
    params = {
        "factors": [
            {"key": "gap_break", "min_gap_pct": 99.0, "lookback": 3},  # =0
            {"key": "ma_cross", "fast": 80, "slow": 10},  # negative (fast > slow)
        ]
    }
    t = 30
    score = _combo_score_or(_CLOSES, _DATA, _INDICATORS, params, t)
    assert score <= 0, f"OR should be ≤0 when both factors are blocked, got {score}"


def test_weighted_mode():
    """Weighted: correct weight distribution."""
    params = {
        "factors": [
            {"key": "momentum", "lookback": 3, "threshold": 0.001, "weight": 0.7},
            {"key": "ma_cross", "fast": 5, "slow": 15, "weight": 0.3},
        ]
    }
    t = 30
    score = _combo_score_weighted(_CLOSES, _DATA, _INDICATORS, params, t)
    assert score > 0, f"Weighted score should be positive in uptrend, got {score}"
    assert -100 < score < 100, f"Weighted score in reasonable range, got {score}"


def test_product_mode():
    """Product: both factors positive → positive result."""
    params = {
        "factors": [
            {"key": "momentum", "lookback": 3, "threshold": 0.001},
            {"key": "ma_cross", "fast": 5, "slow": 15},
        ]
    }
    t = 30
    score = _combo_score_product(_CLOSES, _DATA, _INDICATORS, params, t)
    assert score > 0, f"Product should be positive with both factors positive, got {score}"


def test_product_mode_one_zero():
    """Product: one factor near zero → result near zero."""
    params = {
        "factors": [
            {"key": "gap_break", "min_gap_pct": 99.0, "lookback": 3},  # =0
            {"key": "ma_cross", "fast": 5, "slow": 15},
        ]
    }
    t = 30
    score = _combo_score_product(_CLOSES, _DATA, _INDICATORS, params, t)
    assert score == 0, f"Product should be 0 when any factor is ~0, got {score}"


def test_hierarchical_layer1_passes():
    """Hierarchical: layer1 passes → layer2 score returned."""
    params = {
        "factors": [
            {"key": "momentum", "lookback": 3, "threshold": 0.001},  # layer1: momentum positive
            {"key": "ma_cross", "fast": 5, "slow": 15},  # layer2: ma_cross score
        ],
        "layer_split": 1,
    }
    t = 30
    score = _combo_score_hierarchical(_CLOSES, _DATA, _INDICATORS, params, t)
    assert score > 0, f"Hierarchical should be positive when layer1 passes, got {score}"


def test_hierarchical_layer1_fails():
    """Hierarchical: layer1 fails → zero."""
    params = {
        "factors": [
            {"key": "gap_break", "min_gap_pct": 99.0, "lookback": 3},  # layer1: won't pass (0)
            {"key": "ma_cross", "fast": 5, "slow": 15},  # layer2: would score
        ],
        "layer_split": 1,
    }
    t = 30
    score = _combo_score_hierarchical(_CLOSES, _DATA, _INDICATORS, params, t)
    assert score == 0, f"Hierarchical should be 0 when layer1 fails, got {score}"


def test_conditional_mode():
    """Conditional: different weights applied based on condition factor."""
    params = {
        "factors": [
            {"key": "momentum", "lookback": 3, "threshold": 0.001,
             "weight_trend": 0.7, "weight_sideways": 0.3},
            {"key": "ma_cross", "fast": 5, "slow": 15,
             "weight_trend": 0.3, "weight_sideways": 0.7},
        ],
        "condition": {
            "key": "adx_trend", "adx_thr": 25,
            "trend_threshold": 25,
        }
    }
    t = 30
    score = _combo_score_conditional(_CLOSES, _DATA, _INDICATORS, params, t)
    assert score > 0, f"Conditional should be positive in uptrend, got {score}"


def test_rank_mode():
    """Rank: normalization reduces scale differences."""
    params = {
        "factors": [
            {"key": "momentum", "lookback": 3, "threshold": 0.001},
            {"key": "ma_cross", "fast": 5, "slow": 15},
        ]
    }
    t = 30
    score = _combo_score_rank(_CLOSES, _DATA, _INDICATORS, params, t)
    assert -100 <= score <= 100, f"Rank score out of range [-100, 100], got {score}"


def test_registry_has_all_combos():
    """All 7 combo functions registered in _SCORE_REGISTRY."""
    expected = ["_combo_and", "_combo_or", "_combo_weighted",
                "_combo_rank", "_combo_product",
                "_combo_hierarchical", "_combo_conditional"]
    for key in expected:
        assert key in _SCORE_REGISTRY, f"Missing from registry: {key}"
        assert callable(_SCORE_REGISTRY[key]), f"Not callable: {key}"


# ═══════════════════════════════════════════════════════════════════
# 测试 3: 边界条件
# ═══════════════════════════════════════════════════════════════════

def test_empty_factors():
    """All combo modes handle empty factors gracefully."""
    params = {"factors": []}

    for fn_name in ["_combo_score_and", "_combo_score_or", "_combo_score_weighted",
                    "_combo_score_rank", "_combo_score_product"]:
        fn = globals()[fn_name]
        score = fn(_CLOSES, _DATA, _INDICATORS, params, 50)
        assert score == 0, f"{fn_name} should return 0 for empty factors, got {score}"


def test_nonexistent_factor_key():
    """Combo modes handle missing factor keys gracefully."""
    params = {
        "factors": [
            {"key": "nonexistent_factor"},
            {"key": "momentum", "lookback": 3, "threshold": 0.001},
        ]
    }
    # AND with a nonexistent factor
    score = _combo_score_and(_CLOSES, _DATA, _INDICATORS, params, 30)
    # Should work with the one valid factor
    assert score > 0, f"AND should skip unknown factors, got {score}"


if __name__ == "__main__":
    import inspect
    funcs = [v for v in globals().values()
             if callable(v) and v.__name__.startswith("test_")]
    passed, failed = 0, 0
    for fn in sorted(funcs, key=lambda f: f.__name__):
        try:
            fn()
            print(f"  ✅ {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{'='*40}\n{passed} passed / {failed} failed / {passed+failed} total")
    sys.exit(1 if failed > 0 else 0)
