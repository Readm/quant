# Pre-Commit Verification Checklist

> 此文件是审计日志。每次提交前必须更新，pre-commit hook 强制检查。

## Last Verification: 2026-04-26 08:00 UTC

---

### 1. 架构检查
- [x] 模块依赖图已生成 (dashboard/src/data/architecture/deps.mmd)
- [x] 无循环导入
- [x] 模块边界无破坏
- [x] 架构图已放入 Dashboard「架构」Tab

### 2. 数据管线完整性
- [x] 全链路追踪: Evaluator → report_writer → converter → dashboard
- [x] Alpha 字段在结果 JSON 中存在
- [x] 字段名映射正确
- [x] validate_dashboard.py 通过

### 3. 冒烟测试
- [x] 管道导入验证通过 (Orchestrator + 38模板)
- [x] 结果 JSON 有效
- [x] Dashboard 数据格式验证通过
- [x] TypeScript 编译通过

### 4. 代码审查
- [x] 安全扫描无密钥泄露
- [x] 无静默异常捕获
- [x] LLM API 调用无降级逻辑
- [x] 新增: 冒烟测试脚本、架构图生成器、pre-commit hook、CHECKLIST.md

---

## 检查历史

2026-04-26 08:00 | Hermes | PASS | 初始化验证体系: smoke_test, pre-commit hook, gen_architecture, CHECKLIST.md
