# Expand Strategy Logic Combinatorial Space

## 目标
突破当前 "单因子打分→排名→选股" 的单一逻辑结构，让候选策略能组合因子、条件门控、多阶段筛选、风险控制和市场环境分支。

## 现状
- `_SCORE_REGISTRY` 26个打分函数，每个策略只用一个
- 候选参数只调 N/R/E/V 和组合参数（持仓数、调仓频率、权重方式）
- 回测引擎内无止损/止盈/条件逻辑
- 搜索空间：~26模板 × ~50参数组合 = ~1300种变体

## 改动清单（按实现顺序）

---

### Phase 1: 因子加权混合 [isolated]

**改 `backtest/engine.py`**

在 `_SCORE_REGISTRY` 中加入通用组合打分函数：

```python
"_composite": _score_composite,
```

`_score_composite(closes, data, indicators, params, t)` 从 `params` 中读取 `factors` 列表：
```python
params = {
    "factors": [
        {"key": "rsi", "weight": 0.6, "period": 14},
        {"key": "momentum", "weight": 0.4, "lookback": 20},
    ]
}
```
遍历每个 factor，调用 `_SCORE_REGISTRY[factor.key]` 取得分数，加权求和。

**改 `experts/orchestrator.py`**

`_generate_diverse_candidates` 中，除单因子模板外，按概率生成复合因子候选：
- 60% 单因子（当前逻辑）
- 30% 双因子加权（随机选2个不同模板，随机权重 0.3/0.7 或 0.5/0.5）
- 10% 三因子（选3个，等权）

`template_key` 设为 `"_composite"`，`params["factors"]` 保存子因子配置。

---

### Phase 2: 信号门控 [isolated]

**改 `backtest/engine.py`**

在 `PortfolioBacktester._compute_score_at` 中，打分后应用门控条件：

```python
def _apply_gate(score, closes, data, indicators, params, t):
    gate = params.get("gate")
    if not gate:
        return score
    gate_type = gate["type"]
    gate_param = gate.get("param", 2.0)
    
    if gate_type == "volume_surge":
        vol = data["volumes"][t]
        avg_vol = sum(data["volumes"][t-20:t]) / 20 if t >= 20 else 1
        return score if vol / avg_vol > gate_param else 0.0
    
    elif gate_type == "above_ma":
        ma = sum(closes[t-200:t]) / 200 if t >= 200 else closes[t]
        return score if closes[t] > ma else 0.0
    
    elif gate_type == "below_ma":
        ma = sum(closes[t-200:t]) / 200 if t >= 200 else closes[t]
        return score if closes[t] < ma else 0.0
    
    elif gate_type == "adx_filter":
        adx = indicators.get("adx", [0]*len(closes))[t] if t < len(indicators.get("adx",[])) else 0
        return score if adx > gate_param else 0.0  # 只在强趋势时生效
    
    elif gate_type == "low_vol":
        atr = indicators.get("atr", [1]*len(closes))[t] if t < len(indicators.get("atr",[])) else 1
        return score if atr / closes[t] < gate_param else 0.0  # 低波动过滤
    
    return score
```

**门控类型清单**（第一期可全部实现）：

| 门控 | 含义 | 参数 |
|------|------|------|
| `volume_surge` | 成交量 > MA × N倍 | threshold: 1.5~3.0 |
| `above_ma` | 价格在N日均线上方 | lookback: 50~250 |
| `below_ma` | 价格在N日均线下方 | lookback: 50~250 |
| `adx_filter` | ADX > 阈值（强趋势才交易） | threshold: 20~40 |
| `low_vol` | ATR/价格 < 阈值（低波动） | threshold: 0.01~0.05 |
| `rsi_zone` | RSI在区间内才交易 | lower: 20~40, upper: 60~80 |
| `profit_pct` | 持仓浮盈>X%时止盈 | threshold: 0.05~0.20 |
| `loss_pct` | 持仓浮亏>X%时止损 | threshold: 0.03~0.10 |

**改 `experts/orchestrator.py`**

在候选生成中，50%的候选配置一个门控（随机选门控类型和参数）。

---

### Phase 3: 两阶段筛选 [data_format]

**改 `backtest/engine.py`**

`PortfolioBacktester._select_stocks` 改造为支持两阶段：

```python
def _select_stocks(self, scores, t):
    stage = self.candidate.get("selection_stage", "single")
    
    if stage == "single":
        return normal_top_n_selection(scores, t)
    
    elif stage == "two_stage":
        # 阶段1: 按主因子选宽池
        primary_scores = self._compute_scores(t, self.params["primary_factor"])
        pool = top_k_stocks(primary_scores, self.params["pool_size"])  # 选Top-100
        
        # 阶段2: 按次因子从池中精选
        secondary_scores = self._compute_scores(t, self.params["secondary_factor"])
        filtered = {s: secondary_scores[s] for s in pool}
        return top_n_stocks(filtered, self.params["n_stocks"])  # 选Top-4
```

候选参数新增：
```python
{
    "selection_stage": "two_stage",
    "primary_factor": {"key": "momentum", "weight": 1.0},
    "secondary_factor": {"key": "rsi", "weight": 1.0},
    "pool_size": 100,  # 随机范围 30~300
}
```

---

### Phase 4: 风险覆盖层 [data_format]

**改 `backtest/engine.py`**

