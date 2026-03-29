import { useState } from 'react'
import {
  Brain, GitBranch, CheckCircle2, Zap, RefreshCw,
  MessageSquare, TrendingUp, TrendingDown, Scale,
  LayoutGrid, Target, Globe, Layers,
} from 'lucide-react'
import {
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ComposedChart, Line,
} from 'recharts'

const evolutionData = [
  { round: 1, ann: 7.2,  score: 85 },
  { round: 2, ann: 9.2,  score: 90 },
  { round: 3, ann: 9.9,  score: 95 },
  { round: 4, ann: 9.9,  score: 95 },
  { round: 5, ann: 9.9,  score: 95 },
  { round: 6, ann: 9.9,  score: 95 },
]

const regimeData = [
  { regime: 'trend_narrow', count: 631, pct: 86.9, color: '#6366f1' },
  { regime: 'bull_trend',   count:  41, pct:  5.6, color: '#4ade80' },
  { regime: 'bear_trend',   count:  26, pct:  3.6, color: '#f87171' },
  { regime: 'warmup',       count:  20, pct:  2.8, color: '#94a3b8' },
  { regime: 'range_wide',   count:   4, pct:  0.6, color: '#fbbf24' },
  { regime: 'range_narrow', count:   4, pct:  0.6, color: '#22d3ee' },
]

const mechItems = [
  { Ic: CheckCircle2, title: '精英保留',    desc: 'Top3直接进入下轮，保留最优基因',           color: '#4ade80' },
  { Ic: GitBranch,     title: '基因突变',    desc: 'Top10各产生2个参数扰动变体（±15%）',       color: '#6366f1' },
  { Ic: Zap,           title: '种子注入',    desc: '每轮加入3个新的随机因子组合',               color: '#fbbf24' },
]

const experts = [
  { id: 'META', name: '元专家',         role: '迭代控制 · 汇总判断 · 最终裁决', color: '#a78bfa', icon: Brain,         tag: '顶层' },
  { id: 'E1A', name: '趋势专家',        role: '趋势识别 · 动量追踪',              color: '#6366f1', icon: TrendingUp,    tag: '流水线A' },
  { id: 'E1B', name: '均值回归专家',    role: '超买超卖 · 反弹捕捉',              color: '#22d3ee', icon: TrendingDown,  tag: '流水线A' },
  { id: 'E1C', name: '网络搜索专家',    role: '实时信息 · 因子增强',              color: '#fbbf24', icon: Globe,         tag: '实时数据' },
  { id: 'E2',  name: '评估专家',        role: '量化评分 · 过滤淘汰',              color: '#f59e0b', icon: Target,         tag: '评估入口' },
  { id: 'E3A', name: '趋势辩护专家',    role: '趋势策略倡导 · 反驳均值的局限性',  color: '#6366f1', icon: MessageSquare,  tag: '对抗B 正方' },
  { id: 'E3B', name: '均值回归辩护专家', role: '均值回归倡导 · 反驳趋势的局限性',  color: '#22d3ee', icon: MessageSquare,  tag: '对抗B 反方' },
  { id: 'E4',  name: '组合专家',        role: '风控校准 · 仓位分配 · 组合优化',  color: '#4ade80', icon: Scale,          tag: '组合输出' },
]

function ExpertCard({ expert }: { expert: typeof experts[0] }) {
  const [open, setOpen] = useState(false)
  const Ic = expert.icon

  return (
    <div
      className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden"
      style={{ borderColor: expert.color + '33' }}
    >
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between p-3.5 hover:bg-slate-700/30 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ backgroundColor: expert.color + '22', border: `1px solid ${expert.color}44` }}
          >
            <Ic size={15} style={{ color: expert.color }} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-white text-sm">{expert.name}</span>
              <span
                className="text-xs px-1.5 py-0.5 rounded font-mono"
                style={{ backgroundColor: expert.color + '22', color: expert.color }}
              >
                {expert.id}
              </span>
              <span className="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-400">
                {expert.tag}
              </span>
            </div>
            <div className="text-xs text-slate-400 mt-0.5">{expert.role}</div>
          </div>
        </div>
        <div className="text-slate-500 text-xs">{open ? '▲' : '▼'}</div>
      </button>

      {open && (
        <div className="px-3.5 pb-4 space-y-2 border-t border-slate-700">
          <div className="pt-3 text-xs text-slate-400">
            多专家辩论系统 · {expert.tag} · {expert.role}
          </div>
        </div>
      )}
    </div>
  )
}

