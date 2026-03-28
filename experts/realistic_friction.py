"""
realistic_friction.py — 真实摩擦成本适配器

功能：
  1. 在任意价格数据上叠加真实摩擦成本（买卖价差、冲击成本、佣金）
  2. 区分"理想回测"和"含摩擦实盘预估"两个版本
  3. 输出对比报告，说明每种成本的业绩损耗

摩擦层次：
  Layer1: 佣金+印花税（固定费率）
  Layer2: 买卖价差（资产相关）
  Layer3: 市场冲击（订单量相关）
  Layer4: 滑点（极端行情放大）
"""

import math
from dataclasses import dataclass
from typing import List, Literal
from experts.expert1_generator import BacktestReport


# ─────────────────────────────────────────────
#  成本参数（真实市场数据）
# ─────────────────────────────────────────────

@dataclass
class FrictionParams:
    """
    各类资产的真实摩擦成本参数。
    数据来源：公开市场数据 + 业界经验
    """
    # 佣金（单边%，买卖双向收取）
    commission_rate: float = 0.03    # A股：万3双边 = 0.03%

    # 印花税（仅卖出收取，%）
    stamp_duty_rate: float = 0.10   # A股：千1印花税

    # 买卖价差（%，相对价格）
    spread_bps: float = 5.0          # A股主板：5~15bps（0.05%~0.15%）
    crypto_spread_bps: float = 20.0   # 加密货币：20~50bps

    # 市场冲击（订单额/总市值%，大单触发）
    market_impact_bps: float = 10.0  # 10bps/总仓

    # 滑点（极端行情，%）
    slippage_bps: float = 5.0         # 正常5bps
    slippage_extreme_bps: float = 30.0 # 极端行情（波动>3%/天）30bps

    # 最低佣金（每次交易保底）
    min_commission: float = 5.0      # A股：5元/笔

    # 加密货币特殊：资金费率（每8小时）
    funding_rate: float = 0.001        # 约0.01%/8h（每8h）

    def for_asset(self, asset_type: str = "stock") -> "FrictionParams":
        """按资产类型返回参数集"""
        p = FrictionParams()
        if asset_type == "crypto":
            p.commission_rate  = 0.04    # 币安现货：0.04%Maker/Taker
            p.spread_bps      = 20.0
            p.market_impact_bps= 15.0
            p.slippage_bps    = 5.0
            p.slippage_extreme_bps = 50.0
            p.stamp_duty_rate = 0.0     # 无印花税
            p.funding_rate    = 0.001
        elif asset_type == "futures":
            p.commission_rate = 0.02    # 期货：万2双边
            p.spread_bps     = 2.0
            p.slippage_bps   = 3.0
            p.stamp_duty_rate = 0.0
        return p  # stock default


# ─────────────────────────────────────────────
#  单笔交易摩擦成本计算
# ─────────────────────────────────────────────

@dataclass
class TradeCost:
    """单笔交易成本明细"""
    side            : str   # "buy" / "sell"
    price           : float
    quantity        : float
    commission      : float  # 佣金
    spread_cost     : float  # 价差损耗
    market_impact   : float  # 市场冲击
    slippage        : float  # 滑点
    stamp_duty      : float  # 印花税（仅卖出）
    total_cost      : float  # 总成本
    total_cost_bps  : float  # 总成本（基点）

    def summary(self) -> str:
        return (f"佣金{self.commission:.1f}元 + "
                f"价差{self.spread_cost:.1f}元 + "
                f"冲击{self.market_impact:.1f}元 + "
                f"滑点{self.slippage:.1f}元"
                f"{f' + 印花税{self.stamp_duty:.1f}元' if self.stamp_duty>0 else ''}"
                f" = {self.total_cost:.2f}元 ({self.total_cost_bps:.1f}bps)")


