import { ListOrdered, TrendingUp, TrendingDown, Zap, Shield, Presentation, Scale } from 'lucide-react'

const strategies = [
  {
    type: 'trend',
    Icon: TrendingUp,
    color: '#6366f1',
    strategies: [
      { name: '双均线交叉', key: 'ma_cross',    params: { fast: 20, slow: 60 },   desc: 'MA(10,60)金叉买入，死叉卖出' },
      { name: 'MACD趋势',  key: 'macd',        params: { fp: 12, sp: 26, sig: 9 }, desc: 'MACD(12,26,9) 零轴上方看多' },
      { name: '动量突破',  key: 'momentum',     params: { lookback: 20, threshold: 0.05 }, desc: 'N日动量超过threshold视为趋势' },
      { name: 'ADX趋势确认', key: 'adx_trend', params: { adx_thr: 25, atr_mult: 2.0 }, desc: 'ADX>25确认趋势，ATR止损' },
    ],
  },
  {
    type: 'mean_reversion',
    Icon: TrendingDown,
    color: '#22d3ee',
    strategies: [
      { name: 'RSI均值回归', key: 'rsi',        params: { period: 14, lower: 30, upper: 70 }, desc: 'RSI<30超卖买入，>70超买卖出' },
      { name: '布林带回归', key: 'bollinger',   params: { period: 20, std_mult: 2.0 },     desc: '价格触及布林下轨买入，上轨卖出' },
      { name: '成交量异常', key: 'vol_surge',   params: { vol_ma: 20, threshold: 2.0 },   desc: '成交量突增threshold倍于均值' },
    ],
  },
]

export default function StrategyView() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-4">
        <ListOrdered size={24} className="text-yellow-400" />
        <div>
          <h2 className="text-xl font-bold text-white">策略库</h2>
          <p className="text-slate-400 text-sm">
            趋势策略 · 均值回归策略 · 多专家协作生成
          </p>
        </div>
      </div>

      {/* Strategy templates */}
      {strategies.map(group => (
        <div key={group.type} className="bg-slate-800 rounded-xl p-6 border border-slate-700">
          <div className="flex items-center gap-2 mb-4">
            <group.Icon size={16} style={{ color: group.color }} />
            <h3 className="text-white font-semibold capitalize">
              {group.type === 'trend' ? '📈 趋势策略' : '🔄 均值回归策略'}
            </h3>
            <span className="text-xs text-slate-500 ml-auto">{group.strategies.length} 个模板</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {group.strategies.map(s => (
              <div key={s.key} className="bg-slate-900 rounded-lg p-4 border border-slate-700">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-white text-sm">{s.name}</span>
                  <span className="text-xs font-mono text-slate-500">{s.key}</span>
                </div>
                <div className="text-xs text-slate-400 mb-2">{s.desc}</div>
                <div className="flex flex-wrap gap-1">
                  {Object.entries(s.params).map(([k, v]) => (
                    <span key={k} className="text-xs px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono">
                      {k}={v}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

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

      {/* Key stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: '策略收敛率', value: '94.2%', sub: '3轮内收敛', Icon: TrendingUp, color: '#4ade80' },
          { label: 'Qlib 回测通过率', value: '78.6%', sub: '经Qlib验证', Icon: Shield, color: '#6366f1' },
          { label: '平均夏普比率', value: '0.87', sub: '过Qlib验证', Icon: Zap, color: '#fbbf24' },
        ].map(m => (
          <div key={m.label} className="bg-slate-800 rounded-xl p-4 border border-slate-700 text-center">
            <div className="text-xs text-slate-500 mb-1">{m.label}</div>
            <div className="text-2xl font-bold" style={{ color: m.color }}>{m.value}</div>
            <div className="text-xs text-slate-500 mt-0.5">{m.sub}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
