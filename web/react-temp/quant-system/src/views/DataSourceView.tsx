import { Globe, Database } from 'lucide-react'

const sources = [
  { name:'腾讯证券', type:'A股日线', status:'active', latency:'<50ms', rows:'242条/年', cover:['沪深300','上证指数','行业指数'] },
  { name:'东方财富', type:'期货/板块', status:'active', latency:'<100ms', rows:'实时', cover:['申万行业','商品期货','资金流'] },
  { name:'新浪财经', type:'期货K线', status:'partial', latency:'<200ms', rows:'日线', cover:['螺纹钢','沪铜','黄金'] },
  { name:'Stooq',   type:'加密/港股', status:'active', latency:'<500ms', rows:'日线', cover:['BTC','ETH','AAPL'] },
  { name:'TuShare', type:'A股详细', status:'inactive', latency:'N/A', rows:'积分不足', cover:['财报','融资融券'] },
]

export default function DataSourceView() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-4">
        <Database size={24} className="text-cyan-400" />
        <div>
          <h2 className="text-xl font-bold text-white">数据来源与数据库</h2>
          <p className="text-slate-400 text-sm">多源冗余 · 本地持久化缓存</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {sources.map(s => (
          <div key={s.name} className="bg-slate-800 rounded-xl p-5 border border-slate-700">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Globe size={16} className="text-slate-400" />
                <span className="font-semibold text-white">{s.name}</span>
              </div>
              <span className="px-2 py-0.5 rounded-full text-xs font-medium"
                style={{
                  backgroundColor: s.status==='active'?'#4ade8022':s.status==='partial'?'#fbbf2422':'#f8717122',
                  color: s.status==='active'?'#4ade80':s.status==='partial'?'#fbbf24':'#f87171'
                }}>
                {s.status==='active'?'● 运行中':s.status==='partial'?'● 部分':'✕ 停用'}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="bg-slate-900 rounded p-2">
                <div className="text-slate-500 text-xs">类型</div>
                <div className="text-white">{s.type}</div>
              </div>
              <div className="bg-slate-900 rounded p-2">
                <div className="text-slate-500 text-xs">延迟</div>
                <div className="text-white">{s.latency}</div>
              </div>
              <div className="bg-slate-900 rounded p-2 col-span-2">
                <div className="text-slate-500 text-xs">覆盖</div>
                <div className="text-slate-300 text-xs">{s.cover.join(' · ')}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label:'指数数据', val:'5个',  file:'sh000300_2024.csv', color:'#6366f1' },
          { label:'股票数据', val:'10个', file:'sh600519_2024.csv', color:'#22d3ee' },
          { label:'申万行业', val:'50个', file:'sectors_daily.json', color:'#4ade80' },
          { label:'策略存档', val:'3个',  file:'thread_c_expert_v*.json', color:'#fbbf24' },
        ].map(c => (
          <div key={c.label} className="bg-slate-800 rounded-lg p-4 border border-slate-700">
            <div className="text-xs text-slate-500 mb-1">{c.label}</div>
            <div className="text-xl font-bold" style={{ color: c.color }}>{c.val}</div>
            <div className="text-xs text-slate-600 mt-1 font-mono">{c.file}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
