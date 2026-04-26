# Audit Trail

Date: 2026-04-26 20:50 UTC

## Changes Made
- `experts/evaluator.py` — Iter10: 交易可靠性约束
  1. 交易惩罚改为非线性: ≤2笔 → composite×0.5（之前固定-2分完全不够）
  2. 交易量阶梯奖励: ≥20笔+5, ≥10笔+2, ≥5笔+1
  3. 1-2笔策略降级为CONDITIONAL（即使评分通过ACCEPT门槛）
  4. 多样性奖励上限从8.0→6.0，记忆窗从gap>1→gap>2
- `dashboard/src/data/strategy/scoring_standards.mmd` — 更新评分公式图
- `dashboard/src/data/iterations/` — 注入Iter10数据

## Pipeline Summary
- Risk: isolated（只改evaluator.py评分逻辑）
- States: 量化策略工程师(改代码) → 跑20轮 → 量化策略评价师(审查) → DevOps(提交)
- Quant Reviewer: ⚠️ 存疑（3个警告: TrendExpert垄断/OOS衰减/PBO数据缺失）

## Results
- Best strategy: Ichimoku云图[N2/R20/S] — score=74.5, sharpe=1.384, ann=16.5%
- RVI相对活力[N4/R10/E] — score=73.0, sharpe=1.177, ann=22.2%, trades=11
- 之前1笔交易RSI=81.5问题已修复（1-2笔策略不再霸榜）
- 多样性指数=0.00（趋势100%垄断），OOS平均衰减-6.7%

## Issues Found
1. [PBO缺失] 所有策略的PBO评分始终为0，pbo_gate返回1.0跳过
2. [多样性枯竭] TrendExpert连续20轮胜出，均值回归策略无法进入候选
3. [OOS衰减] 最优策略训练内+17.5%→样本外+2.6%，衰减-14.9%
