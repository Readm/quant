# 变更计划 — Dashboard 策略迭代图注入

## 需求
创建策略工程师维护的迭代流程图和评分标准图，Dashboard 加载渲染。

## 影响范围
- 新建: `dashboard/src/data/strategy/iteration_flow.mmd`
- 新建: `dashboard/src/data/strategy/scoring_standards.mmd`
- 新建: `dashboard/src/components/MermaidDiagram.tsx`
- 修改: `dashboard/src/views/StrategyView.tsx`
- 修改: `dashboard/package.json`
- 风险: data_format（新增数据文件 + 组件 + View + 依赖）
- 涉及角色: 策略工程师（图内容）→ 前端工程师（渲染）→ 代码质量工程师（审）→ DevOps（提交）

## 修改内容

### Task 1 — 策略工程师：创建 Mermaid 图
创建 `iteration_flow.mmd` 和 `scoring_standards.mmd`

iteration_flow.mmd 内容（从 orchestrator.py v5.0 提取）:
- 10 步: 候选生成 → 组合回测 → 评估评分 → 冠军保留 → LLM评审 → 风险评估 → 组合优化 → Paper Trade验证 → 元监控 → 元专家规划 → 回到候选生成
- 每步标注关键参数和产出

scoring_standards.mmd 内容（从 evaluator.py v5.x 提取）:
- 评分公式: Sortino 22% + Calmar 18% + IR 18% + DD 18% + Alpha缩放 24%
- 硬过滤阈值: 年化>-2%, 夏普>0.05, 交易>=1, 回撤<25%
- PBO门控: 0.50硬拒, 0.30折扣
- 决策阈值: ACCEPT>=45, CONDITIONAL>=25, <25 REJECT
- 多样性/交易质量奖励

### Task 2 — 前端工程师：渲染 Mermaid 图
1. `npm install mermaid` 到 dashboard/
2. 新建 `MermaidDiagram.tsx` 组件 — 接收 .mmd 文件路径（用 `import.meta.glob` 加载），渲染 Mermaid 图
3. 修改 StrategyView.tsx:
   - 保留策略模板列表区
   - 替换"Pipeline"区为渲染的 iteration_flow.mmd
   - 在下方新增区渲染 scoring_standards.mmd

## 依赖
- Task 1 → Task 2 无硬依赖（文件路径确定后两者可并行）
- Task 1 + Task 2 → Code Quality 审查

## 分派
- 策略工程师: Task 1
- 前端工程师: Task 2
- 代码质量工程师: 审查全部改动
- DevOps: V1-V6 → commit
