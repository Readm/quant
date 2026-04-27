import { useState } from 'react'
import { Layers, TrendingUp, TrendingDown, Filter } from 'lucide-react'

// ── 完整策略模板定义 ─────────────────────────────────────────────────────────
interface Template {
  key: string
  name: string
  type: 'trend' | 'mean_reversion'
  category: 'classic' | 'innovative'
  params: { name: string; range: string; desc: string }[]
  logic: string
  formula: string
  signal: string  // 信号含义
  aShare: string  // A股适用性说明
}

const TEMPLATES: Template[] = [
  // ── 趋势策略（经典）────────────────────────────────────────────────────────
  {
    key: 'ma_cross', name: '双均线交叉', type: 'trend', category: 'classic',
    params: [
      { name: 'fast', range: '5–60天', desc: '短期均线周期' },
      { name: 'slow', range: '20–250天', desc: '长期均线周期，必须 > fast' },
    ],
    logic: '计算短期与长期移动平均线之差，正值表示短线高于长线（多头排列），信号越大越倾向持有。',
    formula: 'score = (MA_fast / MA_slow - 1) × 100',
    signal: '正 = 短线在长线上方（上涨趋势）；越大 = 趋势越强',
    aShare: '适中。A股趋势明显时效果好，但均线滞后，震荡市假信号多。建议 fast=10, slow=30。',
  },
  {
    key: 'macd', name: 'MACD趋势', type: 'trend', category: 'classic',
    params: [
      { name: 'fp', range: '5–20天', desc: '快线EMA周期（默认12）' },
      { name: 'sp', range: '15–60天', desc: '慢线EMA周期（默认26）' },
      { name: 'sig', range: '5–15天', desc: '信号线EMA周期（默认9）' },
    ],
    logic: '计算快慢EMA之差（MACD线），用EMA再平滑得到信号线，两者之差为柱状图（Histogram）。',
    formula: 'MACD = EMA(fp) − EMA(sp)\nscore = MACD_hist = MACD − Signal',
    signal: '正 = MACD在信号线上方（多头）；负 = 死叉',
    aShare: '较好。A股机构常用MACD，自我实现效应较强。注意金叉后成交量确认。',
  },
  {
    key: 'momentum', name: '动量突破', type: 'trend', category: 'classic',
    params: [
      { name: 'lookback', range: '5–80天', desc: '回望期（计算涨跌幅的窗口）' },
      { name: 'threshold', range: '1%–15%', desc: '最小涨幅门槛（暂未在打分中使用）' },
    ],
    logic: '计算过去N天的价格涨跌幅，作为动量信号。动量效应：近期涨的继续涨。',
    formula: 'score = (close[t] / close[t−N] − 1) × 100',
    signal: '正 = 近期上涨；越大 = 动量越强',
    aShare: '有效。A股动量效应显著，特别在牛市初期。回望期建议15–40天，过长会包含趋势反转。',
  },
  {
    key: 'adx_trend', name: 'ADX趋势确认', type: 'trend', category: 'classic',
    params: [
      { name: 'adx_thr', range: '15–40', desc: 'ADX强度门槛（ADX>25为强趋势）' },
      { name: 'atr_mult', range: '1.0–4.5', desc: 'ATR止损倍数（未在打分中直接使用）' },
    ],
    logic: '用ADX量化趋势强度，再结合MACD方向判断涨/跌趋势。ADX高且方向为正 = 强上涨趋势。',
    formula: 'direction = sign(MACD_hist) 或 sign(close − MA20)\nscore = ADX × direction',
    signal: '大正值 = 强上涨趋势；大负值 = 强下跌趋势；|score|小 = 无趋势',
    aShare: '适中。A股ADX在趋势行情中有效，但横盘期ADX始终低（<20），信号稀少。',
  },
  {
    key: 'ichimoku_signal', name: 'Ichimoku云图', type: 'trend', category: 'classic',
    params: [
      { name: 'tenkan', range: '5–20天', desc: '转换线周期（默认9）' },
      { name: 'kijun', range: '15–55天', desc: '基准线周期（默认26）' },
    ],
    logic: '一目均衡表：转换线 = (N天最高+最低)/2，基准线同理。转换线高于基准线 = 多头信号。',
    formula: 'tenkan_line = (max_high(tenkan) + min_low(tenkan)) / 2\nscore = (tenkan / kijun − 1) × 100',
    signal: '正 = 转换线在基准线上方；负 = 空头。结合云图更完整但此处简化为双线。',
    aShare: '较好。Ichimoku来自日本，设计上与亚洲股市特征更契合，A股机构也在使用。',
  },
  {
    key: 'kst', name: 'KST动量', type: 'trend', category: 'classic',
    params: [
      { name: 'r1', range: '5–15天', desc: '第一个ROC周期' },
      { name: 'r2', range: '10–20天', desc: '第二个ROC周期（r2 > r1）' },
    ],
    logic: 'Know Sure Thing：合并多周期ROC，r2权重加倍，消除单一周期噪声。',
    formula: 'ROC1 = (close[t]/close[t−r1] − 1) × 100\nscore = ROC1 + ROC2 × 2',
    signal: '正 = 多周期动量向上；权重设计使长周期主导',
    aShare: '一般。与纯动量类似，多周期叠加有一定噪声过滤效果。',
  },
  {
    key: 'trix', name: 'TRIX三重指数', type: 'trend', category: 'classic',
    params: [
      { name: 'period', range: '8–30天', desc: 'EMA嵌套周期（三层EMA）' },
    ],
    logic: '对价格做三次EMA平滑，再计算相邻值的变化率。三重平滑极大消除短线噪声。',
    formula: 'E1 = EMA(close, p)\nE2 = EMA(E1, p)\nE3 = EMA(E2, p)\nscore = (E3[t]/E3[t−1] − 1) × 1000',
    signal: '正 = 三重平滑均线向上；信号少但可靠性高',
    aShare: '一般。噪声小但反应极慢，A股短期波动大，TRIX容易错过行情。',
  },
  {
    key: 'donchian_breakout', name: 'Donchian突破', type: 'trend', category: 'classic',
    params: [
      { name: 'period', range: '10–60天', desc: 'N日最高/最低价通道周期' },
    ],
    logic: '计算过去N天的最高和最低价，构成通道。价格在通道中位置越高 = 越接近突破。',
    formula: 'upper = max(high, period), lower = min(low, period)\nscore = (close − mid) / mid × 100',
    signal: '正 = 价格在通道上半部分（近期高点附近）；突破新高时信号最强',
    aShare: '较好。A股涨停板突破是经典信号，Donchian能捕捉类似效果。',
  },
  {
    key: 'aroon_signal', name: 'Aroon交叉', type: 'trend', category: 'classic',
    params: [
      { name: 'period', range: '10–50天', desc: 'Aroon计算周期' },
    ],
    logic: 'Aroon Up = 距最近高点的距离（越短越接近100），Aroon Down同理。两者之差为方向信号。',
    formula: 'aroon_up = (period − days_since_high) / period × 100\nscore = aroon_up − aroon_down',
    signal: '大正值 = 最近高点在最近低点之后（上涨趋势）；接近0 = 盘整',
    aShare: '适中。能识别价格方向，但A股日内波动大，高低点判断有偏差。',
  },

  // ── 趋势策略（创新）─────────────────────────────────────────────────────────
  {
    key: 'smart_money', name: '主力资金流', type: 'trend', category: 'innovative',
    params: [
      { name: 'period', range: '10–40天', desc: '统计窗口（默认20天）' },
      { name: 'vol_weight', range: '1.0–3.0', desc: '成交量权重指数（越大越重视量能）' },
    ],
    logic: '量价同向分析：放量上涨（主力买入）权重高，缩量下跌（主力控盘）得到折扣。核心思路是识别机构资金方向。',
    formula: 'avg_vol = mean(vol, period)\nfor each day: chg = close[i]/close[i−1]−1\n  w = (vol[i]/avg_vol)^vol_w if chg>0 else 1/(vol[i]/avg_vol)^vol_w\nscore = Σ(chg × w) × 100',
    signal: '大正值 = 主力持续净买入；负值 = 主力分发出货',
    aShare: '★★★ 适合A股。A股主力资金明显，量价关系更显著。可识别庄股吸筹/出货行为。',
  },
  {
    key: 'gap_break', name: '跳空缺口突破', type: 'trend', category: 'innovative',
    params: [
      { name: 'min_gap_pct', range: '1%–5%', desc: '最小缺口幅度（最低价/前收盘-1）' },
      { name: 'lookback', range: '5–20天', desc: '向前搜索未填补缺口的天数' },
    ],
    logic: '向上跳空且缺口未被回补（最低价始终高于缺口前收盘）是强趋势信号。缺口越新、越大 = 信号越强。',
    formula: 'for i in [t−lookback, t]:\n  gap = low[i]/close[i−1] − 1\n  if gap > min_gap and not filled_after:\n    score = max(score, gap×100 / (t−i+1))',
    signal: '正值 = 存在未填补上跳空缺口；越大 = 缺口越近/越大',
    aShare: '★★★★ 高度适合A股。A股跳空缺口具有重要技术意义，经常不回补，突破确认性强。',
  },
  {
    key: 'limit_board', name: '涨停动能', type: 'trend', category: 'innovative',
    params: [
      { name: 'gain_thr', range: '5%–10%', desc: '认定"近涨停"的单日涨幅门槛（A股涨停≈10%）' },
      { name: 'lookback', range: '5–30天', desc: '统计近涨停天数的回望期' },
    ],
    logic: '统计回望期内的"近涨停"天数，近期权重更高。多个近涨停 = 强动量趋势，代理连板效应。',
    formula: 'for i in [t−lookback, t]:\n  gain = close[i]/close[i−1] − 1\n  if gain >= gain_thr:\n    w = (i − (t−lookback) + 1) / lookback  # 越近权重越高\n    score += gain × w × 100',
    signal: '正值 = 近期有多次大涨；越大 = 连板动能越强',
    aShare: '★★★★★ A股专属。连板股短期动量极强，此信号直接针对A股涨停机制设计。',
  },
  {
    key: 'trend_composite', name: '趋势复合信号', type: 'trend', category: 'innovative',
    params: [
      { name: 'ma_fast', range: '5–20天', desc: '短期均线' },
      { name: 'ma_slow', range: '20–60天', desc: '长期均线' },
      { name: 'mom_period', range: '10–30天', desc: '动量计算周期' },
      { name: 'vol_period', range: '10–30天', desc: '成交量均值计算周期' },
    ],
    logic: '三重确认机制：均线方向（40%）+ 动量方向（40%）+ 量能方向（20%）。三者一致时放大1.3倍，强调多维度共振。',
    formula: 'ma_sig = (MA_fast/MA_slow − 1) × 100\nmom_sig = (close[t]/close[t−N] − 1) × 100\nvol_sig = cur_vol/avg_vol − 1\nscore = ma_sig×0.4 + mom_sig×0.4 + vol_sig×20×0.2\nif all positive: score × 1.3',
    signal: '大正值 = 三维度同步看涨；1.3倍放大在三重共振时触发',
    aShare: '★★★ 组合信号鲁棒性更好。A股量价配合是教科书信号，三重确认减少假突破。',
  },

  // ── 均值回归策略（经典）─────────────────────────────────────────────────────
  {
    key: 'rsi', name: 'RSI均值回归', type: 'mean_reversion', category: 'classic',
    params: [
      { name: 'period', range: '5–30天', desc: 'RSI计算周期（默认14）' },
      { name: 'lower', range: '15–40', desc: '超卖线（低于此值 = 超卖）' },
      { name: 'upper', range: '60–85', desc: '超买线（高于此值 = 超买）' },
    ],
    logic: 'RSI衡量涨跌幅比率，反映超买/超卖。均值回归策略：超卖买入，超买卖出。',
    formula: 'RS = avg_gain(period) / avg_loss(period)\nRSI = 100 − 100/(1+RS)\nscore = (lower+upper)/2 − RSI  # 超卖→正，超买→负',
    signal: '正 = 超卖（RSI低于中线）；负 = 超买；分值越大=超卖越深',
    aShare: '较好。A股散户多，情绪驱动超买超卖频繁。RSI短周期（7–10天）在A股更有效。',
  },
  {
    key: 'bollinger', name: '布林带回归', type: 'mean_reversion', category: 'classic',
    params: [
      { name: 'period', range: '10–60天', desc: '布林带中轨（SMA）周期' },
      { name: 'std_mult', range: '1.2–3.5', desc: '标准差倍数（默认2倍，上下轨距离）' },
    ],
    logic: '价格偏离均线越远，回归概率越高。价格低于均线 = 正分（超卖），高于均线 = 负分（超买）。',
    formula: 'mean = SMA(close, period)\nstd = σ(close, period)\nscore = −(close[t] − mean) / (std_mult × std) × 100',
    signal: '正 = 价格低于中轨（超卖区域）；负 = 价格高于中轨；接近下轨时信号最强',
    aShare: '适中。布林带在震荡市表现好，趋势市（如单边牛市）容易连续跌破下轨而无法回归。',
  },
  {
    key: 'vol_surge', name: '成交量异常', type: 'mean_reversion', category: 'classic',
    params: [
      { name: 'vol_ma', range: '10–40天', desc: '成交量均线周期' },
      { name: 'threshold', range: '1.5–4.0', desc: '放量倍数门槛（暂未在打分中使用）' },
    ],
    logic: '异常放量通常伴随情绪顶点（无论涨跌），均值回归策略将高量视为反转信号。',
    formula: 'avg_vol = mean(volume, vol_ma)\nscore = −(vol[t]/avg_vol − 1) × 100  # 放量越大=分数越低（反转信号）',
    signal: '负 = 当前成交量异常放大（可能见顶）；正 = 缩量（底部积累）',
    aShare: '一般。A股放量含义复杂（主力对倒、涨停上板等），单纯量能信号需配合价格方向。',
  },
  {
    key: 'mfi_signal', name: 'MFI资金流', type: 'mean_reversion', category: 'classic',
    params: [
      { name: 'period', range: '7–28天', desc: 'MFI计算周期（默认14）' },
      { name: 'lower', range: '10–35', desc: '超卖线' },
      { name: 'upper', range: '65–90', desc: '超买线' },
    ],
    logic: '当前实现：用短期动量倒置作为均值回归信号。MFI理论上是RSI的量价版本（含成交量）。',
    formula: '(简化实现) lb = period\nmom = (close[t]/close[t−lb] − 1) × 100\nscore = −mom  # 跌越多得分越高',
    signal: '正 = 近期下跌（超卖），期待反弹；负 = 近期上涨（超买）',
    aShare: '一般。简化实现未使用MFI原始公式，后续可改进为真实资金流量计算。',
  },
  {
    key: 'rvi_signal', name: 'RVI相对活力', type: 'mean_reversion', category: 'classic',
    params: [
      { name: 'period', range: '5–20天', desc: '计算周期' },
    ],
    logic: '(当前简化实现）短期动量倒置。RVI理论应比较收盘与高低价范围的关系。',
    formula: 'mom = (close[t]/close[t−period] − 1) × 100\nscore = −mom',
    signal: '正 = 近期跌幅大（超卖）；均值回归期待反弹',
    aShare: '一般。与其他动量类似，A股短期反弹幅度通常受限于涨停板。',
  },
  {
    key: 'kdwave', name: 'KDJ波形', type: 'mean_reversion', category: 'classic',
    params: [
      { name: 'fastk', range: '5–18', desc: 'K值计算周期（随机指标RSV窗口）' },
      { name: 'slowk', range: '2–6', desc: 'K/D平滑周期' },
    ],
    logic: '(当前简化实现）短期动量倒置。KDJ理论应计算RSV（随机值）后平滑得到K、D、J三线。',
    formula: 'mom = (close[t]/close[t−fastk] − 1) × 100\nscore = −mom',
    signal: '正 = 近期下跌；KDJ超卖（J<0）时信号最强',
    aShare: '★★★ KDJ是A股最常用指标之一，完整实现后效果应显著。建议改进为真实KDJ计算。',
  },
  {
    key: 'multi_roc_signal', name: 'ROC多周期', type: 'mean_reversion', category: 'classic',
    params: [
      { name: 'p1', range: '5–15天', desc: '短期ROC周期' },
      { name: 'p2', range: '15–30天', desc: '中期ROC周期' },
      { name: 'p3', range: '25–60天', desc: '长期ROC周期' },
    ],
    logic: '(当前简化实现）以最长周期做短期动量倒置。理论上应计算三个周期ROC并综合。',
    formula: 'mom = (close[t]/close[t−p3] − 1) × 100\nscore = −mom',
    signal: '正 = 长周期跌幅大；期待大级别反弹',
    aShare: '一般。多周期ROC可以区分短线和中线机会，完整实现后有潜力。',
  },
  {
    key: 'obos_composite', name: 'OBOS超买超卖', type: 'mean_reversion', category: 'classic',
    params: [
      { name: 'period', range: '10–40天', desc: '计算周期' },
    ],
    logic: '(当前简化实现）短期动量倒置，代理超买超卖综合指标。理论上OBOS = 上涨股数-下跌股数。',
    formula: 'mom = (close[t]/close[t−period] − 1) × 100\nscore = −mom',
    signal: '正 = 近期超卖；负 = 近期超买',
    aShare: '一般。真实OBOS需要市场广度数据（上涨/下跌股数），当前仅用个股近似。',
  },
  {
    key: 'elder_ray_signal', name: 'Elder Ray信号', type: 'mean_reversion', category: 'classic',
    params: [
      { name: 'ema_period', range: '8–26天', desc: 'EMA周期（Elder力量指数基础）' },
    ],
    logic: '(当前简化实现）短期动量倒置。Elder Ray理论：牛力 = 最高价-EMA，熊力 = 最低价-EMA。',
    formula: 'mom = (close[t]/close[t−ema_period] − 1) × 100\nscore = −mom',
    signal: '正 = 近期下跌；期待反弹',
    aShare: '一般。完整Elder Ray应用高低价与EMA之差，可改进。',
  },

  // ── 均值回归策略（创新）─────────────────────────────────────────────────────
  {
    key: 'lanban_fade', name: '烂板反转', type: 'mean_reversion', category: 'innovative',
    params: [
      { name: 'limit_thr', range: '6%–10%', desc: '认定"近涨停"的盘中最高涨幅门槛' },
      { name: 'fade_days', range: '1–7天', desc: '向前搜索烂板事件的天数' },
      { name: 'confirm_days', range: '1–5天', desc: '确认期：烂板后需等待几天再介入' },
    ],
    logic: '"烂板"：股价盘中涨停（最高价/前收≥limit_thr）但收盘大幅回落（收盘涨幅<盘中涨幅×50%）。主力高位出货后，短期超卖，策略捕捉随后反弹。',
    formula: 'for i in [t−fade_days−confirm, t−confirm]:\n  hi_gain = high[i]/close[i−1] − 1\n  cl_gain = close[i]/close[i−1] − 1\n  if hi_gain >= limit_thr and cl_gain < hi_gain×0.5:\n    strength = (hi_gain − cl_gain) × 100\n    score += strength / (t−i+1)',
    signal: '正值 = 近期发生烂板且已进入确认期；值越大=烂板越近/越严重',
    aShare: '★★★★★ A股专属策略。烂板是A股独有现象（10%涨停限制+T+1规则），此信号直接针对A股机制设计。',
  },
  {
    key: 'vol_price_diverge', name: '量价背离', type: 'mean_reversion', category: 'innovative',
    params: [
      { name: 'lookback', range: '10–40天', desc: '计算量价背离的统计窗口' },
      { name: 'sensitivity', range: '0.5–2.0', desc: '信号敏感度（倍数）' },
    ],
    logic: '量价背离：价格上涨但成交量萎缩，说明上涨动力不足；价格下跌但成交量放大，说明恐慌抛售接近尾声。两者均为均值回归机会。',
    formula: 'price_mom = (close[t]/close[t−N] − 1) × 100\nvol_trend = recent_vol/early_vol − 1\nif price_mom>0 and vol_trend<−0.1:  # 涨价缩量\n  score = |price_mom| × (1+|vol_trend|) × sensitivity\nelif price_mom<0 and vol_trend>0.1:  # 跌价放量\n  score = |price_mom| × 0.8 × sensitivity',
    signal: '正值 = 存在量价背离（预期价格反转）；无背离时信号为0',
    aShare: '★★★★ 量价关系是A股技术分析核心。成交量真实反映资金动向，背离信号在A股较可靠。',
  },
  {
    key: 'multi_signal_combo', name: '多信号组合', type: 'mean_reversion', category: 'innovative',
    params: [
      { name: 'rsi_period', range: '7–21天', desc: 'RSI计算周期' },
      { name: 'rsi_lower', range: '25–45', desc: 'RSI超卖线' },
      { name: 'bb_period', range: '10–30天', desc: '布林带周期' },
      { name: 'vol_surge_thr', range: '1.2–3.0', desc: '放量门槛（当前量/均量）' },
    ],
    logic: 'AND逻辑复合：RSI超卖（40%）× 价格近布林下轨（40%）× 成交量放大确认（20%）。三者同时满足时信号最强，解决单一指标假信号多的问题。',
    formula: 'rsi_sig = max(0, rsi_lower − RSI) / rsi_lower  # 超卖程度\nbb_sig = max(0, −(close−mean)/(2×std))  # 偏离程度\nvol_sig = min(cur_vol/avg_vol/thr, 2.0)  # 量能确认\nscore = (rsi_sig×40 + bb_sig×40) × (0.5 + 0.5×vol_sig)',
    signal: '正值 = RSI超卖且价格近布林下轨；量能放大时信号翻倍',
    aShare: '★★★★ 多重确认降低假信号率。A股情绪驱动超买超卖，配合成交量验证可提高成功率。',
  },
  {
    key: 'mean_rev_composite', name: '均值回归复合', type: 'mean_reversion', category: 'innovative',
    params: [
      { name: 'period', range: '10–40天', desc: '均值和标准差的计算窗口' },
      { name: 'z_enter', range: '1.0–2.5', desc: '入场Z-Score门槛（偏离超过此值才出信号）' },
      { name: 'z_exit', range: '0.2–1.0', desc: '出场Z-Score（回归到此范围内信号消失）' },
    ],
    logic: 'Z-Score量化价格偏离均值的程度（单位：标准差）。Z<−z_enter = 极度超卖（买入信号）；|Z|<z_exit = 回归中性（信号消失）。加入反弹确认：超卖后开始反弹则放大1.4倍。',
    formula: 'z = (close[t] − mean) / std\nif |z| < z_exit: score = 0\nelse: score = −z × 20\nif z<−z_exit and close[t]>close[t−2]: score × 1.4  # 反弹确认',
    signal: '正 = 价格大幅低于均值（超卖）；z_exit过滤均值附近的噪声',
    aShare: '★★★ Z-Score是量化均值回归的标准工具。A股波动率高，需要较大的z_enter（≥1.5）才有意义。',
  },
]

