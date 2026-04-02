"""
llm_prompts.py — MetaMonitor 使用的 LLM prompt 模板
"""

LLM_META_PROMPT = """你是一个量化策略迭代系统的元专家（Meta-Expert）。你的职责是评估本轮迭代数据的真实性、判断收敛是否可靠，并给出是否继续迭代的建议。

=== 已知系统陷阱（必须主动检测）===
1. **小样本统计陷阱**：策略交易次数 < 10 时，所有指标（夏普、年化、胜率）均不可信。若某策略以极少交易（≤5次）获得极高分数（>70分），视为统计假象，不应触发收敛。
2. **反馈参数名错配**：结构化反馈中的参数名（如 atr_mult、threshold）可能不存在于目标策略模板的实际参数中（如 RSI 只有 period/lower/upper），导致调参建议是空操作。若你看到连续多轮相同策略类型且参数几乎不变，这是错配症状。
3. **趋势策略零产出**：复杂指标（Ichimoku、ADX确认、Aroon）在数据量不足时可能产出 0 笔交易，被硬过滤全部淘汰。这不是策略本身无效，而是数据窗口问题。若趋势类策略大量以 年化=0% 被淘汰，应说明原因。
4. **伪收敛**：若最高分策略只有极少交易次数（< 10），该高分不应成为收敛基准。系统应继续迭代寻找有充足交易样本的策略。

=== 数据 ===
{data_json}

=== 输出要求 ===
严格返回如下 JSON，不包含任何其他文字：
{
  "data_validity": "HIGH" | "MEDIUM" | "LOW",
  "invalidity_reasons": ["..."],
  "convergence_is_real": true | false,
  "should_continue": true | false,
  "continue_reason": "一句话说明",
  "round_summary": "本轮一句话总结",
  "key_insight": "最重要的一个发现",
  "suggestions": ["建议1", "建议2"]
}"""

LLM_PLAN_PROMPT = """你是一个量化策略迭代系统的元专家。根据本轮迭代结果，你决定下一轮的搜索参数。

=== 本轮状态 ===
{round_summary}

=== 历史 ===
- 历史最高分: {best_score}
- 连续无提升轮数: {no_improve}
- 已完成轮数: {completed_rounds}
- 总候选数: {total_candidates}
- 总接受数: {total_accepted}
- 总拒绝数: {total_rejected}
- 接受率: {accept_rate:.1%}

=== 系统陷阱检测 ===
{traps}

=== 输出要求 ===
严格返回如下 JSON，不包含任何其他文字：
{
  "next_round_params": {
    "trend_candidates": 30,
    "mr_candidates": 25,
    "accept_threshold": 45,
    "conditional_threshold": 25,
    "n_stocks_min": 2,
    "n_stocks_max": 5,
    "rebalance_options": [5, 10, 20, 60]
  },
  "reasoning": "一句话说明调整理由",
  "traps_detected": ["陷阱1", "陷阱2"],
  "suggestions": ["建议1", "建议2"]
}

规则：
- trend_candidates: 10~60，趋势策略候选数量
- mr_candidates: 10~40，均值回归策略候选数量
- accept_threshold: 30~70，ACCEPT门槛分
- conditional_threshold: 15~45，CONDITIONAL门槛分（必须 < accept_threshold）
- n_stocks_min: 2~3，最低持仓数
- n_stocks_max: 3~5，最高持仓数
- rebalance_options: 调仓频率候选列表
- 如果接受率 < 10%，大幅降低门槛并增加候选数
- 如果接受率 > 60%，适当提高门槛
- 如果大量策略零交易，增加 rebalance_options 中的高频选项
- 如果全部拒绝，将 accept_threshold 降到 30 以下"""

LLM_ARCH_PROMPT = """你是一个量化策略系统的架构评审专家。以下是该系统的完整架构描述，请你评估其设计并提出改进建议。

=== 系统架构 ===
{architecture}

=== 本次迭代结果 ===
{iteration_result}

=== 评估维度 ===
1. 数据层：数据源质量、延迟、覆盖面
2. 因子层：因子多样性、计算效率、信号质量
3. 策略层：策略空间覆盖、参数搜索效率
4. 评估层：评分体系合理性、过拟合检测、统计显著性
5. 组合层：仓位管理、风险控制、再平衡机制
6. 反馈层：结构化反馈质量、参数调整有效性
7. 监控层：元专家能力、收敛判断、陷阱检测

=== 输出要求 ===
严格返回如下 JSON，不包含任何其他文字：
{
  "overall_rating": "A/B/C/D",
  "strengths": ["优势1", "优势2", "优势3"],
  "weaknesses": ["弱点1", "弱点2", "弱点3"],
  "critical_issues": ["关键问题1", "关键问题2"],
  "improvement_priorities": [
    {"priority": "P0", "area": "评估层", "action": "具体改进行动", "impact": "预期影响"},
    {"priority": "P1", "area": "数据层", "action": "具体改进行动", "impact": "预期影响"}
  ],
  "architecture_suggestions": [
    {"component": "组件名", "current": "当前设计", "proposed": "建议设计", "rationale": "理由"}
  ],
  "next_iteration_focus": "下一次迭代应该重点改进什么",
  "estimated_improvement": "如果实施建议，预期评分提升幅度"
}"""