function ArchitectureDiagram() {
  return (
    <div className="bg-slate-900 rounded-xl p-5 border border-slate-700 overflow-x-auto">
      <h3 className="text-white font-semibold mb-5">🏗️ 系统架构图</h3>
      <div className="min-w-[720px] space-y-3">

        {/* Layer 0: Meta */}
        <div className="flex items-center justify-center">
          <div className="rounded-xl px-5 py-3 text-center"
            style={{ backgroundColor: '#a78bfa22', border: '1.5px solid #a78bfa55' }}>
            <div className="flex items-center gap-2 justify-center mb-1">
              <Brain size={15} className="text-purple-400" />
              <span className="font-bold text-white text-sm">🧠 元专家 META</span>
            </div>
            <div className="text-xs text-slate-400">控制迭代节奏 · 汇总判断 · 输出最终报告</div>
          </div>
        </div>

        <div className="flex justify-center">
          <svg width="16" height="18" viewBox="0 0 16 18">
            <path d="M8 0 L8 14 M3 9 L8 14 L13 9" stroke="#475569" strokeWidth="1.5" fill="none" strokeLinecap="round" />
          </svg>
        </div>

        {/* Layer 1 */}
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-xl p-3" style={{ backgroundColor: '#6366f111', border: '1px solid #6366f133' }}>
            <div className="flex items-center gap-2 mb-2">
              <RefreshCw size={12} className="text-indigo-400" />
              <span className="text-xs font-bold text-indigo-300">🔄 流水线模式 A</span>
            </div>
            {[
              { id: 'E1A', name: '📈 趋势专家',     color: '#6366f1' },
              { id: 'E1B', name: '🔄 均值回归专家', color: '#22d3ee' },
              { id: 'E1C', name: '🌐 网络搜索专家', color: '#fbbf24' },
            ].map(e => (
              <div key={e.id} className="flex items-center gap-2 text-xs bg-slate-800/60 rounded-lg px-3 py-1.5"
                style={{ borderLeft: `2px solid ${e.color}` }}>
                <span className="font-mono font-bold" style={{ color: e.color }}>{e.id}</span>
                <span className="text-white">{e.name}</span>
              </div>
            ))}
          </div>

          <div className="rounded-xl p-3" style={{ backgroundColor: '#f59e0b11', border: '1px solid #f59e0b33' }}>
            <div className="flex items-center gap-2 mb-2">
              <MessageSquare size={12} className="text-amber-400" />
              <span className="text-xs font-bold text-amber-300">🗡️ 对抗辩论模式 B</span>
            </div>
            {[
              { id: 'E2',  name: '⚡ 评估专家',            color: '#f59e0b' },
              { id: 'E3A', name: '📈 趋势辩护(正方)',    color: '#6366f1' },
              { id: 'E3B', name: '🔄 均值回归辩护(反方)', color: '#22d3ee' },
            ].map(e => (
              <div key={e.id} className="flex items-center gap-2 text-xs bg-slate-800/60 rounded-lg px-3 py-1.5"
                style={{ borderLeft: `2px solid ${e.color}` }}>
                <span className="font-mono font-bold" style={{ color: e.color }}>{e.id}</span>
                <span className="text-white">{e.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Blackboard */}
        <div className="flex flex-col items-center">
          <svg width="16" height="18" viewBox="0 0 16 18">
            <path d="M8 0 L8 14 M3 9 L8 14 L13 9" stroke="#475569" strokeWidth="1.5" fill="none" strokeLinecap="round" />
          </svg>
          <div className="mt-1 rounded-xl px-5 py-2 text-center"
            style={{ backgroundColor: '#fbbf2422', border: '1.5px solid #fbbf2444' }}>
            <div className="flex items-center gap-2 justify-center">
              <LayoutGrid size={13} className="text-yellow-400" />
              <span className="font-bold text-white text-xs">📌 共享黑板</span>
            </div>
            <div className="text-xs text-slate-400 mt-0.5">所有专家输出写入 · 每轮清空</div>
          </div>
        </div>

        <div className="flex justify-center">
          <svg width="16" height="18" viewBox="0 0 16 18">
            <path d="M8 0 L8 14 M3 9 L8 14 L13 9" stroke="#475569" strokeWidth="1.5" fill="none" strokeLinecap="round" />
          </svg>
        </div>

        <div className="flex justify-center">
          <div className="rounded-xl px-6 py-3 text-center"
            style={{ backgroundColor: '#4ade8022', border: '1.5px solid #4ade8044' }}>
            <div className="flex items-center gap-2 justify-center mb-1">
              <Scale size={14} className="text-green-400" />
              <span className="font-bold text-white text-sm">📊 组合专家 E4</span>
            </div>
            <div className="text-xs text-slate-400">风控校准 · 仓位分配 · 止损线设置</div>
          </div>
        </div>

        {/* Output */}
        <div className="flex justify-center">
          <div className="rounded-xl px-6 py-3 text-center"
            style={{ backgroundColor: '#4ade8015', border: '1.5px solid #4ade8040' }}>
            <div className="text-xs text-green-400 mb-1 font-medium">🎯 最终输出</div>
            <div className="text-white font-bold text-sm">MA金叉(10,60) × RSI+布林 × 新闻事件驱动</div>
            <div className="text-xs text-green-400/70 mt-1">预期年化 +10~15% · 最大回撤 ≤12% · 夏普 ≥0.5</div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function ExpertView() {
  const [showAll, setShowAll] = useState(false)

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Brain size={24} className="text-purple-400" />
        <div>
          <h2 className="text-xl font-bold text-white">专家系统进化框架</h2>
          <p className="text-slate-400 text-sm">v3.0 · 8位专家 · 多模式协作</p>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { Ic: Brain,         label: '专家总数',   value: '8位',   sub: '3类角色',    color: '#a78bfa' },
          { Ic: Layers,        label: '元因子库',   value: '20个',  sub: '5大家族',    color: '#6366f1' },
          { Ic: TrendingUp,    label: '初始策略池', value: '174个', sub: '因子组合',    color: '#22d3ee' },
          { Ic: CheckCircle2,  label: '收敛轮次',   value: '3轮',   sub: '达到收敛',    color: '#4ade80' },
        ].map(m => (
          <div key={m.label} className="bg-slate-800 rounded-xl p-4 border border-slate-700">
            <div className="flex items-center gap-3 mb-2">
              <div className="p-1.5 rounded-lg" style={{ backgroundColor: m.color + '22' }}>
                <m.Ic size={15} style={{ color: m.color }} />
              </div>
              <span className="text-slate-400 text-xs">{m.label}</span>
            </div>
            <div className="text-xl font-bold text-white">{m.value}</div>
            <div className="text-xs text-slate-500 mt-0.5">{m.sub}</div>
          </div>
        ))}
      </div>

      <ArchitectureDiagram />

      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-white font-semibold">🧠 专家角色详解</h3>
          <button
            onClick={() => setShowAll(s => !s)}
            className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-600 text-slate-400 hover:text-white transition-colors"
          >
            {showAll ? '收起' : '展开全部 8 位专家'}
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {experts.filter((_, i) => showAll || i < 4).map(exp => (
            <ExpertCard key={exp.id} expert={exp} />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <h3 className="text-white font-semibold mb-4">🧬 进化机制</h3>
          <div className="space-y-2.5">
            {mechItems.map(m => (
              <div key={m.title} className="flex items-start gap-3 bg-slate-900 rounded-lg p-3 border border-slate-700">
                <m.Ic size={14} style={{ color: m.color }} className="mt-0.5 flex-shrink-0" />
                <div>
                  <div className="font-medium text-white text-sm">{m.title}</div>
                  <div className="text-slate-400 text-xs mt-0.5">{m.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <h3 className="text-white font-semibold mb-3">📈 进化轨迹</h3>
          <ResponsiveContainer width="100%" height={210}>
            <ComposedChart data={evolutionData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="round" tick={{ fill: '#94a3b8', fontSize: 12 }}
                label={{ value: 'Round', fill: '#64748b', fontSize: 11 }} />
              <YAxis yAxisId="ann" orientation="left"
                tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={(v) => v + '%'} domain={[-5, 20]} />
              <YAxis yAxisId="score" orientation="right"
                tick={{ fill: '#94a3b8', fontSize: 11 }} domain={[70, 120]} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 8 }} labelStyle={{ color: '#fff' }} />
              <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 12 }} />
              <Line yAxisId="ann" type="monotone" dataKey="ann" name="年化收益率%"
                stroke="#6366f1" strokeWidth={2} dot={{ fill: '#6366f1', r: 4 }} />
              <Line yAxisId="score" type="monotone" dataKey="score" name="综合评分"
                stroke="#22d3ee" strokeWidth={2} dot={{ fill: '#22d3ee', r: 4 }} />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="mt-3 space-y-1">
            <div className="text-xs text-slate-500">市场状态分布（2022-2024）</div>
            <div className="flex gap-1 flex-wrap">
              {regimeData.map(r => (
                <span key={r.regime} className="text-xs px-1.5 py-0.5 rounded font-mono"
                  style={{ backgroundColor: r.color + '22', color: r.color }}>
                  {r.regime} {r.pct}%
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