`PortfolioBacktester._rebalance` 中，在确定新持仓后、执行交易前，应用风险规则：

```python
def _apply_risk_overlay(self, positions, closes, params, t):
    risk_rules = params.get("risk_rules", {})
    if not risk_rules:
        return positions
    
    for pos in positions:
        entry_price = pos["entry_price"]
        current_price = closes[t]
        pnl_pct = (current_price - entry_price) / entry_price
        
        # 止损
        stop_loss = risk_rules.get("stop_loss", 0)
        if stop_loss > 0 and pnl_pct < -stop_loss:
            pos["action"] = "sell"  # 强制卖出
        
        # 止盈
        take_profit = risk_rules.get("take_profit", 0)
        if take_profit > 0 and pnl_pct > take_profit:
            pos["action"] = "sell"  # 强制卖出
        
        # 跟踪止盈
        trailing = risk_rules.get("trailing_stop", 0)
        if trailing > 0:
            peak = pos.get("peak_price", entry_price)
            if current_price > peak:
                pos["peak_price"] = current_price
            elif (peak - current_price) / peak > trailing:
                pos["action"] = "sell"
    
    return positions
```

候选参数新增：
```python
{
    "risk_rules": {
        "stop_loss": 0.05,      # 5%止损, 随机范围 0.03~0.15
        "take_profit": 0.15,    # 15%止盈, 随机范围 0.08~0.30
        "trailing_stop": 0.08,  # 8%回辙跟踪, 随机范围 0.05~0.15
    }
}
```

三个规则可以随机组合（任意启用0~3个），也可以全不启用。

---

### Phase 5: 市场条件分支 [architecture]

**改 `backtest/engine.py`**

在 `_compute_score_at` 上层包装一个条件分支：

```python
def _score_regime_adaptive(closes, data, indicators, params, t):
    """根据市场状态选择不同因子"""
    regime = self._detect_regime(closes, indicators, t)
    
    branches = params.get("branches", {})
    if regime == "trend" and "trend_factor" in branches:
        return self._compute_single_score(closes, data, indicators, branches["trend_factor"], t)
    elif regime == "mean_reversion" and "mr_factor" in branches:
        return self._compute_single_score(closes, data, indicators, branches["mr_factor"], t)
    elif regime == "high_vol" and "safe_factor" in branches:
        return self._compute_single_score(closes, data, indicators, branches["safe_factor"], t)
    
    return 0.0
```

候选参数新增：
```python
{
    "template_key": "_regime_adaptive",
    "branches": {
        "trend_factor": {"key": "macd", "params": {...}},
        "mr_factor": {"key": "rsi", "params": {...}},
        "safe_factor": {"key": "bollinger", "params": {...}},
    }
}
```

需要实现市场状态检测函数 `_detect_regime`（基于ADX趋势强度 + ATR波动率 + 均线斜率），这部分`indicators`中已有adx/atr/ma等数据。

---

## 候选生成器的改动（orchestrator.py）

Phase 1-5 全部上线后，`_generate_diverse_candidates` 的候选结构变成：

```python
{
    "strategy_id": "...",
    "strategy_name": "RSIx动量 Adx门控 两阶段选股",
    "template_key": "_composite",     # Phase 1
    "params": {
        "factors": [                  # Phase 1: 因子加权
            {"key": "rsi", "weight": 0.6, "period": 14, "lower": 30, "upper": 70},
            {"key": "momentum", "weight": 0.4, "lookback": 20, "threshold": 0.05}
        ],
        "gate": {                     # Phase 2: 门控
            "type": "adx_filter",
            "param": 25
        },
        "selection_stage": "two_stage",   # Phase 3: 两阶段
        "primary_factor": {"key": "momentum"},
        "secondary_factor": {"key": "rsi"},
        "pool_size": 100,
        "risk_rules": {                   # Phase 4: 风险
            "stop_loss": 0.05,
            "take_profit": 0.15
        },
        "template_key": "_regime_adaptive",  # Phase 5: 分支（可选）
    },
    "portfolio_params": {...}  # 已有
}
```

每类特征（因子复合/门控/两阶段/风险/分支）以独立的概率启用，可以叠加。一个候选可以同时有：复合因子+门控+风险+两阶段。也可以只启用其中一部分。

---

## 风险分级

| Phase | 文件 | 风险 | 影响 |
|-------|------|:----:|------|
| 1 因子加权 | engine.py + orchestrator.py | isolated | 新模板键，不破坏现有单因子 |
| 2 门控 | engine.py + orchestrator.py | isolated | 不影响无门控的候选 |
| 3 两阶段 | engine.py + orchestrator.py | data_format | `_select_stocks` 新增分支 |
| 4 风险层 | engine.py | data_format | 持仓管理新增逻辑 |
| 5 市场分支 | engine.py | data_format | 新模板键 + 状态检测 |

## 测试验证

每 Phase 完成后：
1. `cd ~/hermes/quant && python3 -c "from backtest.engine import *; print('OK')"`
2. 跑 5 轮小规模迭代（`--symbols astock --days 200 --rounds 5`）验证不崩
3. 检查生成的候选中有无新逻辑结构的策略

## 全量迭代

全部 Phase 完成后跑 20 轮全量验证：
```bash
cd ~/hermes/quant && python3 -m experts.orchestrator --symbols astock --days 800 --rounds 20
```
