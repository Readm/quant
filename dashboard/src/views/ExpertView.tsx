/**
 * ExpertView — 专家系统节点图
 * 展示每个专家的真实输入/输出连接 + Prompt/指令链
 * 节点对应 experts/ 下的实际代码
 */
import { useState } from 'react'
import { Brain, ChevronDown, ChevronRight } from 'lucide-react'

// ── Types ──────────────────────────────────────────────────────────
interface Port {
  label: string          // data key name, e.g. "BacktestReport"
  detail: string         // what it contains
  color?: string
}
interface NodeDef {
  id: string
  title: string
  codeRef: string        // class.method()
  file: string
  color: string
  instruction: {         // the "prompt" — rule / logic that drives this expert
    title: string
    lines: string[]
  } | null
  ins: Port[]            // incoming ports (labeled arrows IN)
  outs: Port[]           // outgoing ports (labeled arrows OUT)
  note?: string          // footnote
}

// ── Pipeline definition: each row is either a single node or a parallel pair ──
type Row =
  | { kind: 'single'; node: NodeDef }
  | { kind: 'parallel'; left: NodeDef; right: NodeDef }

// ── All expert nodes (code-accurate) ──────────────────────────────
const DATA_NODE: NodeDef = {
  id: 'data', title: '数据加载', codeRef: 'Orchestrator._load_data()', file: 'orchestrator.py',
  color: '#22d3ee',
  instruction: null,
  ins: [
    { label: 'symbols', detail: 'List[str]  e.g. ["SPY", "BTCUSDT"]', color: '#64748b' },
    { label: 'n_days',  detail: 'int  历史天数 (default 500)',           color: '#64748b' },
  ],
  outs: [
    { label: 'data',       detail: 'closes[], opens[], highs[], lows[], volumes[], dates[]', color: '#22d3ee' },
    { label: 'indicators', detail: 'MA20/60/200 · RSI14 · ATR14 · returns[]',                color: '#22d3ee' },
  ],
  note: '优先 Tencent QFQ K线 → 降级本地缓存 data/raw/',
}

const TREND_GEN: NodeDef = {
  id: 'trendGen', title: 'TrendExpert\n.generate_candidates(4)', codeRef: 'TrendExpert.generate_candidates()',
  file: 'specialists/expert1a_trend.py', color: '#6366f1',
  instruction: {
    title: '参数调参指令链',
    lines: [
      '输入: StructuredFeedback.adjustment + param + magnitude + unit',
      '  LOW_SHARPE      → tighten_stop_loss  → atr_mult ×0.5',
      '  HIGH_DRAWDOWN   → decrease_position  → position ×0.7',
      '  LOW_RETURN      → increase_lookback  → lookback +5天',
      '  LOW_WIN_RATE    → decrease_lookback  → period  −5天',
      '  FEW_TRADES      → add_filter         → threshold −0.2%',
      '──────────────────────────────────',
      '30% 随机探索: params × (1 ± 0.3)',
      '30% 反馈引导: _tune_from_feedback(tpl, fb)',
      '40% Exploitation: _apply_sf_adjustment(best_params, last_sf)',
    ],
  },
  ins: [
    { label: 'feedback_history', detail: 'List[StructuredFeedback] ← 上轮 Evaluator 输出', color: '#818cf8' },
    { label: 'need_diversify',   detail: 'bool  同质化检测结果', color: '#64748b' },
  ],
  outs: [
    { label: 'candidates[4]', detail: '{strategy_id, template_key: ma_cross|macd|momentum|adx_trend, params, tags}', color: '#6366f1' },
  ],
}

