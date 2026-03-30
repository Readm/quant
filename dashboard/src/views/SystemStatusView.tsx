import { useState, useEffect } from 'react'
import { Activity, Database, Layers, Brain, BarChart3, Settings,
         CheckCircle, XCircle, AlertCircle, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'

// ── Types ────────────────────────────────────────────────────────
interface ModuleEntry { name: string; status: 'ok' | 'error' | 'warn'; error?: string }
interface DataSymbol  { symbol: string; source: string; count: number; start: string; end: string; last_close: number; change_pct: number }

interface Status {
  generated_at: string
  data:       { status: string; count: number; symbols: DataSymbol[] }
  factors:    { status: string; files: string[]; export_count: number; factor_table: number; errors: string[] }
  strategies: { status: string; total: number; ok: number; errors: string[]; modules: ModuleEntry[] }
  experts:    { status: string; total: number; ok: number; errors: string[]; modules: ModuleEntry[] }
  backtest:   { status: string; engines: ModuleEntry[] }
  config:     { status: string; initial_capital?: number; max_drawdown?: number; commission_rate?: number; error?: string }
}

// ── Helper components ────────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  if (status === 'ok')
    return <span className="flex items-center gap-1 text-green-400 text-xs font-semibold"><CheckCircle size={12}/> OK</span>
  if (status === 'error')
    return <span className="flex items-center gap-1 text-red-400 text-xs font-semibold"><XCircle size={12}/> ERROR</span>
  return <span className="flex items-center gap-1 text-yellow-400 text-xs font-semibold"><AlertCircle size={12}/> WARN</span>
}

