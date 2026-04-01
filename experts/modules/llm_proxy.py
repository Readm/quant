"""
llm_proxy.py — LLM 调用代理（MiniMax API）
=========================================
配置：在项目根目录 .env 文件中设置：
  MINIMAX_API_KEY=sk-cp-...
  MINIMAX_BASE_URL=https://api.minimaxi.chat/v1
  MINIMAX_MODEL=MiniMax-Text-01
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional


# ── 加载 .env ────────────────────────────────────────────────────

def _load_env():
    """从项目根目录 .env 加载配置（优先使用 python-dotenv，降级为手动解析）"""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        # 手动解析
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

_API_KEY  = lambda: os.environ.get("MINIMAX_API_KEY", "")
_BASE_URL = lambda: os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.chat/v1").rstrip("/")
_MODEL    = lambda: os.environ.get("MINIMAX_MODEL", "MiniMax-Text-01")
# MiniMax Token Plan 使用 /text/chatcompletion_v2，而非 OpenAI 的 /chat/completions
_ENDPOINT = lambda: os.environ.get("MINIMAX_ENDPOINT", "/text/chatcompletion_v2")


# ── JSON 解析工具 ─────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """从 LLM 回复中提取 JSON（处理 markdown 代码块、前后杂文）"""
    # 去掉 ```json ... ``` 包裹
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if m:
        text = m.group(1)
    # 找第一个 { 或 [ 到最后一个 } 或 ]
    start = min(
        (text.find("{") if "{" in text else len(text)),
        (text.find("[") if "[" in text else len(text)),
    )
    if start == len(text):
        return {}
    bracket = text[start]
    end_bracket = "}" if bracket == "{" else "]"
    end = text.rfind(end_bracket)
    if end == -1:
        return {}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}


# ── 核心调用 ─────────────────────────────────────────────────────

def llm_analyze(prompt: str,
                task: str = "",
                schema: Optional[dict] = None,
                model: str = "auto",
                temperature: float = 0.7,
                timeout_ms: int = 30000,
                max_tokens: int = 4096) -> dict:
    """
    调用 MiniMax Chat API，返回解析后的 dict。
    失败时返回 {"error": "..."}，调用方应降级到规则逻辑。
    """
    api_key = _API_KEY()
    if not api_key:
        return {"error": "MINIMAX_API_KEY 未配置，请检查 .env 文件"}

    base_url = _BASE_URL()
    chosen_model = _MODEL() if model in ("auto", "") else model

    # 构造 system prompt：要求输出纯 JSON
    field_hint = ""
    if schema and "properties" in schema:
        field_hint = "必须包含字段: " + ", ".join(schema["properties"].keys()) + "。"
    system_content = (
        "你是一个量化交易分析专家。"
        "请严格以 JSON 格式输出分析结果，不要输出任何其他文字、解释或 Markdown。"
        + field_hint
    )

    payload = json.dumps({
        "model": chosen_model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user",   "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}{_ENDPOINT()}",
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        timeout_s = max(5, timeout_ms // 1000)
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"}
    except Exception as e:
        return {"error": str(e)}

    # 检查 MiniMax base_resp 错误码
    base_resp = body.get("base_resp", {})
    if base_resp.get("status_code", 0) not in (0, None):
        return {"error": f"MiniMax error {base_resp.get('status_code')}: {base_resp.get('status_msg')}"}

    # 提取 assistant 消息（支持 chatcompletion_v2 和 OpenAI 两种格式）
    try:
        choices = body.get("choices", [])
        if not choices:
            return {"error": f"响应无 choices: {str(body)[:200]}"}
        choice = choices[0]
        # chatcompletion_v2: choices[0].messages[0].content
        # OpenAI 格式:        choices[0].message.content
        if "messages" in choice:
            content = choice["messages"][0]["content"]
        else:
            content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        return {"error": f"解析响应失败: {e} | body={str(body)[:200]}"}

    result = _extract_json(content)
    if not result:
        # 保留完整原始内容在 raw 字段，供调用方（如代码生成器）使用
        return {"error": f"LLM 未返回有效 JSON: {content[:200]}", "raw": content}
    return result


# ── 策略生成（LLM 驱动）────────────────────────────────────────

STRATEGY_SYSTEM_PROMPT = """你是一个量化交易策略生成专家。

给定市场状态、已有策略表现和反馈，生成若干新的策略候选。
每个策略必须包含：
  - strategy_name: 中文策略名
  - template_key: 英文关键字（ma_cross/macd/momentum/adx_trend/ichimoku_signal/kst/trix/
                   donchian_breakout/aroon_signal/rsi/bollinger/vol_surge/mfi_signal/
                   rvi_signal/kdwave/multi_roc_signal/obos_composite/elder_ray_signal 之一）
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
    """使用 LLM 生成策略候选。失败时返回 [] 由 orchestrator 用规则兜底。"""
    existing = []
    for e in (trend_evals or []) + (mr_evals or []):
        existing.append({
            "name":   e.strategy_name, "type":   e.strategy_type,
            "ann":    e.annualized_return, "sharpe": e.sharpe_ratio,
            "dd":     e.max_drawdown_pct,  "trades": e.total_trades,
        })

    context = (
        f"当前市场状态: {market_regime}（第 {round_num} 轮迭代）\n"
        f"已有策略:\n{json.dumps(existing, ensure_ascii=False, indent=2)}\n\n"
        f"请生成 {n_candidates} 个新的策略候选（避免与已有策略重复）。"
    )

    result = llm_analyze(
        prompt=STRATEGY_SYSTEM_PROMPT + "\n\n" + context,
        task="generate_strategies",
        temperature=0.9,
        timeout_ms=30000,
    )

    if "error" in result:
        return []

    data = result if isinstance(result, list) else result.get("data") or result.get("candidates") or []
    candidates = []
    for item in (data if isinstance(data, list) else []):
        if not isinstance(item, dict):
            continue
        candidates.append({
            "strategy_id":   f"llm_{int(time.time())}_{len(candidates)}",
            "strategy_name": item.get("strategy_name", "未命名"),
            "template_key":  item.get("template_key", "momentum"),
            "params":        item.get("params", {}),
            "strategy_type": item.get("strategy_type", "trend"),
            "tags":          item.get("tags", []),
            "rationale":     item.get("rationale", ""),
            "source":        "llm",
        })
    return candidates