const MR_GEN: NodeDef = {
  id: 'mrGen', title: 'MRExpert\n.generate_candidates(3)', codeRef: 'MeanReversionExpert.generate_candidates()',
  file: 'specialists/expert1b_mean_reversion.py', color: '#22d3ee',
  instruction: {
    title: '参数调参指令链',
    lines: [
      '输入: StructuredFeedback.adjustment (与 TrendExpert 相同结构)',
      '  LOW_WIN_RATE  → decrease_lookback → period −5天',
      '  HIGH_DRAWDOWN → tighten_stop_loss → atr_mult ×0.7',
      '  FEW_TRADES   → add_filter (放宽 RSI/Band 阈值)',
      '──────────────────────────────────',
      '30% 随机  |  30% 反馈  |  40% Exploitation',
    ],
  },
  ins: [
    { label: 'feedback_history', detail: 'List[StructuredFeedback] ← 上轮 Evaluator 输出', color: '#818cf8' },
    { label: 'need_diversify',   detail: 'bool', color: '#64748b' },
  ],
  outs: [
    { label: 'candidates[3]', detail: '{strategy_id, template_key: rsi|bband, params, tags}', color: '#22d3ee' },
  ],
}

const TREND_BT: NodeDef = {
  id: 'trendBt', title: 'TrendExpert\n.backtest()', codeRef: 'TrendExpert.backtest()',
  file: 'specialists/expert1a_trend.py', color: '#6366f1',
  instruction: {
    title: '信号逻辑 (template_key 分支)',
    lines: [
      'ma_cross:  signal = 1 当 MA20>MA60  (level-based)',
      '           signal = −1 当 MA20<MA60',
      'macd:      signal = 1 当 MACD>signal_line (level-based)',
      'momentum:  signal = 1 当 (close/close[-lb]−1) > threshold',
      'adx_trend: signal = 1 当 ADX>adx_thr AND close>close[-1]',
      '↓ _debounce_signals(min_consecutive=2, cooldown_days=2)',
      '   消除一次性假信号，需连续2天确认',
      '↓ _simulate() 含交易成本:',
      '   买入 = equity×95% / close × (1−0.08%)',
      '   卖出收入 = pos×close × (1−0.18%)',
    ],
  },
  ins: [
    { label: 'data',          detail: 'closes[], highs[], lows[], volumes[]', color: '#22d3ee' },
    { label: 'indicators',    detail: 'MA20/60, RSI14, ATR14',                color: '#22d3ee' },
    { label: 'candidate',     detail: '{template_key, params}  ← TrendGen',   color: '#6366f1' },
  ],
  outs: [
    { label: 'BacktestReport', detail: 'strategy_id · daily_returns[] · ann_return · sharpe · max_dd · win_rate · total_trades', color: '#4ade80' },
  ],
}

const MR_BT: NodeDef = {
  id: 'mrBt', title: 'MRExpert\n.backtest()', codeRef: 'MeanReversionExpert.backtest()',
  file: 'specialists/expert1b_mean_reversion.py', color: '#22d3ee',
  instruction: {
    title: '信号逻辑 (template_key 分支)',
    lines: [
      'rsi:   signal = 1 当 RSI < lower(30)',
      '       signal = −1 当 RSI > upper(70)',
      'bband: signal = 1 当 close < lower_band',
      '       signal = −1 当 close > upper_band',
      '↓ _simulate() 含交易成本 (同 TrendExpert)',
    ],
  },
  ins: [
    { label: 'data',       detail: 'closes[], highs[], lows[]', color: '#22d3ee' },
    { label: 'candidate',  detail: '{template_key: rsi|bband, params}  ← MRGen', color: '#22d3ee' },
  ],
  outs: [
    { label: 'BacktestReport', detail: 'strategy_id · daily_returns[] · ann_return · sharpe · max_dd · win_rate · total_trades', color: '#4ade80' },
  ],
}

