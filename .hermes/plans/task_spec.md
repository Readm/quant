# 需求解析 — 修复 IterationView 静默 loading bug

## Purpose
修复 IterationView.tsx 中当 index.json 的 id 与迭代数据文件名不匹配时，页面永远显示"加载中..."且无错误提示的问题。

## Scope
- 修改文件: `dashboard/src/views/IterationView.tsx`
- 只改前端，不改后端
- 不改数据格式

## Out of scope
- 后端数据格式变更
- 其他 Dashboard 视图
- index.json 的内容修改

## Risk classification
isolated — 仅前端单层修改，不涉及数据格式变更

## Acceptance criteria
1. 当 index.json 的 id 匹配失败时，页面显示错误提示（不是永远 loading）
2. 正常加载路径不受影响
3. TypeScript 编译通过
4. Vite build 通过
