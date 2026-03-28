"""
llm_proxy.py — LLM 调用代理（统一接口，支持 MaxClaw llm-task）
用途：
  - 策略候选生成（替代规则模板）
  - 牛市/熊市案例分析
  - 结构化反馈优化建议
"""

import json, time
from typing import Optional, Any


# ── LLM Task 包装器 ────────────────────────────

def llm_analyze(prompt: str, task: str,
                schema: Optional[dict] = None,
                model: str = "auto",
                temperature: float = 0.7,
                timeout_ms: int = 30000) -> dict:
    """
    通过 MaxClaw llm-task 工具调用 LLM。
    失败时返回 {"error": "...} 而非抛出异常。
    """
    try:
        from openclaw.invoke import invoke
        result = invoke(
            prompt=prompt,
            task=task,
            schema=schema,
            model=model,
            temperature=temperature,
            timeoutMs=timeout_ms,
        )
        if isinstance(result, dict):
            if "error" in result:
                return {"error": result["error"]}
            return result
        return {"data": result}
    except Exception as e:
        return {"error": str(e)}


# ── 策略生成 ────────────────────────────────────

STRATEGY_SYSTEM_PROMPT = """你是一个量化交易策略生成专家。

给定市场状态、已有策略表现和反馈，生成3个新的策略候选。
每个策略必须包含：
  - strategy_name: 中文策略名
  - template_key: 英文关键字（ma_cross, macd, momentum, adx_trend, rsi, bollinger, vol_surge 之一）
  - params: 参数字典（数值合理，不要极端值）
  - strategy_type: "trend" 或 "mean_reversion"
  - tags: 标签列表
  - rationale: 一句话生成逻辑

输出格式为JSON数组，不要输出其他内容。"""


def generate_strategy_candidates_via_llm(
    market_regime: str,
    trend_evals: list,
    mr_evals: list,
    round_num: int = 1,
    n_candidates: int = 3,
) -> list:
    """
    使用 LLM 生成策略候选。
    trend_evals / mr_evals: 已有策略的评估结果列表。
    返回新的策略候选列表。
    """
    # 构造上下文
    regime_name = getattr(market_regime, "name", market_regime) if hasattr(market_regime, "name") else str(market_regime)

    existing = []
    for e in (trend_evals or []):
        existing.append({
            "name": e.strategy_name, "type": e.strategy_type,
            "ann": e.annualized_return, "sharpe": e.sharpe_ratio,
            "dd": e.max_drawdown_pct, "trades": e.total_trades,
        })
    for e in (mr_evals or []):
        existing.append({
            "name": e.strategy_name, "type": e.strategy_type,
            "ann": e.annualized_return, "sharpe": e.sharpe_ratio,
            "dd": e.max_drawdown_pct, "trades": e.total_trades,
        })

    context = (
        f"当前市场状态: {regime_name}（第 {round_num} 轮迭代）\n"
        f"已有策略:\n{json.dumps(existing, ensure_ascii=False, indent=2)}\n\n"
        f"请生成 {n_candidates} 个新的策略候选（避免与已有策略重复），"
        f"考虑市场状态 {regime_name} 的特征。"
    )

    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "strategy_name": {"type": "string"},
                "template_key": {"type": "string"},
                "params": {"type": "object"},
                "strategy_type": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string"},
            },
            "required": ["strategy_name", "template_key", "params", "strategy_type", "tags", "rationale"]
        }
    }

    result = llm_analyze(
        prompt=STRATEGY_SYSTEM_PROMPT + "\n\n" + context,
        task="generate_strategies",
        schema=schema,
        temperature=0.9,
        timeout_ms=30000,
    )

    if "error" in result:
        # LLM 失败时返回空列表（orchestrator 会用规则兜底）
        return []

    data = result.get("data") or result.get("candidates") or []
    if isinstance(data, dict) and "candidates" in data:
        data = data["candidates"]

    # 规范化字段
    candidates = []
    for item in data:
        if not isinstance(item, dict):
            continue
        candidates.append({
            "strategy_id": f"llm_{int(time.time())}_{len(candidates)}",
            "strategy_name": item.get("strategy_name", "未命名"),
            "template_key": item.get("template_key", "momentum"),
            "params": item.get("params", {}),
            "strategy_type": item.get("strategy_type", "trend"),
            "tags": item.get("tags", []),
            "rationale": item.get("rationale", ""),
            "source": "llm",
        })
    return candidates


# ── 反馈优化建议 ────────────────────────────────

FEEDBACK_SYSTEM_PROMPT = """你是一个量化策略反馈优化专家。
给定策略表现和市场状态，给出参数调整建议。
输出JSON：{"adjustment": "...", "param": "...", "magnitude": N, "unit": "..."}"""


def get_llm_feedback(strategy_name: str, params: dict, ann_ret: float,
                     sharpe: float, max_dd: float, market_regime: str) -> dict:
    """获取 LLM 生成的策略反馈"""
    context = (
        f"策略: {strategy_name}\n参数: {params}\n"
        f"年化收益: {ann_ret:+.2f}%\n夏普: {sharpe:.3f}\n"
        f"最大回撤: {max_dd:.2f}%\n市场状态: {market_regime}\n\n"
        f"请给出参数调整建议（JSON格式）。"
    )
    schema = {
        "type": "object",
        "properties": {
            "adjustment": {"type": "string"},
            "param": {"type": "string"},
            "magnitude": {"type": "number"},
            "unit": {"type": "string"},
        }
    }
    result = llm_analyze(
        prompt=FEEDBACK_SYSTEM_PROMPT + "\n\n" + context,
        task="strategy_feedback",
        schema=schema,
        temperature=0.5,
        timeout_ms=20000,
    )
    if "error" in result:
        return {}
    return {k: result.get(k) for k in ("adjustment", "param", "magnitude", "unit")}
