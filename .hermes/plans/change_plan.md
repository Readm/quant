# Change Plan: Dashboard 轻量化 (Plan A + B)

> **For Hermes:** Dispatch to 前端工程师 (Frontend Engineer). Use subagent-driven-development.

**Goal:** 将 Dashboard 构建时间从 ~8s 降至 ~3s，产物 JS 减少 ~1.5MB，node_modules 减少 75MB。

**Architecture:** 
- Plan A: 迭代 JSON 从 `import.meta.glob` (打包进 JS) 改为运行时 `fetch()` (从 `public/` 静态目录服务)
- Plan B: Mermaid 流程图从运行时 JS 渲染 (mermaid.js) 改为预渲染静态 SVG，移除 mermaid 依赖

**风险等级:** isolated (所有改动在 dashboard/ 目录内，无后端数据链影响)

**涉及角色:** 前端工程师

**数据依赖:** 无 — 数据流方向不变，仅加载方式变化

---

## Task 1: 移动迭代数据到 public/

**Objective:** 将迭代 JSON 文件从 `src/data/iterations/` 移到 `public/data/iterations/`，使其被 Vite 作为静态文件复制到 `dist/`，不打包进 JS。

**Files:**
- Move: `dashboard/src/data/iterations/index.json` → `dashboard/public/data/iterations/index.json`
- Move: `dashboard/src/data/iterations/multi_expert_v4_20260427_0022.json` → `dashboard/public/data/iterations/multi_expert_v4_20260427_0022.json`

**Steps:**

1. 创建 `public/data/iterations/` 目录，移动文件：

```bash
cd ~/hermes/quant/dashboard
mkdir -p public/data/iterations
mv src/data/iterations/index.json public/data/iterations/
mv src/data/iterations/multi_expert_v4_20260427_0022.json public/data/iterations/
```

2. 验证移动后 `src/data/iterations/` 是否为空（旧文件不可留，否则 `import.meta.glob` 会继续打包它们）：

```bash
ls src/data/iterations/
```

期望输出为空（或只剩 README 之类无关文件）。

---

## Task 2: 改 IterationView.tsx — index.json 加载

**Objective:** 将 index.json 从编译时 `import.meta.glob({eager: true})` 改为运行时 `fetch()`。

**Files:**
- Modify: `dashboard/src/views/IterationView.tsx:67-76`

**Step 1: 删除编译时加载代码**

删除第 67-76 行：

```typescript
// ── Lazy-load individual iteration files (only load when selected) ──
const ITERATION_LOADERS = import.meta.glob('../data/iterations/*.json') as
  Record<string, () => Promise<{ default: IterationLog }>>
const INDEX_DATA = (() => {
  try {
    const m = import.meta.glob('../data/iterations/index.json', { eager: true }) as any
    const key = Object.keys(m)[0]
    return (key ? m[key].default : []) as ThreadMeta[]
  } catch { return [] as ThreadMeta[] }
})()
```

**Step 2: 添加运行时 fetch 状态变量**

在组件函数内（`export default function IterationView() {` 之后），添加：

```typescript
const [threads, setThreads] = useState<ThreadMeta[]>([])
const [threadsLoading, setThreadsLoading] = useState(true)
```

**Step 3: 添加 fetch index.json 的 useEffect**

在组件函数内，其他 useEffect 之前添加：

```typescript
useEffect(() => {
  fetch('./data/iterations/index.json')
    .then(r => r.json())
    .then(data => { setThreads(data); setThreadsLoading(false) })
    .catch(() => { setThreads([]); setThreadsLoading(false) })
}, [])
```

**Step 4: 更新线程选择逻辑**

找到 `selectThread` 函数（第 592 行附近），确保它使用 `threads` state 而非 `INDEX_DATA`（当前代码很可能已经用了 state，需要确认。如果 `threads` 变量原本就是来自 `INDEX_DATA` 的 useState，把初始化改为 `useState<ThreadMeta[]>([])` 即可）。

**Step 5: 添加加载中状态**

在 `if (threads.length === 0) return (...)` 之前，添加：

```typescript
if (threadsLoading) return (
  <div className="flex items-center gap-2 text-slate-400 p-8">
    <RefreshCw size={18} className="animate-spin"/>加载中...
  </div>
)
```

需要导入 `RefreshCw`（如果没有的话 — 检查导入语句）。

---

## Task 3: 改 IterationView.tsx — 迭代数据按需加载

**Objective:** 将具体迭代数据的加载从动态 `import()` 改为 `fetch()`。

**Files:**
- Modify: `dashboard/src/views/IterationView.tsx` (第 594-608 行的 useEffect)

**Step 1: 替换数据加载 useEffect**

将第 594-608 行改为：

```typescript
useEffect(() => {
  if (!activeThreadId) return
  setLoading(true)
  setLog(null)
  setError(null)
  fetch(`./data/iterations/${activeThreadId}.json`)
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      return r.json()
    })
    .then(data => { setLog(data as IterationLog); setLoading(false) })
    .catch(err => { setError(`加载迭代数据失败: ${err.message}`); setLoading(false) })
}, [activeThreadId])
```

这移除了对 `ITERATION_LOADERS` 和 `Object.keys(...).find(...)` 的依赖。

**Step 2: 确认 `activeThreadId` 与文件名匹配**