const EVAL_NODE: NodeDef = {
  id: 'eval', title: 'Evaluator\n.evaluate_batch()', codeRef: 'Evaluator.evaluate_batch()',
  file: 'evaluator.py', color: '#f59e0b',
  instruction: {
    title: '评估规则 + 弱点诊断',
    lines: [
      '① 硬性过滤 → REJECT:',
      '   ann_ret < 8%  |  sharpe < 0.5  |  trades < 5  |  dd > 40%',
      '② 多维评分:',
      '   sharpe×40% + drawdown×35% + return×25%',
      '   PBO过拟合惩罚: sharpe_after_pbo = sharpe × (1 − pbo_ratio)',
      '③ 决策: score≥60→ACCEPT  40–60→CONDITIONAL  <40→REJECT',
      '④ 弱点诊断 → 结构化反馈 (StructuredFeedback):',
      '   LOW_SHARPE    → tighten_stop_loss  atr_mult ×0.5',
      '   HIGH_DRAWDOWN → decrease_position  position ×0.7',
      '   LOW_RETURN    → increase_lookback  lookback +5天',
      '   LOW_WIN_RATE  → decrease_lookback  period −5天',
      '   FEW_TRADES    → add_filter         threshold −0.2%',
    ],
  },
  ins: [
    { label: 'BacktestReport ×7', detail: 'TrendExpert×4 + MRExpert×3  全部候选策略', color: '#4ade80' },
  ],
  outs: [
    { label: 'EvalResult[]',       detail: '{decision: ACCEPT|REJECT|COND, composite, feedback_text}', color: '#f59e0b' },
    { label: 'StructuredFeedback', detail: '→ fb_history  →  下轮 generate_candidates() 的调参指令', color: '#818cf8' },
  ],
  note: '仅 ACCEPT + CONDITIONAL 的策略进入后续辩论和组合',
}

const REGIME_NODE: NodeDef = {
  id: 'regime', title: 'MarketRegimeExpert\n.detect()', codeRef: 'MarketRegimeExpert.detect()',
  file: 'modules/regime.py', color: '#a78bfa',
  instruction: {
    title: '市场状态分类',
    lines: [
      'ADX_avg(20d) > 25 → 趋势市 (STRONG_TREND / WEAK_TREND)',
      'ADX_avg < 20      → 震荡市 (SIDEWAYS)',
      'vol_ratio = recent_vol / hist_vol > 1.5 → HIGH_VOL',
      'trend_dir: MA20 > MA60 AND MA20上升 → UP',
      'max_position_pct: STRONG_TREND=70% · SIDEWAYS=40% · CRISIS=20%',
    ],
  },
  ins: [
    { label: 'closes[] / returns[]', detail: 'data.closes, data.returns', color: '#22d3ee' },
    { label: 'indicators',          detail: 'MA20/60 · ADX（如有）',      color: '#22d3ee' },
  ],
  outs: [
    { label: 'MarketRegime', detail: '{name: STRONG_TREND|WEAK_TREND|SIDEWAYS|HIGH_VOL|CRISIS, confidence, trend_dir, max_position_pct}', color: '#a78bfa' },
  ],
}

const NEWS_NODE: NodeDef = {
  id: 'news', title: 'NewsSentiment\n.analyze()', codeRef: 'NewsSentimentAnalyzer.analyze()',
  file: 'modules/news_sentiment.py', color: '#94a3b8',
  instruction: {
    title: '情绪分析',
    lines: [
      '基于规则的关键词匹配',
      '输出 bullish_score / bearish_score / neutral_score',
      '→ 目前为规则引擎，可替换为 LLM 调用',
    ],
  },
  ins:  [{ label: 'symbols', detail: 'List[str]  e.g. ["SPY"]', color: '#64748b' }],
  outs: [{ label: 'sentiment', detail: '{bullish_score, bearish_score, neutral_score}  写入 Blackboard', color: '#94a3b8' }],
}

