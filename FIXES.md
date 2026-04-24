# 量化系统修复记录

## 2026-04-25  Walk-Forward 三步反过拟合 + 两项执行 Bug

### Fix 1 — Holdout 函数恒为 0%
**文件**: `experts/orchestrator.py` · `_holdout_validate`  
**原因**: `primary_data.get("returns", ...)` 找不到顶层键，始终返回 `[0]*n`，OOS 验证永远显示 0%。  
**修复**: 直接读 `e.oos_annualized_return`（由引擎在 OOS 段计算后写入 EvalResult）。

---

### Fix 2 — 幸存者偏差（流动性筛选用了未来数据）
**文件**: `scripts/run_iteration.py` · `_load_a_share_symbols`  
**原因**: `rows[-60:]` 取的是 2026 年最新 60 天成交额，用 2026 年的流动性来决定 2020–2025 年的回测股票池，引入幸存者偏差。  
**修复**: 改为 `rows[:-OOS_DAYS][-60:]`，只看训练期末尾 60 天，不碰样本外区间。

---

### Fix 3 — Walk-Forward IS/OOS 分段回测
**文件**: `backtest/engine.py`、`experts/orchestrator.py`、`experts/specialists/expert1a_trend.py`、`experts/evaluator.py`  
**原因**: 所有历史数据（含样本外）都参与 IS 参数优化，等同于用测试集调参。  
**修复**:
- `engine.py`: 提取 `_sim_range(t_start, t_end, ...)`，IS 只跑 `[1, n-252)`，OOS 跑 `[n-252, n)`，OOS 年化写入 `BacktestReport.oos_annualized_return`
- `evaluator.py`: `EvalResult` 新增 `oos_annualized_return: float = 0.0`，在 `evaluate()` 中从 `BacktestReport` 复制
- `orchestrator.py`: `OOS_DAYS = 252` 常量；`_backtest_one_cand` 传入 `oos_days=252`

---

### Fix 4 — pct_chgs 未透传（涨跌停过滤失效）
**文件**: `experts/data_loader.py` · `load_symbols_data`  
**原因**: 数据字典中缺少 `pct_chgs` 键，引擎始终得到空列表，涨跌停阈值过滤完全失效。  
**修复**: 添加 `"pct_chgs": raw_d.get("pct_chgs", [])` 到输出 dict。

---

### Fix 5 — 同日信号+成交（未来函数）
**文件**: `backtest/engine.py` · `_sim_range`  
**原因**: 调仓时用 `closes[t]`（今日收盘）计算信号，同时也用 `closes[t]` 成交。收盘价只有收盘后才知道，无法在知道收盘价之前下单并以收盘价成交。  
**修复**: 信号在 `t` 日收盘后生成，以 `exec_t = t + 1` 次日价格成交（含涨跌停过滤同步改为 `exec_t`）。最后一根 K 线不再触发调仓（`t + 1 < t_end` 守卫）。

---

### Fix 6 — 冠军保留被同名变体踢出
**文件**: `experts/orchestrator.py` · 冠军注入块  
**原因**: 冠军注入以 `strategy_name` 去重（格式 `"Aroon交叉[N4/R5/E]"`，只含模板+组合参数），LLM 下一轮生成同名但指标参数不同的变体，导致冠军被踢出，最优分数在轮次间反复振荡下降。  
**修复**: 改为以 `strategy_id`（含完整参数 hash）去重，保证冠军精确参数一定被保留。
