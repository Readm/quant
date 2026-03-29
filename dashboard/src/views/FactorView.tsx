import { Layers, CheckCircle2, GitBranch } from 'lucide-react'

const factorComparison = [
  // Qlib 已有（重叠）
  { id: 'KST',             name: 'Know Sure Thing',       source: 'Qlib',       priority: '✅ 已覆盖' },
  { id: 'Aroon',           name: 'Aroon Up/Down/Osc',     source: 'Qlib',       priority: '✅ 已覆盖' },
  { id: 'Donchian Channel', name: 'Donchian 通道',        source: 'Qlib',       priority: '✅ 已覆盖' },
  { id: 'OBOS Composite',  name: 'OBOS 综合指标',         source: 'Qlib',       priority: '✅ 已覆盖' },
  { id: 'PPO',             name: '价格百分比震荡',         source: 'Qlib',       priority: '✅ 已覆盖' },
  { id: 'Momentum Matrix', name: '多周期ROC矩阵',         source: 'Qlib',       priority: '✅ 已覆盖' },
  { id: 'RVI',             name: '相对波动率指数',         source: 'Qlib',       priority: '✅ 已覆盖' },
  { id: 'MFI Signal',      name: 'MFI 信号',               source: 'Qlib',       priority: '✅ 已覆盖' },
]

const quantUnique = [
  // quant 独有 TODO
  { id: 'F001', name: 'Ichimoku Cloud',        nameCn: '一目均衡表',    priority: '★★★★★', note: '经典5线系统，Qlib完全无对应' },
  { id: 'F002', name: 'Ichimoku Signal',       nameCn: 'Ichimoku信号',  priority: '★★★★☆', note: '基于 Ichimoku Cloud 的交易信号' },
  { id: 'F003', name: 'Accumulation/Distribution', nameCn: '累积派发线', priority: '★★★★★', note: 'Chaikin AD，量价经典指标' },
  { id: 'F004', name: 'Chanlun Bi',            nameCn: '缠论笔',         priority: '★★★★★', note: '缠论核心概念，Qlib完全无对应' },
  { id: 'F005', name: 'Chanlun Tao',           nameCn: '缠论线段',       priority: '★★★★☆', note: '缠论线段简化，Qlib完全无对应' },
  { id: 'F006', name: 'Parabolic SAR',         nameCn: '抛物线止损转向', priority: '★★★★☆', note: '趋势+止损，Qlib无原生对应' },
  { id: 'F007', name: 'Elder Ray',              nameCn: '艾达透视',       priority: '★★★★☆', note: 'Elder三大指标之一，Qlib完全无对应' },
  { id: 'F008', name: 'Force Index',            nameCn: '强力指数',       priority: '★★★★☆', note: 'Elder三大指标之一' },
  { id: 'F009', name: 'Chaikin Oscillator',    nameCn: 'Chaikin震荡',   priority: '★★★★☆', note: 'AD线的EMA差值，Qlib完全无对应' },
  { id: 'F010', name: 'Ultra Spline',           nameCn: '二次样条趋势',   priority: '★★★☆☆', note: '自定义非线性趋势拟合' },
  { id: 'F011', name: 'KDJ Wave',               nameCn: 'KD波浪',         priority: '★★★☆☆', note: 'KDJ指标的波浪化' },
  { id: 'F012', name: 'Mass Index',             nameCn: '梅斯线',         priority: '★★★☆☆', note: '波动率突破指标' },
  { id: 'F013', name: 'TRIX',                   nameCn: '三重指数平滑',   priority: '★★★☆☆', note: '三重EMA嵌套消除噪音' },
]

const qlibAlpha158 = [
  { family: 'KBar',     count: 9,   desc: 'open/high/low/close/volume + VR/DBRP' },
  { family: 'Price',    count: 20,  desc: '开盘/收盘价衍生指标（ROIC/PE/PS/PC）' },
  { family: 'Volume',   count: 5,   desc: '成交量衍生指标（VWAP/OBV/市场外成交）' },
  { family: 'Rolling',  count: 150, desc: '30算子 × 5窗口（Mean/Std/Max/Min/Sum等）' },
]

