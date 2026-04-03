# TODO — 量化系统改进路线图

### 2\. tushare 宽数据未接入策略

`data/tushare/` 共 4.2GB，`daily\_basic`（PE/PB/换手率）、`moneyflow`（资金流向）
等高价值数据完全没有接入 `compute\_factor\_score()`。
只有 `index\_daily/000300.SH.csv` 被用作基准，其余闲置。

\---

## 🟡 值得做（影响研究质量）

### 3\. 策略搜索状态持久化

`\_seen\_cand\_hashes` 和 `\_best\_ever` 是 Orchestrator 的内存状态，
每次运行结束即丢失。应序列化到 `results/search\_state.json`，
下次运行自动恢复，避免重复探索已知无效区域。

### 4\. research pipeline 生成的因子质量偏低

当前 3 个生成因子的 IC 在 -0.002 \~ 0.017，远低于可用标准（IC > 0.05）。
需要：① 扩大回测数据至全量 tushare 数据；② 提高 sandbox\_evaluator 验证标准。

### 5\. tushare/daily 与 data/raw 两套 A股数据并存

应设计统一的 DataAdapter 层，上层代码只看到标准 OHLCV 接口。

\---

## 🟢 长期改进

### 6\. 策略结果数据库（SQLite）

当前结果是散落 JSON，无法查询历史最优参数。

### 7\. 论文→因子的全链路去重

`seen\_papers.json` 只记录 arxiv ID，不记录"论文产出了哪个因子 key"。
应在 `registry.json` 中增加 `source\_paper\_id` 字段，建立双向映射。

### 8\. 补充单元测试

`factors/` 全是纯函数，最适合测试：

* `test\_factors.py` — sma/rsi/macd/atr 边界条件
* `test\_evaluator.py` — 四维评分逻辑
* `test\_engine.py` — portfolio simulation 收益计算
* 

