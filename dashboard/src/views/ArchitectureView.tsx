/**
 * ArchitectureView — 系统架构可视化
 *
 * 展示模块依赖图 + 模块说明 + 数据流 + 因子覆盖矩阵
 * 代码自动生成: scripts/gen_architecture.py → deps.json
 */
import { useMemo, useRef, useCallback, useState } from 'react'
import ReactFlow, {
  Node,
  Edge,
  Position,
  useNodesState,
  useEdgesState,
  Background,
  BackgroundVariant,
  MarkerType,
  NodeProps,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { Layers, Database, Brain, Activity, GitBranch } from 'lucide-react'

// ── 模块说明 ──────────────────────────────────────────────
const MODULE_DESCRIPTIONS: Record<string, string> = {
  '编排层': 'Orchestrator — 20轮迭代主循环, 调度所有子模块。生成候选→回测→评估→评审→组合→OOS→反馈',
  '策略层': 'FactorComboExpert — 38模板, 1~3因子组合候选生成。从 FACTOR_TABLE 挑选因子生成候选策略',
  '评估层': 'Evaluator — 四维评分(Sortino+Calmar+IR+DD+Alpha) + PBO过拟合检测',
  '评审层': 'DebateManager — 两阶段LLM评审: 逐策略评审→阵营权重裁决',
  '回测层': 'PortfolioBacktester — 多股组合回测: 因子打分→选股→权重→再平衡, 含交易成本',
  '因子层': '47因子库 — 趋势/均值回归/动量/量价/波幅/缠论, 纯NumPy实现',
  '数据层': '腾讯行情API(主) + 本地缓存(Stooq) + 沪深300CSV(基准)',
  '模块层': '风险引擎/LLM代理/数据获取/Alpha158/WalkForward/PBO分析/Blackboard',
  '配置层': '交易成本(买0.08%/卖0.18%), 风控参数, 市场映射',
  '报告层': '结果序列化 + Dashboard数据注入',
  '其他': '工具类/初始化脚本',
}

// ── 数据来源 ──────────────────────────────────────────────
const DATA_SOURCES = [
  { name: '腾讯行情API', url: 'web.ifzq.gtimg.cn', type: '主数据源', desc: 'SPY/BTCUSDT/ETHUSDT 日K线, 前复权, 500天' },
  { name: '本地缓存', path: 'data/raw/', type: '备用', desc: 'Stooq/akshare 采集的历史数据, JSON格式' },
  { name: 'Tushare', path: 'data/tushare/', type: '辅助', desc: '沪深300基准(000300.SH), 日K/复权/资金流 4.1G' },
]

// ── 因子覆盖矩阵 ──────────────────────────────────────────
const FACTOR_COVERAGE = [
  { id: 'F00-F12', name: '经典指标', total: 5, scored: 5, templated: 5, note: 'MA/MACD/RSI/Bollinger/ATR' },
  { id: 'F17-F23', name: '趋势类', total: 7, scored: 7, templated: 5, note: 'Ichimoku/SAR/KST/TRIX/Donchian/Aroon' },
  { id: 'F24-F35', name: '动量类', total: 5, scored: 3, templated: 2, note: 'Force/Elder/PPO/Matrix/ROC' },
  { id: 'F26-F31', name: '均值回归', total: 5, scored: 5, templated: 5, note: 'MFI/RVI/KDW/OBOS' },
  { id: 'F32-F42', name: '量价类', total: 6, scored: 5, templated: 5, note: 'VPT/A/D/Mass/Ergodic' },
  { id: 'F14-F39', name: '波幅类', total: 2, scored: 2, templated: 2, note: 'UltraSpline/UltraBand' },
  { id: 'F46-F47', name: '缠论', total: 2, scored: 2, templated: 2, note: '笔/套' },
]

// ── Marker 颜色 ───────────────────────────────────────────
const CAT_COLORS: Record<string, string> = {
  '编排层': '#a855f7',
  '策略层': '#6366f1',
  '评估层': '#f59e0b',
  '评审层': '#f87171',
  '回测层': '#22d3ee',
  '因子层': '#4ade80',
  '数据层': '#06b6d4',
  '模块层': '#94a3b8',
  '配置层': '#64748b',
  '报告层': '#c084fc',
}

// ── 颜色节点 ──────────────────────────────────────────────
function CatNode({ data }: NodeProps<{ label: string; category: string }>) {
  const color = CAT_COLORS[data.category] || '#64748b'
  return (
    <div className="rounded-lg border px-3 py-2 shadow-md"
      style={{ backgroundColor: '#0f172a', borderColor: color + '60' }}>
      <div className="text-xs font-mono leading-tight flex items-center gap-1.5">
        <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: color }} />
        <span style={{ color }} className="font-semibold">{data.category}</span>
      </div>
      <div className="text-[10px] text-slate-300 mt-0.5">{data.label}</div>
    </div>
  )
}

const nodeTypes = { catNode: CatNode }

