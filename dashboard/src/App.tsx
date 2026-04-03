import { useState } from 'react'
import { BarChart3, Database, Brain, Layers, ListOrdered, Circle, Activity, GitBranch } from 'lucide-react'
import DataSourceView from './views/DataSourceView'
import BacktestView from './views/BacktestView'
import ExpertView from './views/ExpertView'
import FactorView from './views/FactorView'
import StrategyView from './views/StrategyView'
import SystemStatusView from './views/SystemStatusView'
import IterationView from './views/IterationView'

type ViewKey = 'status' | 'data' | 'backtest' | 'expert' | 'factor' | 'strategy' | 'iteration'

const NAV = [
  { key: 'iteration' as ViewKey, label: '迭代过程', Icon: GitBranch,   color: '#a855f7' },
  { key: 'status'    as ViewKey, label: '系统状态', Icon: Activity,    color: '#94a3b8' },
  { key: 'data'      as ViewKey, label: '数据来源', Icon: Database,    color: '#22d3ee' },
  { key: 'backtest'  as ViewKey, label: '回测框架', Icon: BarChart3,   color: '#6366f1' },
  { key: 'expert'    as ViewKey, label: '专家框架', Icon: Brain,       color: '#a78bfa' },
  { key: 'factor'    as ViewKey, label: '因子库',   Icon: Layers,      color: '#4ade80' },
  { key: 'strategy'  as ViewKey, label: '策略库',   Icon: ListOrdered, color: '#fbbf24' },
]

const VIEWS: Record<ViewKey, React.ComponentType> = {
  status:    SystemStatusView,
  data:      DataSourceView,
  backtest:  BacktestView,
  expert:    ExpertView,
  factor:    FactorView,
  strategy:  StrategyView,
  iteration: IterationView,
}

export default function App() {
  const [active, setActive] = useState<ViewKey>('iteration')

  const View = VIEWS[active]

  return (
    <div className="min-h-screen bg-slate-900 text-white font-sans">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-slate-950/90 backdrop-blur-md border-b border-slate-800 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <BarChart3 size={16} className="text-white" />
            </div>
            <div>
              <div className="font-bold text-white leading-none">Quant System</div>
              <div className="text-xs text-slate-500 leading-none mt-0.5">
                专家系统策略平台 · v3.0
              </div>
            </div>
          </div>
          <div className="hidden md:flex items-center gap-2 text-xs text-slate-500">
            <Circle size={6} className="text-green-400 fill-green-400" />
            <span>GitHub Pages · CI/CD</span>
            <span className="mx-2 text-slate-700">·</span>
            <span>Qlib + quant 融合引擎</span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="max-w-7xl mx-auto mt-3 flex gap-1 overflow-x-auto">
          {NAV.map(({ key, label, Icon, color }) => (
            <button
              key={key}
              onClick={() => setActive(key)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap"
              style={{
                backgroundColor: active === key ? color + '22' : 'transparent',
                color:        active === key ? color       : '#64748b',
                border:       active === key ? `1px solid ${color}44` : '1px solid transparent',
              }}
            >
              <Icon size={13} />
              {label}
            </button>
          ))}
        </nav>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-6 py-6">
        <View />
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800 mt-8 py-4 px-6">
        <div className="max-w-7xl mx-auto flex items-center justify-between text-xs text-slate-600">
          <span>Quant System v3.0 · Built with React + Vite · Deployed via GitHub Actions</span>
          <span>Powered by Qlib (微软亚洲研究院) + quant (Readm)</span>
        </div>
      </footer>
    </div>
  )
}