function PriorityBadge({ priority }: { priority: string }) {
  const starCount = priority.replace(/[^★]/g, '').length
  const stars = '★'.repeat(starCount) + '☆'.repeat(5 - starCount)
  const color = starCount >= 4 ? '#4ade80' : starCount === 3 ? '#fbbf24' : '#94a3b8'
  return (
    <span className="font-mono text-xs" style={{ color }}>
      {stars}
    </span>
  )
}

export default function FactorView() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-4">
        <Layers size={24} className="text-green-400" />
        <div>
          <h2 className="text-xl font-bold text-white">因子库</h2>
          <p className="text-slate-400 text-sm">
            quant 因子 vs Qlib Alpha158/360 · 对比报告 · TODO 清单
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'quant 因子总数',  value: '32',   sub: '个函数',         color: '#fbbf24' },
          { label: 'Qlib 已有',       value: '12',   sub: '无需重复实现',    color: '#4ade80' },
          { label: 'quant 独有',      value: '20',   sub: '建议补入 Qlib',  color: '#f87171' },
          { label: 'Qlib Alpha158',   value: '184',  sub: '含滚动因子150个', color: '#6366f1' },
        ].map(m => (
          <div key={m.label} className="bg-slate-800 rounded-xl p-4 border border-slate-700 text-center">
            <div className="text-xs text-slate-500 mb-1">{m.label}</div>
            <div className="text-2xl font-bold" style={{ color: m.color }}>{m.value}</div>
            <div className="text-xs text-slate-500 mt-0.5">{m.sub}</div>
          </div>
        ))}
      </div>

      {/* Qlib Alpha158 Structure */}
      <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
        <h3 className="text-white font-semibold mb-4">🧬 Qlib Alpha158 因子结构</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {qlibAlpha158.map(f => (
            <div key={f.family} className="bg-slate-900 rounded-lg p-4 border border-slate-700">
              <div className="text-xs text-slate-500 mb-1">{f.family}</div>
              <div className="text-xl font-bold text-indigo-400">{f.count}</div>
              <div className="text-xs text-slate-500 mt-1">{f.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Qlib Already Covered */}
      <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
        <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
          <CheckCircle2 size={16} className="text-green-400" />
          Qlib 已有对应（无需重复实现）
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {factorComparison.map(f => (
            <div key={f.id} className="bg-slate-900 rounded-lg px-3 py-2 border border-slate-700">
              <div className="text-xs font-mono text-indigo-400">{f.id}</div>
              <div className="text-xs text-slate-300 mt-0.5">{f.name}</div>
            </div>
          ))}
        </div>
      </div>

      {/* quant Unique — TODO */}
      <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
        <h3 className="text-white font-semibold mb-4 flex items-center gap-2">
          <GitBranch size={16} className="text-yellow-400" />
          quant 独有因子（建议接入 Qlib）— TODO 清单
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-700">
                <th className="text-left py-2 px-2 font-medium">编号</th>
                <th className="text-left py-2 px-2 font-medium">英文名</th>
                <th className="text-left py-2 px-2 font-medium">中文名</th>
                <th className="text-left py-2 px-2 font-medium">优先级</th>
                <th className="text-left py-2 px-2 font-medium">备注</th>
              </tr>
            </thead>
            <tbody>
              {quantUnique.map(f => (
                <tr key={f.id} className="border-b border-slate-800 hover:bg-slate-700/30">
                  <td className="py-2 px-2 font-mono text-yellow-400">{f.id}</td>
                  <td className="py-2 px-2 text-slate-300">{f.name}</td>
                  <td className="py-2 px-2 text-slate-400">{f.nameCn}</td>
                  <td className="py-2 px-2"><PriorityBadge priority={f.priority} /></td>
                  <td className="py-2 px-2 text-slate-500">{f.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
