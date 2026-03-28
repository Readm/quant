import { useState } from 'react'
import { BarChart3, Database, Brain, Layers, ListOrdered, Circle } from 'lucide-react'
import DataSourceView from './views/DataSourceView'
import BacktestView from './views/BacktestView'
import ExpertView from './views/ExpertView'
import FactorView from './views/FactorView'
import StrategyView from './views/StrategyView'

type ViewKey = 'data' | 'backtest' | 'expert' | 'factor' | 'strategy'

const NAV = [
  { key: 'data' as ViewKey,     label: '数据来源',  Icon: Database,    color: '#22d3ee' },
  { key: 'backtest' as ViewKey, label: '回测框架',  Icon: BarChart3,   color: '#6366f1' },
  { key: 'expert' as ViewKey,   label: '专家框架',  Icon: Brain,       color: '#a78bfa' },
  { key: 'factor' as ViewKey,   label: '因子库',    Icon: Layers,      color: '#4ade80' },
  { key: 'strategy' as ViewKey, label: '策略库',   Icon: ListOrdered, color: '#fbbf24' },
]

export default function App() {
  const [active, setActive] = useState<ViewKey>('data')

  return (
    <div className="min-h-screen bg-slate-900 text-white font-sans">
      {/* Header */}
      <div className="sticky top-0 z-50 bg-slate-950/90 backdrop-blur-md border-b border-slate-800 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <BarChart3 size={16} className="text-white" />
            </div>
            <div>
              <div className="font-bold text-white leading-none">Quant System</div>
              <div className="text-xs text-slate-500 leading-none mt-0.5">专家系统策略平台 · v3.0</div>
            </div>
          </div>
          <div className="hidden md:flex items-center gap-2 text-xs text-slate-500">
            <Circle size={6} className="text-green-400 fill-green-400" />
            <span>实时监控中</span>
            <span className="mx-2 text-slate-700">·</span>
            <span>Thread C · 2026-03-26</span>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Nav */}
        <div className="flex gap-2 mb-6 overflow-x-auto pb-1">
          {NAV.map(item => {
            const Ic = item.Icon
            const isActive = active === item.key
            return (
              <button key={item.key} onClick={() => setActive(item.key)}
                className={"flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all whitespace-nowrap " +
                  (isActive ? 'text-white shadow-lg' : 'text-slate-400 hover:text-white hover:bg-slate-800')}
                style={isActive ? { backgroundColor: item.color + '22', border: '1px solid ' + item.color + '44' } : {}}>
                <Ic size={18} style={{ color: isActive ? item.color : undefined }} />
                {item.label}
              </button>
            )
          })}
        </div>

        {/* Views */}
        {active === 'data'     && <DataSourceView />}
        {active === 'backtest' && <BacktestView />}
        {active === 'expert'    && <ExpertView />}
        {active === 'factor'    && <FactorView />}
        {active === 'strategy'  && <StrategyView />}
      </div>

      {/* Footer */}
      <div className="border-t border-slate-800 mt-8 px-6 py-3 text-center text-xs text-slate-600">
        Quant System v3.0 · 专家系统进化引擎 · 数据: 腾讯证券 / 东方财富 / 新浪财经 / Stooq · 缓存: ~/.openclaw/quant_cache/
      </div>
    </div>
  )
}