function ModuleList({ modules, defaultOpen = false }: { modules: ModuleEntry[]; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  const errors = modules.filter(m => m.status !== 'ok')
  return (
    <div className="mt-2">
      <button onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-slate-400 hover:text-white transition-colors">
        {open ? <ChevronDown size={12}/> : <ChevronRight size={12}/>}
        {open ? '收起' : `展开详情 (${errors.length} 个问题)`}
      </button>
      {open && (
        <div className="mt-2 space-y-1 max-h-52 overflow-y-auto pr-1">
          {modules.map(m => (
            <div key={m.name}
              className="flex items-start gap-2 px-3 py-1.5 rounded-lg bg-slate-900/60 text-xs">
              {m.status === 'ok'
                ? <CheckCircle size={11} className="text-green-400 mt-0.5 shrink-0"/>
                : <XCircle    size={11} className="text-red-400 mt-0.5 shrink-0"/>}
              <span className="text-slate-300 font-mono">{m.name}</span>
              {m.error && <span className="text-red-300/70 truncate">{m.error}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Layer cards ──────────────────────────────────────────────────
function DataCard({ data }: { data: Status['data'] }) {
  const [open, setOpen] = useState(false)
  const bySource: Record<string, DataSymbol[]> = {}
  data.symbols.forEach(s => {
    const src = s.source || 'unknown'
    ;(bySource[src] = bySource[src] || []).push(s)
  })
  return (
    <LayerCard color="#22d3ee" Icon={Database} title="Layer 1 · 数据层" status={data.status}
      metrics={[
        { label: '已缓存标的', value: String(data.count) },
        { label: '数据来源',   value: Object.keys(bySource).join(' / ') || '—' },
      ]}>
      <button onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-slate-400 hover:text-white transition-colors mt-2">
        {open ? <ChevronDown size={12}/> : <ChevronRight size={12}/>}
        {open ? '收起' : '查看所有标的'}
      </button>
      {open && (
        <div className="mt-2 space-y-1 max-h-52 overflow-y-auto pr-1">
          {data.symbols.map(s => (
            <div key={s.symbol}
              className="grid grid-cols-[80px_1fr_60px_70px] gap-2 px-3 py-1.5 rounded-lg bg-slate-900/60 text-xs items-center">
              <span className="font-mono text-cyan-300">{s.symbol}</span>
              <span className="text-slate-400">{s.start} → {s.end}</span>
              <span className="text-slate-400 text-right">{s.count}天</span>
              <span className={`text-right font-semibold ${s.change_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {s.change_pct >= 0 ? '+' : ''}{s.change_pct}%
              </span>
            </div>
          ))}
        </div>
      )}
    </LayerCard>
  )
}

function FactorCard({ factors }: { factors: Status['factors'] }) {
  return (
    <LayerCard color="#4ade80" Icon={Layers} title="Layer 2 · 因子库" status={factors.status}
      metrics={[
        { label: 'FACTOR_TABLE 注册', value: String(factors.factor_table) },
        { label: '导出函数',          value: String(factors.export_count) },
        { label: '文件数',            value: String(factors.files.length) },
      ]}>
      <div className="mt-2 flex flex-wrap gap-1">
        {factors.files.map(f => (
          <span key={f} className="px-2 py-0.5 bg-slate-900/60 rounded text-xs font-mono text-green-300">{f}</span>
        ))}
      </div>
      {factors.errors.length > 0 && (
        <div className="mt-2 space-y-1">
          {factors.errors.map((e, i) => (
            <div key={i} className="text-xs text-red-300 bg-red-900/20 rounded px-2 py-1">{e}</div>
          ))}
        </div>
      )}
    </LayerCard>
  )
}

function StrategyCard({ strategies }: { strategies: Status['strategies'] }) {
  return (
    <LayerCard color="#fbbf24" Icon={BarChart3} title="Layer 3 · 策略库" status={strategies.status}
      metrics={[
        { label: '模块总数',  value: String(strategies.total) },
        { label: '加载成功',  value: String(strategies.ok), highlight: strategies.ok === strategies.total },
        { label: '加载失败',  value: String(strategies.total - strategies.ok) },
      ]}>
      <ModuleList modules={strategies.modules} defaultOpen={strategies.ok < strategies.total} />
    </LayerCard>
  )
}

function ExpertCard({ experts }: { experts: Status['experts'] }) {
  return (
    <LayerCard color="#a78bfa" Icon={Brain} title="Layer 4 · 专家系统" status={experts.status}
      metrics={[
        { label: '模块总数',  value: String(experts.total) },
        { label: '加载成功',  value: String(experts.ok), highlight: experts.ok === experts.total },
        { label: '加载失败',  value: String(experts.total - experts.ok) },
      ]}>
      <ModuleList modules={experts.modules} defaultOpen={experts.ok < experts.total} />
    </LayerCard>
  )
}

function BacktestCard({ backtest }: { backtest: Status['backtest'] }) {
  return (
    <LayerCard color="#6366f1" Icon={BarChart3} title="Layer 5 · 回测引擎" status={backtest.status}
      metrics={[
        { label: '引擎', value: backtest.engines.filter(e => e.status === 'ok').map(e => e.name).join(' / ') || '—' },
      ]}>
      <div className="mt-2 space-y-1">
        {backtest.engines.map(e => (
          <div key={e.name}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900/60 text-xs">
            {e.status === 'ok'
              ? <CheckCircle size={11} className="text-green-400 shrink-0"/>
              : <XCircle    size={11} className="text-red-400 shrink-0"/>}
            <span className="font-mono text-slate-300">{e.name}</span>
            {e.error && <span className="text-red-300/70 truncate">{e.error}</span>}
          </div>
        ))}
      </div>
    </LayerCard>
  )
}

function ConfigCard({ config }: { config: Status['config'] }) {
  return (
    <LayerCard color="#94a3b8" Icon={Settings} title="Config · 系统配置" status={config.status}
      metrics={[
        { label: '初始资金',   value: config.initial_capital != null ? `¥${config.initial_capital?.toLocaleString()}` : '—' },
        { label: '最大回撤限制', value: config.max_drawdown   != null ? `${(config.max_drawdown! * 100).toFixed(0)}%` : '—' },
        { label: '手续费率',   value: config.commission_rate != null ? `${(config.commission_rate! * 100).toFixed(3)}%` : '—' },
      ]}>
      {config.error && <div className="mt-2 text-xs text-red-300">{config.error}</div>}
    </LayerCard>
  )
}

// ── Generic layer card ────────────────────────────────────────────
interface Metric { label: string; value: string; highlight?: boolean }
function LayerCard({ color, Icon, title, status, metrics, children }: {
  color: string; Icon: React.ComponentType<any>; title: string
  status: string; metrics: Metric[]; children?: React.ReactNode
}) {
  return (
    <div className="bg-slate-800 rounded-xl p-5 border border-slate-700" style={{ borderLeftColor: color, borderLeftWidth: 3 }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon size={16} style={{ color }} />
          <span className="font-semibold text-sm text-white">{title}</span>
        </div>
        <StatusBadge status={status} />
      </div>
      <div className="flex flex-wrap gap-4">
        {metrics.map(m => (
          <div key={m.label}>
            <div className="text-xs text-slate-500">{m.label}</div>
            <div className={`text-lg font-bold ${m.highlight ? 'text-green-400' : 'text-white'}`}>{m.value}</div>
          </div>
        ))}
      </div>
      {children}
    </div>
  )
}

// ── Overall health bar ────────────────────────────────────────────
function HealthBar({ status }: { status: Status }) {
  const layers = [status.data, status.factors, status.strategies, status.experts, status.backtest, status.config]
  const okCount = layers.filter(l => l.status === 'ok').length
  const pct = Math.round(okCount / layers.length * 100)
  const color = pct === 100 ? '#4ade80' : pct >= 66 ? '#fbbf24' : '#f87171'
  return (
    <div className="bg-slate-800 rounded-xl p-5 border border-slate-700 mb-6">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Activity size={18} className="text-slate-400" />
          <span className="font-bold text-white">系统整体状态</span>
        </div>
        <span className="text-sm text-slate-400">{okCount}/{layers.length} 层正常</span>
      </div>
      <div className="h-3 bg-slate-700 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <div className="mt-2 flex justify-between text-xs text-slate-500">
        <span>数据层 · 因子库 · 策略库 · 专家系统 · 回测引擎 · 配置</span>
        <span style={{ color }}>{pct}%</span>
      </div>
    </div>
  )
}

// ── Main view ─────────────────────────────────────────────────────
export default function SystemStatusView() {
  const [status, setStatus] = useState<Status | null>(null)
  const [error,  setError]  = useState<string | null>(null)

  useEffect(() => {
    import('../data/status.json')
      .then(m => setStatus(m.default as Status))
      .catch(e => setError(String(e)))
  }, [])

  if (error)
    return (
      <div className="flex items-center gap-3 text-red-400 p-8">
        <XCircle size={24} />
        <div>
          <div className="font-bold">无法加载状态数据</div>
          <div className="text-sm text-slate-400 mt-1">运行 <code className="text-yellow-300">python3 scripts/build_status.py</code> 后重新构建</div>
          <div className="text-xs text-slate-500 mt-1">{error}</div>
        </div>
      </div>
    )

  if (!status)
    return <div className="flex items-center gap-2 text-slate-400 p-8"><RefreshCw size={18} className="animate-spin"/> 加载中...</div>

  const genTime = new Date(status.generated_at).toLocaleString('zh-CN')

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <Activity size={24} className="text-slate-300" />
          <div>
            <h2 className="text-xl font-bold text-white">系统状态</h2>
            <p className="text-slate-400 text-sm">各模块加载状态 · 数据覆盖 · 配置检查</p>
          </div>
        </div>
        <div className="text-xs text-slate-500">上次扫描: {genTime}</div>
      </div>

      <HealthBar status={status} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <DataCard     data={status.data} />
        <FactorCard   factors={status.factors} />
        <StrategyCard strategies={status.strategies} />
        <ExpertCard   experts={status.experts} />
        <BacktestCard backtest={status.backtest} />
        <ConfigCard   config={status.config} />
      </div>
    </div>
  )
}
