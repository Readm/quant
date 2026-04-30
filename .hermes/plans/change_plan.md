# Change Plan — 移除废弃 data/raw 代码 + 扩展因子数据源

## Phase 1: 移除 data/raw 废弃代码（isolated）
- 目标: `backtest/local_data.py`
- 移除 `load_symbol()` 中优先读 `data/raw/*.json` 的逻辑
- 保留 `load_symbol()` 接口不变，直接走 tushare CSV
- 移除 `data/raw` 相关的 docstring 引用
- 风险: isolated（单文件，无数据格式变化，路径是空目录）

## Phase 2: 扩展数据源到 daily_basic / moneyflow（data_format）
- 目标: `backtest/local_data.py` + `experts/data_loader.py` + `factors/`
- 在 `_load_tushare_csv` 同级加 `_load_daily_basic()` 和 `_load_moneyflow()`
- 将扩展数据通过 `extensions` 字段传递（已有空 dict）
- 新增基本面因子（PE 分位数、PB 分位数、换手率突变等）
- 注册到 `_SCORE_REGISTRY` 和 FactorComboExpert 模板
- 风险: data_format（跨 backtest/ → factors/ → experts/）

## 依赖顺序
Phase 1 → Phase 2（先清理再扩展）
