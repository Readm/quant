# Change Plan: Expand Strategy Logic Combinatorial Space

## 需求
突破当前"单因子打分→排名→选股"的单一逻辑结构，让候选策略能组合因子、条件门控、多阶段筛选、风险控制和市场环境分支。

## 全局风险等级
- Phase 1-2: isolated
- Phase 3-4: data_format
- Phase 5: data_format (新增注册表 entry)

## 文件影响矩阵

| Phase | engine.py | orchestrator.py | 依赖顺序 |
|-------|-----------|-----------------|---------|
| 1 因子加权 | _score_composite + 注册 | 复合因子候选生成 | 可并行 |
| 2 门控 | _apply_gate + 集成 | 门控参数注入 | 可并行 |
| 3 两阶段 | _select_stocks 双阶段 | 两阶段候选参数 | 可并行 |
| 4 风险层 | _apply_risk_overlay + 集成 | 风险规则参数 | 可并行 |
| 5 市场分支 | _detect_regime + _score_regime_adaptive + 注册 | 分支参数注入 | 可并行 |

每个 Phase 的 engine.py 和 orchestrator.py 改动**不冲突**，可并行分派。

## 分派计划

### Backtest Engineer (engine.py)
- Phase 1: Add `_score_composite` function + register in `_SCORE_REGISTRY` as `"_composite"`
- Phase 2: Add `_apply_gate` function + integrate into `_compute_score_at` pipeline
- Phase 3: Refactor `_select_stocks` to support `"two_stage"` mode
- Phase 4: Add `_apply_risk_overlay` function + integrate into `_sim_range` rebalance loop
- Phase 5: Add `_detect_regime` + `_score_regime_adaptive` + register as `"_regime_adaptive"`

### Quant Strategy Engineer (orchestrator.py)
- Phase 1: Update `_generate_diverse_candidates` to generate 60% single / 30% dual / 10% triple factor composites
- Phase 2: 50% of candidates get a random gate config
- Phase 3: Some candidates get `"two_stage"` selection config
- Phase 4: Some candidates get risk_rules config
- Phase 5: Some candidates get regime_adaptive branches

## 自检条件 (each Phase)
1. ✅ `python3 -c "from backtest.engine import *; print('OK')"`
2. ✅ Small smoke test: 5 rounds with --days 200 --rounds 5
3. ✅ Generated candidates include new logic structures

## 数据链影响
- Phase 3 (two_stage) and Phase 4 (risk overlay) may add new fields to BacktestReport params
- No field name changes to existing BacktestReport fields
- Dashboard data format unchanged (no new report fields)
