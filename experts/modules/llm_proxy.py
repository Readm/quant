"""
llm_proxy.py — LLM 调用代理 (DeepSeek v4 Pro)
===============================================
配置：在项目根目录 .env 文件中设置：
  DEEPSEEK_API_KEY=sk-xxx
  DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
  DEEPSEEK_MODEL=deepseek-chat

规则：任何 API 错误直接抛出异常，禁止降级/静默返回。
      此规则写入 CLAUDE.md，所有调用方必须遵守。
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
    """从项目根目录 .env 加载配置"""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

_API_KEY = lambda: os.environ.get("DEEPSEEK_API_KEY", "")
_BASE_URL = lambda: os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
_MODEL = lambda: os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


# ── JSON 提取 ────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    """从 LLM 回复中提取 JSON"""
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if m:
        text = m.group(1)
    start = min(
        (text.find("{") if "{" in text else len(text)),
        (text.find("[") if "[" in text else len(text)),
    )
    if start == len(text):
        raise ValueError(f"LLM 未返回 JSON: {text[:300]}")
    bracket = text[start]
    end_bracket = "}" if bracket == "{" else "]"
    end = text.rfind(end_bracket)
    if end == -1:
        raise ValueError(f"LLM 返回格式错误: {text[:300]}")
    return json.loads(text[start:end + 1])


# ── 核心调用 ─────────────────────────────────────────────────────

def llm_analyze(prompt: str,
                task: str = "",
                schema: Optional[dict] = None,
                model: str = "auto",
                temperature: float = 0.7,
                timeout_ms: int = 30000,
                max_tokens: int = 4096) -> dict:
    """
    调用 DeepSeek Chat API，返回解析后的 dict。

    规则：任何失败直接 raise，不返回 {"error": ...}。
          调用方不得捕获后降级，必须让异常传播。
    """
    api_key = _API_KEY()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置，请检查 .env 文件")

    base_url = _BASE_URL().rstrip("/")
    chosen_model = _MODEL() if model in ("auto", "") else model

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
        f"{base_url}/chat/completions",
        data=payload,
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    timeout_s = max(5, timeout_ms // 1000)

    # 网络层重试（仅 No route to host / timeout），API 错误不重试
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"DeepSeek HTTP {e.code}: {err_body}") from e
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            if attempt == 3:
                raise RuntimeError(f"DeepSeek 网络失败(3次重试): {e}") from e
            print(f"  [LLM] 网络重试 {attempt}/3: {e}")
            time.sleep(3 * attempt)
        except Exception as e:
            raise RuntimeError(f"DeepSeek 请求失败: {e}") from e

    # 提取 content
    try:
        choices = body.get("choices", [])
        if not choices:
            raise RuntimeError(f"DeepSeek 响应无 choices: {str(body)[:300]}")
        content = choices[0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(
            f"DeepSeek 解析响应失败: {e} | body={str(body)[:300]}"
        ) from e

    result = _extract_json(content)
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
  - strategy_type: "combo"
  - tags: 标签列表
  - rationale: 一句话生成逻辑

输出格式为JSON数组，不要输出其他内容。"""


def generate_strategy_candidates_via_llm(
    market_regime: str,
    all_evals: list,
    round_num: int = 1,
    n_candidates: int = 3,
) -> list:
    """使用 LLM 生成策略候选。失败直接 raise。"""
    existing = []
    for e in (all_evals or []):
        existing.append({
            "name":   getattr(e, "strategy_name", "?"),
            "type":   getattr(e, "strategy_type", "combo"),
            "ann":    getattr(e, "annualized_return", 0),
            "sharpe": getattr(e, "sharpe_ratio", 0),
            "dd":     getattr(e, "max_drawdown_pct", 0),
            "trades": getattr(e, "total_trades", 0),
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
            "strategy_type": "combo",
            "tags":          item.get("tags", []),
            "rationale":     item.get("rationale", ""),
            "source":        "llm",
        })
    return candidates
