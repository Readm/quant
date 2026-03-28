"""
regime_detector.py — 市场状态检测器（无未来函数版）

核心原则：每个时间点 t，regime 状态只用 t-1 及之前的数据计算。
绝对禁止：使用未来数据 / 前瞻指标 / 全样本统计。

检测方法（纯历史滚动窗口）：
  1. 波动率 regime：高/低波动，基于 recent_vol / rolling_avg_vol 比值
  2. 趋势 regime：趋势强度，基于 ADX 或均线多头排列
  3. 市场状态：上涨 / 下跌 / 震荡，基于最近 N 天累计收益方向

Regime 分类（4象限）：
  ┌─────────────────────────────┬─────────────────────────────┐
  │  高波动+上涨（动量市场）     │  高波动+下跌（恐慌/做空市场） │
  ├─────────────────────────────┼─────────────────────────────┤
  │  低波动+上涨（慢牛市场）     │  低波动+震荡（区间整理市场）   │
  └─────────────────────────────┴─────────────────────────────┘

推荐策略（基于检测到的 regime）：
  · 动量市场 → 趋势追踪（MA金叉、MACD）
  · 恐慌/做空市场 → 反向布局（RSI超卖买入）
  · 慢牛市场 → 买入持有 + 移动止盈
  · 震荡市场 → 均值回归（布林带RSI）
"""

import math
from dataclasses import dataclass
from enum import Enum


class VolRegime(Enum):
    LOW_VOL  = "低波动"
    HIGH_VOL = "高波动"


class TrendRegime(Enum):
    UPTREND   = "上涨"
    DOWNTREND = "下跌"
    SIDEWAYS  = "震荡"


@dataclass
class MarketRegime:
    """当前市场状态快照（只基于历史数据）"""
    timestamp_idx: int   # 数据索引（时间点）

    vol_regime    : VolRegime    # 波动率状态
    trend_regime  : TrendRegime  # 趋势状态

    # 原始指标值（用于调试/可解释性）
    recent_vol     : float   # 最近20天年化波动率
    avg_hist_vol   : float   # 历史平均年化波动率（滚动60天窗口）
    vol_ratio      : float   # recent_vol / avg_hist_vol（>1=高波动）
    adx_value      : float   # ADX趋势强度指标
    recent_return  : float   # 最近20天累计收益（>0=上涨）
    price_vs_ma120 : float   # 当前价格 / 120日均线（>1=在均线上方）

    # 综合评分（0~100，50=中性）
    regime_score   : float   # >50偏多，<50偏空
    regime_label   : str     # 综合标签

    # 推荐的策略类型（基于检测到的状态）
    recommended_strategies: list[str]  # e.g. ["RSI均值回归","布林带"]
    position_cap           : float      # 建议最大仓位（0~1）

    # 数据来源（用于调试）
    lookback_used: int  # 用多少天历史数据做出判断


