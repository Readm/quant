import { useState, useEffect } from 'react'
import { GitBranch, TrendingUp, TrendingDown, CheckCircle, XCircle,
         AlertCircle, MessageSquare, ChevronDown, ChevronRight,
         Award, RefreshCw } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'

// ── Types ──────────────────────────────────────────────────────
interface EquityPoint { i: number; v: number }
interface Strategy {
  id: string; name: string; type: string; template: string
  params: Record<string, number>
  decision: string; score: number
  ann_return: number; sharpe: number; max_drawdown: number
  win_rate: number; total_trades: number
  feedback: string; weakness: string; adjustment: string
  adj_param: string; reason: string
  equity_curve: EquityPoint[]
  selected: boolean
}
interface Debate {
  winner: string; trend_weight: number; mr_weight: number
  bull_confidence: number; bear_confidence: number
  final_advice: string
  bull_points: string[]; bear_points: string[]
  bull_summary: string; bear_summary: string
}
interface Round {
  round: number; strategies: Strategy[]
  debate: Debate; holdout: any[]
  selected: string[]; converged: boolean
}
interface IterationLog {
  run_at: string; symbols: string[]; days: number
  total_rounds: number; rounds: Round[]
  global_top: any[]; convergence: any
}

// ── Palette ──────────────────────────────────────────────────────
const COLORS = ['#6366f1','#22d3ee','#4ade80','#fbbf24','#f87171','#a78bfa','#fb923c','#34d399']
const TYPE_COLOR: Record<string, string> = { trend: '#6366f1', mean_reversion: '#22d3ee' }

// ── Decision badge ────────────────────────────────────────────────
function DecisionBadge({ d }: { d: string }) {
  if (d === 'ACCEPT')
    return <span className="flex items-center gap-1 text-green-400 text-xs font-bold"><CheckCircle size={11}/>ACCEPT</span>
  if (d === 'REJECT')
    return <span className="flex items-center gap-1 text-red-400 text-xs font-bold"><XCircle size={11}/>REJECT</span>
  return <span className="flex items-center gap-1 text-yellow-400 text-xs font-bold"><AlertCircle size={11}/>COND</span>
}