const DEBATE_NODE: NodeDef = {
  id: 'debate', title: 'DebateManager\n.conduct_debate()', codeRef: 'DebateManager.conduct_debate()',
  file: 'debate_manager.py', color: '#f87171',
  instruction: {
    title: '5层对抗辩论 Pipeline',
    lines: [
      'L1  TrendExpert 开场: stance = "score=X ann=+Y% sharpe=Z"',
      '    证据 = [regime_name, ADX, MaxPos, Trades, Sharpe]',
      'L2  MRExpert 开场: stance = "score=X win_rate=Y% sharpe=Z"',
      '    证据 = [regime_name, vol_ratio, WinRate, MaxPos]',
      '    ↕  互相反驳 (_trend_counter / _mr_counter)',
      'L3  BullResearcher.research(ann_ret, sharpe, win_rate, regime, confidence)',
      '      → BullCase { market_tailwinds, upside_targets, entry_conditions, confidence }',
      '    BearResearcher.research(ann_ret, sharpe, max_dd, regime, confidence)',
      '      → BearCase { market_headwinds, downside_risks, failure_modes, confidence }',
      'L4  _judge(): winner = TREND/MR/TIE',
      '    base_weight = {STRONG_TREND:(0.60,0.30), SIDEWAYS:(0.25,0.55)}[regime]',
      '    delta = (bull_conf − bear_conf) × 0.15  → 调整基准权重',
      '    bear_conf>0.6 + HIGH_RISK → ×0.7 全面降仓',
      'L5  _weights(): trend_weight + mr_weight  (归一化)',
    ],
  },
  ins: [
    { label: 'trend_evals',  detail: 'ACCEPT|COND 趋势策略 EvalResult[]  ← Evaluator', color: '#f59e0b' },
    { label: 'mr_evals',     detail: 'ACCEPT|COND 均值回归策略 EvalResult[]  ← Evaluator', color: '#f59e0b' },
    { label: 'MarketRegime', detail: '{name, confidence, trend_dir}  ← RegimeExpert', color: '#a78bfa' },
    { label: 'risk_results', detail: 'RiskResult[]  ← RiskExpert (传入 _judge 作仓位折扣)', color: '#fb923c' },
  ],
  outs: [
    { label: 'DebateResult', detail: '{winner, trend_weight, mr_weight, bull_case, bear_case, final_advice}', color: '#f87171' },
  ],
}

const RISK_NODE: NodeDef = {
  id: 'risk', title: 'RiskExpert\n.analyze_batch()', codeRef: 'RiskExpert.analyze_batch()',
  file: 'modules/risk_expert.py', color: '#fb923c',
  instruction: {
    title: '风险计算',
    lines: [
      'VaR99 = 排序 daily_returns，取第 1% 分位数',
      'CVaR  = 超过 VaR99 阈值部分的均值',
      'rating:  VaR99<1% → LOW · 1-2% → MEDIUM',
      '         2-4% → HIGH · >4% → VERY_HIGH',
      '→ HIGH/VERY_HIGH 在 _build_portfolio 时 weight ×0.5',
    ],
  },
  ins: [
    { label: '(name, params, daily_returns[], trades)', detail: '× 每个 ACCEPT|COND 策略  ← Evaluator', color: '#f59e0b' },
  ],
  outs: [
    { label: 'RiskResult[]', detail: '{strategy_name, risk_rating: LOW|MEDIUM|HIGH|VERY_HIGH, var_99, cvar, max_position_pct}', color: '#fb923c' },
  ],
}

const PORTFOLIO_NODE: NodeDef = {
  id: 'portfolio', title: 'Orchestrator\n._build_portfolio()', codeRef: 'Orchestrator._build_portfolio() + compute_correlation_matrix()',
  file: 'orchestrator.py', color: '#34d399',
  instruction: {
    title: '权重分配 + 相关性过滤',
    lines: [
      'score = composite × (trend_weight if trend else mr_weight)',
      'HIGH/VERY_HIGH risk → score ×0.5 折扣',
      '相关性过滤:',
      '  corr_map[(id_i, id_j)] = pearson(daily_returns_i, daily_returns_j)',
      '  |corr| > 阈值 → 低分者 weight ×0.5 惩罚',
      'Top-N 策略 (default top_n=4)',
    ],
  },
  ins: [
    { label: 'all_pass',     detail: 'EvalResult[] ACCEPT|COND  ← Evaluator', color: '#f59e0b' },
    { label: 'DebateResult', detail: 'trend_weight / mr_weight  ← DebateManager', color: '#f87171' },
    { label: 'RiskResult[]', detail: 'risk_rating per strategy  ← RiskExpert', color: '#fb923c' },
  ],
  outs: [
    { label: 'final[N]', detail: 'EvalResult[]  每策略含 weight 字段 (入选 Top-N)', color: '#34d399' },
  ],
}

