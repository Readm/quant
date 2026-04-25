/**
 * ExpertView — 因子组合专家流程图 (React Flow)
 *
 * 展示每轮迭代数据流：
 *   数据加载 → 因子组合专家(55候选) → 回测 → 评估 → LLM评审 → 组合 → OOS验证 → 反馈回路
 *
 * Hover 任一节点查看：输入/输出/Prompt指令/对应源文件
 */
import { useCallback, useMemo, useRef } from 'react'
import ReactFlow, {
  Node,
  Edge,
  Position,
  useNodesState,
  useEdgesState,
  Background,
  BackgroundVariant,
  MarkerType,
  NodeProps,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { Brain, RefreshCw } from 'lucide-react'

// ═══════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════

interface PortDef {
  label: string
  detail: string
}

interface ExpertDef {
  id: string
  title: string
  subtitle: string
  file: string
  color: string
  ins: PortDef[]
  outs: PortDef[]
  promptLines: string[]
  promptTitle: string
}

// ═══════════════════════════════════════════════════════════════
// Expert Definitions
// ═══════════════════════════════════════════════════════════════

const EXPERTS: ExpertDef[] = [
  {
    id: 'data', title: '数据加载', subtitle: 'Orchestrator 入口',
    file: 'backtest/local_data.py', color: '#22d3ee',
    ins: [
      { label: 'symbols', detail: 'List[str]  e.g. ["SPY","BTCUSDT","000300"]' },
      { label: 'n_days', detail: 'int  历史天数 (default 500)' },
    ],
    outs: [
      { label: 'OHLCV 数据', detail: 'closes[], opens[], highs[], lows[], volumes[], dates[]' },
      { label: '技术指标', detail: 'MA20/60/200 · RSI14 · ATR14 · returns[]' },
    ],
    promptLines: [
      '优先腾讯 QFQ K线 → 降级本地缓存 data/raw/',
      '多标的并行加载，数据结构标准化',
    ],
    promptTitle: '数据加载逻辑',
  },
  {
    id: 'comboGen', title: '因子组合专家', subtitle: 'generate_candidates(55)',
    file: 'specialists/factor_combo_expert.py', color: '#8b5cf6',
    ins: [
      { label: 'feedback_history', detail: 'List[StructuredFeedback] ← 上轮 Evaluator' },
      { label: 'need_diversify', detail: 'bool  同质化信号 → 触发随机探索比例提升' },
    ],
    outs: [
      { label: 'candidates[55]', detail: '{strategy_id, template_key, combo_factors, combo_mode, params}' },
    ],
    promptLines: [
      '26 个模板 (趋势9 + 均值回归9 + 创新8)：',
      'ma_cross | macd | momentum | adx | ichimoku | kst | trix',
      'donchian | aroon | rsi | bollinger | vol_surge | mfi | rvi',
      'kdwave | multi_roc | obos | elder_ray | smart_money | gap_break',
      'limit_board | trend_composite | lanban_fade | vol_price_diverge',
      'multi_signal_combo | mean_rev_composite',
      '',
      '▶ 30% 单因子探索 (随机扰动参数 ±30%)',
      '▶ 40% 双因子 AND (两信号同时确认)',
      '▶ 20% 双因子 OR (任一信号触发)',
      '▶ 10% 三因子加权 (加权投票)',
      '',
      '─── 反馈调参指令 ───',
      'LOW_SHARPE      → tighten_stop_loss  → atr_mult ×0.5',
      'HIGH_DRAWDOWN   → decrease_position  → position ×0.7',
      'LOW_RETURN      → increase_lookback  → lookback +5天',
      'LOW_WIN_RATE    → decrease_lookback  → period −5天',
      'FEW_TRADES      → add_filter         → threshold −0.2%',
    ],
    promptTitle: '因子组合 + 参数调参',
  },
  {
    id: 'backtest', title: '组合回测', subtitle: 'PortfolioBacktester',
    file: 'backtest/engine.py', color: '#06b6d4',
    ins: [
      { label: 'OHLCV + 指标', detail: 'closes[], highs[], lows[], volumes[], MA/RSI/ATR' },
      { label: 'candidates[55]', detail: '{template_key, params, portfolio_params}' },
    ],
    outs: [
      { label: 'BacktestReport ×55', detail: 'strategy_id · daily_returns[] · ann_return · sharpe · max_dd' },
    ],
    promptLines: [
      '因子打分 (compute_factor_score → _SCORE_REGISTRY)',
      '→ 选 Top-N 标的 → 权重分配 → 再平衡',
      '',
      '信号逻辑分支 (template_key 分发):',
      'ma_cross: MA20 > MA60 → 做多',
      'macd: MACD > signal_line → 做多',
      'momentum: ROC > threshold → 做多',
      'rsi: RSI < lower → 做多 / RSI > upper → 做空',
      'bollinger: close < lower_band → 做多',
      'ichimoku / kst / trix / donchian / aroon → 因子库调用',
      'mfi / rvi / kdwave / obos / elder_ray → 因子库调用',
      '',
      '↓ 信号去抖: 连续2天确认 + 3天冷却',
      '↓ 交易成本: 买入=0.08%  卖出=0.18%',
      '↓ 并行回测: ProcessPoolExecutor, 多 CPU 核',
    ],
    promptTitle: '信号生成 + 回测引擎',
  },
  {
    id: 'eval', title: '评估专家', subtitle: 'evaluate_batch()',
    file: 'evaluator.py', color: '#f59e0b',
    ins: [
      { label: 'BacktestReport ×55', detail: '全部候选策略' },
    ],
    outs: [
      { label: 'EvalResult[]', detail: '{decision: ACCEPT|REJECT|COND, composite, sharpe, dd, sortino, calmar}' },
      { label: 'StructuredFeedback', detail: '→ fb_history → 下轮调参指令' },
    ],
    promptLines: [
      '① 硬性过滤 → REJECT:',
      '   ann_ret < 8% | sharpe < 0.5 | trades < 5 | dd > 40%',
      '② 多维评分 (加权复合):',
      '   sharpe×40% + drawdown×35% + return×25%',
      '   PBO过拟合惩罚: sharpe × (1 − pbo_ratio)',
      '③ 决策门槛:',
      '   score ≥ 60  → ACCEPT',
      '   40 ≤ score < 60 → CONDITIONAL',
      '   score < 40 → REJECT',
      '④ 弱点诊断 → StructuredFeedback',
    ],
    promptTitle: '评估规则 + 弱点诊断',
  },
  {
    id: 'debate', title: 'LLM 策略评审', subtitle: 'conduct_debate() v5',
    file: 'debate_manager.py', color: '#f87171',
    ins: [
      { label: 'all_pass[]', detail: 'ACCEPT|COND 策略 EvalResult[]' },
    ],
    outs: [
      { label: 'DebateResult', detail: '{winner, strategy_verdicts[], weight_advice}' },
    ],
    promptLines: [
      '阶段1 — 逐策略 LLM 评审 (最多5个):',
      '  筛选: total_trades>0 AND composite≥35',
      '  输入: 年化收益 · 夏普 · 回撤 · 胜率 · 交易次数',
      '  输出: pros/cons · 评级(STRONG_BUY/BUY/HOLD/SELL)',
      '         confidence · weight_advice · 一句话分析',
      '阶段2 — 阵营裁决 LLM:',
      '  输入: 全部策略评审结论',
      '  输出: winner · 权重分配 · reason · 交易员建议',
      'LLM 失败降级: winner=TIE, 等权',
    ],
    promptTitle: '两阶段 LLM 策略评审',
  },
  {
    id: 'portfolio', title: '组合构建', subtitle: '_build_portfolio()',
    file: 'orchestrator.py', color: '#34d399',
    ins: [
      { label: 'all_pass', detail: 'EvalResult[] ACCEPT|COND' },
      { label: 'DebateResult', detail: '策略评审 + 权重建议' },
    ],
    outs: [
      { label: 'final[Top-4]', detail: 'EvalResult[]  每策略含 weight 字段' },
    ],
    promptLines: [
      '相关性过滤: pearson(daily_returns_i, daily_returns_j)',
      '|corr| > 0.75 → 低分者 weight ×0.5 惩罚',
      'Top-N 策略 (default top_n=4)',
    ],
    promptTitle: '权重分配 + 相关性过滤',
  },
  {
    id: 'holdout', title: 'OOS 样本外验证', subtitle: '_holdout_validate()',
    file: 'orchestrator.py', color: '#64748b',
    ins: [
      { label: 'final[4]', detail: '本轮入选策略' },
      { label: 'symbols_data', detail: '完整历史数据 (含最近 252 天)' },
    ],
    outs: [
      { label: 'holdout_results', detail: '[{name, oospct, bias}]' },
    ],
    promptLines: [
      '最近 252 天样本外回测 (Walk-Forward)',
      'bias = OOS 回报 − 样本内年化预期',
      '|bias| < 10%  → ✅ 理想',
      '|bias| < 20%  → ⚠️ 可接受',
      '|bias| ≥ 20%  → ❌ 过拟合警告',
      '仅第 2 轮起运行',
    ],
    promptTitle: 'OOS Paper Trade 验证',
  },
  {
    id: 'feedback', title: '反馈回路', subtitle: '→ 下轮',
    file: 'orchestrator.py / evaluator.py', color: '#c084fc',
    ins: [
      { label: 'StructuredFeedback ×N', detail: '本轮全部策略反馈' },
      { label: 'holdout_results', detail: 'OOS 偏差结果' },
    ],
    outs: [
      { label: 'fb_list → 下轮 generate_candidates()', detail: 'List[{adjustment, param, magnitude, unit}]' },
    ],
    promptLines: [
      'fb_history.entries 保存全部策略反馈',
      '反馈驱动: 30% 随机探索 + 30% 反馈优化 + 40% 挖掘',
      'need_diversify: 检测历史同质化 → 提升随机探索比例',
      '收敛检测: top_score 连续 5 轮未提升 → break',
      'LLM 元专家: 每轮评估收敛真实性，防假收敛',
    ],
    promptTitle: '跨轮注入机制',
  },
]

// ═══════════════════════════════════════════════════════════════
// Layout Config
// ═══════════════════════════════════════════════════════════════

const NODE_W = 210
const NODE_H = 80
const COL_CENTER = 420
const ROW = 175

const nodeLayout: Record<string, { x: number; y: number }> = {
  data:      { x: COL_CENTER, y: ROW * 0 },
  comboGen:  { x: COL_CENTER, y: ROW * 1 },
  backtest:  { x: COL_CENTER, y: ROW * 2 },
  eval:      { x: COL_CENTER, y: ROW * 3 },
  debate:    { x: COL_CENTER, y: ROW * 4 },
  portfolio: { x: COL_CENTER, y: ROW * 5 },
  holdout:   { x: COL_CENTER, y: ROW * 6 },
  feedback:  { x: COL_CENTER, y: ROW * 7 },
}

// ═══════════════════════════════════════════════════════════════
// Edge Definitions
// ═══════════════════════════════════════════════════════════════

const edgeDefs: [string, string, string?, string?, boolean?][] = [
  // ── Forward flow ──
  ['data',     'comboGen', 'data-out', 'data-in'],
  ['data',     'backtest', 'data-out', 'data-in'],
  ['comboGen', 'backtest', 'out-0',    'candidate-in'],
  ['backtest', 'eval',     'out-0',    'in-0'],
  ['eval',     'debate',   'trend-out','in-0'],
  ['eval',     'portfolio','trend-out','allpass-in'],
  ['debate',   'portfolio','out-0',    'debate-in'],
  ['portfolio','holdout',  'out-0',    'in-0'],
  ['data',     'holdout',  'data-out', 'data-in'],
  ['holdout',  'feedback', 'out-0',    'holdout-in'],
  ['eval',     'feedback', 'fb-out',   'sf-in'],
  // ═══ Feedback loop ═══
  ['feedback', 'comboGen', 'out-0',    'fb-in', true],
]

// ═══════════════════════════════════════════════════════════════
// Build Nodes & Edges
// ═══════════════════════════════════════════════════════════════

function buildNodes(): Node[] {
  return EXPERTS.map((expert, i) => {
    const pos = nodeLayout[expert.id] || { x: 0, y: i * ROW }
    return {
      id: expert.id, type: 'expertNode', position: pos, data: expert,
      sourcePosition: Position.Bottom, targetPosition: Position.Top,
    }
  })
}

function buildEdges(): Edge[] {
  return edgeDefs.map(([src, tgt, srcH, tgtH, isFeedback], i) => {
    const ff = !isFeedback
    return {
      id: `e-${src}-${tgt}-${i}`,
      source: src, target: tgt,
      sourceHandle: srcH || undefined, targetHandle: tgtH || undefined,
      animated: ff,
      style: {
        stroke: isFeedback ? '#c084fc' : '#475569',
        strokeWidth: isFeedback ? 2.5 : 1.5,
        strokeDasharray: isFeedback ? '8 4' : undefined,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: isFeedback ? '#c084fc' : '#475569',
        width: isFeedback ? 14 : 12, height: isFeedback ? 14 : 12,
      },
    }
  })
}

// ═══════════════════════════════════════════════════════════════
// Custom Expert Node Component
// ═══════════════════════════════════════════════════════════════

function ExpertNode({ data }: NodeProps<ExpertDef>) {
  const tooltipRef = useRef<HTMLDivElement>(null)

  const handleMouseEnter = useCallback((e: React.MouseEvent) => {
    const tooltip = tooltipRef.current
    if (!tooltip) return
    tooltip.style.display = 'block'
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const left = Math.min(rect.right + 12, window.innerWidth - 400)
    tooltip.style.left = `${left}px`
    tooltip.style.top = `${Math.max(rect.top - 10, 10)}px`
  }, [])

  const handleMouseLeave = useCallback(() => {
    const tooltip = tooltipRef.current
    if (tooltip) tooltip.style.display = 'none'
  }, [])

  return (
    <>
      <div
        className="rounded-xl border overflow-hidden shadow-xl shadow-black/40 transition-transform hover:scale-105"
        style={{
          width: NODE_W, backgroundColor: '#0f172a',
          borderColor: data.color + '60', cursor: 'pointer',
        }}
        onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}
      >
        <div
          className="px-3 py-2.5"
          style={{ backgroundColor: data.color + '18', borderBottom: `1px solid ${data.color}25` }}
        >
          <div className="text-xs font-bold text-white leading-tight">{data.title}</div>
          <div className="text-[10px] leading-tight mt-0.5" style={{ color: data.color }}>{data.subtitle}</div>
          <code className="text-[9px] text-slate-600 mt-0.5 block truncate font-mono">{data.file}</code>
        </div>
        <div className="px-3 py-1.5">
          <div className="flex flex-wrap gap-1 mb-1">
            <span className="text-[9px] text-slate-600 uppercase font-mono">入→</span>
            {data.ins.slice(0, 2).map((p, i) => (
              <span key={i} className="text-[9px] px-1.5 py-0.5 rounded font-mono truncate max-w-[130px]"
                style={{ backgroundColor: data.color + '12', color: data.color }}>{p.label}</span>
            ))}
          </div>
          <div className="flex flex-wrap gap-1">
            <span className="text-[9px] text-slate-600 uppercase font-mono">出→</span>
            {data.outs.slice(0, 2).map((p, i) => (
              <span key={i} className="text-[9px] px-1.5 py-0.5 rounded font-mono truncate max-w-[130px]"
                style={{ backgroundColor: '#10b98115', color: '#4ade80' }}>{p.label}</span>
            ))}
          </div>
        </div>
      </div>

      {/* Hover Tooltip */}
      <div ref={tooltipRef} className="fixed z-[9999] hidden pointer-events-auto" style={{ maxWidth: 380 }}>
        <div className="rounded-xl border shadow-2xl p-4 text-xs"
          style={{ backgroundColor: '#0f172a', borderColor: data.color + '50', boxShadow: `0 0 40px ${data.color}15` }}>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: data.color }} />
            <span className="font-bold text-white text-sm">{data.title}</span>
            <code className="text-[10px] text-slate-500 ml-auto">{data.file}</code>
          </div>
          <div className="mb-3">
            <div className="text-[10px] uppercase tracking-widest mb-1.5" style={{ color: data.color }}>📥 输入</div>
            {data.ins.map((p, i) => (
              <div key={i} className="flex gap-1.5 mb-1">
                <code className="font-bold shrink-0" style={{ color: data.color }}>{p.label}</code>
                <span className="text-slate-400">{p.detail}</span>
              </div>
            ))}
          </div>
          <div className="mb-3">
            <div className="text-[10px] uppercase tracking-widest mb-1.5 text-emerald-400">📤 输出</div>
            {data.outs.map((p, i) => (
              <div key={i} className="flex gap-1.5 mb-1">
                <code className="font-bold text-emerald-400 shrink-0">{p.label}</code>
                <span className="text-slate-400">{p.detail}</span>
              </div>
            ))}
          </div>
          {data.promptLines.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-widest mb-1.5 text-amber-400">⚙ {data.promptTitle}</div>
              <div className="rounded-lg p-2.5 space-y-0.5 font-mono text-[11px] max-h-[280px] overflow-y-auto"
                style={{ backgroundColor: data.color + '08', border: `1px solid ${data.color}18` }}>
                {data.promptLines.map((line, i) => (
                  <div key={i} className={line.startsWith('──') || line.startsWith('↓') ? 'text-slate-500 border-t border-slate-700/30 mt-0.5 pt-0.5' : 'text-slate-300 leading-relaxed'}>{line}</div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

// ═══════════════════════════════════════════════════════════════
// Main View
// ═══════════════════════════════════════════════════════════════

const nodeTypes = { expertNode: ExpertNode }
const initialNodes = buildNodes()
const initialEdges = buildEdges()

export default function ExpertView() {
  const [nodes, _setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, _setEdges, onEdgesChange] = useEdgesState(initialEdges)

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Brain size={24} className="text-purple-400" />
        <div>
          <h2 className="text-xl font-bold text-white">
            专家系统 — 迭代流程图
            <RefreshCw size={14} className="inline ml-2 text-purple-400 animate-spin" style={{ animationDuration: '3s' }} />
          </h2>
          <p className="text-slate-400 text-sm">
            因子组合专家 v5 · 26 模板 × 1~3 因子组合 · 55 候选/轮 · Hover 查看详情
          </p>
        </div>
      </div>
      <div className="rounded-xl border border-slate-800 overflow-hidden" style={{ height: '80vh' }}>
        <ReactFlow
          nodes={nodes} edges={edges}
          onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView fitViewOptions={{ padding: 0.25 }}
          minZoom={0.25} maxZoom={1.5}
          nodesDraggable={false} nodesConnectable={false} elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
          defaultViewport={{ x: 80, y: 0, zoom: 0.55 }}
        >
          <Background variant={BackgroundVariant.Dots} gap={18} size={0.4} color="#1e293b" />
        </ReactFlow>
      </div>
    </div>
  )
}
