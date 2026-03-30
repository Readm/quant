import { useState } from 'react'
import {
  Brain, TrendingUp, TrendingDown, BarChart2, ShieldAlert,
  Swords, Scale, ChevronDown, ChevronRight, Database,
  GitMerge, RefreshCw, Target, Activity, Search, Filter,
} from 'lucide-react'

// ── Pipeline Step Descriptor ───────────────────────────────────────
interface PipelineStep {
  id: string
  phase: string         // section label (e.g. "A 生成", "B 评估")
  icon: React.ElementType
  color: string
  codeRef: string       // class.method()
  title: string
  inputLabel: string
  inputItems: string[]
  outputLabel: string
  outputItems: string[]
  logic: string[]       // bullet points of core logic
  prompt?: string       // how the "prompt" / instruction is formed
}

const STEPS: PipelineStep[] = [
  {
    id: 'data',
    phase: '数据',
    icon: Database,
    color: '#22d3ee',
    codeRef: 'Orchestrator._load_data()',
    title: '数据加载',
    inputLabel: '配置',
    inputItems: ['symbols: List[str]', 'n_days: int (default 500)', 'Tencent API: sh000300 / btcusdt'],
    outputLabel: '输出',
    outputItems: [
      'data: {closes, opens, highs, lows, volumes, dates}',
      'indicators: {MA20, MA60, MA200, RSI14, ATR14, returns}',
      '降级: 本地缓存 data/raw/{SYMBOL}_{date}.json',
    ],
    logic: [
      '优先 Tencent QFQ K线（前复权日K）',
      '失败时降级到本地缓存（yfinance / Qlib 离线数据）',
      '_compute_indicators(): SMA, RSI (EMA平滑), ATR (真实波幅)',
      '返回 symbols_data[0]（只用第一个 symbol 进行回测）',
    ],
  },
  {
    id: 'gen',
    phase: 'A 生成',
    icon: GitMerge,
    color: '#6366f1',
    codeRef: 'TrendExpert / MeanReversionExpert .generate_candidates()',
    title: '候选策略生成',
    inputLabel: '输入',
    inputItems: [
      'feedback_history: List[StructuredFeedback]（上轮评估产生）',
      'need_diversify: bool（同质化检测结果）',
      'count: 4（趋势）+ 3（均值回归）',
    ],
    outputLabel: '输出',
    outputItems: [
      '{strategy_id, template_key, params, tags, diversity_note}',
      '趋势模板: ma_cross / macd / momentum / adx_trend',
      '均值回归模板: rsi / bband',
    ],
    logic: [
      '30% 随机探索: _randomize(params, ±30%)',
      '30% 反馈引导: _tune_from_feedback → increase/decrease_lookback, tighten_stop_loss, add_filter',
      '40% Exploitation: _apply_sf_adjustment(best_params, last_sf)',
      '不足时填充默认模板参数',
    ],
    prompt: '上轮 StructuredFeedback 的 adjustment / param / magnitude / unit → _tune_from_feedback 解析为参数调整指令',
  },
  {
    id: 'bt',
    phase: 'A 回测',
    icon: BarChart2,
    color: '#4ade80',
    codeRef: 'TrendExpert / MeanReversionExpert .backtest()',
    title: '策略回测执行',
    inputLabel: '输入',
    inputItems: [
      'data: OHLCV dict',
      'ind: indicators dict',
      'params: {fast, slow} / {period, lower, upper} 等',
      'template_key: "ma_cross" / "rsi" 等',
    ],
    outputLabel: '输出',
    outputItems: [
      'BacktestReport: {strategy_id, daily_returns, annualized_return,',
      '  sharpe_ratio, max_drawdown_pct, win_rate, profit_factor, total_trades}',
    ],
    logic: [
      '_signal_series(): 生成 Level 信号（1=多仓/-1=空仓/0=空仓）',
      '  MA交叉: 1 when MA20>MA60; RSI: 1 when RSI<lower',
      '_debounce_signals(min_consecutive=2, cooldown=2): 过滤噪声',
      '_simulate(): equity=cash+pos×close，含交易成本(买0.08%+卖0.18%)',
      '_build_report(): 年化/夏普/最大回撤/胜率/盈亏比',
    ],
    prompt: 'template_key 决定信号逻辑分支，params 为信号函数参数（可视为"超参提示"）',
  },
  {
    id: 'eval',
    phase: 'B 评估',
    icon: Filter,
    color: '#f59e0b',
    codeRef: 'Evaluator.evaluate() / evaluate_batch()',
    title: '策略评估 + 结构化反馈',
    inputLabel: '输入',
    inputItems: [
      'BacktestReport (每个候选策略)',
      '历史评估记录 fb_history',
    ],
    outputLabel: '输出',
    outputItems: [
      'EvalResult: {decision: ACCEPT/REJECT/CONDITIONAL, composite_score}',
      'StructuredFeedback: {weakness, adjustment, param, magnitude, unit}',
      '  → 下轮 generate_candidates 的调参指令',
    ],
    logic: [
      '硬性过滤: ann_ret<8% | sharpe<0.5 | trades<5 | dd>40% → REJECT',
      '多维评分: sharpe×40% + drawdown×35% + return×25%',
      'PBO过拟合惩罚: 样本外调整夏普（pbo_score）',
      '综合分≥60→ACCEPT，40-60→CONDITIONAL，<40或硬过滤→REJECT',
      'weakness识别 → adjustment指令（increase_lookback / tighten_stop_loss等）',
    ],
    prompt: '弱点→调整映射: low_trades→increase_lookback; high_dd→tighten_stop_loss; low_win_rate→add_filter',
  },
  {
    id: 'regime',
    phase: 'B 市场状态',
    icon: Activity,
    color: '#a78bfa',
    codeRef: 'MarketRegimeExpert.detect() + NewsSentimentAnalyzer.analyze()',
    title: '市场状态 + 情绪分析',
    inputLabel: '输入',
    inputItems: [
      'data.closes / data.returns',
      'indicators: MA20/60, ADX',
      'symbols: List[str]（情绪分析用）',
    ],
    outputLabel: '输出',
    outputItems: [
      'MarketRegime: {name, confidence, trend_dir, max_position_pct}',
      '  名称: STRONG_TREND/WEAK_TREND/RANGE_BOUND/HIGH_VOL',
      'sentiment: {bullish_score, bearish_score, neutral_score}',
    ],
    logic: [
      'ADX均值（最近20天）: >25→趋势, <20→震荡',
      'vol_ratio = recent_vol / hist_vol: >1.5→高波动',
      '趋势方向: MA20 vs MA60 + 动量momentum20',
      'Blackboard.write("Regime", rnd, "regime", regime)',
    ],
  },
  {
    id: 'debate',
    phase: 'C 辩论',
    icon: Swords,
    color: '#f87171',
    codeRef: 'DebateManager.conduct_debate()',
    title: '对抗辩论（5层）',
    inputLabel: '输入',
    inputItems: [
      'trend_evals: List[EvalResult] (通过评估的趋势策略)',
      'mr_evals: List[EvalResult] (通过评估的均值回归策略)',
      'market_regime: MarketRegime',
      'risk_results: List[RiskResult]',
    ],
    outputLabel: '输出',
    outputItems: [
      'DebateResult: {winner: TREND/MR/TIE, trend_weight, mr_weight}',
      'bull_case: BullCase (看多论点 + 置信度)',
      'bear_case: BearCase (看空论点 + 置信度)',
      'final_advice: str（综合建议）',
    ],
    logic: [
      'L1 开场: TrendExpert 陈述 / MRExpert 陈述（量化指标驱动）',
      'L2 反驳: 互相攻击对方最弱证据',
      'L3 Bull/Bear 研究: 对 Top-2 策略做研究（仅有交易的策略）',
      'L4 判决: _judge() 综合 regime + bull/bear conf → winner',
      'L5 权重: _weights() → trend_weight + mr_weight = 1.0',
    ],
    prompt: 'Bull论据 = market_tailwinds + upside_targets (ann_ret, sharpe, win_rate → BullResearcher.research())\nBear论据 = market_headwinds + downside_risks (ann_ret, sharpe, max_dd → BearResearcher.research())',
  },
  {
    id: 'risk',
    phase: 'C 风险',
    icon: ShieldAlert,
    color: '#fb923c',
    codeRef: 'RiskExpert.analyze_batch()',
    title: '风险评估',
    inputLabel: '输入',
    inputItems: [
      '(strategy_name, params, daily_returns, total_trades)',
      '× 每个通过评估的策略',
    ],
    outputLabel: '输出',
    outputItems: [
      'RiskResult: {risk_rating, var_99, cvar, max_position_pct}',
      '  rating: LOW / MEDIUM / HIGH / VERY_HIGH',
    ],
    logic: [
      'VaR99: 99%置信区间最大单日损失',
      'CVaR: 超过VaR阈值的平均损失',
      'HIGH/VERY_HIGH策略在组合构建时降权',
    ],
  },
  {
    id: 'portfolio',
    phase: 'D 组合',
    icon: Scale,
    color: '#34d399',
    codeRef: 'Orchestrator._build_portfolio() + compute_correlation_matrix()',
    title: '组合构建 + 相关性过滤',
    inputLabel: '输入',
    inputItems: [
      'debate.trend_weight / mr_weight',
      'all_pass: List[EvalResult]',
      'risk_results: List[RiskResult]',
      'market_regime',
    ],
    outputLabel: '输出',
    outputItems: [
      'portfolio: Dict[strategy_id → EvalResult]（含 weight）',
      '最终入选 Top-N 策略',
    ],
    logic: [
      '混合得分 = composite × (trend_weight if trend else mr_weight)',
      'HIGH/VERY_HIGH风险策略 × 0.5 折扣',
      '相关系数 > 阈值的策略对：低分者降权',
      '取 Top-N（default 4）',
    ],
  },
  {
    id: 'holdout',
    phase: 'D 验证',
    icon: Target,
    color: '#94a3b8',
    codeRef: 'Orchestrator._holdout_validate() (rnd > 1)',
    title: 'Holdout OOS 验证',
    inputLabel: '输入',
    inputItems: [
      'final: 本轮入选策略',
      'symbols_data[0]: 完整历史数据',
      'regime: 市场状态',
    ],
    outputLabel: '输出',
    outputItems: [
      '[{name, oospct, bias}] 每策略样本外偏差',
      '|bias|<10%: 理想; |bias|<20%: 可接受',
    ],
    logic: [
      '仅第2轮起运行（首轮无基准）',
      '用最近 HOLDOUT_DAYS 天做 OOS paper trade',
      '计算 bias = OOS回报 - 样本内年化预期',
    ],
  },
  {
    id: 'feedback',
    phase: 'E 反馈',
    icon: RefreshCw,
    color: '#818cf8',
    codeRef: 'FeedbackHistory + Orchestrator._generate_diverse_candidates()',
    title: '反馈回路（跨轮）',
    inputLabel: '输入',
    inputItems: [
      'EvalResult.structured_feedback（本轮全部策略）',
      'evaluator.fb_history: FeedbackHistory',
    ],
    outputLabel: '下轮输入',
    outputItems: [
      'fb_list: List[StructuredFeedback.to_simple_dict()]',
      '→ generate_candidates(fb_list) 的调参指令',
      'need_diversify: evaluator.need_diversify() 同质化检测',
    ],
    logic: [
      'fb_history.entries 保存最近 K 轮结构化反馈',
      '同类型策略反馈按 strategy_type 筛选',
      '调参链: weakness → adjustment → param + magnitude + unit',
      '收敛检测: 连续2轮 Top-N 集合相同 → 提前终止',
    ],
    prompt: '反馈链示例:\n  low_trades(5次) → increase_lookback → param=fast, magnitude=+7天\n  high_dd(35%) → tighten_stop_loss → param=atr_mult, magnitude=×0.7',
  },
]

