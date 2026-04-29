# Pre-Commit Verification Checklist

> 此文件是审计日志。每次提交前必须更新，pre-commit hook 强制检查。

## Last Verification: 2026-04-29 16:06 UTC

---

### 1. v5.8 — 修复Alpha缩放扁平化 + 权重调整
- [x] evaluator.py: alpha_scaled = alpha*5 → alpha*1 (线性缩放, 消除>20%后封顶问题)
- [x] evaluator.py: 权重 Sortino 0.22→0.26, Alpha 0.24→0.18
- [x] 权重总和 = 1.0 已验证
- [x] 冒烟测试: 导入evaluator并通过权重和检查
- [x] 20轮全A股回测完成(13轮收敛)
- [x] Dashboard数据注入: index.json + 新iter JSON
- [x] Vite build 通过（2.79s）
- [x] validate_dashboard.py 通过

### 2. v5.9 — 修复 trade_return 计算使用真实成本基准
- [x] backtest/engine.py:815 修复 (risk overlay sell)
- [x] backtest/engine.py:955-959 修复 (regular rebalance sell)
- [x] 旧逻辑: net/initial_cash - 1/N → 即使-50%亏损也显示正收益
- [x] 新逻辑: (net - cost_basis) / cost_basis → 正确反映盈亏
- [x] 50%亏损场景验证: old=+0.2493, new=-0.5010
- [x] 语法检查通过
- [x] smoke_test.py 通过
- [x] validate_dashboard.py 通过
- [x] Vite build 通过

### 3. v5.9b — 修复后全量回测验证
- [x] 10轮全A股回测完成（10轮收敛）
- [x] 真实胜率确认: 45%-64%（vs 修复前100%）
- [x] Dashboard数据注入: 因子组合v5.9_20260429_2118
- [x] Vite build 通过（2.98s）
- [x] validate_dashboard.py 通过

### 4. v5.10 — 修复 Sharpe 公式：CAGR/σ → mean(r)/σ×√252
- [x] 标准定义: Sharpe = mean(rᵢ) / σ(rᵢ) × √252
- [x] 旧公式 CAGR/σ 在正收益序列下虚高 Sharpe（11.8→6.1 验证）
- [x] smoke_test.py 通过
- [x] ann(CAGR) 保留用于 Calmar 计算不受影响

### 5. v5.11 — n_stocks 2→10 + 启用反垄断评分
- [x] B: n_stocks 范围从 [2,5] 扩大到 [2,10]（orchestrator/llm_prompts/meta_monitor ×4 处修改）
- [x] C: _monopoly_suppression 从死代码变为实际调用（evaluator.py）
- [x] 反垄断逻辑: Top-3 全是趋势时，均值回归策略 +3 分
- [x] diversity_bonus 保留（最高+8），与反垄断叠加使用
- [x] smoke_test.py 通过

### 6. v5.12 — v5.10+v5.11 全量回测验证
- [x] 20 轮全 A 股回测完成（20轮收敛，最高分 89.5→96.6 ↑7.1）
- [x] #1 RSI均值回归 — 反垄断生效，均值回归策略居首
- [x] 新 Sharpe 2.8~3.3（旧 7+），合理
- [x] n_stocks N5~N9 出现，分散化有效
- [x] Dashboard 验证通过 + Vite build 通过

### 7. v5.13 — 添加执行损耗(execution_shortfall)跟踪
- [x] 每次买入时记录: 信号价(t日收盘) → 执行价(t+1日收盘) 的差值
- [x] BacktestReport 新增 execution_shortfall_median/mean 字段
- [x] EvalResult 新增对应字段
- [x] smoke_test.py 通过

### 8. v5.14 — 系统设计总结角色 + Dashboard tooltips
- [x] 新建 role_system_designer.md SOP（设计日志维护职责）
- [x] 新建 DESIGN_RECORD.md，记录 7 个设计决策
- [x] 更新 team_architecture.md（Mermaid图+角色表+工作流）
- [x] IterationView.tsx 表头添加 hover tooltip（9 个指标解释）
- [x] smoke_test.py + TypeScript 编译通过

### 9. v5.15 — 修复 Dashboard 渲染错误 + E2E 冒烟测试
- [x] 修复: IterationView 策略 equity_curve 缺失时崩溃（加 `|| []` 防御）
- [x] 修复: daily_returns_to_equity curve[0] 双包装 bug
- [x] 修复: validate_dashboard.py 路径错误 + 兼容旧格式
- [x] 增强: validate_dashboard.py 同时检查 src/data/ 和 public/data/
- [x] 增强: run_iteration.py 写入后自动同步到 public/data/
- [x] 新增: scripts/smoke_dashboard_e2e.mjs — Playwright 浏览器渲染冒烟
- [x] 集成: smoke_test.py [7] — Dashboard E2E 渲染测试
- [x] Vite build 通过
- [x] E2E 渲染测试通过（7/7 项）

### 检查历史
| 时间 | 检查者 | 结果 | 变更描述 |
|------|--------|:----:|---------|
| 2026-04-29 18:26 UTC | Hermes | ✅ PASS | v5.9 trade_return 修复：使用真实成本基准而非 total_cash |
| 2026-04-26 22:40 UTC | Hermes | ✅ PASS | evaluator.py 3项修复(PBO/OOS/反垄断) |
| 2026-04-27 00:28 UTC | Hermes | ✅ PASS | 策略逻辑组合空间扩展 v5.0 (Phase 1-5) |
| 2026-04-27 10:40 UTC | Hermes | ✅ PASS | Dashboard 轻量化: fetch 加载 + SVG 预渲染 |
| 2026-04-27 14:30 UTC | Hermes | ✅ PASS | 移除旧版遗留文件 (−9.2MB + stale .mmd) |