def compute_regime(closes: list, highs: list | None = None,
                   lows: list | None = None,
                   vol_window: int = 20,
                   trend_window: int = 60,
                   current_idx: int | None = None) -> MarketRegime:
    """
    计算当前市场状态。

    参数：
      closes      : 收盘价列表（全量历史数据）
      current_idx : 当前评估的时间点索引（默认为最后一天）
                   用途：在回测中模拟"只有历史数据可用"

    安全约束：
      此函数绝对不使用任何未来的数据。
      current_idx 默认为 len(closes)-1（即"今天"），
      传入更小的值可模拟历史某时间点的regime状态。
    """
    n = len(closes)
    if highs is None: highs = closes
    if lows  is None: lows  = closes

    # 确认当前评估点
    if current_idx is None:
        current_idx = n - 1

    # ── 边界保护 ──────────────────────────────────────────
    min_required = max(vol_window, trend_window, 150)
    if current_idx < min_required:
        # 数据不足，返回中性状态
        return _neutral_regime(current_idx, lookback_used=current_idx)

    # ── 第一步：波动率 regime（只用历史数据）──────────────
    #
    # recent_vol：最近 vol_window 天的年化波动率
    # avg_hist_vol：历史上前 vol_window~trend_window 天的平均波动率
    #
    # 关键：两者都只用 current_idx 及之前的数据
    # 不存在任何前瞻（look-ahead）bias

    # 最近 vol_window 天日收益率
    start_vol = max(0, current_idx - vol_window + 1)
    recent_rets = [
        math.log(closes[i] / closes[i - 1])
        for i in range(start_vol + 1, current_idx + 1)
    ]
    mu_rv = sum(recent_rets) / len(recent_rets)
    recent_var = sum((r - mu_rv) ** 2 for r in recent_rets) / len(recent_rets)
    recent_vol = math.sqrt(recent_var * 252)  # 年化

    # 历史平均波动率（再往前推 trend_window 天）
    start_hist = max(0, current_idx - trend_window)
    end_hist   = start_vol
    hist_rets = [
        math.log(closes[i] / closes[i - 1])
        for i in range(start_hist + 1, end_hist + 1)
    ]
    if len(hist_rets) >= 10:
        mu_hv = sum(hist_rets) / len(hist_rets)
        hist_var = sum((r - mu_hv) ** 2 for r in hist_rets) / len(hist_rets)
        avg_hist_vol = math.sqrt(hist_var * 252)
    else:
        avg_hist_vol = recent_vol

    vol_ratio = recent_vol / (avg_hist_vol + 1e-9)
    vol_regime = VolRegime.HIGH_VOL if vol_ratio > 1.1 else VolRegime.LOW_VOL

    # ── 第二步：趋势 regime ──────────────────────────────
    #
    # 使用 ADX 类似物（基于均线斜率的方向性指标）
    # 仅用历史数据，无前瞻

    # 计算 trend_window 天均线
    start_ma = max(0, current_idx - trend_window + 1)
    ma_vals = []
    for t in range(start_ma, current_idx + 1):
        window_c = closes[start_ma:t + 1]
        ma_vals.append(sum(window_c) / len(window_c))

    # 最近 ma_window 天的均线斜率（趋势强度）
    ma_window = 10
    if len(ma_vals) > ma_window:
        slope_numerator = sum(
            (ma_vals[i] - ma_vals[i - 1])
            for i in range(len(ma_vals) - ma_window + 1, len(ma_vals))
        )
        slope_denom = sum(abs(ma_vals[i] - ma_vals[i - 1]) for i in
                         range(len(ma_vals) - ma_window + 1, len(ma_vals)))
        adx_value = abs(slope_numerator) / (slope_denom + 1e-9) * 100
    else:
        adx_value = 0.0

    # 价格 vs 120日均线（>1 = 在均线之上 = 偏多）
    ma120_start = max(0, current_idx - 119)
    ma120 = sum(closes[ma120_start:current_idx + 1]) / (current_idx - ma120_start + 1)
    price_vs_ma120 = closes[current_idx] / (ma120 + 1e-9)

    # 最近 20 天累计收益（判断方向）
    ret_start = max(0, current_idx - 19)
    recent_return = (closes[current_idx] / (closes[ret_start] + 1e-9)) - 1

    # 趋势状态判断（只用历史）
    if adx_value > 0.15 and price_vs_ma120 > 1.02:
        trend_regime = TrendRegime.UPTREND
    elif adx_value > 0.15 and price_vs_ma120 < 0.98:
        trend_regime = TrendRegime.DOWNTREND
    else:
        trend_regime = TrendRegime.SIDEWAYS

    # ── 第三步：综合评分（-100~+100，偏空到偏多）─────────
    #
    # 只用历史数据计算的方向性指标组成
    score = 0.0
    score += (price_vs_ma120 - 1.0) * 50   # 价格vs均线权重
    score += recent_return * 100            # 近期方向权重
    score += (1 - vol_ratio) * 20          # 低波动给正分
    regime_score = max(-100, min(100, score))

    # ── 第四步：标签 ───────────────────────────────────
    if   regime_score >  20: label = "偏多"
    elif regime_score < -20: label = "偏空"
    else:                    label = "中性"

    # ── 第五步：推荐策略（基于检测到的状态，非预测）──────
    if vol_regime == VolRegime.HIGH_VOL:
        if trend_regime == TrendRegime.UPTREND:
            rec_strategies = ["动量突破", "MACD趋势"]
            pos_cap = 0.40
        elif trend_regime == TrendRegime.DOWNTREND:
            rec_strategies = ["RSI超卖", "布林带反向"]
            pos_cap = 0.25
        else:
            rec_strategies = ["布林带", "RSI均值回归"]
            pos_cap = 0.30
    else:  # LOW_VOL
        if trend_regime == TrendRegime.UPTREND:
            rec_strategies = ["均线多头", "趋势追踪"]
            pos_cap = 0.60
        elif trend_regime == TrendRegime.DOWNTREND:
            rec_strategies = ["固收替代", "防御配置"]
            pos_cap = 0.20
        else:
            rec_strategies = ["RSI均值回归", "布林带"]
            pos_cap = 0.40

    lookback = current_idx - start_ma  # 实际用了多少天

    return MarketRegime(
        timestamp_idx   = current_idx,
        vol_regime     = vol_regime,
        trend_regime   = trend_regime,
        recent_vol     = round(recent_vol * 100, 2),    # 转为百分比
        avg_hist_vol   = round(avg_hist_vol * 100, 2),
        vol_ratio      = round(vol_ratio, 3),
        adx_value      = round(adx_value, 4),
        recent_return  = round(recent_return * 100, 2),
        price_vs_ma120= round(price_vs_ma120, 3),
        regime_score   = round(regime_score, 1),
        regime_label   = label,
        recommended_strategies = rec_strategies,
        position_cap   = pos_cap,
        lookback_used  = lookback,
    )


