# Pre-Commit Verification Checklist

> 此文件是审计日志。每次提交前必须更新，pre-commit hook 强制检查。

## Last Verification: 2026-04-29 18:30 UTC

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

### 检查历史
| 时间 | 检查者 | 结果 | 变更描述 |
|------|--------|:----:|---------|
| 2026-04-26 22:40 UTC | Hermes | ✅ PASS | evaluator.py 3项修复(PBO/OOS/反垄断) |
| 2026-04-27 00:28 UTC | Hermes | ✅ PASS | 策略逻辑组合空间扩展 v5.0 (Phase 1-5) |
| 2026-04-27 10:40 UTC | Hermes | ✅ PASS | Dashboard 轻量化: fetch 加载 + SVG 预渲染 |
| 2026-04-27 14:30 UTC | Hermes | ✅ PASS | 移除旧版遗留文件 (−9.2MB + stale .mmd) |