检查 `ThreadSelector` 组件中 `activeThreadId` 的值。它来自 `index.json` 中的 `id` 字段。当前 index.json 内容：

```json
[{"id": "multi_expert_v4_20260427_0022", ...}]
```

文件名是 `multi_expert_v4_20260427_0022.json`，`id` 与之匹配 ✓。fetch URL 为 `./data/iterations/multi_expert_v4_20260427_0022.json` ✓。

---

## Task 4: 预渲染 Mermaid 图为 SVG

**Objective:** 用 mermaid CLI 将两个 .mmd 文件渲染为静态 SVG，存入 `public/` 目录。

**Files:**
- Create: `dashboard/public/data/strategy/iteration_flow.svg`
- Create: `dashboard/public/data/strategy/scoring_standards.svg`
- Source: `dashboard/src/data/strategy/iteration_flow.mmd`
- Source: `dashboard/src/data/strategy/scoring_standards.mmd`

**Step 1: 安装 mermaid-cli 并渲染**

```bash
cd ~/hermes/quant/dashboard
npx @mermaid-js/mermaid-cli mmdc -i src/data/strategy/iteration_flow.mmd -o public/data/strategy/iteration_flow.svg -b '#0f172a' -w 1200
npx @mermaid-js/mermaid-cli mmdc -i src/data/strategy/scoring_standards.mmd -o public/data/strategy/scoring_standards.svg -b '#0f172a' -w 1000
```

验证：

```bash
ls -lh public/data/strategy/*.svg
```

每个 SVG 应该 < 100KB。

---

## Task 5: 移除 MermaidDiagram 组件，改造 StrategyView

**Objective:** 删除 `MermaidDiagram.tsx`，在 `StrategyView.tsx` 中用 `<img>` 标签替换。

**Files:**
- Delete: `dashboard/src/components/MermaidDiagram.tsx`
- Modify: `dashboard/src/views/StrategyView.tsx`

**Step 1: 删除 MermaidDiagram.tsx**

```bash
rm dashboard/src/components/MermaidDiagram.tsx
```

**Step 2: 修改 StrategyView.tsx**

将第 2 行的导入：

```typescript
import MermaidDiagram from '../components/MermaidDiagram'
```

替换为：

```typescript
import { Presentation, Scale } from 'lucide-react'
```

将第 72-76 行：

```tsx
      {/* Strategy iteration flow diagram */}
      <MermaidDiagram fileKey="strategy/iteration_flow" title="策略迭代流程" />

      {/* Scoring standards diagram */}
      <MermaidDiagram fileKey="strategy/scoring_standards" title="评分标准" />
```

替换为：

```tsx
      {/* Strategy iteration flow diagram */}
      <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
        <h3 className="text-white font-semibold mb-4 text-sm flex items-center gap-2">
          <Presentation size={15} className="text-indigo-400" />
          策略迭代流程
        </h3>
        <img src="./data/strategy/iteration_flow.svg" alt="策略迭代流程" className="w-full" />
      </div>

      {/* Scoring standards diagram */}
      <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
        <h3 className="text-white font-semibold mb-4 text-sm flex items-center gap-2">
          <Scale size={15} className="text-indigo-400" />
          评分标准
        </h3>
        <img src="./data/strategy/scoring_standards.svg" alt="评分标准" className="w-full" />
      </div>
```

---

## Task 6: 移除 mermaid 依赖

**Objective:** 从 package.json 移除 mermaid，清理 node_modules。

**Files:**
- Modify: `dashboard/package.json`

**Step 1: 从 package.json 移除 mermaid**

编辑 `dashboard/package.json`，从 `dependencies` 中删除 `"mermaid": "^11.14.0",` 行。

**Step 2: 清理并重装依赖**

```bash
cd ~/hermes/quant/dashboard
rm -rf node_modules/.vite  # 清 Vite 缓存
npm install                 # 更新 lockfile
```

确认 mermaid 不再存在：

```bash
ls node_modules/mermaid 2>/dev/null && echo "STILL EXISTS" || echo "REMOVED"
```

期望输出: `REMOVED`

---

## Task 7: 构建验证

**Objective:** 确认构建时间缩短、产物变小、无 TypeScript 错误。

**Step 1: 构建**

```bash
cd ~/hermes/quant/dashboard
time node ./node_modules/vite/bin/vite.js build
```

期望：
- 构建时间 < 4s
- 无 TypeScript 错误
- 无明显大 chunk 警告

**Step 2: 检查产物**

```bash
ls -lh dist/assets/*.js
```

期望：
- 无 `multi_expert_v4_*` 开头的 JS chunk（数据不再打包）
- 无 mermaid 相关的 40+ 小 chunk
- 总 JS 文件数大幅减少

**Step 3: 启动预览并确认**

```bash
cd dist && python3 -m http.server 9000 --bind 0.0.0.0 &
```

从浏览器访问 `http://localhost:9000`，确认：
- 迭代数据页能加载并显示最新迭代
- 策略页能看到两张流程图

---

## Task 8: 更新 CHECKLIST.md

**Files:**
- Modify: `CHECKLIST.md`

```bash
cd ~/hermes/quant
# 更新 Last Verification 时间戳
# 添加变更描述：Dashboard 轻量化 — fetch 加载 + SVG 预渲染
git add CHECKLIST.md
```
