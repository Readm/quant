"""
factor_codegen.py — LLM 驱动的因子代码生成器
=============================================
输入：FactorProposal + 可用的额外数据字段列表
输出：compute_score(closes, data, indicators, extensions, params, t) 的 Python 代码字符串
"""

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from experts.modules.llm_proxy import llm_analyze
from experts.researchers.research_expert import FactorProposal, KNOWN_DATA

# 函数签名（生成的代码必须定义此函数）
_FUNC_SIG = "def compute_score(closes, data, indicators, extensions, params, t):"

_CODEGEN_PROMPT = """
你是一名量化工程师，请为以下因子编写 Python 打分函数。

【因子信息】
名称: {name_cn}  |  类型: {type}  |  Key: {key}
描述: {description}
公式: {formula}
参数: {params}
可用数据字段:
  - closes: list[float]（收盘价序列，closes[t] 为当前收盘价）
  - data: dict，包含 highs/lows/volumes/opens（格式同 closes）
  - indicators: dict，可用 key: rsi14, macd_hist, adx, bb_upper, bb_lower, bb_mid
  - extensions: dict，包含额外数据: {extra_keys}（可能为空列表）
  - params: dict，策略参数
  - t: int，当前时间步索引

【要求】
1. 函数名必须是 compute_score，签名完全一致
2. 只能使用 Python 内置函数和 math 模块（已自动导入 import math）
3. 不能有 import 语句（math 已在外部 import）
4. t 索引不足时返回 0.0
5. 返回 float：正值=买入信号，负值=卖出信号，0=中性
6. 对于 {type} 策略：{type_hint}
7. 代码简洁，不超过 40 行，不要注释
8. 从 extensions 访问额外数据：arr = extensions.get("key_name", [])

请直接输出 Python 代码，不要任何 markdown 包裹，不要解释。
"""

_FALLBACK_TEMPLATE = '''
def compute_score(closes, data, indicators, extensions, params, t):
    # Fallback: 短期动量
    lb = max(int(params.get("lookback", 10)), 3)
    if t < lb or closes[t - lb] <= 0:
        return 0.0
    return (closes[t] / closes[t - lb] - 1) * 100
'''


class FactorCodegen:
    def generate(self, proposal: FactorProposal, extra_keys: list[str]) -> str:
        """
        生成 compute_score 函数代码字符串。
        失败时返回空字符串。
        """
        type_hint = ("正值=强趋势方向" if proposal.type == "trend"
                     else "正值=超卖/均值回归买入")
        prompt = _CODEGEN_PROMPT.format(
            name_cn=proposal.name_cn,
            type=proposal.type,
            key=proposal.key,
            description=proposal.description,
            formula=proposal.formula,
            params=proposal.params,
            extra_keys=extra_keys or "（无）",
            type_hint=type_hint,
        )

        result = llm_analyze(prompt, task="factor_codegen", temperature=0.2, max_tokens=1024)

        # llm_analyze 解析 JSON，但代码是纯文本，需要特殊处理
        # 先从 result 中拿 raw text（llm_proxy 有时把纯文本当 error）
        code = self._extract_code(result)
        if not code:
            # 降级：用更简单的提示重试
            code = self._retry_simple(proposal)

        if not code:
            return ""

        code = self._ensure_import(code)
        if not self._validate(code):
            return ""
        return code

    @staticmethod
    def _extract_code(result: dict) -> str:
        """从 llm_analyze 结果中提取代码字符串，处理各种 LLM 输出格式"""
        # 1. 检查已知代码字段
        for key in ("code", "python_code", "function", "compute_score"):
            if key in result and isinstance(result[key], str):
                v = result[key].strip()
                if "def compute_score" in v:
                    return FactorCodegen._strip_markdown(v)

        # 2. 优先 raw 字段（完整内容），其次 error 字段（可能被截断到200字符）
        raw = result.get("raw", "") or result.get("error", "") or ""
        if not raw:
            # 把整个 result dict 转成字符串兜底
            raw = str(result)

        # 3. 剥除 markdown 代码块（```python ... ``` 或 ``` ... ```）
        raw = FactorCodegen._strip_markdown(raw)

        if "def compute_score" in raw:
            idx = raw.find("def compute_score")
            return raw[idx:].strip()
        return ""

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """去除 LLM 常见的 ```python ... ``` 包裹"""
        import re
        # 匹配 ```python 或 ``` 开头的代码块
        m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
        if m:
            return m.group(1).strip()
        # 去掉单行反引号
        return text.replace("`", "").strip()

    def _retry_simple(self, proposal: FactorProposal) -> str:
        """第二次尝试：直接要求输出函数体，用 raw text 接口"""
        prompt = (
            f"写一个Python函数 compute_score(closes, data, indicators, extensions, params, t) "
            f"实现因子: {proposal.description}。"
            f"公式: {proposal.formula}。"
            f"只用 math 模块，不能 import，返回 float。直接输出代码，无其他文字。"
        )
        # 直接调 llm_proxy 的底层，获取原始文本
        try:
            from experts.modules.llm_proxy import _API_KEY, _BASE_URL, _ENDPOINT, _MODEL
            import json, urllib.request
            payload = json.dumps({
                "model": _MODEL(),
                "messages": [
                    {"role": "system", "content": "你是Python工程师，只输出代码，无任何说明。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 800,
            }, ensure_ascii=False).encode()
            req = urllib.request.Request(
                f"{_BASE_URL()}{_ENDPOINT()}",
                data=payload,
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {_API_KEY()}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                body = json.loads(r.read())
            choices = body.get("choices") or body.get("reply", "")
            if isinstance(choices, list) and choices:
                text = choices[0].get("message", {}).get("content", "")
            else:
                text = str(choices)
            if _FUNC_SIG in text:
                idx = text.find("def compute_score")
                return text[idx:].strip()
        except Exception:
            pass
        return ""

    @staticmethod
    def _ensure_import(code: str) -> str:
        """确保顶部有 import math"""
        if "import math" not in code:
            code = "import math\n" + code
        return code

    @staticmethod
    def _validate(code: str) -> bool:
        """语法检查 + 安全检查"""
        # 语法
        try:
            ast.parse(code)
        except SyntaxError as e:
            print(f"  [代码生成] 语法错误: {e}")
            return False
        # 必须包含函数定义
        if _FUNC_SIG not in code and "def compute_score(" not in code:
            print("  [代码生成] 未找到 compute_score 函数定义")
            return False
        # 禁止危险操作
        forbidden = ["import os", "import sys", "open(", "__import__",
                     "subprocess", "exec(", "eval(", "compile("]
        for f in forbidden:
            if f in code:
                print(f"  [代码生成] 包含禁止操作: {f}")
                return False
        return True