def calc_trade_cost(price: float, quantity: float, side: str,
                    params: FrictionParams,
                    daily_vol: float = 0.02,
                    is_crypto: bool = False) -> TradeCost:
    """
    计算单笔交易的完整摩擦成本。
    daily_vol: 当日收益率标准差（用于判断极端行情）
    """
    notional = price * quantity

    # 1. 佣金（双向收取，有保底）
    commission = max(notional * params.commission_rate / 100, params.min_commission)

    # 2. 价差（买入时价格向上偏移，卖出时向下偏移）
    spread_rate = params.crypto_spread_bps if is_crypto else params.spread_bps
    spread_cost = notional * spread_rate / 10000 / 2  # 均摊买卖

    # 3. 市场冲击（大订单时额外成本）
    impact_cost = notional * params.market_impact_bps / 10000

    # 4. 滑点（极端行情放大）
    if daily_vol > 0.03:   # >3% 日波动 = 极端
        slip_rate = params.slippage_extreme_bps
    else:
        slip_rate = params.slippage_bps
    slippage = notional * slip_rate / 10000

    # 5. 印花税（仅卖出，A股）
    stamp = notional * params.stamp_duty_rate / 100 if side == "sell" and params.stamp_duty_rate > 0 else 0.0

    total = commission + spread_cost + impact_cost + slippage + stamp
    total_bps = total / notional * 10000

    return TradeCost(
        side=side, price=price, quantity=quantity,
        commission=commission, spread_cost=spread_cost,
        market_impact=impact_cost, slippage=slippage,
        stamp_duty=stamp, total_cost=total, total_cost_bps=total_bps
    )


# ─────────────────────────────────────────────
#  回测报告含摩擦版本
# ─────────────────────────────────────────────

@dataclass
class FrictionAdjustedReport:
    """含摩擦成本调整后的回测报告"""
    original        : BacktestReport
    asset_type     : str  # "stock" / "crypto" / "futures"
    params         : FrictionParams

    # 调整后指标
    adj_return     : float  # 调整后总收益（%）
    adj_ann_return : float  # 调整后年化（%）
    adj_sharpe     : float  # 调整后夏普
    adj_max_dd     : float  # 调整后最大回撤
    adj_win_rate   : float  # 调整后胜率

    # 成本分解
    total_cost     : float  # 累计摩擦成本（元）
    cost_ratio     : float  # 成本/初始资金（%）
    avg_cost_bps   : float  # 平均每笔成本（bps）
    num_trades     : int    # 实际交易次数（去除成本后仍有意义的）

    # 损耗分析
    return_loss    : float  # 因成本损失的收益率（%）
    sharpe_loss    : float  # 夏普损耗
    dd_increase    : float  # 回撤增加（%）
    net_before_cost: float  # 摩擦前净收益（%）

    explanation    : str   # 可解释说明


