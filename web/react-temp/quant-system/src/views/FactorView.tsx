import { useState } from 'react'
import { Layers } from 'lucide-react'

const familyColors: Record<string,string> = {
  "趋势":"#6366f1","均值回归":"#22d3ee","波幅":"#4ade80","量价":"#fbbf24","时序":"#f87171"
}

const allFactors = [
  { id:"F00",name:"MA金叉(5,20)",    family:"趋势",   desc:"快线穿越慢线买入",    regime:["bull_trend","trend_narrow"] },
  { id:"F01",name:"MA金叉(10,60)",   family:"趋势",   desc:"中长期趋势确认",      regime:["bull_trend","bear_trend"] },
  { id:"F02",name:"MACD(12,26,9)",  family:"趋势",   desc:"MACD金叉",           regime:["bull_trend","trend_narrow"] },
  { id:"F03",name:"3月动量正",       family:"趋势",   desc:"季度动量趋势",        regime:["bull_trend"] },
  { id:"F04",name:"ATR突破(20日)",  family:"趋势",   desc:"价格突破N日高点",     regime:["bull_trend","bear_trend"] },
  { id:"F05",name:"价格>20日均线", family:"趋势",   desc:"均线趋势确认",         regime:["bull_trend","range_narrow"] },
  { id:"F06",name:"RSI超卖25",      family:"均值回归",desc:"RSI超卖买入",          regime:["bear_trend","range_wide"] },
  { id:"F07",name:"RSI超卖30",      family:"均值回归",desc:"RSI保守超卖",          regime:["bear_trend","range_wide"] },
  { id:"F08",name:"RSI<40买入",     family:"均值回归",desc:"RSI低位买入",          regime:["range_narrow"] },
  { id:"F09",name:"布林下轨买入",   family:"均值回归",desc:"触及布林下轨反弹",     regime:["range_narrow"] },
  { id:"F10",name:"布林上轨卖出",   family:"均值回归",desc:"触及布林上轨回落",     regime:["range_narrow"] },
  { id:"F11",name:"KDJ超卖反弹",    family:"均值回归",desc:"KDJ低位反弹",          regime:["bear_trend"] },
  { id:"F12",name:"ATR放大确认",    family:"波幅",    desc:"ATR突破历史均值",       regime:["bull_trend","bear_trend"] },
  { id:"F13",name:"ATR收缩预警",    family:"波幅",    desc:"ATR收缩突破在即",       regime:["range_narrow"] },
  { id:"F14",name:"波幅收缩爆发",   family:"波幅",    desc:"布林带收口后爆发",       regime:["range_narrow"] },
  { id:"F15",name:"ROC定价过高",    family:"时序",    desc:"价格变化率择时",         regime:["bear_trend"] },
  { id:"F16",name:"连涨3日",        family:"时序",    desc:"惯性动量",               regime:["bull_trend"] },
]

const families = ["趋势","均值回归","波幅","量价","时序"]

export default function FactorView() {
  const [sel, setSel] = useState<string | null>(null)
  const filtered = sel ? allFactors.filter((f:any) => f.family === sel) : allFactors

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-4">
        <Layers size={24} className="text-green-400" />
        <div><h2 className="text-xl font-bold text-white">元因子库</h2><p className="text-slate-400 text-sm">17个原子因子 · 真正的进化原材料</p></div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { name:"趋势",    count:6, color:"#6366f1" },
          { name:"均值回归", count:6, color:"#22d3ee" },
          { name:"波幅",    count:3, color:"#4ade80" },
          { name:"量价",    count:2, color:"#fbbf24" },
          { name:"时序",    count:2, color:"#f87171" },
        ].map((f:any) => (
          <div key={f.name} onClick={() => setSel(sel === f.name ? null : f.name)}
            className="bg-slate-800 rounded-xl p-4 border cursor-pointer transition-all"
            style={{ borderColor: sel === f.name ? f.color+'88' : '#334155' }}>
            <div className="text-3xl font-bold" style={{ color: f.color }}>{f.count}</div>
            <div className="text-white text-sm font-medium mt-1">{f.name}</div>
            <div className="w-full bg-slate-700 rounded-full h-1.5 mt-2">
              <div className="h-full rounded-full transition-all" style={{ width:(f.count*15)+'%', backgroundColor:f.color }} />
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-2 flex-wrap">
        {families.map((f:any) => (
          <button key={f} onClick={() => setSel(sel === f ? null : f)}
            className={"px-3 py-1.5 rounded-full text-xs font-medium transition-all "+(sel === f ? "bg-indigo-600 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600")}>
            {f}
          </button>
        ))}
        {sel && <button onClick={() => setSel(null)} className="px-2 py-1.5 rounded-full text-xs text-slate-500 hover:text-white">清除</button>}
        <span className="text-slate-600 text-xs self-center ml-2">{filtered.length}个因子</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {filtered.map((f:any) => (
          <div key={f.id} className="bg-slate-800 rounded-xl p-4 border border-slate-700">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-slate-500">[{f.id}]</span>
                <span className="font-semibold text-white text-sm">{f.name}</span>
              </div>
              <span className="px-2 py-1 rounded text-xs"
                style={{ backgroundColor:(familyColors[f.family]||'#94a3b8')+'33', color:familyColors[f.family]||'#94a3b8', border:"1px solid "+(familyColors[f.family]||'#94a3b8')+'55' }}>
                {f.family}
              </span>
            </div>
            <p className="text-slate-400 text-xs mb-2">{f.desc}</p>
            <div className="flex gap-1 flex-wrap">
              {f.regime.map((r:any) => (
                <span key={r} className="px-1.5 py-0.5 bg-slate-900 border border-slate-600 rounded text-xs text-slate-500 font-mono">{r}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
