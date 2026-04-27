# Pre-Commit Verification Checklist

> 此文件是审计日志。每次提交前必须更新，pre-commit hook 强制检查。

## Last Verification: 2026-04-27 14:30 UTC

---

### 1. 架构检查
- [x] 无循环导入
- [x] 本次变更范围：dashboard/ 纯前端（isolated）

### 2. Dashboard 轻量化
- [x] 迭代数据从 `import.meta.glob` 改为运行时 `fetch()` — 消除 464KB data chunk
- [x] Mermaid 图预渲染为 SVG，移除 mermaid 依赖 — 消除 40+ chunks (~1.1MB)
- [x] Vite build 通过（2.99s，原 7.92s → -62%）
- [x] 产物 JS 从 ~2.2MB 降至 ~792KB（-64%）
- [x] 迭代数据页正常访问（fetch 运行时加载）
- [x] 策略流程图正常显示（SVG 静态图片）

### 3. 清理旧版遗留文件
- [x] 删除 9.2MB `src/data/iteration_log.json`（不再被引用）
- [x] 删除 `src/data/strategy/*.mmd`（SVG已预渲染至 `public/data/strategy/`）
- [x] 删除 `src/data/architecture/deps.mmd`（仅保留 `deps.json`）
- [x] git push 触发 Actions 重新部署

### 检查历史
| 时间 | 检查者 | 结果 | 变更描述 |
|------|--------|:----:|---------|
| 2026-04-26 22:40 UTC | Hermes | ✅ PASS | evaluator.py 3项修复(PBO/OOS/反垄断) |
| 2026-04-27 00:28 UTC | Hermes | ✅ PASS | 策略逻辑组合空间扩展 v5.0 (Phase 1-5) |
| 2026-04-27 10:40 UTC | Hermes | ✅ PASS | Dashboard 轻量化: fetch 加载 + SVG 预渲染 |
| 2026-04-27 14:30 UTC | Hermes | ✅ PASS | 移除旧版遗留文件 (−9.2MB + stale .mmd) |