const HOLDOUT_NODE: NodeDef = {
  id: 'holdout', title: 'Orchestrator\n._holdout_validate()', codeRef: '_holdout_validate()  [rnd > 1]',
  file: 'orchestrator.py', color: '#64748b',
  instruction: {
    title: 'OOS Paper Trade 验证',
    lines: [
      '最近 HOLDOUT_DAYS 天样本外回测',
      'bias = OOS回报 − 样本内年化预期',
      '|bias|<10% → ✅理想  |bias|<20% → ⚠️可接受  >20% → ❌',
      '仅第 2 轮起运行（首轮无基准对比）',
    ],
  },
  ins: [
    { label: 'final[N]',     detail: '本轮入选策略  ← _build_portfolio', color: '#34d399' },
    { label: 'symbols_data', detail: '完整历史数据 (含最近 HOLDOUT_DAYS 天)', color: '#22d3ee' },
  ],
  outs: [
    { label: 'holdout_results', detail: '[{name, oospct, bias}]  展示在 RoundPanel', color: '#94a3b8' },
  ],
  note: '首轮跳过，直接进入反馈回路',
}

const FEEDBACK_NODE: NodeDef = {
  id: 'feedback', title: 'FeedbackHistory\n(反馈回路)', codeRef: 'evaluator.fb_history + _generate_diverse_candidates()',
  file: 'orchestrator.py  /  evaluator.py', color: '#818cf8',
  instruction: {
    title: '跨轮注入机制',
    lines: [
      'fb_history.entries 保存全部策略 StructuredFeedback',
      '下轮 generate_candidates(fb_list):',
      '  fb_list = [sf.to_simple_dict() for sf in fb_history.entries]',
      '  按 strategy_type 过滤 → 同类策略的反馈送入对应 Expert',
      'need_diversify = evaluator.need_diversify():',
      '  检测历史中同质化策略 → 触发随机探索比例提升',
      '收敛检测: top_ids == prev_top_ids  连续2轮相同 → break',
    ],
  },
  ins: [
    { label: 'StructuredFeedback ×N', detail: '本轮全部策略的结构化反馈  ← Evaluator.fb_history', color: '#f59e0b' },
    { label: 'holdout_results',       detail: 'OOS 偏差结果  ← Holdout (参考用)', color: '#94a3b8' },
  ],
  outs: [
    { label: 'fb_list → 下轮 generate_candidates()', detail: 'List[{adjustment, param, magnitude, unit}]  ← 注入 TrendExpert + MRExpert', color: '#818cf8' },
  ],
  note: '↑ 回到顶部：下轮 A 阶段',
}

// ── Row definitions ────────────────────────────────────────────────
const ROWS: Row[] = [
  { kind: 'single',   node: DATA_NODE },
  { kind: 'parallel', left: TREND_GEN,  right: MR_GEN },
  { kind: 'parallel', left: TREND_BT,   right: MR_BT },
  { kind: 'single',   node: EVAL_NODE },
  { kind: 'parallel', left: REGIME_NODE, right: NEWS_NODE },
  { kind: 'single',   node: DEBATE_NODE },
  { kind: 'single',   node: RISK_NODE },
  { kind: 'single',   node: PORTFOLIO_NODE },
  { kind: 'single',   node: HOLDOUT_NODE },
  { kind: 'single',   node: FEEDBACK_NODE },
]

