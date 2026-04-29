# Design Record — Readm/quant 系统设计日志

> 维护者: System Designer
> 记录原则: 只追加不修改，问题→方案结构

---

## 2026-04-26 评分体系认知更正: OOS 不适用

**问题**：误将 OOS（样本外分割）作为评分惩罚因子，用 train/test split 来惩罚策略。

**诊断**：本系统不是 ML。策略参数是随机生成的组合（N=3/R=10/V=weight_method 等枚举值），不是通过梯度下降学习的。每个候选独立产生，在全量数据和子集上的差异只反映统计方差，不是过拟合。

**方案**：移除 OOS 衰减惩罚。评分只基于全量数据指标 + PBO 洗牌检验 + 交易数门槛。OOS Walk-Forward 报告保留为参考信息，不参与评分决策。

**涉及文件**：
- `experts/evaluator.py` — 移除 OOS 权重

---

## 2026-04-26 trade_return 修复: 使用真实成本基准

**问题**：卖出时 trade_return 的分母用了 `total_cash / N`，导致即使亏损 50% 也显示正收益。

**诊断**：`net / initial_cash - 1/N` 不是真实的持仓收益率。需要 `(net - cost_basis) / cost_basis`。

**方案**：两处卖出逻辑（常规调仓 + risk overlay）统一使用持仓成本(cost_basis)作为分母。买入时跟踪 entry_price，卖出时计算 `(卖出净额 - 持仓成本) / 持仓成本`。

**涉及文件**：
- `backtest/engine.py`:957, 815 — 两处 sell 逻辑

**验收**：v5.9 提交。验证: 50%亏损场景下 old=+0.2493, new=-0.5010。

---

## 2026-04-29 Alpha 缩放扁平化修复

**问题**：`alpha_scaled = max(0, min(100, alpha * 5))` 导致 alpha > 20% 后全部封顶 100 分，alpha=20% 和 alpha=86.5% 拿同样的分数，维度失去区分度。

**方案**：改为 `alpha_scaled = max(0, min(100, alpha))`（直接线性映射，alpha 本身已是百分比）。同步降低 Alpha 权重 0.24→0.18，提高 Sortino 权重 0.22→0.26。

**涉及文件**：
- `experts/evaluator.py`:221 — 缩放因子修改
- `experts/evaluator.py`:41-45 — 权重调整（总和保持 1.0）

**验收**：v5.8 提交。冒烟测试通过。

---

## 2026-04-29 Sharpe 公式修正: CAGR/σ → mean(r)/σ×√252

**问题**：Sharpe 计算用了 `CAGR / σ×√252`，不是标准定义 `mean(r)/σ×√252`。CAGR 在正收益序列下因复利放大效应虚高 Sharpe 值。

**方案**：用算术平均日收益替代 CAGR 作为分子。CAGR 保留用于 Calmar 计算（Calmar = CAGR / 最大回撤，这是 Calmar 的标准定义，不受影响）。

**涉及文件**：
- `backtest/engine.py`:998 — Sharpe 计算行

**验收**：v5.10 提交。验证: 模拟数据旧 11.8 → 新 6.1。

---

## 2026-04-29 n_stocks 范围扩展 [2,5]→[2,10]

**问题**：n_stocks 上限为 5（最多同时持有 5 只股票），组合高度集中，单股仓位大，回测结果不具实盘参考性。

**方案**：将 n_stocks 范围上限从 5 扩展到 10。LLM 元专家可动态调节 n_stocks_max 到 3~10。

**涉及文件**：
- `experts/orchestrator.py`:171
- `experts/llm_prompts.py`:55, 69
- `experts/meta_monitor.py`:440, 462

**验收**：v5.11 提交。后续回测中已出现 N6~N9 配置。

---

## 2026-04-29 反垄断评分激活: _monopoly_suppression 从死代码到启用

**问题**：`_monopoly_suppression` 方法在 evaluator.py 中定义但从未被调用，导致反垄断逻辑完全失效。KDJ/MFI 等趋势类策略持续霸榜。

**方案**：在复合评分中加入 `monopoly_bonus = self._monopoly_suppression(...)`, 当 Top-3 全是趋势类时给均值回归策略 +3 分。与原有的 diversity_bonus（最长 8 轮未出现 +8 分）叠加使用，形成两层多样性保护。

**涉及文件**：
- `experts/evaluator.py`:235-237 — 添加调用行

**验收**：v5.11 提交。v5.12 验证: RSI 均值回归以 96.6 分登顶。

---

## 2026-04-29 执行损耗(execution_shortfall)追踪

**问题**：无法区分策略的收益来自"选股能力"还是"信号被市场提前抢跑"。拥挤的信号在信号发出到实际成交之间价格已经跳升。

**方案**：每次买入时记录 `(close[t+1] - close[t]) / close[t]`（信号价到执行价的差值），存入 BacktestReport 的 execution_shortfall_median/mean 字段，通过 EvalResult 传递到结果输出。

**涉及文件**：
- `backtest/engine.py`:912 — 新增 exec_shortfalls 列表 + 每次买入计算
- `backtest/engine.py`:1001 — _build_report 计算中位/均值
- `experts/specialists/factor_combo_expert.py`:26-27 — BacktestReport 新增字段
- `experts/evaluator.py`:89-90 — EvalResult 新增字段

**验收**：v5.13 提交。smoke_test 通过。下次全量回测会自动输出各策略的执行损耗。

---
