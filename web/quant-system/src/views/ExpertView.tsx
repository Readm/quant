import { useState } from 'react'
import { Brain, GitBranch, CheckCircle2, CircleDot, Zap, TrendingUp, Layers, RefreshCw, Target, ChevronRight, ChevronDown, MessageSquare, TrendingDown, LayoutGrid, Globe, Scale } from 'lucide-react'
import { XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ComposedChart, Line } from 'recharts'

// ─── Data ───────────────────────────────────────────────────────────────────

const evolutionData = [
  { round:1, ann:7.2,  score:85 },
  { round:2, ann:9.2,  score:90 },
  { round:3, ann:9.9,  score:95 },
  { round:4, ann:9.9,  score:95 },
  { round:5, ann:9.9,  score:95 },
  { round:6, ann:9.9,  score:95 },
]

const regimeData = [
  { regime:"trend_narrow", count:631, pct:86.9, color:"#6366f1" },
  { regime:"bull_trend",   count:41,  pct:5.6,  color:"#4ade80" },
  { regime:"bear_trend",   count:26,  pct:3.6,  color:"#f87171" },
  { regime:"warmup",       count:20,  pct:2.8,  color:"#94a3b8" },
  { regime:"range_wide",   count:4,   pct:0.6,  color:"#fbbf24" },
  { regime:"range_narrow", count:4,   pct:0.6,  color:"#22d3ee" },
]

const mechItems = [
  { Ic:CheckCircle2, title:"精英保留",  desc:"Top3直接进入下轮，保留最优基因",            color:"#4ade80" },
  { Ic:GitBranch,    title:"基因突变",  desc:"Top10各产生2个参数扰动变体（±15%）",         color:"#6366f1" },
  { Ic:CircleDot,    title:"因子杂交",  desc:"Top8两两交换因子片段，产生新组合",            color:"#22d3ee" },
  { Ic:Zap,          title:"种子注入",  desc:"每轮加入3个新的随机因子组合",                 color:"#fbbf24" },
]

// ─── Expert definitions ───────────────────────────────────────────────────────

