# Change Plan: 因子组合引擎接入 — 从候选生成到回测打分全链路对接

## 问题

`factor_combo_expert.py` 生成了 `combo_factors` 和 `combo_mode` 字段，
但 `backtest/engine.py` 的 `compute_factor_score` 只读 `template_key`，
组合因子和模式从未被消费。策略名虽然叫"RSI+动量"，实际只跑了RSI。

## 风险等级

data_format — 跨层（backtest/engine.py ↔ experts/specialists/factor_combo_expert.py），
候选数据契约改变，但回测引擎接口(compute_factor_score 签名)不变。

## 设计方案

### 设计原则

1. **引擎层（engine.py）只加注册表条目，不改核心逻辑**
   - `compute_factor_score` 的签名不变（`template_key` + `params`）
   - 组合模式用新的注册表键名 `_combo_<mode>` 区分
   - 组合参数以标准格式放在 `params.factors` 数组里

2. **候选生成层（factor_combo_expert.py）改输出格式**
   - 多因子模式时，`template_key` 设为 `_combo_<mode>`
   - `params.factors` 包含所有因子及其权重
   - 单因子模式不变

3. **去重心（orchestrator.py）只改候选哈希**
   - `_cand_hash` 需要正确处理 combo 策略的哈希（用 factors 列表代替单 template_key）

### 架构

```
factor_combo_expert.py:
  single  → {template_key: "rsi", ...}              ← 不变
  and     → {template_key: "_combo_and", params: {factors: [{key:"rsi",...}, {key:"momentum",...}]}}
  or      → {template_key: "_combo_or",  params: {factors: [...]}}
  weighted→ {template_key: "_combo_weighted", params: {factors: [{key:..., weight:0.5}, {key:..., weight:0.3}, {key:..., weight:0.2}]}}
  rank    → {template_key: "_combo_rank", params: {factors: [...]}}
  product → {template_key: "_combo_product", params: {factors: [...]}}
  hier    → {template_key: "_combo_hierarchical", params: {factors: [{key:"primary",...}, {key:"secondary",...}]}}
  cond_w  → {template_key: "_combo_conditional", params: {factors: [...], condition_factor: {...}}}

backtest/engine.py:
  compute_factor_score(template_key="rsi", params, t)           ← 单因子: 不变
  compute_factor_score(template_key="_combo_and", params, t)    ← 多因子: 分派到新函数
```

### 文件改动清单

| 文件 | 改动 | 类型 |
|:---|:---|:---|
| `backtest/engine.py` | 新增 7 个打分函数 + 注册到 `_SCORE_REGISTRY` | 新增 |
| `experts/specialists/factor_combo_expert.py` | COMBO_MODES 补全 + 候选生成输出新格式 + 参数调优适配 factors | 修改 |
| `experts/orchestrator.py` | `_cand_hash` / `_fresh_random_params` / dedup 适配 combo 策略 | 修改 |

## 实现步骤

### Step 1: engine.py 新增 7 个组合打分函数

所有函数共享统一参数格式:

```python
params = {
    "factors": [
        {"key": "rsi", "period": 14, "lower": 30, "upper": 70},
        {"key": "momentum", "lookback": 20, "threshold": 0.05},
    ],
    # 某些模式有额外控制参数 (condition_key, rank_normalize, etc.)
}
```

#### 1a. `_combo_score_and` — AND 双确认

```
for each factor:
    score = compute_factor_score(closes, data, indicators, factor_params, factor["key"], t)
    if score <= 0:
        return 0.0   # 任一因子无信号 → 不交易
return mean(all_scores)  # 都通过 → 取平均信号强度
```

特点：最严格，交易次数最少。适合做趋势确认（先用 ADX 判断有趋势，再用 MACD 择时）。

#### 1b. `_combo_score_or` — OR 任一触发

```
for each factor:
    score = compute_factor_score(...)
return max(all_scores)  # 取最强的信号
```

特点：最宽松，交易次数最多。适合互补因子（一个看超买超卖、一个看量价背离，任一发现机会就买）。

#### 1c. `_combo_score_weighted` — 加权求和

```
加权求和 (enhance existing _score_composite)
factors 数组每项可带 weight (默认为 1.0/N)
```

**这就是已有的 `_score_composite`，仅改名接入。**

#### 1d. `_combo_score_rank` — 排序等权

```
for each factor:
    rank = 按当前标的得分排全市场第几名
    因子得分 = (N - rank + 1) / N   # 归一化到 [0, 1]
final_score = mean(各因子等权排名分)
```