// ── 组件 ─────────────────────────────────────────────────────────────────────

type TypeFilter = 'all' | 'trend' | 'mean_reversion'
type CatFilter = 'all' | 'classic' | 'innovative'

function CategoryBadge({ cat }: { cat: 'classic' | 'innovative' }) {
  return cat === 'innovative'
    ? <span className="px-1.5 py-0.5 rounded text-xs bg-yellow-500/20 text-yellow-400 border border-yellow-500/30">创新</span>
    : <span className="px-1.5 py-0.5 rounded text-xs bg-slate-700 text-slate-400 border border-slate-600">经典</span>
}

function AShareStars({ text }: { text: string }) {
  const m = text.match(/★+/)
  if (!m) return null
  return <span className="text-yellow-400 text-xs">{m[0]}</span>
}

function TemplateCard({ t, expanded, onToggle }: { t: Template; expanded: boolean; onToggle: () => void }) {
  const isTrend = t.type === 'trend'
  const borderColor = isTrend ? 'border-indigo-500/30' : 'border-emerald-500/30'
  const hoverBg   = isTrend ? 'hover:bg-indigo-500/5' : 'hover:bg-emerald-500/5'
  const typeColor = isTrend ? 'text-indigo-400' : 'text-emerald-400'

  return (
    <div className={`bg-slate-800 rounded-xl border ${borderColor} overflow-hidden`}>
      {/* Header — always visible */}
      <button
        className={`w-full text-left px-5 py-4 flex items-start gap-4 ${hoverBg} transition-colors`}
        onClick={onToggle}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-white font-semibold">{t.name}</span>
            <span className="font-mono text-xs text-slate-500">{t.key}</span>
            <CategoryBadge cat={t.category} />
          </div>
          <div className="flex items-center gap-3 mt-1.5 flex-wrap">
            <span className={`text-xs ${typeColor}`}>
              {isTrend ? '📈 趋势' : '↩️ 均值回归'}
            </span>
            <span className="text-xs text-slate-500">参数: {t.params.map(p => p.name).join(', ')}</span>
            <AShareStars text={t.aShare} />
          </div>
          {!expanded && (
            <p className="text-xs text-slate-500 mt-1 line-clamp-1">{t.logic}</p>
          )}
        </div>
        <span className="text-slate-500 text-xs mt-1 shrink-0">{expanded ? '▲' : '▼'}</span>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-slate-700">
          {/* Logic */}
          <div className="mt-4">
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">逻辑说明</div>
            <p className="text-sm text-slate-300 leading-relaxed">{t.logic}</p>
          </div>

          {/* Formula */}
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">计算公式</div>
            <pre className="text-xs bg-slate-900 text-green-300 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap font-mono leading-relaxed">{t.formula}</pre>
          </div>

          {/* Signal */}
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">信号含义</div>
            <p className="text-sm text-amber-300">{t.signal}</p>
          </div>

          {/* Parameters */}
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">参数列表</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {t.params.map(p => (
                <div key={p.name} className="bg-slate-900 rounded-lg p-2.5 flex gap-3">
                  <code className="text-indigo-300 text-xs font-mono shrink-0">{p.name}</code>
                  <div>
                    <div className="text-xs text-slate-400">{p.range}</div>
                    <div className="text-xs text-slate-500">{p.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* A-share suitability */}
          <div>
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-1.5">A股适用性</div>
            <p className="text-sm text-slate-300">{t.aShare}</p>
          </div>
        </div>
      )}
    </div>
  )
}

