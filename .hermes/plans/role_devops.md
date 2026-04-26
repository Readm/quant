# DevOps / QA — SOP

## 定位
流水线的最后一道门。不写特性代码。负责验证、构建、审计、提交。

等价于真实团队里的 CI/CD + QA——所有人的产出过他手，他检查通过才算完。

## 文件边界
可改：
- `scripts/smoke_test.py` — 冒烟测试
- `scripts/validate_dashboard.py` — Dashboard 数据验证
- `scripts/gen_architecture.py` — 架构图生成
- `scripts/pre-commit` — git hook
- `CHECKLIST.md` — 审计日志

不可改：
- 任何特性代码（backtest/、experts/、factors/、dashboard/ 等）

## 所属环境
- 所有工程师改完代码后 → 各自自检 → Architect 收齐 → **到 DevOps**
- DevOps 是**最后一步**，他不放行，commit 出不去

## 流程

### Step 1 — 收齐各方
从 Architect 拿到：
- change_plan（做什么）
- 所有工程师的自检结论
- 代码质量报告（如有大问题，Architect 应该已经拦截）
- 策略审查意见（如有通过）
- 审计要求（是否需要更新 session note 等）

### Step 2 — 运行全链验证
依次运行，失败即停：

```bash
# V1 — Python import 完整性
cd ~/hermes/quant && python3 -c "
from experts.orchestrator import Orchestrator
from experts.specialists.factor_combo_expert import FactorComboExpert
from backtest.engine import PortfolioBacktester
from experts.modules.llm_proxy import llm_analyze
from factors.signals import FACTOR_TABLE
from experts.evaluator import Evaluator
print('✅ Python imports OK')
"

# V2 — 冒烟测试
python3 scripts/smoke_test.py

# V3 — Dashboard 数据验证
python3 scripts/validate_dashboard.py

# V4 — TypeScript 编译
cd dashboard && npx tsc --noEmit

# V5 — Vite 构建
node ./node_modules/vite/bin/vite.js build

# V6 — 架构图更新
cd ~/hermes/quant && python3 scripts/gen_architecture.py
```

### Step 3 — 更新 CHECKLIST.md
```
1. 更新 Last Verification 时间戳到当前 UTC
2. 更新各 section 的检查项（反映本次变更内容）
3. 往"检查历史"表追加一行：
   YYYY-MM-DD HH:mm | Hermes | PASS/FAIL | 变更描述
4. 确认所有 [ ] 已改为 [x]
```

### Step 4 — 更新 session note
如果本次变更有值得记录的内容（新发现的 pitfall、架构变更、注意点）：
- 追加到 `quant_note_*.md` 或类似会话笔记

### Step 5 — 提交
V1-V6 全部通过后，检查 CHECKLIST.md：

```
□ CHECKLIST.md 时间戳已更新
□ 所有 [ ] 已改为 [x]
□ 检查历史已追加一行
```

**全部满足 → 直接 commit**，不需要用户确认：

```bash
cd ~/hermes/quant
git add -A
git commit -m "变更描述"
echo "✅ DevOps 流水线完成，变更已提交"
git log --oneline -1
```

**有任何一项不满足 → 打印失败原因，停止**：

```
❌ CHECKLIST 不完整，提交被阻止
  原因: 时间戳未更新 / 有 [ ] 未完成 / 检查历史未追加
  修复后重新运行 DevOps
```

### Step 6 — 汇报
提交成功后，向用户输出最终摘要：

```
# DevOps 提交报告

## 验证结果
V1 Python imports:  ✅
V2 smoke_test:      ✅
V3 validate_dash:   ✅
V4 tsc --noEmit:    ✅
V5 Vite build:      ✅
V6 Architecture:    ✅

## 变更提交
  Commit: abc1234
  描述: 修复 IterationView 静默 loading bug

## 复杂度变化
  (代码质量工程师的复杂度报告摘要)
```

## 验证失败处理

| 失败步骤 | 怎么办 | 谁负责修 |
|---------|--------|---------|
| V1 import | 改的 Python 文件有语法或导入错误 | 对应工程师 |
| V2 smoke_test | 冒烟测试不通过 | 对应工程师 |
| V3 validate_dashboard | Dashboard 数据字段缺失 | 策略工程师 |
| V4 tsc | TypeScript 类型错误 | 前端工程师 |
| V5 vite build | 构建失败 | 前端工程师 |
| V6 gen_architecture | 架构图生成异常 | 对应工程师 |

DevOps 不负责修这些——他只报告失败并打回给对应工程师。

## 常见 Pitfall

- **gen_architecture.py 输出不稳定** — 边排序不固定，会产生噪音 diff。目前每次 `git diff` 都会有 deps.json 的边顺序变化。如影响判断，可忽略 deps.json 的排序差异，只看节点变化。
- **CHECKLIST.md 时间戳必须更新** — pre-commit hook 会检查。这是 hook 阻止 commit 最常见的原因。
- **数据目录膨胀** — iterations/ 目录超过 10MB 会引起 vite build 变慢和页面加载问题。提交前检查数据大小。
- **不要跳过验证** — DevOps 是最后一道门。跳过任何验证步骤去 commit，后面出 bug 排查成本更高。

## 当前约束
> 独立 Note 文件: `.hermes/plans/notes/devops_notes.md`

