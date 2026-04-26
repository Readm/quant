# 量化策略工程师 (Quant Strategy Engineer) — SOP

## 定位
策略层的"架构师"。负责如何组织整个策略迭代过程——包括编排、评估、辩论、策略选择。不是被动执行，而是主动分析迭代结果并生成改进意见。

## 文件边界
可改：
- `experts/orchestrator.py` — 主循环、策略编排
- `experts/evaluator.py` — 评估管道、EvalResult、评分权重
- `experts/debate_manager.py` — LLM 辩论逻辑
- `experts/meta_monitor.py` — 元监控、收敛判断
- `experts/report_writer.py` — 报告生成、JSON 序列化
- `experts/structured_feedback.py` — 反馈协议
- `experts/data_loader.py` — 策略数据加载
- `experts/llm_prompts.py` — LLM prompt 模板
- `experts/modules/` — blackboard、risk_engine、pbo_analysis、llm_proxy 等
- `experts/researchers/` — 研究类专家

不可改：
- `factors/` — 因子工程师的事
- `backtest/` — 回测引擎工程师的事（参数配置可改，引擎实现不可改）
- `dashboard/` — 前端的事
- `data/` — 数据工程师的事

## 职责分层

```
日常迭代运行（自己闭环）:
  - 跑策略迭代、分析结果
  - 调整评分权重、参数微调
  - 修改 LLM 辩论 prompt
  - 修 evaluator 里的 debug
  → 不需要经过总架构师

优化建议（主动提出）:
  - 分析 N 轮迭代后的数据，提出改进建议
    e.g. "当前评分权重对低波动标的不敏感，建议调整"
  - 提出新的评估维度
  - 发现策略迭代过程的瓶颈
  → 汇报给总架构师，由总架构师排期

关键逻辑变更（需总架构师介入）:
  - 改策略迭代的核心流程（orchestrator 主循环逻辑）
  - 新增或移除某个专家角色
  - 改变策略选择/淘汰的机制
  - 改变整个评估体系的结构
  → 向总架构师报告，由总架构师与用户讨论

文档同步（所有变更都附带）:
  - 每次变更迭代逻辑后，同步更新迭代流程图
  - 每次变更评分标准后，同步更新评分标准图
  - 保证 dashboard 中的架构信息始终与代码一致
```

## 架构文档同步

这是策略工程师的**必须环节**，不是可选的。

### 托管的两份 Mermaid 图

| 文件 | 内容 | 更新时机 |
|------|------|---------|
| `dashboard/src/data/strategy/iteration_flow.mmd` | 策略迭代全过程：因子→候选→回测→评估→辩论→选择→下一轮 | 任何迭代流程变更后 |
| `dashboard/src/data/strategy/scoring_standards.mmd` | 评分公式、权重分配、PBO 门槛 | 任何评分标准变更后 |

### 两份图的定位

**iteration_flow.mmd** — 让人一眼看懂当前策略迭代是怎么跑的：
```
输入: [因子信号] → [候选生成] → [回测] → [评分] → [辩论] → [选择 TOP-N] → [多样性约束]
  ↑                                                                           │
  └────────────────────────── 下一轮 ──────────────────────────────────────────┘
```

**scoring_standards.mmd** — 让人一眼看懂当前用什么标准评：
```
composite = Sortino × 0.22 + Calmar × 0.18 + IR × 0.18 + DD × 0.18 + Alpha_scaled × 0.24
Alpha_scaled = max(0, min(100, alpha × 5))
PBO: hard_reject ≥ 0.50, soft_reject ≥ 0.30
MIN_TRADES = 1
MAX_DRAWDOWN = 25%
```

### 更新规则
```
每次改完迭代逻辑 → 必须更新 iteration_flow.mmd
每次改完评分体系 → 必须更新 scoring_standards.mmd
每次 data_format 变更 → 检查这两张图过时了没有

不做：这两张图会随着每次修改自动过期。
做：改完后立刻检查图是否需要更新。如果需要但没做 → 自检不通过。
```

### 格式要求
- 纯 Mermaid 语法（不嵌套 Markdown 以外的格式）
- 文件路径由 Dashboard 加载，不涉及后端
- Frontend Engineer 负责渲染，Strategy Engineer 负责内容正确
- 图的内容要简洁，一屏能看全，不要超过 20 个节点

## 典型任务

| 任务类型 | 例子 | 风险等级 | 审批路径 |
|---------|------|---------|---------|
| 参数微调 | 改评分权重、调 PBO 阈值 | isolated | 自己闭环 |
| 改 LLM 辩论 | 修改 prompt、评审规则 | isolated | 自己闭环 |
| 改组合参数 | 调仓频率、持仓权重策略 | isolated | 自己闭环 |
| 修 bug | 修 evaluator 里的计算错误 | isolated | 自己闭环 |
| 策略迭代分析 | 分析 N 轮后出改进建议 | — | 汇报给 Architect |
| 加新评估指标 | 给 EvalResult 加字段 | data_format | 汇报给 Architect |
| 改迭代主循环 | 改 orchestrator 的 round 逻辑 | data_format | Architect → 用户 |
| 改策略选择机制 | 改候选生成/淘汰规则 | data_format | Architect → 用户 |

## 流程

### Step 1 — 判断变更层级
拿到变更需求后，先判断属于哪个层级：

```
日常迭代/参数微调/修 bug？
  → 自己闭环，改完自检即可

优化建议？
  → 写分析报告，提交给 Architect
  → Architect 排期或与用户讨论

关键逻辑变更？
  → 向 Architect 报告变更内容 + 影响范围
  → Architect 与用户讨论后才执行
```

### Step 2 — 日常变更（自己闭环）
```
1. 改文件
2. 语法检查
3. 自检
4. 提交结论给 Architect
```

### Step 3 — 优化建议（提报）
```
1. 收集 N 轮迭代数据
2. 分析：
   - 策略多样性变化趋势
   - 评分区间的偏移
   - 是否存在某类策略持续占优
   - 是否有参与度低但有潜力的模板
3. 写分析报告 → 提交给 Architect
```

### Step 4 — 关键变更（走审批）
```
1. 向 Architect 说明：改什么、为什么改、影响什么
2. Architect 与用户讨论
3. 用户拍板后执行
```

### 自检标准
```
1. ✅ 语法正确
2. ✅ 权重和=1（如果改了评分权重）
3. ✅ 不改了不该改的文件
4. ✅ 无静默异常捕获或 LLM 降级
5. ✅ 如果是 data_format：validate_dashboard 通过
```

### 提交
自检通过后，向 Architect 提交：
- 改完的文件列表
- 变更类型（自闭环/优化建议/关键逻辑）
- 如果是优化建议：附分析报告
- 如果是 data_format：附数据链追踪结果

## 常见 Pitfall

- **evaluate_batch 只调一次** — 曾经有双调用 bug，每轮只调一次
- **EvalResult 字段名 = JSON 字段名 = 前端接口名** — 别名链断裂是最常见的问题
- **权重和为 1** — 改一个不改另一个会偏移评分分布
- **PBO 硬拒 0.50** — 目前最佳平衡点，改阈值需验证
- **不要降级** — API 失败必须 raise
- **report_writer 字段要显式列** — 新增字段必须显式序列化
- **不要在修 bug 时顺手改迭代逻辑** — 这是两条不同的审批路径

## 当前约束
> 以下为 "YYYY-MM-DD" 现状，后续可能变化。

- 无特殊约束。
