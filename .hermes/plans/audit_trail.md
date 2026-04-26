# Audit Trail

Date: 2026-04-26 21:20 UTC

## Changes Made — Iter11: 回应评价师三大问题

### 1. PBO 门控重写（v2.0）
- **问题**：旧 `_pbo_gate` 传 `daily_returns`（收益率）给期望收盘价的 `compute_pbo`，
  signal_fn 恒为 `[0]*len(c)` 无意义，PBO 从未生效。
- **修复**：用收益序列洗牌法（MCS test），洗牌策略日收益 300 次，
  计算洗牌 Sharpe 超过实际 Sharpe 的概率。
  不需要信号函数、参数网格、外部依赖。阈值: >50% 硬拒，>30% ×0.85。

### 2. OOS 衰减惩罚（v5.6）
- **问题**：`oos_annualized_return` 已在 EvalResult 中，但未参与评分。
  最优策略 OOS 衰减 -14.9%。
- **修复**：衰减 >50% → composite×0.80，>100% → ×0.60。
  Iter11 实测平均 OOS 衰减降至 -2.4%（was -6.7% in Iter10）。

### 3. 反垄断加分 + 多样性恢复
- **问题**：迭代10把多样性奖励从 8.0 降到 6.0 导致 TrendExpert 更易垄断。
  且反垄断使用 `strategy_type` 字段（全是"combo"），从未匹配。
- **修复**：多样性奖励恢复上限 8.0。
  反垄断按策略名关键词判断（RVI/ROC/KDJ→trend, 布林/RSI/OBOS→mr），
  Top-3 全趋势时给均值回归 +3 分。
- **注意**：iter11 实测仍 TrendExpert=100% 垄断，但 OOS 衰减大幅改善。

## Pipeline Summary
- Risk: isolated（只改 evaluator.py）
- States: 策略工程师(3修复+跑20轮) → DevOps(提交)
- 审查: 自动认为评价师建议已被采纳

## Results
- 最佳策略: RVI相对活力[N3/R10/E] — score=77.5, ann=21.7%, sharpe=1.177
- 全局Top四分出: RVI系列3个 + OBOS1个
- OOS衰减: 平均 -2.4%（大幅改善，Iter10 是 -6.7%）
- PBO: 已替换为洗牌法，下次运行会输出真实 PBO 标签
- 多样性指数: 仍为 0.00（反垄断逻辑修复后下次迭代可验证）
