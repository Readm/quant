import { Database, Cloud, Server, BarChart2, Globe } from 'lucide-react'

const dataSources = [
  {
    source: '腾讯财经 A股日K',
    symbol: 'sh.600519',
    interval: '日线（1d）',
    period: '2015-01-01 ~ 最新',
    fields: 'open / high / low / close / volume',
    color: '#ef4444',
    tag: '主力数据',
  },
  {
    source: 'Yahoo Finance 美股',
    symbol: 'SPY, QQQ',
    interval: '日线（1d）',
    period: '2010-01-01 ~ 最新',
    fields: 'adjusted close / volume',
    color: '#6366f1',
    tag: '美股',
  },
  {
    source: 'Binance 加密货币',
    symbol: 'BTC/USDT',
    interval: '1min / 5min / 1d',
    period: '2020-01-01 ~ 最新',
    fields: 'open / high / low / close / volume',
    color: '#f59e0b',
    tag: '加密',
  },
  {
    source: 'Qlib CN_DATA (GitHub)',
    symbol: '全市场 A股',
    interval: '日线 / 1分钟线',
    period: '2008-01-01 ~ 2020-08',
    fields: 'OHLCV + Alpha158 因子集',
    color: '#22d3ee',
    tag: 'Qlib官方',
  },
]

export default function DataSourceView() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-4">
        <Database size={24} className="text-cyan-400" />
        <div>
          <h2 className="text-xl font-bold text-white">数据来源</h2>
          <p className="text-slate-400 text-sm">
            多数据源 · Qlib 二进制格式 · 本地 JSON 缓存
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {dataSources.map(ds => (
          <div key={ds.source} className="bg-slate-800 rounded-xl p-5 border border-slate-700">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Globe size={14} style={{ color: ds.color }} />
                <span className="font-semibold text-white text-sm">{ds.source}</span>
              </div>
              <span
                className="text-xs px-2 py-0.5 rounded font-mono"
                style={{ backgroundColor: ds.color + '22', color: ds.color }}
              >
                {ds.tag}
              </span>
            </div>
            <div className="space-y-2 text-xs">
              {[
                { label: '标的',    value: ds.symbol },
                { label: '时间粒度', value: ds.interval },
                { label: '时间范围', value: ds.period },
                { label: '数据字段', value: ds.fields },
              ].map(row => (
                <div key={row.label} className="flex gap-2">
                  <span className="text-slate-500 w-16 flex-shrink-0">{row.label}</span>
                  <span className="text-slate-300 font-mono">{row.value}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Qlib vs quant Data Architecture */}
      <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
        <h3 className="text-white font-semibold mb-4">📐 数据架构（Qlib + quant 融合）</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          {[
            {
              title: 'quant 数据采集',
              desc: '腾讯财经日K / Yahoo Finance / Binance\n↓\nJSON 本地缓存',
              color: '#fbbf24',
              icon: Cloud,
            },
            {
              title: 'quant → Qlib 转换',
              desc: 'JSON → Qlib 二进制格式 (.pkl)\n↓\n统一因子表达式引擎',
              color: '#22d3ee',
              icon: Server,
            },
            {
              title: 'Qlib 数据服务',
              desc: 'qlib.data.D 高性能查询\n↓\nAlpha158 / Alpha360 因子计算',
              color: '#4ade80',
              icon: BarChart2,
            },
          ].map(item => (
            <div
              key={item.title}
              className="rounded-lg p-4 border"
              style={{ backgroundColor: item.color + '11', borderColor: item.color + '33' }}
            >
              <div className="flex items-center gap-2 mb-2">
                <item.icon size={13} style={{ color: item.color }} />
                <span className="font-medium text-white">{item.title}</span>
              </div>
              <pre className="text-slate-400 whitespace-pre-wrap leading-relaxed">{item.desc}</pre>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