def apply_friction(original: BacktestReport,
                  asset_type: str = "stock",
                  initial_cash: float = 1_000_000.0,
                  position_size_pct: float = 0.95) -> FrictionAdjustedReport:
    """
    将摩擦成本叠加到任意 BacktestReport 上。
    逻辑：
      1. 从 original 提取 trades 信息
      2. 估算每笔成交金额（基于 initial_cash * position_size_pct）
      3. 计算每笔摩擦成本并累计
      4. 调整最终收益率、夏普、胜率
    """
    p = FrictionParams().for_asset(asset_type)

    # 估算平均持仓金额（简化：假设每次用95%资金建仓）
    avg_position = initial_cash * position_size_pct

    # 原始指标
    net_before = original.total_return    # 摩擦前净收益
    ann_before = original.annualized_return
    sharpe_before = original.sharpe_ratio
    dd_before  = original.max_drawdown_pct
    n_trades   = original.total_trades
    daily_rets = original.daily_returns or []

    if n_trades == 0:
        return FrictionAdjustedReport(
            original=original, asset_type=asset_type, params=p,
            adj_return=net_before, adj_ann_return=ann_before,
            adj_sharpe=sharpe_before, adj_max_dd=dd_before, adj_win_rate=original.win_rate,
            total_cost=0.0, cost_ratio=0.0, avg_cost_bps=0.0, num_trades=0,
            return_loss=0.0, sharpe_loss=0.0, dd_increase=0.0,
            net_before_cost=net_before,
            explanation="无交易，成本为0"
        )

    # 计算每笔成本
    # 假设每次成交额 = avg_position / n_trades (简化)
    per_trade_notional = avg_position / n_trades if n_trades > 0 else 0.0

    # 判断极端行情比例（用于滑点计算）
    extreme_days = sum(1 for r in daily_rets[-60:] if abs(r) > 0.03) if daily_rets else 0
    vol_ratio = extreme_days / max(len(daily_rets[-60:]), 1)

    # 计算各类型成本
    total_commission = 0.0
    total_spread     = 0.0
    total_impact    = 0.0
    total_slippage  = 0.0
    total_stamp     = 0.0
    n_effective_trades = 0  # 去除成本后仍有正收益潜力的交易

    for i in range(n_trades):
        # 估算每笔价格（用均价代理）
        price_proxy = initial_cash * 1.05 / n_trades if n_trades > 0 else 100.0
        # 假设买卖各半
        side = "buy" if i % 2 == 0 else "sell"
        daily_vol = 0.02  # 默认日波动

        cost = calc_trade_cost(
            price=price_proxy,
            quantity=1.0,
            side=side,
            params=p,
            daily_vol=daily_vol,
            is_crypto=(asset_type == "crypto")
        )

        # 累计成本（买卖双向）
        total_commission += cost.commission * 2  # 买卖各收
        total_spread     += cost.spread_cost * 2
        total_impact    += cost.market_impact * 2
        total_slippage  += cost.slippage * 2
        if side == "sell":
            total_stamp += cost.stamp_duty

        # 如果成本 < 预期收益的30%，仍计入有效交易
        gross_per_trade = per_trade_notional * (abs(original.total_return / 100) / n_trades) if n_trades > 0 else 0
        if cost.total_cost < gross_per_trade * 0.8:
            n_effective_trades += 1

    total_cost = total_commission + total_spread + total_impact + total_slippage + total_stamp
    cost_ratio = total_cost / initial_cash * 100
    avg_bps = (total_cost / per_trade_notional / n_trades * 10000) if n_trades > 0 else 0

    # ── 调整收益率 ──────────────────────────
    # 成本直接从最终权益扣除（简化模型）
    final_notional = initial_cash * (1 + net_before / 100)
    adj_notional = final_notional - total_cost
    adj_return = (adj_notional / initial_cash - 1) * 100
    return_loss = net_before - adj_return

    # 年化调整（相同时间窗口）
    ann_adj = ((adj_notional / initial_cash) **
                (252 / max(len(daily_rets), 1)) - 1) * 100

    # ── 调整夏普（成本增加波动率）─────────────
    # 成本引入了额外"负收益"，增加波动率估算
    cost_series = [0.0] * len(daily_rets)
    for i in range(n_trades):
        if i < len(cost_series):
            cost_series[i] = -(total_cost / n_trades / initial_cash)

    import math
    def std(vals):
        n = len(vals)
        if n < 2: return 0.0
        m = sum(vals) / n
        return math.sqrt(sum((v-m)**2 for v in vals) / (n-1))

    combined_rets = [daily_rets[i] + cost_series[i] for i in range(len(daily_rets))]
    vol_adj = std(combined_rets) * math.sqrt(252)
    adj_sharpe = ann_adj / 100 / vol_adj if vol_adj > 0 else 0.0
    sharpe_loss = sharpe_before - adj_sharpe

    # ── 调整最大回撤 ────────────────────────
    # 成本使权益曲线下移，增加回撤深度
    cum = 1.0
    peak = 1.0
    max_dd = 0.0
    cum_rets = combined_rets
    for r in cum_rets:
        cum *= (1 + r)
        if cum > peak: peak = cum
        dd = (cum - peak) / peak
        if dd < max_dd: max_dd = dd
    adj_max_dd = abs(max_dd) * 100
    dd_increase = adj_max_dd - dd_before

    # ── 调整胜率（部分交易被成本抵消）────────
    gross_pnl = [0.0] * n_trades
    wins_before = sum(1 for g in gross_pnl if g > 0)
    # 成本后：部分小赚交易变成亏损
    break_even = total_cost / n_trades / (per_trade_notional or 1.0)
    n_wins_after = sum(1 for g in gross_pnl if g > break_even * 2)
    adj_win_rate = n_wins_after / n_trades * 100 if n_trades > 0 else 0.0

    # ── 可解释说明 ─────────────────────────
    asset_cn = {"stock":"A股","crypto":"加密货币","futures":"期货"}.get(asset_type,asset_type)
    spread_cn = p.crypto_spread_bps if asset_type=="crypto" else p.spread_bps
    slip_cn = p.slippage_extreme_bps if vol_ratio > 0.2 else p.slippage_bps
    explanation = (
        f"【{asset_cn}市场摩擦成本分析】\n"
        f"  基准：A {'模拟' if asset_type=='stock' else asset_type} 市场，"
        f"交易{original.total_trades}笔，平均持仓{avg_position/1e4:.0f}万/笔\n"
        f"  成本构成（每笔均值）：\n"
        f"    · 佣金：{p.commission_rate:.2f}%双向 ≈ {total_commission/n_trades/2:.0f}元/笔\n"
        f"    · 价差：~{spread_cn:.0f}bps ≈ {total_spread/n_trades/2:.1f}元/笔\n"
        f"    · 市场冲击：~{p.market_impact_bps:.0f}bps ≈ {total_impact/n_trades/2:.1f}元/笔\n"
        f"    · 滑点：~{slip_cn:.0f}bps ≈ {total_slippage/n_trades/2:.1f}元/笔"
    )
    if p.stamp_duty_rate > 0:
        explanation += f"\n    · 印花税（仅卖出）：{p.stamp_duty_rate:.1f}% ≈ {total_stamp:.0f}元/笔"
    explanation += (
        f"\n  累计总成本：{total_cost:.0f}元（占初始资金{cost_ratio:.2f}%）\n"
        f"  业绩损耗：收益 -{return_loss:.1f}pp | 夏普 -{sharpe_loss:.2f} | 回撤 +{dd_increase:.1f}pp\n"
        f"  调整后：年化{ann_adj:.1f}%（原始{ann_before:.1f}%）| "
        f"夏普{adj_sharpe:.2f}（原始{sharpe_before:.2f}）"
    )

    return FrictionAdjustedReport(
        original=original, asset_type=asset_type, params=p,
        adj_return=round(adj_return, 2),
        adj_ann_return=round(ann_adj, 2),
        adj_sharpe=round(adj_sharpe, 3),
        adj_max_dd=round(adj_max_dd, 2),
        adj_win_rate=round(adj_win_rate, 1),
        total_cost=round(total_cost, 0),
        cost_ratio=round(cost_ratio, 2),
        avg_cost_bps=round(avg_bps, 1),
        num_trades=n_effective_trades,
        return_loss=round(return_loss, 2),
        sharpe_loss=round(sharpe_loss, 3),
        dd_increase=round(dd_increase, 2),
        net_before_cost=round(net_before, 2),
        explanation=explanation
    )


