# Change Plan — 修正 trade_return 计算 bug

## 需求
修复 `backtest/engine.py` 中 trade return 计算：卖出的收益率用 `net / initial_cash` 而非实际成本，导致所有交易的 win_rate=100%。

## 风险等级: isolated
不改接口签名（BacktestReport字段名不变），只改计算逻辑内部。

## 任务分派

### Task 1 — 回测引擎工程师
- **文件**: `backtest/engine.py`
- **改动点**:
  1. **Line 951**（常规卖出）: `trades.append(net / initial_cash - 1.0 / max(len(sym_list), 1))`
     → 改为用 `shares * entry_price * (1 + BUY_COST)` 作为成本基准计算 trade_return
     → 需要从 `self._holding_entry_prices.pop(sym, None)` 读取 entry_price
  
  2. **Line 815**（风险覆盖卖出）: `trades_list.append(net / initial_cash - 1.0 / max(len(closes_by_sym), 1))`
     → 同理改为成本基准计算
     → 已有 `entry_price = self._holding_entry_prices.get(sym, 0)` 可用
  
  3. 卖出后清理 `_holding_entry_prices` 和 `_holding_peak_prices` 中已平仓的符号
     
  4. 风险覆盖方法 `_apply_risk_overlay` 返回时，需同步清理已平仓符号的 `_holding_entry_prices` 和 `_holding_peak_prices`

- **验证方法**:
  1. `python3 -c "compile(open('backtest/engine.py').read(), 'backtest/engine.py', 'exec')"` → 语法正确
  2. 写一段双随机行情验证：买入100元，50元卖出 → trade_return ≈ -50%

### Task 2 — 代码质量审查
- 审查 `backtest/engine.py` 的改动
- 重点: 异常路径（entry_price=0时的兜底）、并发安全
- 输出质量报告

### Task 3 — DevOps
- 冒烟测试 + dashboard验证 + build + commit

## 依赖顺序
```
Task 1 ─→ Task 2 ─→ Task 3
```