// ── Step Card ──────────────────────────────────────────────────────
function StepCard({ step, idx, isLast }: { step: PipelineStep; idx: number; isLast: boolean }) {
  const [open, setOpen] = useState(false)
  const Icon = step.icon
  const phaseColors: Record<string, string> = {
    '数据': '#22d3ee', 'A 生成': '#6366f1', 'A 回测': '#4ade80',
    'B 评估': '#f59e0b', 'B 市场状态': '#a78bfa',
    'C 辩论': '#f87171', 'C 风险': '#fb923c',
    'D 组合': '#34d399', 'D 验证': '#94a3b8', 'E 反馈': '#818cf8',
  }

  return (
    <div className="flex gap-3">
      {/* Left: step indicator + connector */}
      <div className="flex flex-col items-center" style={{ minWidth: 36 }}>
        <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 border"
          style={{ backgroundColor: step.color + '22', borderColor: step.color + '55' }}>
          <Icon size={16} style={{ color: step.color }} />
        </div>
        {!isLast && (
          <div className="w-px flex-1 mt-1" style={{ backgroundColor: step.color + '33', minHeight: 20 }} />
        )}
      </div>

      {/* Right: card content */}
      <div className="flex-1 pb-4">
        {/* Phase badge + title */}
        <div className="flex items-center gap-2 mb-2 cursor-pointer select-none"
          onClick={() => setOpen(o => !o)}>
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded"
            style={{ backgroundColor: step.color + '22', color: step.color }}>
            {step.phase}
          </span>
          <span className="text-white font-semibold text-sm">{step.title}</span>
          <code className="text-xs text-slate-500 font-mono hidden md:inline">{step.codeRef}</code>
          <span className="ml-auto text-slate-600">
            {open ? <ChevronDown size={13}/> : <ChevronRight size={13}/>}
          </span>
        </div>

        {/* I/O summary (always visible) */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
          <div className="bg-slate-800/60 rounded-lg px-3 py-2 border border-slate-700/50">
            <div className="text-slate-500 text-[10px] uppercase tracking-wide mb-1">{step.inputLabel}</div>
            {step.inputItems.map((item, i) => (
              <div key={i} className="text-slate-400 font-mono leading-relaxed">{item}</div>
            ))}
          </div>
          <div className="bg-slate-800/60 rounded-lg px-3 py-2 border border-slate-700/50">
            <div className="text-slate-500 text-[10px] uppercase tracking-wide mb-1">{step.outputLabel}</div>
            {step.outputItems.map((item, i) => (
              <div key={i} className="text-slate-300 font-mono leading-relaxed">{item}</div>
            ))}
          </div>
        </div>

        {/* Expanded: logic + prompt */}
        {open && (
          <div className="mt-2 space-y-2">
            <div className="bg-slate-900 rounded-lg px-3 py-2 border border-slate-700">
              <div className="text-slate-500 text-[10px] uppercase tracking-wide mb-1.5">核心逻辑</div>
              <ul className="space-y-0.5">
                {step.logic.map((line, i) => (
                  <li key={i} className="text-xs text-slate-300 flex gap-1.5">
                    <span style={{ color: step.color }} className="mt-0.5 shrink-0">›</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </div>
            {step.prompt && (
              <div className="bg-indigo-950/40 rounded-lg px-3 py-2 border border-indigo-800/40">
                <div className="text-indigo-400 text-[10px] uppercase tracking-wide mb-1.5">
                  Prompt / 调参指令链
                </div>
                <pre className="text-xs text-indigo-200 font-mono whitespace-pre-wrap leading-relaxed">
                  {step.prompt}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Data Flow Phases Header ────────────────────────────────────────
function PhaseBar() {
  const phases = [
    { label: 'A  生成+回测', color: '#6366f1' },
    { label: 'B  评估+市场', color: '#f59e0b' },
    { label: 'C  辩论+风险', color: '#f87171' },
    { label: 'D  组合+验证', color: '#34d399' },
    { label: 'E  反馈回路', color: '#818cf8' },
  ]
  return (
    <div className="flex gap-2 flex-wrap">
      {phases.map(p => (
        <div key={p.label} className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full"
          style={{ backgroundColor: p.color + '15', border: `1px solid ${p.color}44`, color: p.color }}>
          <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: p.color }} />
          {p.label}
        </div>
      ))}
    </div>
  )
}

// ── Expert Roster ──────────────────────────────────────────────────
const EXPERTS = [
  { name: 'TrendExpert',          role: '生成+回测趋势策略',             color: '#6366f1', icon: TrendingUp,   file: 'specialists/expert1a_trend.py' },
  { name: 'MeanReversionExpert',  role: '生成+回测均值回归策略',          color: '#22d3ee', icon: TrendingDown, file: 'specialists/expert1b_mean_reversion.py' },
  { name: 'Evaluator',            role: '评分 + 结构化反馈 + PBO惩罚',   color: '#f59e0b', icon: Filter,       file: 'evaluator.py' },
  { name: 'MarketRegimeExpert',   role: '市场状态检测 (ADX/vol/MA)',     color: '#a78bfa', icon: Activity,     file: 'modules/regime.py' },
  { name: 'NewsSentimentAnalyzer',role: '新闻情绪分析',                   color: '#94a3b8', icon: Search,       file: 'modules/news_sentiment.py' },
  { name: 'DebateManager',        role: '5层对抗辩论 + 权重分配',         color: '#f87171', icon: Swords,       file: 'debate_manager.py' },
  { name: 'BullResearcher',       role: '看多论点 + 置信度',              color: '#4ade80', icon: TrendingUp,   file: 'specialists/bull_researcher.py' },
  { name: 'BearResearcher',       role: '看空论点 + 失效模式',            color: '#fb7185', icon: TrendingDown, file: 'specialists/bear_researcher.py' },
  { name: 'RiskExpert',           role: 'VaR99 / CVaR / 风险等级',       color: '#fb923c', icon: ShieldAlert,  file: 'modules/risk_expert.py' },
  { name: 'Orchestrator',         role: '主循环 + 组合构建 + 相关性过滤', color: '#34d399', icon: Brain,        file: 'orchestrator.py' },
]

// ── Main View ──────────────────────────────────────────────────────
export default function ExpertView() {
  const [tab, setTab] = useState<'pipeline' | 'roster'>('pipeline')

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Brain size={24} className="text-purple-400" />
        <div>
          <h2 className="text-xl font-bold text-white">专家系统架构</h2>
          <p className="text-slate-400 text-sm">多专家协作量化系统 v4.0 · 代码对应流程图</p>
        </div>
      </div>

      {/* Tab */}
      <div className="flex gap-1 border-b border-slate-700 pb-1">
        {(['pipeline', 'roster'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1 rounded-t text-xs font-medium transition-colors ${
              tab === t ? 'text-white bg-slate-700' : 'text-slate-500 hover:text-slate-300'
            }`}>
            {t === 'pipeline' ? '完整流程图' : '专家一览'}
          </button>
        ))}
      </div>

      {tab === 'pipeline' && (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <p className="text-slate-400 text-xs leading-relaxed max-w-2xl">
              每一步对应 <code className="text-indigo-300">experts/</code> 下的具体类和方法。
              点击每个节点展开核心逻辑和调参指令链（Prompt）。
              流程分 A→E 五个阶段，每轮迭代都会执行 A-D，E 阶段结果注入下轮 A。
            </p>
            <PhaseBar />
          </div>

          <div className="bg-slate-800/50 rounded-xl p-5 border border-slate-700">
            {STEPS.map((step, idx) => (
              <StepCard key={step.id} step={step} idx={idx} isLast={idx === STEPS.length - 1} />
            ))}
          </div>
        </div>
      )}

      {tab === 'roster' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {EXPERTS.map(e => {
            const Icon = e.icon
            return (
              <div key={e.name} className="bg-slate-800 rounded-xl p-4 border border-slate-700 flex gap-3">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                  style={{ backgroundColor: e.color + '22', border: `1px solid ${e.color}44` }}>
                  <Icon size={16} style={{ color: e.color }} />
                </div>
                <div className="min-w-0">
                  <div className="text-white font-semibold text-sm">{e.name}</div>
                  <div className="text-slate-400 text-xs mt-0.5">{e.role}</div>
                  <code className="text-[10px] text-slate-600 font-mono">{e.file}</code>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
