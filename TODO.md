# TODO — 量化系统路线图

---

## 六层架构（2026-03-29 重构）

```
Layer 1 │ 历史数据    │ data/                  ← 待建立
Layer 2 │ 基础因子库  │ factors/               ← ✅ 已重构（从experts/modules/独立）
Layer 3 │ 策略库      │ strategies/            ← ⚠️ 部分（5文件）
Layer 4 │ 专家系统    │ experts/               ← ✅ 基本完整
Layer 5 │ 回测系统    │ backtest/              ← ✅
Layer 6 │ 看板系统    │ dashboard/             ← ✅
```

### Layer 1 — 历史数据（data/）
- **当前状态**：目录不存在，数据获取分散在 `experts/modules/data_fetcher.py` 和 `experts/modules/__init__.py`
- **TODO**：建立统一的 `data/` 目录，统一接口

### Layer 2 — 基础因子库（factors/）
- **当前状态**：✅ 已重构为独立包
  ```
  factors/
  ├── __init__.py          统一导出
  ├── base_operators.py    底层算子（sma/ema/roc/rsi/atr/BB等）
  ├── trend.py             趋势因子（Ichimoku/KST/TRIX/Donchian/Aroon/ParabolicSAR）
  ├── mean_reversion.py    均值回归（MFI/RVI/KDWave/OBOS）
  ├── momentum.py          动量因子（ForceIndex/ElderRay/PPO/MomentumMatrix）
  ├── volume.py            量价因子（AD/VPT/MassIndex/Ergodic/SignalHorizon）
  ├── volatility.py        波幅因子（UltraSpline/UltraBand）
  ├── chanlun.py           缠论因子（笔/线段）
  ├── composite.py         综合因子（Chaikin Oscillator）
  └── signals.py           统一信号生成器 + FACTOR_TABLE
  ```
- **已知问题**：`factor_library.py` 原文件引用了未定义的 `sma_cross`/`macd_divergence`/`rsi_divergence` 等，已在 `factors/signals.py` FACTOR_TABLE 中修正
- **TODO**：补充 `F001-F013` 高优先级独家因子（Ichimoku/缠论/AD线等）的 Qlib Expression 格式封装

### Layer 3 — 策略库（strategies/）
- **当前文件**：`backtest_engine.py` / `param_optimizer.py` / `regime_engine.py` / `xb_tier1_binance.py` / `xb_tier2_ashare.py`
- **TODO**：策略独立文件化（每个策略一个 .py，含参数说明和注释）

### Layer 4 — 专家系统（experts/）
- **TODO**：补充 `expert2_evaluator` 模块（`experts/__init__.py` 导入失败）

### Layer 5 — 回测系统（backtest/）
- ✅ runner.py / vectorbt_engine.py / local_data.py

### Layer 6 — 看板系统（dashboard/）
- ✅ React 18 + Tailwind v3 + 5视图 + GitHub Pages CI/CD

---

## 最新提交

- `b67bf3d` refactor: migrate dashboard to root, clean web/ dir, fix CI/CD paths
- 全部在 `/home/readm/quant/` (WSL)，Git 统一管理

---

## 最新回测结果（vectorbt，真实成本）

### SPY（300天，2025年）
| 策略 | 年化 | 夏普 | 最大回撤 | 交易次数 | 胜率 |
|------|------|------|---------|---------|------|
| 🟢 动量突破 | **+20.2%** | **1.89** | -10.0% | 4笔 | 50% |
| 🔵 双均线交叉 | +15.8% | 1.77 | -10.0% | 1笔 | 100% |
| 🟡 布林带回归 | +12.7% | 1.67 | -8.7% | 2笔 | 100% |

### BTCUSDT（300天，2025年）
| 策略 | 年化 | 夏普 | 最大回撤 | 交易次数 | 胜率 |
|------|------|------|---------|---------|------|
| 🟢 RSI均值回归 | **+46.3%** | **1.64** | -15.8% | 3笔 | 100% |
| 🔵 RSI均值回归 | +40.3% | 1.52 | -15.7% | 10笔 | 70% |
| 🟡 布林带回归 | +28.8% | 1.24 | -14.3% | 8笔 | 88% |

---

最后更新：2026-03-29 01:42 UTC
