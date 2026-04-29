# Bug Note #0427 — InstrumentedOrchestrator 读取 RoundReportFake 误用属性

## 现象
Dashboard 回测曲线区域显示"本轮无通过策略（全部淘汰）"，但元专家评估显示已接受策略（如6个），"通过评估"计数器也为6。

## 根因
`InstrumentedOrchestrator.run()` (`scripts/run_iteration.py:151-166`) 使用 `getattr(rp, "trend_evals", [])` 和 `getattr(rp, "mr_evals", [])` 获取策略列表，但 v5 重构后 `_run_llm_track` (`experts/orchestrator.py:1081`) 仅设置 `rp.all_evals` 和 `rp.all_reports`。

同理，`rp.trend_reports` 和 `rp.mr_reports` 也未被设置，导致 equity_curve 数据为空。

结果：
- `t_evals + mr_evals` 恒空 → `strategies` 列表为空
- `t_reports + mr_reports` 恒空 → `dr_map` 为空 → `equity_curve` 为空
- Dashboard IterationView 过滤 `decision !== 'REJECT' && equity_curve.length > 0` → 无可见策略 → 显示"本轮无通过策略"

## 历史
自 `1c88a2e` (2026-03-30) 引入 `InstrumentedOrchestrator` 以来，`trend_evals`/`mr_evals` 从未被设置在 `RoundReportFake` 上。但此前的数据文件是通过 `orchestrator.run()` → `generate_final_report()` → `save_report()` 直接生成的（不含 `selected` 和 `equity_curve` 字段），手动迁移到 `dashboard/public/data/iterations/` 后得以前台显示策略列表，但 `selected` 始终为 false。

## 修复
`scripts/run_iteration.py`:
- `t_evals + mr_evals` → `all_evals`
- `t_reports + mr_reports` → `all_reports`

## 影响范围
- 新生成的迭代 JSON 文件会正确填充 `selected` 和 `equity_curve`
- 旧文件需要重新生成或手动修复

## 冒烟测试
`scripts/test_bug_orchestrator_evals.py` 验证：
1. 老代码路径（t_evals + mr_evals）产生空策略列表
2. 修复后代码正确填充策略、selected 和 equity_curve
