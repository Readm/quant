# Quant 代码库 Review 报告
> Review 时间: 2026-04-03
> Review 范围: `/home/readm/quant/` 全量代码

---

## 📌 项目定位

六层多专家量化策略迭代系统:
```
数据层 → 因子库(47+) → 策略生成 → 回测引擎 → 专家协作层 → 看板
```
核心流程: TrendExpert + MeanReversionExpert 生成候选 → Evaluator 四维评分 → DebateManager LLM辩论 → RiskExpert 风险审查 → Orchestrator 多轮迭代

---

## ✅ 做得好的地方

1. **架构分层清晰** — 各层边界明确，依赖方向单一，无循环依赖
2. **CLAUDE.md 规范严格** — 禁止静默捕获异常是正确工程实践
3. **结构化反馈协议** — `Weakness`/`AdjustmentDirection` 枚举设计让策略调优可机器解析
4. **PBO 过拟合检测** — 基于 Bailey & Lopez de Prado 论文的 Walk-Forward 方法论扎实
5. **缠论/AD Line/Ichimoku** — 有中国特色的因子实现（非简单复制国外策略）
6. **Qlib Bridge** — `alpha158.py` 完整复现 158 个 Qlib 因子，打通 Qlib 数据

---

## 🚨 P0 — 必须修复

### 1. PBO 门控完全失效
**证据**: 最新结果 JSON 显示接受率 = 94.6%（351/371），远高于合理值 < 70%

```python
# evaluator.py 第 35 行
PBO_HARD_REJECT = 0.6   # 这个阈值基本没触发过
```

**影响**: 几乎所有候选策略都通过"过拟合检验"，系统实际上没有过滤低质量策略

**建议**:
```python
# 动态阈值：首轮宽松，末轮严格
PBO_HARD_REJECT = 0.4   # 首轮
# 或引入接受率惩罚项
if acceptance_rate > 0.75:
    for e in candidates: e.composite *= 0.9
```

### 2. 策略严重同质化
**证据**: 最新结果 Top4 全部是"主力资金流"或"量价背离"变体，4轮迭代后仍集中在单一因子家族

**根因**:
- `TrendExpert` 和 `MeanReversionExpert` 的参数扰动空间有限
- `CORR_THRESHOLD = 0.75` 定义了但未强制执行
- 多样性比例（30%随机探索）被固定.seed压制

**建议**: 每轮强制要求候选中 ≥30% 来自非 Top3 因子家族

### 3. ARCHITECTURE.md 严重过时
文档里提到的这些文件**已被删除但仍写在架构图里**:
- `backtest/vectorbt_engine.py` ❌
- `backtest/runner.py` ❌
- `experts/backtest_engine.py` ❌
- `experts/coordinator.py` ❌
- `strategies/` 整个目录 ❌

---

## ⚠️ P1 — 重要问题

### 4. 沙箱评估器门槛过低
```python
# sandbox_evaluator.py 第 18 行
IC_MIN_PASS = 0.01   # "极低门槛，避免拒绝所有因子"
```
TODO 里写了"IC > 0.05"才是可用标准，但实际 IC 通过门槛只有 0.01

### 5. NewsSentiment 模块存在但未启用
```python
# report_writer.py 第 50 行
sentiment_enabled: bool = False  # TODO: news_sentiment 未启用
```
情绪传感器层是死代码——`NewsSentimentAnalyzer` 写好了但从未在 `Orchestrator.run()` 里被调用

### 6. Research Expert 产出的因子 IC 偏低
三个注册因子 IC 范围：-0.002 ~ 0.017，远低于可用标准。沙箱测试只测了单标的，样本外验证不足

### 7. `RoundReportFake` 是废弃代码
```python
# orchestrator.py 末尾
class RoundReportFake:
    def __init__(self, rnd): ...
```
定义了但从未被实例化，应该删除

### 8. 参数网格用浮点数而非整数
```python
# orchestrator.py
"fast": 20, "slow": 60  # 实际生成时可能是 13.6, 26.4
```
技术指标周期理应是整数，小数参数浪费计算资源

---

## 💡 优化建议（按优先级）

### 立即可做
| 优先级 | 问题 | 操作 |
|--------|------|------|
| P0 | ARCHITECTURE.md 过时 | 更新为当前实际文件列表 |
| P0 | PBO 接受率惩罚 | `evaluator.py` 加 acceptance_rate 反馈 |
| P1 | RoundReportFake | 删除 |
| P1 | NewsSentiment 未启用 | 接入 `Orchestrator` 或删掉 |

### 值得做
| 优先级 | 问题 | 方案 |
|--------|------|------|
| P1 | 策略同质化 | 强制多样性配额 + 相关性约束执行 |
| P1 | IC 门槛 | 从 0.01 提升到 0.03 |
| P2 | 搜索状态持久化 | 序列化 `_seen_cand_hashes` 到 JSON |
| P2 | tushare 宽数据未接入 | DataAdapter 统一 OHLCV 接口 |

---

## 📊 总体评级

| 维度 | 评分 | 说明 |
|------|------|------|
| 架构设计 | A | 分层清晰，模块边界好 |
| 代码质量 | B+ | 无静默异常，但有一些废弃代码 |
| 策略质量 | C | PBO 失效 + 同质化严重 |
| 文档同步 | D | ARCHITECTURE.md 严重过时 |
| 评估体系 | C | 评分维度合理但门控失效 |

**综合评级：C+**

核心迭代循环跑起来了，但 PBO 门控失效是系统性风险——会让你在实盘中付出代价。建议优先修复 P0 问题再继续迭代。
