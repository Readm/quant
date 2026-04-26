# 变更计划 — Iter11: 修复PBO+OOS衰减+多样性（回应评价师）

## 需求
根据 Iter10 量化策略评价师审查结论，修复三个问题：
1. PBO 评分始终为 0，门控从未生效（死代码）
2. OOS 衰减最高 -14.9%，但评分中不惩罚衰减
3. TrendExpert 连续 20 轮垄断，多样性指数 0.00

## 风险等级
isolated（只改 evaluator.py 的评分逻辑，不改数据链）

## 问题根因分析

### PBO 缺失
`_pbo_gate()` 传入 `report.daily_returns` 给期望收盘价的 `compute_pbo`，
且 signal_fn 使用 `lambda c, **kw: [0]*len(c)` 恒为 0 的信号。
同时 `compute_pbo` 要求的 PBO 语义（越高越稳健）与 `_pbo_gate` 的阈值（>=0.6 硬拒）方向相反。
结果是这个门控从未生效过。

### OOS 衰减
`oos_annualized_return` 已在 EvalResult 中，但完全未参与评分。

### 多样性
Iter10 把多样性奖励上限从 8.0 降到 6.0，使 TrendExpert 更易垄断。
应反向操作。

## 修改内容

### 1. `_pbo_gate` 重写为收益序列洗牌法（MCS test）
- 不需要参数网格，不需要信号函数
- 洗牌策略日收益序列 300 次，每次计算 Sharpe
- PBO = 洗牌后 Sharpe 超过实际 Sharpe 的概率
- 阈值：>0.30 硬拒（超过 30% 的随机洗牌能打败实际策略→过拟合）
- 这比参数网格法更简单、更鲁棒（对参数不敏感）

### 2. 加入 OOS 衰减惩罚
- 从 EvalResult 读取 `oos_annualized_return`
- 计算衰减率: `decay = (in_sample_ann - oos_ann) / abs(oos_ann)` 
- 衰减 > 50% → composite ×0.80
- 衰减 > 100%（样本外亏损）→ composite ×0.60

### 3. 多样性奖励调回+加强
- 上限从 6.0 恢复到 8.0
- 增加一个额外的"反垄断"加分：如果当前轮 top-3 全部是同一 type（trend），
  给其他 type 的候选 +3 加分（强制干预）
