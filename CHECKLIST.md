# Pre-Commit Verification Checklist

> 此文件是审计日志。每次提交前必须更新，pre-commit hook 强制检查。

## Last Verification: 2026-04-26 15:00 UTC

---

### 1. 架构检查
- [x] 模块依赖图已生成 (gen_architecture.py, 55节点)
- [x] 无循环导入
- [x] 边排序已稳定（JSON 输出不再有噪音 diff）

### 2. 数据管线完整性
- [x] Alpha/score/sharpe 字段链路完整
- [x] validate_dashboard.py 通过

### 3. 冒烟测试
- [x] smoke_test.py 全部通过
- [x] TypeScript 编译通过 (npx tsc --noEmit)

### 4. 代码审查
- [x] 安全扫描无密钥泄露
- [x] 无静默异常捕获 / LLM降级
- [x] 修 IterationView 静默 loading bug：id 不匹配时显示错误提示而非永远"加载中..."
- [x] gen_architecture.py 边排序稳定：JSON 输出按 (source, target) 排序

---

## 检查历史

2026-04-26 15:00 | Hermes | PASS | gen_architecture.py 边排序稳定 + IterationView bug 修复
2026-04-26 14:00 | Hermes | PASS | 修 IterationView 静默 loading bug：id 不匹配时不报错无限loading
2026-04-26 08:30 | Hermes | PASS | 系统架构 Tab + 数据迁移
2026-04-26 08:10 | Hermes | PASS | 修复hook: 时间戳去重
2026-04-26 08:00 | Hermes | PASS | 初始化验证体系
