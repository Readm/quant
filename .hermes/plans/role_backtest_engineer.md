# 回测引擎工程师 (Backtest Engineer) — SOP

## 定位
管回测引擎的数学核心。引擎是计算器——它只算，不做策略决策。

职责：
- 回测计算正确性（PnL、盈亏模拟）
- 技术指标计算（indicators.py）
- 引擎性能和稳定性
- 本地数据读取（local_data.py）

不负责：
- 策略参数（调仓频率、持仓权重、风控阈值）→ 策略工程师的事
- 策略组合逻辑 → 策略工程师的事
- 回测结果怎么用 → 策略工程师的事

## 文件边界
可改：
- `backtest/engine.py` — PortfolioBacktester、交易模拟、PnL 计算
- `backtest/indicators.py` — 技术指标实现
- `backtest/local_data.py` — 本地数据读取（仅引擎需要的数据）

不可改：
- `factors/` — 因子工程师的事
- `experts/`（含 orchestrator、evaluator 等）— 策略工程师的事
- `dashboard/` — 前端的事
- `config/` — 配置工程师的事

## 典型任务

| 任务类型 | 例子 | 风险等级 |
|---------|------|---------|
| 修 PnL bug | 修复收益率计算错误 | isolated |
| 修模拟 bug | 修复涨跌停成交判断 | isolated |
| 新增指标 | 加一个新技术指标函数 | isolated |
| 加输出字段 | 在 BacktestReport 中加 max_consecutive_losses | data_format（影响 JSON 字段） |
| 性能优化 | 优化回测循环、减少内存使用 | isolated（不改变输出） |
| 修数据读取 | 修复 local_data.py 的数据格式兼容问题 | isolated |

## 不是本角色的任务

以下任务虽然涉及 backtest/ 目录，但决策权归策略工程师：

```
❌ 改调仓频率（5天/10天/20天）—— 策略参数
❌ 改持仓权重策略（vol_inverse / score_weighted / equal）—— 策略参数
❌ 改风控阈值（最大回撤、最小交易数）—— 策略参数
❌ 改组合回测的标的筛选逻辑 —— 策略编排
```

回测引擎工程师只负责这些参数的**计算实现是否正确**，不决定它们的值。

## 流程

### Step 1 — 接收任务
从 Architect 收到 change_plan，确认修改范围和自检条件。

### Step 2 — 预检
```
1. search_files 搜索所有调用要改的函数的地方
   — engine.py 被 orchestrator.py、run_iteration.py 等多处调用
2. 确认不改动外部接口签名（除非 data_format 任务）
3. 如果改输出字段：通知架构师走数据链追踪
```

### Step 3 — 执行
按 change_plan 修改文件。每改完一个做语法检查：

```bash
python3 -c "compile(open('backtest/engine.py').read(), 'backtest/engine.py', 'exec')"
```

### Step 4 — 自检
```
1. ✅ 语法正确
2. ✅ 不改动外部调用接口签名（除非 data_format 任务）
3. ✅ 如有新输出字段：输出样例 JSON 确认格式
4. ✅ 引擎不崩溃（至少 import + 一次构造调用）
5. ✅ 不改了不该改的文件
```

### Step 5 — 提交
自检通过后，提交给 Architect：
- 改完的文件列表
- 自检结论 ✅/❌
- 如有新输出字段，附上字段名和示例值

## 常见 Pitfall

- **外部调用方多** — PortfolioBacktester 被 orchestrator.py、run_iteration.py、run_multi_expert.py 多处调用。改接口签名要通知所有人。
- **并发安全** — `_backtest_one_cand` 用 ProcessPoolExecutor 跑，模块级变量 `_worker_symbols_data` 改时要小心。
- **涨跌停判断** — engine.py line 581 有 TODO，当前涨跌停判断不精确，改此处时注意。
- **回测结果字段对齐** — BacktestReport 的字段名和 report_writer.py 的序列化字段名必须一致，否则 JSON 到 Dashboard 链路断。
- **不要偷偷改策略逻辑** — 引擎只实现计算，不做策略决策。不要在 fix bug 时顺手改了参数默认值。

## 当前约束
> 以下为 "YYYY-MM-DD" 现状，后续可能变化。

- 无特殊约束。
