import { BarChart3, TrendingUp, Shield, Activity, Zap } from 'lucide-react'
import { XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ComposedChart, Bar } from 'recharts'

const backtestResults = [
  { year:"2022",      benchmark:-21.3, strategy:8.1  },
  { year:"2023",      benchmark:-11.7, strategy:15.2 },
  { year:"2024",      benchmark:16.2,  strategy:28.4 },
  { year:"2025(YTD)", benchmark:5.3,   strategy:12.1 },
]

const metrics = [
  { Icon:TrendingUp, label:"初始资金",  value:"¥1,000,000", color:"#6366f1" },
  { Icon:Shield,     label:"手续费",    value:"0.03%",       color:"#22d3ee" },
  { Icon:Activity,   label:"滑点",      value:"0.05%",       color:"#4ade80" },
  { Icon:Zap,        label:"信号模式",  value:"T+1确认",     color:"#fbbf24" },
]

const scores = [
  { label:"夏普比率", val:"≥1.0 → 40分", color:"#6366f1" },
  { label:"最大回撤", val:"≤5% → 40分",  color:"#f87171" },
  { label:"年化收益", val:"≥30% → 40分", color:"#4ade80" },
  { label:"交易次数", val:"5~50次 → 20分", color:"#fbbf24" },
  { label:"胜率",     val:"40~85% → 20分", color:"#22d3ee" },
]

function StatCard({ Icon, label, value, color }: { Icon: React.ComponentType<any>; label: string; value: string; color: string }) {
  return (
    <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
      <div className="flex items-center gap-3 mb-3">
        <div className="p-2 rounded-lg" style={{ backgroundColor: color + '22' }}>
          <Icon size={18} style={{ color }} />
        </div>
        <span className="text-slate-400 text-sm">{label}</span>
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
    </div>
  )
}

export default function BacktestView() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-4">
        <BarChart3 size={24} className="text-indigo-400" />
        <div><h2 className="text-xl font-bold text-white">回测框架</h2><p className="text-slate-400 text-sm">Unified Backtest Engine · 多品种 · 多仓位</p></div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {metrics.map(s => <StatCard key={s.label} Icon={s.Icon} label={s.label} value={s.value} color={s.color} />)}
      </div>

      <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
        <h3 className="text-white font-semibold mb-4">年度收益对比（最优策略 vs 沪深300基准）</h3>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={backtestResults} barGap={4}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="year" tick={{ fill:'#94a3b8', fontSize:12 }} />
            <YAxis tick={{ fill:'#94a3b8', fontSize:11 }} tickFormatter={(v) => v+'%'} />
            <Tooltip contentStyle={{ backgroundColor:'#1e293b', border:'1px solid #334155', borderRadius:8 }} labelStyle={{ color:'#fff' }} />
            <Legend wrapperStyle={{ color:'#94a3b8', fontSize:12 }} />
            <Bar dataKey="benchmark" name="沪深300基准" fill="#334155" radius={[4,4,0,0]} />
            <Bar dataKey="strategy" name="最优策略" fill="#6366f1" radius={[4,4,0,0]} />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="flex gap-4 mt-3 text-xs flex-wrap">
          {backtestResults.map(r => (
            <span key={r.year}>
              <span className="text-slate-400">{r.year}: </span>
              <span style={{ color: r.strategy > r.benchmark ? '#4ade80' : '#f87171' }}>{r.strategy > 0 ? '+' : ''}{r.strategy}%</span>
              <span className="text-slate-600 ml-1">(基准 {r.benchmark > 0 ? '+' : ''}{r.benchmark}%)</span>
            </span>
          ))}
        </div>
      </div>

      <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
        <h3 className="text-white font-semibold mb-4">评分体系（满分200分）</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {scores.map((m, i) => (
            <div key={i} className="bg-slate-900 rounded-lg p-3 border border-slate-700 text-center">
              <div className="text-xs text-slate-500 mb-1">{m.label}</div>
              <div className="text-sm font-bold" style={{ color: m.color }}>{m.val}</div>
            </div>
          ))}
        </div>
        <div className="mt-3 text-xs text-slate-500">等级: A ≥140分 / B ≥100分 / C ≥60分 / D &lt;60分</div>
      </div>
    </div>
  )
}