const experts = [
  {
    id:"META", name:"元专家", en:"Meta Orchestrator", role:"迭代控制 · 汇总判断 · 最终裁决",
    color:"#a78bfa", icon:Brain, mode:["全程"],
    tag:"顶层",
    prompt:`你是整个专家系统的元 orchestrator（编排者）。

职责：
1. 控制迭代节奏：决定何时收敛、何时继续
2. 汇总所有专家意见，权衡冲突
3. 输出最终策略报告，向人解释"本轮为什么选这3个策略"
4. 裁决辩论中的分歧点

工作流程：
- 每轮迭代开始 → 读取黑板历史
- 调度 Pipeline 模式（A）或 对抗辩论模式（B）
- 汇总 Expert2~Expert4 的意见
- 输出综合裁决和下轮指令`,
    inputs:["共享黑板", "上一轮评估报告", "迭代历史"],
    outputs:["迭代指令", "调度模式选择", "最终策略报告"],
    example:"Round3 决策：采用对抗辩论模式，E3A趋势 vs E3B均值回归，E4风控做裁判",
  },
  {
    id:"E1A", name:"趋势专家", en:"Trend Expert", role:"趋势识别 · 动量追踪",
    color:"#6366f1", icon:TrendingUp, mode:["A"],
    tag:"🔄 流水线A",
    prompt:`你是趋势追踪专家。专注识别并跟随市场主要趋势。

核心能力：ADX趋势强度识别、均线多空排列、MACD趋势确认、动量指标
策略方向：均线金叉(MA5,20)、MACD(12,26,9)、季度动量、ATR突破
适用市场：bull_trend / bear_trend / trend_narrow`,
    inputs:["沪深300 K线", "ADX/MA/MACD指标", "市场宽度"],
    outputs:["趋势方向信号", "趋势强度评分", "候选趋势策略"],
    example:"MA(10,60)金叉，ADX=38 → 上升趋势确认 → 候选策略：MA金叉",
  },
  {
    id:"E1B", name:"均值回归专家", en:"Mean Reversion Expert", role:"超买超卖 · 反弹捕捉",
    color:"#22d3ee", icon:TrendingDown, mode:["A"],
    tag:"🔄 流水线A",
    prompt:`你是均值回归专家。专注识别价格偏离均值后的回归机会。

核心能力：RSI超买超卖识别、布林带支撑阻力、KDJ随机指标超卖信号
策略方向：RSI<30超卖买入、布林下轨支撑买入、KDJ低位反弹
适用市场：bear_trend / range_narrow / range_wide`,
    inputs:["沪深300 K线", "RSI/布林/KDJ指标", "历史波动率"],
    outputs:["超买超卖信号", "回归概率评分", "候选均值回归策略"],
    example:"RSI(14)=27，布林下轨支撑 → 超卖反弹信号 → 候选：RSI超卖买入",
  },
  {
    id:"E1C", name:"网络搜索专家", en:"Web Search Expert", role:"实时信息 · 因子增强",
    color:"#fbbf24", icon:Globe, mode:["A","B"],
    tag:"🌐 实时数据",
    prompt:`你是网络搜索专家。负责从外部获取实时市场情绪和事件驱动因子。

信息来源：微博热搜、东方财富板块资金流、申万行业涨跌榜、实时宏观新闻

A模式：为流水线提供基本面确认
B模式：为对抗辩论提供反驳证据

输入：市场当前状态 + 策略候选列表
输出：
- 新闻情绪评分（-100 ~ +100）
- 事件驱动因子（政策利好/利空）
- 对各策略的影响评估`,
    inputs:["候选策略列表", "市场状态", "今日新闻/热搜"],
    outputs:["情绪评分", "事件因子", "策略调整建议"],
    example:"搜索'新能源政策'→ 政策利好 → 对E1A正向，对E1B中性 → 增强E1A权重",
  },
  {
    id:"E2", name:"评估专家", en:"Evaluator Expert", role:"量化评分 · 过滤淘汰",
    color:"#f59e0b", icon:Target, mode:["流水线入口"],
    tag:"⚡ 评估入口",
    prompt:`你是量化评估专家。负责对候选策略进行严格历史回测评分。

评分维度（满分200）：
- 夏普比率 ≥1.0 → 40分 | ≥0.5 → 30分 | ≥0.2 → 20分
- 最大回撤 ≤5% → 40分 | ≤10% → 30分 | ≤20% → 20分
- 年化收益 ≥30% → 40分 | ≥15% → 30分 | ≥5% → 20分
- 交易次数 5~50次 → 20分 | 50~100次 → 10分
- 胜率 ≥85% → 40分 | ≥60% → 30分 | ≥40% → 20分

硬过滤规则：
- 年化 < 10% → 直接淘汰
- 最大回撤 > 30% → 直接淘汰
- 交易次数 < 3 → 直接淘汰`,
    inputs:["候选策略列表", "沪深300历史K线", "评分体系"],
    outputs:["回测报告", "评分排名", "幸存策略列表（进辩论）"],
    example:"RSI+MA策略：年化+10.2%, 夏普0.38, 回撤8.3%, 胜率71% → 评分92分(B级) → 进入辩论",
  },
  {
    id:"E3A", name:"趋势辩护专家", en:"Trend Advocate", role:"趋势策略倡导 · 反驳均值的局限性",
    color:"#6366f1", icon:MessageSquare, mode:["B"],
    tag:"🗡️ 对抗B 正方",
    prompt:`你是趋势辩护专家（Advocate）。在对抗辩论模式中代表趋势策略。

你的立场：
- 趋势策略在趋势市场中是最高收益策略
- 市场80%时间处于趋势状态（ADX > 25）
- 均线、MACD等趋势指标在牛市/熊市中持续有效

辩论策略：
1. 倡导：提出趋势策略的核心优势（高盈亏比、趋势市场高胜率）
2. 反驳：反驳均值回归专家对趋势策略的批评
3. 辩护：解释趋势策略短期回撤的可接受性

常见反驳点：
- "趋势策略震荡市失效" → 反驳：布林带可过滤
- "信号滞后" → 反驳：缩短参数可减少滞后`,
    inputs:["评估报告（E2）", "均值专家论点", "历史趋势策略表现"],
    outputs:["趋势策略辩护词", "支持数据/案例", "反驳对方弱点的论据"],
    example:"2019-2021牛市：MA(10,60)年化+38%，夏普1.2 → 趋势市场最强策略",
  },
  {
    id:"E3B", name:"均值回归辩护专家", en:"Mean Reversion Advocate", role:"均值回归倡导 · 反驳趋势的局限性",
    color:"#22d3ee", icon:MessageSquare, mode:["B"],
    tag:"🗡️ 对抗B 反方",
    prompt:`你是均值回归辩护专家（Advocate）。在对抗辩论模式中代表均值回归策略。

你的立场：
- 市场大部分时间是震荡/无趋势状态
- 价格终将回归均值，超买超卖是最稳定的盈利来源
- 均值回归策略的胜率显著高于趋势追踪

辩论策略：
1. 倡导：提出均值回归策略的高胜率优势
2. 反驳：反驳趋势专家关于"趋势市场"的前提假设
3. 辩护：解释均值回归在A股震荡市的独特优势

常见反驳点：
- "均值回归趋势市场失效" → 反驳：A股散户主导，震荡市占80%
- "RSI抄底容易被套" → 反驳：布林带止损可控制风险`,
    inputs:["评估报告（E2）", "趋势专家论点", "历史均值回归表现"],
    outputs:["均值回归辩护词", "支持数据/案例", "反驳对方弱点的论据"],
    example:"2022熊市：RSI+布林策略回撤-9%，纯趋势策略回撤-35% → 熊市防御优势明显",
  },
  {
    id:"E4", name:"组合专家", en:"Portfolio Expert", role:"风控校准 · 仓位分配 · 组合优化",
    color:"#4ade80", icon:Scale, mode:["全程"],
    tag:"📊 组合输出",
    prompt:`你是组合优化专家。负责将辩论胜出的策略进行风控和仓位优化。

核心职责：
1. 风控评估：每个策略的最大回撤风险
2. 仓位分配：根据置信度分配仓位（核心仓/卫星仓）
3. 相关性控制：避免过度集中在同类策略
4. 风险预算：控制整体组合回撒在可接受范围

仓位规则：
- 单策略仓位上限：20%
- 单类策略仓位上限：50%（趋势/均值回归各半）
- 实时风控：每日监控，触发止损线自动减仓

组合输出格式：
- 策略权重分配
- 风险预算（VaR/最大回撒目标）
- 再平衡触发条件
- 应急止损方案`,
    inputs:["辩论结果", "各策略风险评估", "市场状态"],
    outputs:["组合配置方案", "风控规则", "仓位分配表", "止损线设置"],
    example:"MA金叉(10,60) 40% + RSI+布林 35% + 新闻事件驱动 25% → 预期回撤≤12%",
  },
]

