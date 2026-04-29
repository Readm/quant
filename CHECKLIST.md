# Pre-Commit Verification Checklist

> 此文件是审计日志。每次提交前必须更新，pre-commit hook 强制检查。

## Last Verification: 2026-04-29 18:26 UTC

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

### 检查历史
| 时间 | 检查者 | 结果 | 变更描述 |
|------|--------|:----:|---------|
| 2026-04-29 18:26 UTC | Hermes | ✅ PASS | v5.9 trade_return 修复：使用真实成本基准而非 total_cash |
| 2026-04-26 22:40 UTC | Hermes | ✅ PASS | evaluator.py 3项修复(PBO/OOS/反垄断) |
| 2026-04-27 00:28 UTC | Hermes | ✅ PASS | 策略逻辑组合空间扩展 v5.0 (Phase 1-5) |
| 2026-04-27 10:40 UTC | Hermes | ✅ PASS | Dashboard 轻量化: fetch 加载 + SVG 预渲染 |
| 2026-04-27 14:30 UTC | Hermes | ✅ PASS | 移除旧版遗留文件 (−9.2MB + stale .mmd) |
