# 变更计划 — Switch to A-share only

## 需求
1. 系统只关注 A 股，移除所有非 A 股标的
2. 默认加载全部 A 股（~5,495只），每个策略做全市场扫描 + 选股组合
3. 修正之前 SPY 被错误映射到沪深300的问题

## 风险等级
data_format（数据加载方式变化）

## 修改项

### 1. `data_loader.py` — 发现全部 A 股标的
新增函数 `discover_astock_universe()` 扫描 `data/tushare/daily/` 下所有 `.csv` 文件，
返回完整股票代码列表（约 5,495 只）。
移除 `_TENCENT_MAP` 中的 SPY/BTCUSDT/ETHUSDT 映射。

### 2. `data_loader.py` — 默认加载全 A 股
`load_symbols_data` 新增特殊模式：`symbols=["astock"]` 时加载全部 A 股。

### 3. `orchestrator.py` — 默认参数改为 A 股
`__main__` 的 `--symbols` 默认值从 `[AAPL, NVDA, BTCUSDT, ETHUSDT]` 改为全部 A 股。
`n_days` 从 500 改为 800（A 股数据有 2,001 天可用）。

## 注意事项
- 5,495 只股票 × 800 天的 OHLCV 数据量约 200MB
- ProcessPoolExecutor 通过 `_init_backtest_worker` 序列化到 worker，加载一次
- 每轮回测对 55 个候选 × 5000 只股票做因子评分，选 Top-4 持仓
- 评分权重、PBO 洗牌、反垄断等逻辑不变