// ── Equity Curves Chart ───────────────────────────────────────────
function EquityCurvesChart({ strategies }: { strategies: Strategy[] }) {
  const visible = strategies.filter(s => s.equity_curve.length > 0)
  if (visible.length === 0)
    return <div className="text-slate-500 text-sm p-4">无 equity 数据</div>

  // 对齐到最短曲线长度，合并为一个时间序列
  const minLen = Math.min(...visible.map(s => s.equity_curve.length))
  const data = Array.from({ length: minLen }, (_, i) => {
    const pt: Record<string, number> = { i }
    visible.forEach(s => { pt[s.name] = s.equity_curve[i]?.v ?? 100 })
    return pt
  })

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="i" tick={{ fill: '#64748b', fontSize: 10 }}
          label={{ value: '交易日', position: 'insideBottomRight', fill: '#475569', fontSize: 10 }} />
        <YAxis tick={{ fill: '#64748b', fontSize: 10 }}
          tickFormatter={v => `${v}`}
          label={{ value: '净值', angle: -90, position: 'insideLeft', fill: '#475569', fontSize: 10 }} />
        <ReferenceLine y={100} stroke="#475569" strokeDasharray="4 2" />
        <Tooltip
          contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
          formatter={(v: number, name) => [`${v.toFixed(1)}`, name]}
        />
        <Legend wrapperStyle={{ fontSize: 11, paddingTop: 6 }} />
        {visible.map((s, i) => (
          <Line key={s.id} type="monotone" dataKey={s.name}
            stroke={COLORS[i % COLORS.length]}
            strokeWidth={s.selected ? 2.5 : 1}
            strokeDasharray={s.selected ? undefined : '4 3'}
            dot={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

// ── Strategy Table ────────────────────────────────────────────────
function StrategyRow({ s, idx }: { s: Strategy; idx: number }) {
  const [open, setOpen] = useState(false)
  const color = COLORS[idx % COLORS.length]
  return (
    <>
      <tr className={`border-b border-slate-700/50 hover:bg-slate-700/20 cursor-pointer
          ${s.selected ? 'bg-slate-700/30' : ''}`}
        onClick={() => setOpen(o => !o)}>
        <td className="py-2 px-3">
          <span className="w-2.5 h-2.5 rounded-full inline-block mr-2" style={{ backgroundColor: color }} />
          <span className={`text-sm ${s.selected ? 'text-white font-semibold' : 'text-slate-300'}`}>{s.name}</span>
          {s.selected && <Award size={11} className="inline ml-1 text-yellow-400" />}
        </td>
        <td className="py-2 px-3 text-center">
          <span className="text-xs px-1.5 py-0.5 rounded" style={{ backgroundColor: (TYPE_COLOR[s.type] || '#888') + '22', color: TYPE_COLOR[s.type] || '#888' }}>
            {s.type === 'trend' ? '趋势' : '均值回归'}
          </span>
        </td>
        <td className="py-2 px-3 text-center"><DecisionBadge d={s.decision} /></td>
        <td className="py-2 px-3 text-right text-white font-bold">{s.score.toFixed(1)}</td>
        <td className={`py-2 px-3 text-right font-semibold ${s.ann_return >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {s.ann_return >= 0 ? '+' : ''}{s.ann_return.toFixed(1)}%
        </td>
        <td className="py-2 px-3 text-right text-slate-300">{s.sharpe.toFixed(2)}</td>
        <td className="py-2 px-3 text-right text-red-300">{s.max_drawdown.toFixed(1)}%</td>
        <td className="py-2 px-3 text-right text-slate-400">{s.total_trades}</td>
        <td className="py-2 px-3 text-slate-400">{open ? <ChevronDown size={13}/> : <ChevronRight size={13}/>}</td>
      </tr>
      {open && (
        <tr className="bg-slate-900/50">
          <td colSpan={9} className="px-4 py-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              <div>
                <div className="text-slate-400 mb-1 font-medium">参数</div>
                <div className="font-mono text-slate-300 bg-slate-800 rounded px-2 py-1.5">
                  {Object.entries(s.params).map(([k,v]) => `${k}=${v}`).join('  ·  ') || '—'}
                </div>
              </div>
              <div>
                <div className="text-slate-400 mb-1 font-medium">专家反馈</div>
                <div className="text-slate-300 bg-slate-800 rounded px-2 py-1.5">{s.feedback || s.reason || '—'}</div>
              </div>
              {s.weakness && (
                <div>
                  <div className="text-slate-400 mb-1 font-medium">识别弱点 → 调整方向</div>
                  <div className="text-yellow-300 bg-slate-800 rounded px-2 py-1.5">
                    {s.weakness} → {s.adjustment} ({s.adj_param})
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function StrategyTable({ strategies }: { strategies: Strategy[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-slate-600 text-slate-400">
            <th className="py-2 px-3 text-left">策略名</th>
            <th className="py-2 px-3 text-center">类型</th>
            <th className="py-2 px-3 text-center">决策</th>
            <th className="py-2 px-3 text-right">综合分</th>
            <th className="py-2 px-3 text-right">年化</th>
            <th className="py-2 px-3 text-right">夏普</th>
            <th className="py-2 px-3 text-right">回撤</th>
            <th className="py-2 px-3 text-right">交易次</th>
            <th className="py-2 px-3"/>
          </tr>
        </thead>
        <tbody>
          {strategies.map((s, i) => <StrategyRow key={s.id || s.name} s={s} idx={i} />)}
        </tbody>
      </table>
    </div>
  )
}

// ── Debate Panel ──────────────────────────────────────────────────
function DebatePanel({ debate }: { debate: Debate }) {
  if (!debate || !debate.winner) return null
  const tw = Math.round((debate.trend_weight || 0) * 100)
  const mw = Math.round((debate.mr_weight || 0) * 100)
  return (
    <div className="space-y-3">
      {/* Winner banner */}
      <div className="flex items-center gap-3 bg-slate-900/60 rounded-xl px-4 py-3">
        <Award size={18} className="text-yellow-400" />
        <div>
          <span className="text-white font-bold">辩论结果：</span>
          <span className="ml-2 font-bold" style={{ color: debate.winner === 'TREND' ? '#6366f1' : '#22d3ee' }}>
            {debate.winner === 'TREND' ? '趋势派胜出' : debate.winner === 'MR' ? '均值回归派胜出' : '平局'}
          </span>
        </div>
        <div className="ml-auto flex gap-4 text-xs">
          <span className="text-indigo-400">趋势权重 {tw}%</span>
          <span className="text-cyan-400">均值回归权重 {mw}%</span>
        </div>
      </div>

      {/* Weight bar */}
      <div className="flex h-2 rounded-full overflow-hidden">
        <div style={{ width: `${tw}%`, backgroundColor: '#6366f1' }} />
        <div style={{ width: `${mw}%`, backgroundColor: '#22d3ee' }} />
      </div>

      {/* Bull / Bear */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="bg-green-900/20 border border-green-700/30 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp size={14} className="text-green-400" />
            <span className="text-green-400 font-semibold text-sm">多头研究员</span>
            <span className="ml-auto text-xs text-green-300">{Math.round(debate.bull_confidence * 100)}% 置信</span>
          </div>
          {debate.bull_summary && <p className="text-slate-300 text-xs mb-2">{debate.bull_summary}</p>}
          <ul className="space-y-1">
            {(debate.bull_points || []).map((p, i) => (
              <li key={i} className="text-xs text-green-200 flex gap-1.5"><span className="text-green-500 mt-0.5">+</span>{p}</li>
            ))}
          </ul>
        </div>
        <div className="bg-red-900/20 border border-red-700/30 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingDown size={14} className="text-red-400" />
            <span className="text-red-400 font-semibold text-sm">空头研究员</span>
            <span className="ml-auto text-xs text-red-300">{Math.round(debate.bear_confidence * 100)}% 置信</span>
          </div>
          {debate.bear_summary && <p className="text-slate-300 text-xs mb-2">{debate.bear_summary}</p>}
          <ul className="space-y-1">
            {(debate.bear_points || []).map((p, i) => (
              <li key={i} className="text-xs text-red-200 flex gap-1.5"><span className="text-red-500 mt-0.5">−</span>{p}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Final advice */}
      {debate.final_advice && (
        <div className="flex gap-2 bg-slate-800 rounded-xl px-4 py-3">
          <MessageSquare size={14} className="text-slate-400 mt-0.5 shrink-0" />
          <p className="text-slate-300 text-xs">{debate.final_advice}</p>
        </div>
      )}
    </div>
  )
}

// ── Round Panel ───────────────────────────────────────────────────
function RoundPanel({ round }: { round: Round }) {
  const [tab, setTab] = useState<'curves' | 'table' | 'debate'>('curves')
  const accepted = round.strategies.filter(s => s.decision === 'ACCEPT')
  const rejected = round.strategies.filter(s => s.decision === 'REJECT')

  return (
    <div className="space-y-4">
      {/* Stats bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: '候选策略', value: round.strategies.length, color: '#94a3b8' },
          { label: '通过评估', value: accepted.length, color: '#4ade80' },
          { label: '淘汰', value: rejected.length, color: '#f87171' },
          { label: '最终入选', value: round.selected.length, color: '#fbbf24' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-slate-800 rounded-xl px-4 py-3 border border-slate-700">
            <div className="text-xs text-slate-400">{label}</div>
            <div className="text-2xl font-bold mt-1" style={{ color }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 border-b border-slate-700 pb-1">
        {(['curves', 'table', 'debate'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1 rounded-t text-xs font-medium transition-colors ${
              tab === t ? 'text-white bg-slate-700' : 'text-slate-500 hover:text-slate-300'
            }`}>
            { t === 'curves' ? '回测曲线' : t === 'table' ? '策略明细' : '专家辩论' }
          </button>
        ))}
      </div>

      {tab === 'curves' && (
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-xs text-slate-400 mb-3">
            所有候选策略净值曲线对比（初始=100，实线=入选，虚线=淘汰）
          </div>
          <EquityCurvesChart strategies={round.strategies} />
        </div>
      )}

      {tab === 'table' && (
        <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          <StrategyTable strategies={round.strategies} />
        </div>
      )}

      {tab === 'debate' && (
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <DebatePanel debate={round.debate} />
        </div>
      )}
    </div>
  )
}

// ── Main View ─────────────────────────────────────────────────────
export default function IterationView() {
  const [log, setLog] = useState<IterationLog | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [activeRound, setActiveRound] = useState(1)

  useEffect(() => {
    import('../data/iteration_log.json')
      .then(m => { setLog(m.default as IterationLog); setActiveRound(1) })
      .catch(e => setErr(String(e)))
  }, [])

  if (err) return (
    <div className="p-8 text-red-400 space-y-2">
      <div className="font-bold flex items-center gap-2"><XCircle size={18}/>迭代日志未找到</div>
      <div className="text-sm text-slate-400">运行以下命令生成数据，再重新构建看板：</div>
      <pre className="bg-slate-800 rounded px-4 py-3 text-xs text-yellow-300">
        python3 scripts/run_iteration.py --symbols SPY BTCUSDT --rounds 3
      </pre>
    </div>
  )

  if (!log) return (
    <div className="flex items-center gap-2 text-slate-400 p-8">
      <RefreshCw size={18} className="animate-spin"/>加载中...
    </div>
  )

  const runAt = new Date(log.run_at).toLocaleString('zh-CN')
  const round = log.rounds.find(r => r.round === activeRound) || log.rounds[0]

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <GitBranch size={24} className="text-purple-400" />
          <div>
            <h2 className="text-xl font-bold text-white">迭代过程</h2>
            <p className="text-slate-400 text-sm">
              {log.symbols.join(' · ')} · {log.days}天 · {log.total_rounds}轮迭代
            </p>
          </div>
        </div>
        <div className="text-right text-xs text-slate-500">
          <div>运行时间</div>
          <div className="text-slate-400">{runAt}</div>
        </div>
      </div>

      {/* Global top */}
      {log.global_top.length > 0 && (
        <div className="bg-gradient-to-r from-indigo-900/40 to-purple-900/40 border border-indigo-700/40 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Award size={16} className="text-yellow-400" />
            <span className="font-bold text-white text-sm">全局最优策略</span>
          </div>
          <div className="flex flex-wrap gap-3">
            {log.global_top.map((s: any) => (
              <div key={s.rank} className="bg-slate-800/80 rounded-lg px-3 py-2 text-xs">
                <span className="text-yellow-400 font-bold mr-1">#{s.rank}</span>
                <span className="text-white font-semibold">{s.name}</span>
                <span className="text-slate-400 ml-2">{(s.ann ?? 0).toFixed(1)}% · 夏普{(s.sharpe ?? 0).toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Round tabs */}
      <div className="flex gap-2">
        {log.rounds.map(r => (
          <button key={r.round} onClick={() => setActiveRound(r.round)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
              activeRound === r.round
                ? 'bg-purple-600/30 text-purple-300 border border-purple-500/50'
                : 'bg-slate-800 text-slate-400 border border-slate-700 hover:text-white'
            }`}>
            第 {r.round} 轮
            {r.converged && <CheckCircle size={11} className="text-green-400" />}
          </button>
        ))}
      </div>

      {/* Round content */}
      {round && <RoundPanel round={round} />}
    </div>
  )
}