// ── Build nodes + edges from deps.json ──────────────────────
function loadGraph() {
  let deps: { nodes: any[]; edges: any[] } = { nodes: [], edges: [] }
  try {
    const m = import.meta.glob('../data/architecture/deps.json', { eager: true }) as any
    const key = Object.keys(m)[0]
    if (key) deps = m[key].default as any
  } catch { /* fallback: empty graph */ }

  // Filter to core modules only (category != '其他')
  const filtered = deps.nodes.filter((n: any) => n.category !== '其他' && n.category !== '模块层')

  // Layout: group by category
  const categories = [...new Set(filtered.map((n: any) => n.category))]
  const colW = 200, rowH = 80
  const nodes: Node[] = filtered.map((n: any, i: number) => {
    const catIdx = categories.indexOf(n.category)
    const x = catIdx * colW + 20
    const y = (filtered.filter((m: any, j: number) => j < i && m.category === n.category).length) * rowH + 20
    return {
      id: n.id, type: 'catNode',
      position: { x, y },
      data: { label: n.label, category: n.category },
      sourcePosition: Position.Right, targetPosition: Position.Left,
    }
  })

  const edges: Edge[] = deps.edges
    .filter((e: any) => filtered.some((n: any) => n.id === e.source) && filtered.some((n: any) => n.id === e.target))
    .map((e: any, i: number) => ({
      id: `e-${i}`, source: e.source, target: e.target,
      animated: false,
      style: { stroke: '#334155', strokeWidth: 1 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#475569', width: 10, height: 10 },
    }))

  return { initialNodes: nodes, initialEdges: edges, categories }
}

// ── Main View ──────────────────────────────────────────────
export default function ArchitectureView() {
  const graph = useMemo(() => loadGraph(), [])
  const [nodes, , onNodesChange] = useNodesState(graph.initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(graph.initialEdges)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Layers size={24} className="text-purple-400" />
        <div>
          <h2 className="text-xl font-bold text-white">系统架构</h2>
          <p className="text-slate-400 text-sm">
            模块依赖图(自动生成) · 数据流 · 因子覆盖矩阵
          </p>
        </div>
      </div>

      {/* Module dependency graph */}
      <div className="bg-slate-900 rounded-xl border border-slate-700 p-4">
        <div className="flex items-center gap-2 mb-3">
          <GitBranch size={14} className="text-slate-400" />
          <span className="text-sm font-bold text-white">模块依赖图</span>
          <span className="text-[10px] text-slate-500 ml-auto">
            {graph.initialNodes.length} 节点 · {graph.initialEdges.length} 边 · 自动生成
          </span>
        </div>
        <div className="border border-slate-700/50 rounded-lg overflow-hidden" style={{ height: 320 }}>
          <ReactFlow
            nodes={nodes} edges={edges}
            onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
            nodeTypes={nodeTypes}
            fitView fitViewOptions={{ padding: 0.3 }}
            minZoom={0.3} maxZoom={1.2}
            nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={16} size={0.4} color="#1e293b" />
          </ReactFlow>
        </div>
      </div>

      {/* Module descriptions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {Object.entries(MODULE_DESCRIPTIONS)
          .filter(([k]) => k !== '其他' && k !== '模块层')
          .map(([name, desc]) => {
            const color = CAT_COLORS[name] || '#64748b'
            return (
              <div key={name} className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-3.5"
                style={{ borderLeft: `3px solid ${color}` }}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                  <span className="text-sm font-semibold text-white">{name}</span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">{desc}</p>
              </div>
            )
          })}
      </div>

      {/* Data Sources */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Database size={14} className="text-cyan-400" />
          <span className="text-sm font-bold text-white">数据来源</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {DATA_SOURCES.map(ds => (
            <div key={ds.name} className="bg-slate-900/60 rounded-lg px-3 py-2.5 border border-slate-700/40">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-xs font-bold text-white">{ds.name}</span>
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-300">{ds.type}</span>
              </div>
              <p className="text-[10px] text-slate-400">{ds.url || ds.path}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">{ds.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Factor coverage matrix */}
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Activity size={14} className="text-green-400" />
          <span className="text-sm font-bold text-white">因子覆盖矩阵</span>
          <span className="text-[10px] text-slate-500 ml-auto">
            38 模板 / 47 因子
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-600">
                <th className="text-left py-2 px-2 text-slate-400 font-medium">分类</th>
                <th className="text-center py-2 px-2 text-slate-400 font-medium">因子数</th>
                <th className="text-center py-2 px-2 text-slate-400 font-medium">有评分</th>
                <th className="text-center py-2 px-2 text-slate-400 font-medium">有模板</th>
                <th className="text-left py-2 px-2 text-slate-400 font-medium">说明</th>
              </tr>
            </thead>
            <tbody>
              {FACTOR_COVERAGE.map(f => (
                <tr key={f.id} className="border-b border-slate-700/50">
                  <td className="py-2 px-2 text-white font-medium">{f.name}</td>
                  <td className="py-2 px-2 text-center text-slate-300">{f.total}</td>
                  <td className="py-2 px-2 text-center">
                    <Bar val={f.scored} max={f.total} color="#4ade80" />
                  </td>
                  <td className="py-2 px-2 text-center">
                    <Bar val={f.templated} max={f.total} color="#6366f1" />
                  </td>
                  <td className="py-2 px-2 text-slate-400">{f.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function Bar({ val, max, color }: { val: number; max: number; color: string }) {
  const pct = Math.round(val / max * 100)
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-slate-300 w-4 text-right">{val}</span>
      <div className="w-12 h-2 rounded-full bg-slate-700 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </span>
  )
}
