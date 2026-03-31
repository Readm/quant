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
interface StrategyVerdict {
  strategy_id: string; strategy_name: string; composite: number
  verdict: string; confidence: number; weight_advice: number
  pros: string[]; cons: string[]; analysis: string
}
interface Debate {
  winner: string; trend_weight: number; mr_weight: number
  verdict_reason: string; final_advice: string
  strategy_verdicts: StrategyVerdict[]
}
interface MetaEvaluation {
  data_validity: string
  invalidity_reasons: string[]
  convergence_is_real: boolean
  should_continue: boolean
  continue_reason: string
  round_summary: string
  key_insight: string
  suggestions: string[]
  _llm_available: boolean
}
interface Round {
  round: number; strategies: Strategy[]
  debate: Debate; holdout: any[]
  selected: string[]; converged: boolean
  meta_evaluation: MetaEvaluation
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

  // Use strategy id as unique dataKey to avoid name collisions
  const minLen = Math.min(...visible.map(s => s.equity_curve.length))
  const data = Array.from({ length: minLen }, (_, i) => {
    const pt: Record<string, number> = { i }
    visible.forEach(s => { pt[s.id] = s.equity_curve[i]?.v ?? 100 })
    return pt
  })

  // Tight Y domain with 1% padding each side
  const allVals = data.flatMap(pt => visible.map(s => pt[s.id] ?? 100))
  const yMin = Math.floor(Math.min(...allVals) * 0.99)
  const yMax = Math.ceil(Math.max(...allVals) * 1.01)

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis dataKey="i" tick={{ fill: '#64748b', fontSize: 10 }}
          label={{ value: '交易日', position: 'insideBottomRight', fill: '#475569', fontSize: 10 }} />
        <YAxis domain={[yMin, yMax]} tick={{ fill: '#64748b', fontSize: 10 }}
          tickFormatter={v => `${v.toFixed(0)}`}
          label={{ value: '净值', angle: -90, position: 'insideLeft', fill: '#475569', fontSize: 10 }} />
        <ReferenceLine y={100} stroke="#475569" strokeDasharray="4 2" />
        <Tooltip
          contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
          formatter={(v: number, _key, props) => {
            const s = visible.find(x => x.id === props.dataKey)
            const label = s ? `${s.name} (${s.type === 'trend' ? '趋势' : 'MR'})` : String(props.dataKey)
            return [`${(v as number).toFixed(2)}`, label]
          }}
        />
        <Legend
          formatter={(_value, entry) => {
            const s = visible.find(x => x.id === entry.dataKey)
            return s ? `${s.name} ${s.params ? Object.values(s.params).join('/') : ''}` : String(entry.dataKey)
          }}
          wrapperStyle={{ fontSize: 10, paddingTop: 6 }}
        />
        {visible.map((s, i) => (
          <Line key={s.id} type="monotone" dataKey={s.id}
            name={s.name}
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

// ── Debate Panel (LLM 策略评审，已移除平局/胜出横幅) ─────────────
function DebatePanel({ debate }: { debate: Debate }) {
  if (!debate) return null
  const verdicts = debate.strategy_verdicts || []
  if (verdicts.length === 0 && !debate.final_advice) return (
    <div className="text-slate-500 text-sm p-4">暂无 LLM 策略评审数据</div>
  )
  return (
    <div className="space-y-3">
      {verdicts.map(sv => {
        const verdictColor = {
          STRONG_BUY: 'text-emerald-400 border-emerald-700/40 bg-emerald-900/20',
          BUY:        'text-green-400  border-green-700/40  bg-green-900/20',
          HOLD:       'text-yellow-400 border-yellow-700/40 bg-yellow-900/20',
          SELL:       'text-red-400    border-red-700/40    bg-red-900/20',
        }[sv.verdict] ?? 'text-slate-400 border-slate-700/40 bg-slate-800/40'
        return (
          <div key={sv.strategy_id} className={`border rounded-xl p-3 ${verdictColor}`}>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-semibold text-sm">{sv.strategy_name}</span>
              <span className="text-xs px-1.5 py-0.5 rounded bg-black/30">{sv.verdict}</span>
              <span className="ml-auto text-xs opacity-70">
                置信 {Math.round(sv.confidence * 100)}% · 仓位 {Math.round(sv.weight_advice * 100)}%
              </span>
            </div>
            {sv.analysis && <p className="text-xs opacity-80 mb-2">{sv.analysis}</p>}
            <div className="grid grid-cols-2 gap-2 text-xs">
              {sv.pros.length > 0 && (
                <ul className="space-y-0.5">
                  {sv.pros.map((p, i) => <li key={i} className="flex gap-1"><span className="opacity-60">+</span>{p}</li>)}
                </ul>
              )}
              {sv.cons.length > 0 && (
                <ul className="space-y-0.5 opacity-70">
                  {sv.cons.map((c, i) => <li key={i} className="flex gap-1"><span>−</span>{c}</li>)}
                </ul>
              )}
            </div>
          </div>
        )
      })}
      {debate.final_advice && (
        <div className="flex gap-2 bg-slate-800 rounded-xl px-4 py-3">
          <MessageSquare size={14} className="text-slate-400 mt-0.5 shrink-0" />
          <p className="text-slate-300 text-xs">{debate.final_advice}</p>
        </div>
      )}
    </div>
  )
}

// ── Meta Expert Panel ─────────────────────────────────────────────
function MetaPanel({ meta }: { meta: MetaEvaluation }) {
  if (!meta || !meta._llm_available) return null

  const validityColor = meta.data_validity === 'HIGH'
    ? 'text-green-400 bg-green-900/20 border-green-700/40'
    : meta.data_validity === 'MEDIUM'
    ? 'text-yellow-400 bg-yellow-900/20 border-yellow-700/40'
    : 'text-red-400 bg-red-900/20 border-red-700/40'

  const continueColor = meta.should_continue
    ? 'text-purple-300 bg-purple-900/20 border-purple-700/40'
    : 'text-slate-400 bg-slate-800/60 border-slate-600/40'

  return (
    <div className="border border-slate-600/60 rounded-xl p-4 bg-slate-900/40 space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-xs font-bold text-slate-300 uppercase tracking-widest">元专家评估</span>
        <span className={`text-xs px-2 py-0.5 rounded border ${validityColor}`}>
          数据可信度 {meta.data_validity}
        </span>
        <span className={`ml-auto text-xs px-2 py-0.5 rounded border ${continueColor}`}>
          {meta.should_continue ? '建议继续迭代' : '可停止迭代'}
        </span>
      </div>

      {meta.round_summary && (
        <p className="text-slate-200 text-sm font-medium">{meta.round_summary}</p>
      )}

      {meta.key_insight && (
        <div className="flex gap-2 text-xs text-amber-300 bg-amber-900/20 rounded-lg px-3 py-2 border border-amber-700/30">
          <span className="shrink-0 font-semibold">关键发现</span>
          <span>{meta.key_insight}</span>
        </div>
      )}

      {(meta.invalidity_reasons || []).length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-slate-500 font-semibold">数据问题</p>
          {meta.invalidity_reasons.map((r, i) => (
            <div key={i} className="flex gap-2 text-xs text-red-300">
              <span className="shrink-0 opacity-60">⚠</span><span>{r}</span>
            </div>
          ))}
        </div>
      )}

      {meta.continue_reason && (
        <p className="text-xs text-slate-400 italic">{meta.continue_reason}</p>
      )}

      {(meta.suggestions || []).length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-slate-500 font-semibold">建议</p>
          {meta.suggestions.map((s, i) => (
            <div key={i} className="flex gap-2 text-xs text-slate-300">
              <span className="shrink-0 text-purple-400">→</span><span>{s}</span>
            </div>
          ))}
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
      {/* Meta expert evaluation */}
      <MetaPanel meta={round.meta_evaluation} />

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