def _neutral_regime(idx: int, lookback_used: int) -> MarketRegime:
    return MarketRegime(
        timestamp_idx   = idx,
        vol_regime     = VolRegime.LOW_VOL,
        trend_regime   = TrendRegime.SIDEWAYS,
        recent_vol     = 0.0,
        avg_hist_vol   = 0.0,
        vol_ratio      = 1.0,
        adx_value      = 0.0,
        recent_return  = 0.0,
        price_vs_ma120= 1.0,
        regime_score   = 0.0,
        regime_label   = "数据不足（中性）",
        recommended_strategies = ["RSI均值回归"],
        position_cap   = 0.30,
        lookback_used  = lookback_used,
    )


def compute_regime_series(closes: list) -> list[MarketRegime]:
    """
    为整个价格序列计算 regime 标签序列。
    用于策略选择（每个时间点知道自己处于什么状态）。

    注意：这是逐点计算，每个 regime 只用该时间点之前的数据。
    """
    results = []
    for i in range(len(closes)):
        r = compute_regime(closes, current_idx=i)
        results.append(r)
    return results


def print_regime_table(regime_series: list[MarketRegime],
                       closes: list, dates: list | None = None,
                       max_rows: int = 30):
    """打印 regime 序列（每 max_rows 天一行）"""
    n = len(regime_series)
    step = max(1, n // max_rows)
    print(f"\n{'='*70}")
    print(f"  🌡️  Market Regime History ({n} days, sampled every {step} days)")
    print(f"{'='*70}")
    print(f"  {'Idx':>4} {'Date':<12} {'收盘价':>10} "
          f"{'波动':^6} {'趋势':^8} {'评分':>6} {'推荐策略':<18} {'仓位'}")
    print(f"  {'─'*65}")
    for i in range(0, n, step):
        r = regime_series[i]
        price = closes[i]
        date_str = dates[i][:10] if dates and i < len(dates) else f"d{i}"
        vol_icon = "📈" if r.vol_regime == VolRegime.LOW_VOL else "📊"
        trend_icon = {"UPTREND":"↑","DOWNTREND":"↓","SIDEWAYS":"→"}.get(
            r.trend_regime.value, "?")
        score_bar = "█" * int(abs(r.regime_score) / 10) + "░" * (
            10 - int(abs(r.regime_score) / 10))
        sign = "+" if r.regime_score > 0 else ""
        rec = ",".join(r.recommended_strategies[:2])
        print(f"  {i:>4} {date_str:<12} {price:>10.2f} "
              f"{vol_icon}{r.vol_ratio:>5.1f}x {trend_icon}{r.trend_regime.value:<6} "
              f"{sign}{r.regime_score:>5.1f} {rec:<18} {r.position_cap:.0%}")
    print(f"{'='*70}")