// ── Connector between rows ─────────────────────────────────────────
// Shows what data flows on the vertical arrow between two rows
const CONNECTORS: { after: string; ports: Port[] }[] = [
  {
    after: 'data',
    ports: [
      { label: 'symbols_data[0].data',       detail: 'OHLCV dict', color: '#22d3ee' },
      { label: 'symbols_data[0].indicators', detail: 'MA20/60, RSI14, ATR14', color: '#22d3ee' },
    ],
  },
  {
    after: 'trendGen/mrGen',
    ports: [
      { label: 'candidates[4] (trend)', detail: 'List[{template_key, params, strategy_id}]', color: '#6366f1' },
      { label: 'candidates[3] (mr)',    detail: 'List[{template_key, params, strategy_id}]', color: '#22d3ee' },
    ],
  },
  {
    after: 'trendBt/mrBt',
    ports: [
      { label: 'BacktestReport ×7', detail: 'strategy_id · daily_returns[] · metrics', color: '#4ade80' },
    ],
  },
  {
    after: 'eval',
    ports: [
      { label: 'EvalResult[] ACCEPT|COND',    detail: '→ DebateManager + RiskExpert + _build_portfolio', color: '#f59e0b' },
      { label: 'StructuredFeedback → fb_history', detail: '→ 反馈回路（绕过辩论，直接注入下轮生成）', color: '#818cf8' },
    ],
  },
  {
    after: 'regime/news',
    ports: [
      { label: 'MarketRegime', detail: 'name · confidence · trend_dir · max_position_pct', color: '#a78bfa' },
      { label: 'sentiment',    detail: 'bullish/bearish/neutral score',                     color: '#94a3b8' },
    ],
  },
  {
    after: 'debate',
    ports: [
      { label: 'DebateResult', detail: 'winner · trend_weight · mr_weight · bull/bear_case · advice', color: '#f87171' },
    ],
  },
  {
    after: 'risk',
    ports: [
      { label: 'RiskResult[]', detail: 'strategy_name · risk_rating · var_99 · cvar', color: '#fb923c' },
    ],
  },
  {
    after: 'portfolio',
    ports: [
      { label: 'final[N]', detail: 'EvalResult[] with weight  Top-N 入选策略', color: '#34d399' },
    ],
  },
  {
    after: 'holdout',
    ports: [
      { label: 'holdout_results', detail: '[{name, oospct, bias}]', color: '#94a3b8' },
    ],
  },
]