// ─── Sub-components ─────────────────────────────────────────────────────────

function StatCard({ Ic, label, value, sub, color }: { Ic: React.ComponentType<any>; label: string; value: string; sub: string; color: string }) {
  return (
    <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
      <div className="flex items-center gap-3 mb-2">
        <div className="p-1.5 rounded-lg" style={{ backgroundColor: color + '22' }}>
          <Ic size={15} style={{ color }} />
        </div>
        <span className="text-slate-400 text-xs">{label}</span>
      </div>
      <div className="text-xl font-bold text-white">{value}</div>
      <div className="text-xs text-slate-500 mt-0.5">{sub}</div>
    </div>
  )
}

function ExpertCard({ expert }: { expert: typeof experts[0] }) {
  const [open, setOpen] = useState(false)
  const Ic = expert.icon

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden"
      style={{ borderColor: expert.color + '33' }}>
      <button onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between p-3.5 hover:bg-slate-700/30 transition-colors text-left">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ backgroundColor: expert.color + '22', border: '1px solid ' + expert.color + '44' }}>
            <Ic size={15} style={{ color: expert.color }} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-white text-sm">{expert.name}</span>
              <span className="text-xs px-1.5 py-0.5 rounded font-mono"
                style={{ backgroundColor: expert.color + '22', color: expert.color }}>
                {expert.id}
              </span>
              {expert.tag && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-slate-700 text-slate-400">{expert.tag}</span>
              )}
            </div>
            <div className="text-xs text-slate-400 mt-0.5">{expert.role}</div>
          </div>
        </div>
        {open
          ? <ChevronDown size={14} className="text-slate-500 flex-shrink-0" />
          : <ChevronRight size={14} className="text-slate-500 flex-shrink-0" />
        }
      </button>

      {open && (
        <div className="px-3.5 pb-4 space-y-3 border-t border-slate-700">
          <div className="pt-3">
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-slate-900/70 rounded-lg p-2">
                <div className="text-slate-500 mb-1 font-medium">📥 输入</div>
                {expert.inputs.map(inp => (
                  <div key={inp} className="text-slate-300">· {inp}</div>
                ))}
              </div>
              <div className="bg-slate-900/70 rounded-lg p-2">
                <div className="text-slate-500 mb-1 font-medium">📤 输出</div>
                {expert.outputs.map(out => (
                  <div key={out} className="text-slate-300">· {out}</div>
                ))}
              </div>
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-500 mb-1.5 font-medium">📋 System Prompt</div>
            <div className="bg-slate-900/80 rounded-lg p-3 text-xs text-slate-300 leading-relaxed font-mono"
              style={{ border: '1px solid ' + expert.color + '18' }}>
              {expert.prompt}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-500 mb-1">💡 输出示例</div>
            <div className="bg-slate-900/40 rounded px-3 py-2 text-xs text-slate-400 italic border-l-2"
              style={{ borderColor: expert.color }}>
              {expert.example}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Architecture diagram ─────────────────────────────────────────────────────

function ArchitectureDiagram() {
  return (
    <div className="bg-slate-900 rounded-xl p-5 border border-slate-700 overflow-x-auto">
      <h3 className="text-white font-semibold mb-5">🏗️ 系统架构图</h3>
      <div className="min-w-[720px] space-y-3">

        {/* Layer 0: Meta */}
        <div className="flex items-center justify-center">
          <div className="rounded-xl px-5 py-3 text-center"
            style={{ backgroundColor:'#a78bfa22', border:'1.5px solid #a78bfa55' }}>
            <div className="flex items-center gap-2 justify-center mb-1">
              <Brain size={15} className="text-purple-400" />
              <span className="font-bold text-white text-sm">🧠 元专家 META</span>
            </div>
            <div className="text-xs text-slate-400">控制迭代节奏 · 汇总判断 · 输出最终报告</div>
          </div>
        </div>

        {/* Arrow */}
        <div className="flex justify-center">
          <svg width="16" height="18" viewBox="0 0 16 18">
            <path d="M8 0 L8 14 M3 9 L8 14 L13 9" stroke="#475569" strokeWidth="1.5" fill="none" strokeLinecap="round"/>
          </svg>
        </div>

        {/* Layer 1: Two modes */}
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-xl p-3" style={{ backgroundColor:'#6366f111', border:'1px solid #6366f133' }}>
            <div className="flex items-center gap-2 mb-2">
              <RefreshCw size={12} className="text-indigo-400" />
              <span className="text-xs font-bold text-indigo-300">🔄 流水线模式 A</span>
              <span className="text-xs text-slate-500 ml-auto">并行评估</span>
            </div>
            <div className="space-y-1.5">
              {[
                { id:"E1A", name:"📈 趋势专家",    color:"#6366f1" },
                { id:"E1B", name:"🔄 均值回归专家",  color:"#22d3ee" },
                { id:"E1C", name:"🌐 网络搜索专家",  color:"#fbbf24" },
              ].map(e => (
                <div key={e.id} className="flex items-center gap-2 text-xs bg-slate-800/60 rounded-lg px-3 py-1.5"
                  style={{ borderLeft: '2px solid ' + e.color }}>
                  <span className="font-mono font-bold" style={{ color: e.color }}>{e.id}</span>
                  <span className="text-white">{e.name}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl p-3" style={{ backgroundColor:'#f59e0b11', border:'1px solid #f59e0b33' }}>
            <div className="flex items-center gap-2 mb-2">
              <MessageSquare size={12} className="text-amber-400" />
              <span className="text-xs font-bold text-amber-300">🗡️ 对抗辩论模式 B</span>
              <span className="text-xs text-slate-500 ml-auto">裁定胜负</span>
            </div>
            <div className="space-y-1.5">
              {[
                { id:"E2",  name:"⚡ 评估专家",         color:"#f59e0b" },
                { id:"E3A", name:"📈 趋势辩护(正方)",  color:"#6366f1" },
                { id:"E3B", name:"🔄 均值回归辩护(反方)",color:"#22d3ee" },
              ].map(e => (
                <div key={e.id} className="flex items-center gap-2 text-xs bg-slate-800/60 rounded-lg px-3 py-1.5"
                  style={{ borderLeft: '2px solid ' + e.color }}>
                  <span className="font-mono font-bold" style={{ color: e.color }}>{e.id}</span>
                  <span className="text-white">{e.name}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Arrow + blackboard */}
        <div className="flex flex-col items-center">
          <svg width="16" height="18" viewBox="0 0 16 18">
            <path d="M8 0 L8 14 M3 9 L8 14 L13 9" stroke="#475569" strokeWidth="1.5" fill="none" strokeLinecap="round"/>
          </svg>
          <div className="mt-1 rounded-xl px-5 py-2 text-center"
            style={{ backgroundColor:'#fbbf2422', border:'1.5px solid #fbbf2444' }}>
            <div className="flex items-center gap-2 justify-center">
              <LayoutGrid size={13} className="text-yellow-400" />
              <span className="font-bold text-white text-xs">📌 共享黑板</span>
            </div>
            <div className="text-xs text-slate-400 mt-0.5">所有专家输出写入 · 每轮清空</div>
          </div>
        </div>

        {/* Arrow to E4 */}
        <div className="flex justify-center">
          <svg width="16" height="18" viewBox="0 0 16 18">
            <path d="M8 0 L8 14 M3 9 L8 14 L13 9" stroke="#475569" strokeWidth="1.5" fill="none" strokeLinecap="round"/>
          </svg>
        </div>

        {/* Layer 3: Portfolio */}
        <div className="flex justify-center">
          <div className="rounded-xl px-6 py-3 text-center"
            style={{ backgroundColor:'#4ade8022', border:'1.5px solid #4ade8044' }}>
            <div className="flex items-center gap-2 justify-center mb-1">
              <Scale size={14} className="text-green-400" />
              <span className="font-bold text-white text-sm">📊 组合专家 E4</span>
              <span className="text-xs text-slate-500 font-mono ml-1">Portfolio Expert</span>
            </div>
            <div className="text-xs text-slate-400">风控校准 · 仓位分配 · 止损线设置</div>
          </div>
        </div>

        {/* Final output */}
        <div className="flex justify-center">
          <div className="rounded-xl px-6 py-3 text-center"
            style={{ backgroundColor:'#4ade8015', border:'1.5px solid #4ade8040' }}>
            <div className="text-xs text-green-400 mb-1 font-medium">🎯 最终输出</div>
            <div className="text-white font-bold text-sm">MA金叉(10,60) × RSI+布林 × 新闻事件驱动</div>
            <div className="text-xs text-green-400/70 mt-1">预期年化 +10~15% · 最大回撤 ≤12% · 夏普 ≥0.5</div>
          </div>
        </div>

        {/* Iteration note */}
        <div className="flex justify-center pt-1">
          <div className="flex items-center gap-2 text-xs text-indigo-400">
            <RefreshCw size={10} />
            <span>Round N 迭代 · 6轮收敛 · 策略池上限 50个</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Main ────────────────────────────────────────────────────────────────────

export default function ExpertView() {
  const [showAll, setShowAll] = useState(false)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Brain size={24} className="text-purple-400" />
        <div>
          <h2 className="text-xl font-bold text-white">专家系统进化框架</h2>
          <p className="text-slate-400 text-sm">v3.0 · 8位专家 · 多模式协作</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard Ic={Brain}         label="专家总数"   value="8位"    sub="3类角色"      color="#a78bfa" />
        <StatCard Ic={Layers}        label="元因子库"   value="20个"   sub="5大家族"      color="#6366f1" />
        <StatCard Ic={TrendingUp}    label="初始策略池" value="174个"  sub="因子组合"      color="#22d3ee" />
        <StatCard Ic={CheckCircle2}  label="收敛轮次"   value="3轮"    sub="达到收敛"      color="#4ade80" />
      </div>

      {/* Architecture */}
      <ArchitectureDiagram />

      {/* Expert cards */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-white font-semibold">🧠 专家角色详解</h3>
          <button onClick={() => setShowAll(s => !s)}
            className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-600 text-slate-400 hover:text-white transition-colors">
            {showAll ? '收起' : '展开全部 8 位专家'}
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {experts.filter((_, i) => showAll || i < 4).map(exp => (
            <ExpertCard key={exp.id} expert={exp} />
          ))}
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <h3 className="text-white font-semibold mb-4">🧬 进化机制</h3>
          <div className="space-y-2.5">
            {mechItems.map(m => (
              <div key={m.title} className="flex items-start gap-3 bg-slate-900 rounded-lg p-3 border border-slate-700">
                <m.Ic size={14} style={{ color: m.color }} className="mt-0.5 flex-shrink-0" />
                <div>
                  <div className="font-medium text-white text-sm">{m.title}</div>
                  <div className="text-slate-400 text-xs mt-0.5">{m.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <h3 className="text-white font-semibold mb-3">📈 进化轨迹</h3>
          <ResponsiveContainer width="100%" height={210}>
            <ComposedChart data={evolutionData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="round" tick={{ fill:'#94a3b8', fontSize:12 }}
                label={{ value:'Round', fill:'#64748b', fontSize:11 }} />
              <YAxis yAxisId="ann" orientation="left"
                tick={{ fill:'#94a3b8', fontSize:11 }} tickFormatter={(v) => v+'%'} domain={[-5, 20]} />
              <YAxis yAxisId="score" orientation="right"
                tick={{ fill:'#94a3b8', fontSize:11 }} domain={[70, 120]} />
              <Tooltip contentStyle={{ backgroundColor:'#1e293b', border:'1px solid #334155', borderRadius:8 }} labelStyle={{ color:'#fff' }} />
              <Legend wrapperStyle={{ color:'#94a3b8', fontSize:12 }} />
              <Line yAxisId="ann" type="monotone" dataKey="ann" name="年化收益率%"
                stroke="#6366f1" strokeWidth={2} dot={{ fill:'#6366f1', r:4 }} />
              <Line yAxisId="score" type="monotone" dataKey="score" name="综合评分"
                stroke="#22d3ee" strokeWidth={2} dot={{ fill:'#22d3ee', r:4 }} />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="mt-3 space-y-1">
            <div className="text-xs text-slate-500">市场状态分布（2022-2024）</div>
            <div className="flex gap-1 flex-wrap">
              {regimeData.map(r => (
                <span key={r.regime} className="text-xs px-1.5 py-0.5 rounded font-mono"
                  style={{ backgroundColor: r.color + '22', color: r.color }}>
                  {r.regime} {r.pct}%
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