# ─────────────────────────────────────────────
#  对比报告生成
# ─────────────────────────────────────────────

def compare_reports(original_reports: list,
                   asset_type: str = "stock",
                   initial_cash: float = 1_000_000.0) -> list:
    """
    对一组策略生成对比报告（原始 vs 含摩擦版本）。
    返回含摩擦调整后的报告列表。
    """
    return [apply_friction(r, asset_type, initial_cash) for r in original_reports]


def print_comparison(compared: list, round_num: int = 1):
    """打印对比表格"""
    print(f"\n{'='*70}")
    print(f"  📊 真实摩擦成本对比报告 — 第 {round_num} 轮")
    print(f"{'='*70}")

    header = (f"  {'策略':<18} {'类型':<8} "
               f"{'原始年化':>10} {'摩擦后年化':>10} "
               f"{'损耗':>8} {'原始夏普':>8} {'摩擦后夏普':>10} "
               f"{'成本占比':>8} {'说明'}")
    print(header)
    print(f"  {'─'*66}")

    for c in compared:
        r = c.original
        loss_icon = "🔴" if c.return_loss > 5 else ("🟡" if c.return_loss > 1 else "🟢")
        asset_icon = {"stock":"📈","crypto":"₿","futures":"📊"}.get(c.asset_type,"📊")
        print(f"  {loss_icon}{r.strategy_name[:16]:<16} {asset_icon}{c.asset_type:<7} "
              f"{c.net_before_cost:>+8.1f}% "
              f"{c.adj_ann_return:>+10.1f}% "
              f"{c.return_loss:>+7.1f}pp "
              f"{c.original.sharpe_ratio:>8.3f} "
              f"{c.adj_sharpe:>+10.3f} "
              f"{c.cost_ratio:>7.2f}%  "
              f"成本{c.total_cost:.0f}元")

    # 汇总
    total_cost = sum(c.total_cost for c in compared)
    avg_loss   = sum(c.return_loss for c in compared) / len(compared)
    worst = max(compared, key=lambda x: x.return_loss)
    best  = min(compared, key=lambda x: x.return_loss)

    print(f"\n  📋 汇总：")
    print(f"     累计摩擦成本：{total_cost:.0f}元")
    print(f"     平均收益损耗：{avg_loss:.1f}pp/策略")
    print(f"     🔴 损耗最大：{worst.original.strategy_name}（损耗{worst.return_loss:.1f}pp）")
    print(f"     🟢 损耗最小：{best.original.strategy_name}（损耗{best.return_loss:.1f}pp）")
    if avg_loss > 10:
        print(f"\n     ⚠️ 警告：平均损耗{avg_loss:.1f}pp，严重侵蚀收益！")
        print(f"     建议：①减少交易频率；②提高策略最低夏普门槛；③加入成本预扣模型")
    elif avg_loss > 3:
        print(f"\n     ⚠️ 注意：平均损耗{avg_loss:.1f}pp，需关注交易频率")
    else:
        print(f"\n     ✅ 成本控制在{avg_loss:.1f}pp以内，策略可持续")

    print(f"\n{'='*70}")
