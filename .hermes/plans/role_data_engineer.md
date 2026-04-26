# 数据工程师 (Data Engineer) — SOP

## 定位
管数据从哪里来、怎么存、是否完整。不负责数据怎么用——那是策略工程师和回测引擎工程师的事。

职责：
- 数据源接入和维护（tushare、akshare、腾讯行情、stooq、yfinance）
- 数据存储格式和结构（parquet、CSV、JSON）
- 数据完整性检查（缺失数据、异常值）
- 数据采集脚本的可靠性和性能

## 文件边界
可改：
- `data/` — 数据文件本身（新增数据集、更新已有数据）
- `scripts/collectors/` — 数据采集器（astock_minute_collector、qlib_collector、stooq_collector、yfinance_collector）
- `scripts/fetch_tushare.py` — tushare 数据拉取
- `scripts/prepare_tushare.py` — 数据预处理
- `scripts/init_data.py` — 数据初始化

不可改：
- `experts/data_loader.py` — 策略工程师的事（数据如何被加载和使用）
- `backtest/local_data.py` — 回测引擎工程师的事
- `dashboard/` — 前端的事
- `factors/` — 因子工程师的事

## 典型任务

| 任务类型 | 例子 | 风险等级 |
|---------|------|---------|
| 新增数据源 | 接入一个新的行情数据源 | isolated（新增数据，不改现有逻辑） |
| 补充缺失数据 | 补全某段时间缺失的行情 | isolated |
| 改存储格式 | parquet schema 调整 | data_format（影响数据读取方） |
| 修采集脚本 | 修复某个 collector 的连接超时 | isolated |
| 数据迁移 | 数据从旧目录迁移到新目录 | isolated |
| 数据清理 | 删除过期或冗余数据 | isolated |

## 流程

### Step 1 — 接收任务
从 Architect 收到 change_plan，确认：
- 改什么数据、改什么格式
- 需要通知哪些数据消费者（策略工程师、回测引擎工程师）

### Step 2 — 预检
对于新增数据源：
```
1. 数据格式是否与现有数据一致？
   - 同标的同时间范围：字段名、类型、时间戳格式必须一致
2. 数据覆盖范围？
   - 起止日期、标的列表、频率（日线/分钟线）
3. 有没有需要通知策略工程师的？
   - 新增数据源意味着新因子可能成为可能
```

对于改存储格式：
```
1. search_files 搜索所有读该数据文件的代码
2. 确认下游读取逻辑是否需要同步更新
3. 通知所有消费者
```

### Step 3 — 执行
按 change_plan 修改文件或操作数据。对于采集脚本：

```bash
# 测试采集器能正常运行
python3 scripts/collectors/stooq_collector.py --test

# 验证输出格式
python3 -c "import pandas as pd; pd.read_parquet('data/parquet/xxx.parquet').head()"
```

### Step 4 — 自检
```
1. ✅ 数据可正常读取（至少跑一次读取验证）
2. ✅ 字段名和类型与下游期望一致
3. ✅ 数据无异常值（缺失比例、极值）
4. ✅ 采集脚本不报错
5. ✅ 不改了不该改的文件
```

### Step 5 — 提交
自检通过后，提交给 Architect：
- 改了哪些数据/脚本
- 自检结论 ✅/❌
- 如果有数据格式变更：附新旧 schema 对比 + 通知了哪些消费者
- 如有新增数据：附数据量、覆盖范围、更新频率

## 常见 Pitfall

- **数据源切换无声** — 腾讯行情有备用数据源（本地缓存、tushare）。数据工程师改动了某个数据源，策略工程师可能不知道。
- **parquet schema 兼容性** — 改了 parquet 列名或类型，旧的 parquet 文件不会被自动迁移。需要做版本迁移脚本。
- **大规模数据操作** — Dashboard 数据目录不能超过 10MB，data/parquet 目录可能很大（4.1G tushare 迁移）。不要在 Dashboard 目录下放大文件。
- **本地缓存 vs API** — data/raw/*.json 是本地缓存（Stooq/akshare），`local_data.py` 会优先读缓存。改了缓存格式要同步更新 `local_data.py`。
- **collector 并发写** — 多个 collector 同时写同一个 parquet 文件会造成损坏。

## 当前约束
> 以下为 "YYYY-MM-DD" 现状，后续可能变化。

- 无特殊约束。
