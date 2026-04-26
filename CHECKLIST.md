# Pre-Commit Verification Checklist

> 此文件是审计日志。每次提交前必须更新，pre-commit hook 强制检查。

## Last Verification: 2026-04-26 08:30 UTC

---

### 1. 架构检查
- [x] 模块依赖图已生成 (gen_architecture.py, 55节点)
- [x] 无循环导入
- [x] 新增: ArchitectureView (ReactFlow 图 + 模块说明 + 数据源 + 因子矩阵)
- [x] 图表引用 gen_architecture.py 自动输出的 deps.json

### 2. 数据管线完整性
- [x] Alpha/score/sharpe 字段链路完整
- [x] validate_dashboard.py 通过

### 3. 冒烟测试
- [x] smoke_test.py 全部通过
- [x] TypeScript 编译通过 (npx tsc --noEmit)

### 4. 代码审查
- [x] 安全扫描无密钥泄露
- [x] 无静默异常捕获 / LLM降级
- [x] 从 ~/quant 拷贝 tushare 数据 (4.1G) 到 ~/hermes/quant

---

## 检查历史

2026-04-26 08:00 | Hermes | PASS | 初始化验证体系
2026-04-26 08:10 | Hermes | PASS | 修复hook: 时间戳去重
2026-04-26 08:30 | Hermes | PASS | 系统架构 Tab + 数据迁移