export default function FactorView() {
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [catFilter,  setCatFilter]  = useState<CatFilter>('all')
  const [search,     setSearch]     = useState('')
  const [expanded,   setExpanded]   = useState<Set<string>>(new Set())

  const filtered = TEMPLATES.filter(t => {
    if (typeFilter !== 'all' && t.type !== typeFilter) return false
    if (catFilter  !== 'all' && t.category !== catFilter) return false
    if (search && !t.name.includes(search) && !t.key.includes(search)) return false
    return true
  })

  const trendCount = TEMPLATES.filter(t => t.type === 'trend').length
  const mrCount    = TEMPLATES.filter(t => t.type === 'mean_reversion').length
  const novCount   = TEMPLATES.filter(t => t.category === 'innovative').length

  const toggle = (key: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  const expandAll  = () => setExpanded(new Set(filtered.map(t => t.key)))
  const collapseAll = () => setExpanded(new Set())

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-2">
        <Layers size={24} className="text-green-400" />
        <div>
          <h2 className="text-xl font-bold text-white">策略因子库</h2>
          <p className="text-slate-400 text-sm">
            {TEMPLATES.length} 个策略模板 · 含逻辑说明、公式、A股适用性
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: '策略总数',    value: TEMPLATES.length, sub: '个模板', color: '#a78bfa' },
          { label: '趋势策略',    value: trendCount, sub: '个',            color: '#6366f1' },
          { label: '均值回归',    value: mrCount,    sub: '个',            color: '#4ade80' },
          { label: '创新策略',    value: novCount,   sub: '个（A股专属）', color: '#fbbf24' },
        ].map(m => (
          <div key={m.label} className="bg-slate-800 rounded-xl p-4 border border-slate-700 text-center">
            <div className="text-xs text-slate-500 mb-1">{m.label}</div>
            <div className="text-2xl font-bold" style={{ color: m.color }}>{m.value}</div>
            <div className="text-xs text-slate-500 mt-0.5">{m.sub}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="bg-slate-800 rounded-xl p-4 border border-slate-700 flex flex-wrap gap-3 items-center">
        <Filter size={14} className="text-slate-500" />

        <div className="flex gap-1.5">
          {([['all','全部'],['trend','趋势'],['mean_reversion','均值回归']] as const).map(([v, label]) => (
            <button key={v}
              onClick={() => setTypeFilter(v)}
              className={`px-3 py-1 rounded-lg text-xs transition-colors ${typeFilter === v ? 'bg-indigo-600 text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'}`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex gap-1.5">
          {([['all','全部'],['classic','经典'],['innovative','创新']] as const).map(([v, label]) => (
            <button key={v}
              onClick={() => setCatFilter(v)}
              className={`px-3 py-1 rounded-lg text-xs transition-colors ${catFilter === v ? 'bg-yellow-600 text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'}`}
            >
              {label}
            </button>
          ))}
        </div>

        <input
          placeholder="搜索名称/key..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="bg-slate-700 text-slate-300 text-xs px-3 py-1.5 rounded-lg border border-slate-600 outline-none focus:border-indigo-500 w-40"
        />

        <div className="ml-auto flex gap-2">
          <button onClick={expandAll}   className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded hover:bg-slate-700">全展开</button>
          <button onClick={collapseAll} className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded hover:bg-slate-700">全收起</button>
          <span className="text-xs text-slate-500 self-center">{filtered.length} / {TEMPLATES.length}</span>
        </div>
      </div>

      {/* Trend group */}
      {(typeFilter === 'all' || typeFilter === 'trend') && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <TrendingUp size={16} className="text-indigo-400" />
            <h3 className="text-sm font-semibold text-indigo-300">
              趋势策略 ({filtered.filter(t => t.type === 'trend').length})
            </h3>
          </div>
          {filtered.filter(t => t.type === 'trend').map(t => (
            <TemplateCard key={t.key} t={t}
              expanded={expanded.has(t.key)}
              onToggle={() => toggle(t.key)}
            />
          ))}
        </div>
      )}

      {/* Mean reversion group */}
      {(typeFilter === 'all' || typeFilter === 'mean_reversion') && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <TrendingDown size={16} className="text-emerald-400" />
            <h3 className="text-sm font-semibold text-emerald-300">
              均值回归策略 ({filtered.filter(t => t.type === 'mean_reversion').length})
            </h3>
          </div>
          {filtered.filter(t => t.type === 'mean_reversion').map(t => (
            <TemplateCard key={t.key} t={t}
              expanded={expanded.has(t.key)}
              onToggle={() => toggle(t.key)}
            />
          ))}
        </div>
      )}

    </div>
  )
}