// ── FlowNode component ─────────────────────────────────────────────
function FlowNode({ node, half }: { node: NodeDef; half?: boolean }) {
  const [open, setOpen] = useState(false)
  const lines = node.title.split('\n')

  return (
    <div className={`rounded-xl border overflow-hidden ${half ? 'flex-1 min-w-0' : 'w-full'}`}
      style={{ borderColor: node.color + '60', backgroundColor: '#0f172a' }}>

      {/* ── Header ── */}
      <div className="flex items-start justify-between px-4 py-3 gap-2 cursor-pointer select-none"
        style={{ backgroundColor: node.color + '18', borderBottom: `1px solid ${node.color}30` }}
        onClick={() => setOpen(o => !o)}>
        <div className="min-w-0">
          {lines.map((l, i) => (
            <div key={i} className={`font-bold leading-tight ${i === 0 ? 'text-white text-sm' : 'text-xs'}`}
              style={{ color: i === 1 ? node.color : undefined }}>
              {l}
            </div>
          ))}
          <code className="text-[10px] text-slate-500 font-mono mt-0.5 block">{node.file}</code>
        </div>
        <span className="text-slate-600 shrink-0 mt-0.5">
          {open ? <ChevronDown size={13}/> : <ChevronRight size={13}/>}
        </span>
      </div>

      {/* ── Input ports (always visible) ── */}
      <div className="px-4 pt-3 pb-1">
        <div className="text-[10px] text-slate-500 uppercase tracking-widest mb-1.5">输入</div>
        <div className="space-y-1">
          {node.ins.map((p, i) => (
            <div key={i} className="flex gap-2 items-start">
              <span className="w-1.5 h-1.5 rounded-full shrink-0 mt-1.5"
                style={{ backgroundColor: p.color || '#64748b' }} />
              <div>
                <span className="text-xs font-mono font-semibold" style={{ color: p.color || '#94a3b8' }}>{p.label}</span>
                <span className="text-[10px] text-slate-500 ml-1.5">{p.detail}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Instruction / Prompt (expanded) ── */}
      {open && node.instruction && (
        <div className="mx-4 my-2 rounded-lg p-3"
          style={{ backgroundColor: node.color + '10', border: `1px solid ${node.color}30` }}>
          <div className="text-[10px] font-bold uppercase tracking-widest mb-2"
            style={{ color: node.color }}>
            ⚙ {node.instruction.title}
          </div>
          <div className="space-y-0.5">
            {node.instruction.lines.map((line, i) => (
              <div key={i} className={`text-[11px] font-mono leading-relaxed ${
                line.startsWith('──') ? 'text-slate-600 border-t border-slate-700/50 mt-1 pt-1' : 'text-slate-300'
              }`}>
                {line}
              </div>
            ))}
          </div>
        </div>
      )}

      {!open && node.instruction && (
        <div className="mx-4 mb-2 mt-1">
          <button className="text-[10px] px-2 py-0.5 rounded"
            style={{ backgroundColor: node.color + '18', color: node.color }}
            onClick={() => setOpen(true)}>
            ⚙ {node.instruction.title} (点击展开)
          </button>
        </div>
      )}

      {/* ── Output ports ── */}
      <div className="px-4 pb-3 pt-1">
        <div className="text-[10px] text-slate-500 uppercase tracking-widest mb-1.5">输出</div>
        <div className="space-y-1">
          {node.outs.map((p, i) => (
            <div key={i} className="flex gap-2 items-start">
              <span className="w-1.5 h-1.5 rounded-full shrink-0 mt-1.5"
                style={{ backgroundColor: p.color || '#4ade80' }} />
              <div>
                <span className="text-xs font-mono font-semibold" style={{ color: p.color || '#4ade80' }}>{p.label}</span>
                <span className="text-[10px] text-slate-500 ml-1.5">{p.detail}</span>
              </div>
            </div>
          ))}
        </div>
        {node.note && (
          <div className="mt-2 text-[10px] text-slate-500 italic">{node.note}</div>
        )}
      </div>
    </div>
  )
}

// ── Connector arrow between rows ───────────────────────────────────
function FlowConnector({ ports }: { ports: Port[] }) {
  return (
    <div className="flex flex-col items-center gap-0.5 py-1">
      <div className="w-px h-3 bg-slate-700" />
      <div className="flex flex-wrap justify-center gap-1.5 px-2">
        {ports.map((p, i) => (
          <div key={i} className="flex items-center gap-1 rounded-full px-2 py-0.5"
            style={{ backgroundColor: (p.color || '#64748b') + '18', border: `1px solid ${(p.color || '#64748b')}40` }}>
            <span className="text-[10px] font-mono font-bold" style={{ color: p.color || '#94a3b8' }}>
              {p.label}
            </span>
            <span className="text-[9px] text-slate-500 hidden sm:inline">→ {p.detail}</span>
          </div>
        ))}
      </div>
      <div className="flex flex-col items-center">
        <div className="w-px h-3 bg-slate-700" />
        <div className="w-0 h-0" style={{
          borderLeft: '5px solid transparent',
          borderRight: '5px solid transparent',
          borderTop: '7px solid #475569'
        }} />
      </div>
    </div>
  )
}

// ── Helper: get connector by "after" key ───────────────────────────
function getConnector(afterKey: string) {
  return CONNECTORS.find(c => c.after === afterKey)
}

// ── Main View ──────────────────────────────────────────────────────
export default function ExpertView() {
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Brain size={24} className="text-purple-400" />
        <div>
          <h2 className="text-xl font-bold text-white">专家系统 — 完整流程图</h2>
          <p className="text-slate-400 text-sm">
            每个节点对应实际代码 · 输入/输出端口已标注数据类型 · 点击节点展开 Prompt/指令链
          </p>
        </div>
      </div>

      {/* Round label */}
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 font-mono">for rnd in 1..max_rounds:</span>
        <span>以下流程在每轮迭代中执行一次，E 阶段的输出注入下轮 A 阶段</span>
      </div>

      {/* Pipeline */}
      <div className="max-w-3xl mx-auto">

        {/* Row 0: Data */}
        <FlowNode node={DATA_NODE} />
        <FlowConnector ports={[
          { label: 'data {closes, highs, lows, volumes}', detail: '', color: '#22d3ee' },
          { label: 'indicators {MA20/60, RSI14, ATR14}',  detail: '', color: '#22d3ee' },
        ]} />

        {/* Row 1: Parallel generation */}
        <div className="mb-1 text-[10px] text-slate-500 text-center font-mono">─── A 阶段: 候选生成 ───</div>
        <div className="flex gap-3">
          <FlowNode node={TREND_GEN} half />
          <FlowNode node={MR_GEN} half />
        </div>
        <FlowConnector ports={[
          { label: 'candidates[4] trend',  detail: '{template_key, params, strategy_id}', color: '#6366f1' },
          { label: 'candidates[3] mr',     detail: '{template_key, params, strategy_id}', color: '#22d3ee' },
        ]} />

        {/* Row 2: Parallel backtest */}
        <div className="mb-1 text-[10px] text-slate-500 text-center font-mono">─── A 阶段: 回测执行 ───</div>
        <div className="flex gap-3">
          <FlowNode node={TREND_BT} half />
          <FlowNode node={MR_BT} half />
        </div>
        <FlowConnector ports={[
          { label: 'BacktestReport ×7', detail: 'strategy_id · daily_returns[] · sharpe · ann_return · max_dd', color: '#4ade80' },
        ]} />

        {/* Row 3: Evaluator */}
        <div className="mb-1 text-[10px] text-slate-500 text-center font-mono">─── B 阶段: 评估 + 反馈生成 ───</div>
        <FlowNode node={EVAL_NODE} />
        <FlowConnector ports={[
          { label: 'EvalResult[] ACCEPT|COND', detail: '→ DebateManager · RiskExpert · _build_portfolio', color: '#f59e0b' },
          { label: 'StructuredFeedback',       detail: '→ fb_history (绕过辩论，异步注入下轮生成)',        color: '#818cf8' },
        ]} />

        {/* Row 4: Parallel market context */}
        <div className="mb-1 text-[10px] text-slate-500 text-center font-mono">─── B 阶段: 市场上下文 ───</div>
        <div className="flex gap-3">
          <FlowNode node={REGIME_NODE} half />
          <FlowNode node={NEWS_NODE} half />
        </div>
        <FlowConnector ports={[
          { label: 'MarketRegime {name, confidence, trend_dir}', detail: '', color: '#a78bfa' },
          { label: 'sentiment {bull/bear score}',                detail: '', color: '#94a3b8' },
        ]} />

        {/* Row 5: Debate */}
        <div className="mb-1 text-[10px] text-slate-500 text-center font-mono">─── C 阶段: 对抗辩论 ───</div>
        <FlowNode node={DEBATE_NODE} />
        <FlowConnector ports={[
          { label: 'DebateResult', detail: 'winner · trend_weight · mr_weight · bull/bear_case', color: '#f87171' },
        ]} />

        {/* Row 6: Risk */}
        <div className="mb-1 text-[10px] text-slate-500 text-center font-mono">─── C 阶段: 风险评估 ───</div>
        <FlowNode node={RISK_NODE} />
        <FlowConnector ports={[
          { label: 'RiskResult[]', detail: 'risk_rating: LOW|MEDIUM|HIGH|VERY_HIGH · var_99 · cvar', color: '#fb923c' },
        ]} />

        {/* Row 7: Portfolio */}
        <div className="mb-1 text-[10px] text-slate-500 text-center font-mono">─── D 阶段: 组合构建 ───</div>
        <FlowNode node={PORTFOLIO_NODE} />
        <FlowConnector ports={[
          { label: 'final[N]', detail: 'EvalResult[] Top-N 策略 + weight 字段', color: '#34d399' },
        ]} />

        {/* Row 8: Holdout */}
        <div className="mb-1 text-[10px] text-slate-500 text-center font-mono">─── D 阶段: OOS 验证 ───</div>
        <FlowNode node={HOLDOUT_NODE} />
        <FlowConnector ports={[
          { label: 'holdout_results', detail: '[{name, oospct, bias}]  展示于看板', color: '#94a3b8' },
        ]} />

        {/* Row 9: Feedback */}
        <div className="mb-1 text-[10px] text-slate-500 text-center font-mono">─── E 阶段: 反馈回路 (→ 下轮 A) ───</div>
        <FlowNode node={FEEDBACK_NODE} />

        {/* Back arrow to top */}
        <div className="flex flex-col items-center mt-2">
          <div className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs text-slate-400 border border-dashed border-slate-600">
            <span style={{ color: '#818cf8' }}>↑</span>
            <span>下轮迭代: fb_list + need_diversify → TrendExpert / MRExpert .generate_candidates()</span>
          </div>
        </div>
      </div>
    </div>
  )
}
