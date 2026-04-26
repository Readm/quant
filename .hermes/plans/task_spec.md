# 需求解析 — Dashboard 策略迭代图注入

## Purpose
创建策略工程师维护的 iteration_flow.mmd 和 scoring_standards.mmd，并让 Dashboard 的 StrategyView 加载渲染这两张图，取代当前硬编码的 6 阶段文字描述。

## Scope
- 新建文件:
  - `dashboard/src/data/strategy/iteration_flow.mmd`
  - `dashboard/src/data/strategy/scoring_standards.mmd`
  - `dashboard/src/components/MermaidDiagram.tsx`
- 修改文件:
  - `dashboard/src/views/StrategyView.tsx`
  - `dashboard/package.json`（新增 mermaid 依赖）
  - `dashboard/package-lock.json`（自动更新）

## Out of scope
- 不改后端 Python 代码
- 不改 ArchitectureView（系统架构图不走 Mermaid）
- 不改其他 View

## Risk classification
data_format — 新增数据文件 (mmd) + 新增组件 + 修改 View + 增依赖，跨前端组件层，但所有改动在 dashboard/ 内

## Acceptance criteria
1. iteration_flow.mmd 准确反映 orchestrator.py v5.0 的 10 步迭代流程
2. scoring_standards.mmd 准确反映 evaluator.py v5.x 的评分公式和阈值
3. StrategyView 在"策略迭代流程"区域渲染 Mermaid 图
4. TypeScript 编译通过
5. Vite build 通过
6. validate_dashboard 通过