特点：解决不同因子量级差异问题。RSI 给 [-1, 1]，动量给 [0, 100]，直接加权求和会被动量主导。排序等权后各因子等影响力。

#### 1e. `_combo_score_product` — 乘积/几何平均

```
final_score = 1.0
for each factor:
    score = compute_factor_score(...)
    if abs(score) < 0.01:
        return 0.0  # 任一因子≈0 → 整体≈0
    final_score *= score
final_score = sign(final_score) * abs(final_score) ^ (1/N)  # 几何平均取符号
```

特点：比 AND 更极端——低确信度因子会拉低整体分数。适合高确信度场景（要求所有因子都确认且都强烈）。

#### 1f. `_combo_score_hierarchical` — 层级筛选

```
# 因子 A 作为筛选层（宽进）
layer1 = compute_factor_score(closes, data, indicators, factorA_params, factorA["key"], t)
if layer1 <= 0:
    return 0.0  # 先决条件不满足

# 因子 B 作为打分层（在筛选后的场景里打分）
return compute_factor_score(closes, data, indicators, factorB_params, factorB["key"], t)
```

特点：两因子不是平等关系，而是**依赖关系**。适合「先看市场状态，再看个股信号」、「先看流动性，再看动量」等场景。

#### 1g. `_combo_score_conditional` — 条件加权

```
params 里的 condition_factor 指示用哪个状态变量决定权重：
  condition_factor: {"key": "adx", "threshold": 25, "method": "above→trend, below→mr"}
  factors: [
    {"key": "momentum", "weight_when_active": 0.7, "weight_when_inactive": 0.3},
    {"key": "rsi", "weight_when_active": 0.3, "weight_when_inactive": 0.7},
  ]
```

特点：权重随环境动态变化。市场趋势强时重动量，震荡时重均值回归。

### Step 2: factor_combo_expert.py 改造

#### 2a. COMBO_MODES 扩展

```python
COMBO_MODES = ["single", "and", "or", "weighted", "rank", "product", "hierarchical", "conditional"]
```

#### 2b. 生成概率分布

```
30% single
20% and
15% or
15% weighted
  5% rank
  5% product
  5% hierarchical
  5% conditional
```

#### 2c. 候选生成输出格式调整

对 multi-factor 模式，构造 factors 数组取代单 template_key：

```python
# 旧: {"template_key": "rsi", "combo_factors": ["momentum"], "combo_mode": "and", ...}
# 新:
if mode == "single":
    c = { "template_key": primary, ... }  # 不变
else:
    factors = [get_factor_entry(primary)] + [get_factor_entry(f) for f in combo_factors]
    if mode == "weighted":
        # 不等权重: 主因子 0.5, 次因子 0.3, 三因子 0.2
        factors[0]["weight"] = 0.5
        factors[1]["weight"] = 0.3
        if len(factors) > 2: factors[2]["weight"] = 0.2
    c = {
        "template_key": f"_combo_{mode}",
        "params": { "factors": factors },
        ...
    }
```

### Step 3: orchestrator.py 适配

#### 3a. `_cand_hash`

combo 策略的哈希需要包含 factors 列表的序列化摘要，而非单 template_key 的 params。

#### 3b. `_fresh_random_params`

对 combo 策略，需要对每个 factor 分别随机参数。

#### 3c. dedup 逻辑

去重时要考虑组合的 factors 组合是否已经见过。

## 验收标准

1. 单元测试: 100 次候选生成测试 — 确保所有 8 种组合模式都被随机到
2. 单元测试: 每种 combo mode 的回测打分函数行为正确（空信号/正信号/负信号各场景）
3. 单元测试: weighted mode 权重总和 = 1.0
4. 单元测试: hierarchical mode 先决条件不满足时确实不执行第二因子
5. smoke_test.py 通过
6. 单一因子回测分数不受影响（single 模式不变）
7. AND 模式：RSI=28 超卖 + 动量未确认 → 不开仓
8. OR 模式：RSI=65 + 动量突破 → 开仓
9. weighted 模式：权重分配正确
10. rank 模式：不同量级因子归一化后等权
11. product 模式：任一因子≈0时整体≈0
12. hierarchical 模式：先决条件不满足时不执行第二因子
13. conditional 模式：ADX>25时动量权重大，ADX<25时RSI权重大

## 测试文件

`tests/test_combo_engine.py` — 组合引擎单元测试
