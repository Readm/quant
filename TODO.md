# TODO — 量化系统路线图

---

## 当前版本
- Dashboard（React）：https://t50d9la8qomk.space.minimaxi.com
- Git: 9 commits
- 数据：SPY(300d) + BTCUSDT(300d) + A股9标的 本地缓存

---

## ✅ 全部完成

### ✅ TODO-001b: 交易成本模型
- 佣金 0.03%（双向）+ 滑点 0.05%（双向）= 买入 0.08%
- 印花税 0.10%（仅卖出）= 卖出 0.18%
- 已集成至 expert1a / expert1b 的 `_simulate()`

### ✅ TODO-002: Bull/Bear 辩论角色（4-Agent辩论）
- `bull_researcher.py` ✅ 牛市研究员（规则+LLM双模式）
- `bear_researcher.py` ✅ 熊市研究员（规则+LLM双模式）
- `debate_manager.py` ✅ 升级4-Agent辩论（Trend+MR+Bull+Bear）

### ✅ TODO-003: LLM 策略候选生成
- `llm_proxy.py` ✅ 统一LLM调用接口（MaxClaw llm-task封装）
- `generate_strategy_candidates_via_llm()` ✅
- `get_llm_feedback()` ✅

### ✅ TODO-004: 因子库（纯NumPy，零依赖）
- `factor_library.py` ✅ 28个因子（趋势/均值回归/成交量/情绪/质量）

### ✅ TODO-001: vectorbt 回测引擎
- `vectorbt_engine.py` ✅ 向量化回测引擎（pip安装成功）
- 版本：vectorbt 0.28.4 + pandas 2.3.3 + scipy 1.17.1
- 纯pandas指标 + vectorbt Portfolio 权益曲线
- 支持参数网格扫描（Top-N 参数组合）
- 支持 A股印花税（卖出额外0.10%）
- 佣金: 0.08%（买） 滑点: 0.05%（双向）

---

## 📊 最新回测结果（vectorbt，真实成本）

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

## 架构总览（v4.2）

```
Orchestrator
  ├── Expert1a 趋势专家（规则+Jitter）
  ├── Expert1b 均值回归专家（规则+Jitter）
  ├── LLM 生成器（MaxClaw LLM）
  └── Expert2 评估专家
          ↓
      BullResearcher（看多）      ← TODO-002 ✅
      BearResearcher（看空）      ← TODO-002 ✅
          ↓
      DebateManager（4-Agent）  ← TODO-002 ✅
          ↓
      因子库（28因子 NumPy）    ← TODO-004 ✅
      vectorbt 引擎（参数扫描）  ← TODO-001 ✅
          ↓
      风控 + 组合优化 + Paper Trade
```

---

最后更新：2026-03-27 01:19 UTC
