"""
research_expert.py — 因子发现专家
====================================
流程：
  1. 搜索 arxiv（量化因子相关论文）
  2. LLM 从摘要中提取因子提案
  3. 判断数据是否已有
  4. 已有 → 直接生成代码；未有 → 尝试一次 akshare 获取，失败写 TODO
  5. 沙盒测试通过 → 注册到因子库

已有数据（无需额外获取）：
  closes, highs, lows, volumes, opens
  indicators: rsi14, macd_hist, adx, bb_upper, bb_lower, bb_mid
"""

import json
import math
import os
import sys
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from experts.modules.llm_proxy import llm_analyze

# ── 已知可用数据字段 ─────────────────────────────────────────────────
KNOWN_OHLCV = {"closes", "highs", "lows", "volumes", "opens"}
KNOWN_INDICATORS = {"rsi14", "macd_hist", "adx", "bb_upper", "bb_lower", "bb_mid"}
KNOWN_DATA = KNOWN_OHLCV | KNOWN_INDICATORS

# 路径
_ROOT       = Path(__file__).parent.parent.parent
_LIB_DIR    = _ROOT / "experts" / "factor_library"
_FACTOR_DIR = _LIB_DIR / "factors"
_TODO_DIR   = _LIB_DIR / "TODO"
_REGISTRY   = _LIB_DIR / "registry.json"

for _d in [_FACTOR_DIR, _TODO_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


@dataclass
class FactorProposal:
    key: str                         # template_key, snake_case
    name_cn: str                     # 中文名
    type: str                        # "trend" or "mean_reversion"
    description: str                 # 因子逻辑描述
    formula: str                     # 数学公式（自然语言描述）
    params: dict                     # 默认参数
    param_ranges: dict               # {param: [lo, hi]}
    required_data: list[str]         # 需要的数据字段
    source: str = ""                 # 论文/来源
    extra_data_desc: dict = field(default_factory=dict)  # 未知数据的描述


@dataclass
class ResearchResult:
    proposal: FactorProposal
    status: str          # "registered" | "sandbox_fail" | "todo_written" | "skipped"
    factor_file: str = ""
    todo_file: str = ""
    ic_score: float = 0.0
    error: str = ""


# ── arxiv 搜索 ───────────────────────────────────────────────────────

def search_arxiv(query: str, max_results: int = 8) -> list[dict]:
    """返回 [{title, abstract, authors, arxiv_id}]"""
    q = urllib.parse.quote(query)
    url = (f"http://export.arxiv.org/api/query"
           f"?search_query=all:{q}"
           f"&max_results={max_results}"
           f"&sortBy=relevance&sortOrder=descending")
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            xml = r.read().decode("utf-8")
    except Exception as e:
        print(f"  [研究专家] arxiv 请求失败: {e}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml)
    papers = []
    for entry in root.findall("atom:entry", ns):
        title    = (entry.find("atom:title", ns)   or _empty()).text or ""
        abstract = (entry.find("atom:summary", ns) or _empty()).text or ""
        arxiv_id = (entry.find("atom:id", ns)      or _empty()).text or ""
        papers.append({
            "title":    title.strip().replace("\n", " "),
            "abstract": abstract.strip()[:1200],
            "arxiv_id": arxiv_id.strip(),
        })
    return papers


def _empty():
    class _E:
        text = ""
    return _E()


# ── LLM 提取因子提案 ─────────────────────────────────────────────────

_EXTRACT_PROMPT = """
你是一名量化研究员，请从以下论文摘要中提取可以实现为截面因子的策略。

【论文信息】
标题：{title}
摘要：{abstract}

【已有数据】
OHLCV: closes（收盘价列表）, highs, lows, volumes, opens
技术指标: rsi14, macd_hist, adx, bb_upper, bb_lower, bb_mid

【任务】
如果摘要中包含可实现的量化因子，提取 1~2 个，输出 JSON 数组。
如果没有可用因子，返回空数组 []。

每个因子对象：
{{
  "key": "snake_case唯一键（英文）",
  "name_cn": "中文名称",
  "type": "trend 或 mean_reversion",
  "description": "因子逻辑，1~3句话",
  "formula": "核心计算公式（数学表达或伪代码）",
  "params": {{"param1": default_value}},
  "param_ranges": {{"param1": [min, max]}},
  "required_data": ["closes", ...],
  "extra_data_desc": {{
    "字段名": "描述（仅当需要 OHLCV/指标之外的数据时填写，否则空对象）"
  }}
}}

required_data 只列出因子真正需要的字段。
如果只需要 OHLCV 和已有指标，extra_data_desc 应为空对象 {{}}。
"""

def extract_proposals(paper: dict) -> list[FactorProposal]:
    prompt = _EXTRACT_PROMPT.format(
        title=paper["title"],
        abstract=paper["abstract"],
    )
    result = llm_analyze(prompt, task="factor_extraction", temperature=0.3, max_tokens=2048)
    if "error" in result:
        print(f"  [研究专家] LLM提取失败: {result['error']}")
        return []

    # result 可能是 list（直接） 或 dict（包含数组）
    items = result if isinstance(result, list) else result.get("factors", result.get("proposals", []))
    if not isinstance(items, list):
        return []

    proposals = []
    for item in items:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        # 强制 key 安全
        key = str(item["key"]).lower().replace("-", "_").replace(" ", "_")[:40]
        p = FactorProposal(
            key=key,
            name_cn=item.get("name_cn", key),
            type=item.get("type", "trend"),
            description=item.get("description", ""),
            formula=item.get("formula", ""),
            params=item.get("params", {}),
            param_ranges=item.get("param_ranges", {}),
            required_data=item.get("required_data", ["closes"]),
            source=paper.get("arxiv_id", ""),
            extra_data_desc=item.get("extra_data_desc", {}),
        )
        proposals.append(p)
    return proposals


# ── 主研究类 ────────────────────────────────────────────────────────

class ResearchExpert:
    """
    每次调用 run() 搜索论文 → 提取因子 → 测试 → 注册。
    可以传入自定义查询，也可以使用默认的 A 股相关查询。
    """

    DEFAULT_QUERIES = [
        "cross-sectional alpha factor A-share China stock market",
        "quantitative momentum factor equity market microstructure",
        "earnings surprise factor stock return prediction",
        "volume price factor technical trading rule",
        "machine learning factor investing equity",
    ]

    def __init__(self, symbols: list[str] = None):
        self.symbols = symbols or ["SH600519"]
        self._registry = self._load_registry()

    def run(self, queries: list[str] = None, papers_per_query: int = 4) -> list[ResearchResult]:
        from experts.researchers.factor_codegen import FactorCodegen
        from experts.researchers.sandbox_evaluator import SandboxEvaluator

        queries = queries or self.DEFAULT_QUERIES[:2]
        codegen   = FactorCodegen()
        evaluator = SandboxEvaluator(self.symbols)
        results   = []

        for query in queries:
            print(f"\n  [研究专家] 搜索: {query}")
            papers = search_arxiv(query, max_results=papers_per_query)
            print(f"  [研究专家] 找到 {len(papers)} 篇论文")

            for paper in papers:
                proposals = extract_proposals(paper)
                for proposal in proposals:
                    # 跳过已注册的
                    if proposal.key in self._registry:
                        print(f"  [研究专家] 跳过（已注册）: {proposal.key}")
                        results.append(ResearchResult(proposal=proposal, status="skipped"))
                        continue

                    print(f"  [研究专家] 处理因子: {proposal.name_cn} ({proposal.key})")
                    result = self._process_proposal(proposal, codegen, evaluator)
                    results.append(result)
                    if result.status == "registered":
                        print(f"  ✅ 注册成功: {proposal.key}  IC={result.ic_score:.3f}")
                    elif result.status == "todo_written":
                        print(f"  📝 TODO 已写入: {result.todo_file}")
                    elif result.status == "sandbox_fail":
                        print(f"  ❌ 沙盒测试失败: {result.error[:80]}")

        return results

    def _process_proposal(
        self,
        proposal: FactorProposal,
        codegen,
        evaluator,
    ) -> ResearchResult:
        # 判断是否有额外数据需求
        unknown_data = {
            k: v for k, v in proposal.extra_data_desc.items()
            if k and k not in KNOWN_DATA
        }

        extra_arrays: dict = {}  # key → list[float|None]

        if unknown_data:
            print(f"  [研究专家] 需要额外数据: {list(unknown_data.keys())}")
            ok, fetched, fail_msg = self._try_fetch_extra(unknown_data)
            if ok:
                extra_arrays = fetched
                print(f"  [研究专家] 额外数据获取成功: {list(fetched.keys())}")
            else:
                # 写 TODO 文件
                todo_path = self._write_todo(proposal, unknown_data, fail_msg)
                return ResearchResult(
                    proposal=proposal, status="todo_written",
                    todo_file=str(todo_path),
                    error=fail_msg,
                )

        # 生成因子代码
        code = codegen.generate(proposal, list(extra_arrays.keys()))
        if not code:
            return ResearchResult(
                proposal=proposal, status="sandbox_fail",
                error="代码生成失败",
            )

        # 沙盒测试
        ic, error = evaluator.test(code, proposal.key, extra_arrays)
        if error:
            return ResearchResult(
                proposal=proposal, status="sandbox_fail",
                error=error,
            )

        # 写入因子文件
        factor_path = self._write_factor(proposal, code, extra_arrays)
        self._register(proposal, ic)

        return ResearchResult(
            proposal=proposal, status="registered",
            factor_file=str(factor_path),
            ic_score=ic,
        )

    def _try_fetch_extra(self, unknown_data: dict) -> tuple[bool, dict, str]:
        """尝试用 akshare 获取一次额外数据，返回 (success, data_dict, error_msg)"""
        try:
            import akshare as ak
        except ImportError:
            return False, {}, "akshare 未安装 (pip install akshare)"

        fetched = {}
        for key, desc in unknown_data.items():
            try:
                arr = _akshare_fetch_by_desc(ak, key, desc, self.symbols[0])
                if arr:
                    fetched[key] = arr
            except Exception as e:
                return False, {}, f"获取 {key} 失败: {e}"

        return bool(fetched), fetched, ""

    def _write_todo(self, proposal: FactorProposal, unknown_data: dict, error: str) -> Path:
        path = _TODO_DIR / f"{proposal.key}_data.md"
        lines = [
            f"# 因子数据需求待处理: {proposal.name_cn} (`{proposal.key}`)\n",
            f"**来源**: {proposal.source}\n",
            f"**描述**: {proposal.description}\n",
            f"**公式**: {proposal.formula}\n",
            "\n## 需要的额外数据\n",
        ]
        for k, desc in unknown_data.items():
            lines.append(f"### `{k}`\n{desc}\n")
        if error:
            lines.append(f"\n## 自动获取失败原因\n```\n{error}\n```\n")
        lines += [
            "\n## 处理方式\n",
            "1. 确认数据来源（akshare/tushare/Wind/第三方API）\n",
            "2. 在 `experts/factor_library/adapters/` 中实现获取函数:\n",
            "   ```python\n",
            f"   def fetch_{k}(symbol: str, n_bars: int) -> list:  ...\n",
            "   ```\n",
            "3. 删除此文件后重新运行 ResearchExpert\n",
        ]
        path.write_text("".join(lines), encoding="utf-8")
        return path

    def _write_factor(self, proposal: FactorProposal, code: str, extra_arrays: dict) -> Path:
        path = _FACTOR_DIR / f"{proposal.key}.py"
        header = f'''"""
Auto-generated factor: {proposal.name_cn}
Key: {proposal.key}
Type: {proposal.type}
Source: {proposal.source}
Description: {proposal.description}
Formula: {proposal.formula}
"""

TEMPLATE_KEY  = "{proposal.key}"
TEMPLATE_NAME = "{proposal.name_cn}"
STRATEGY_TYPE = "{proposal.type}"
DEFAULT_PARAMS = {json.dumps(proposal.params, ensure_ascii=False)}
PARAM_RANGES   = {json.dumps(proposal.param_ranges, ensure_ascii=False)}
REQUIRED_DATA  = {json.dumps(proposal.required_data)}

'''
        # 内嵌的 extra_arrays 数据（如果有）
        if extra_arrays:
            header += f"# 预获取的额外数据（按需使用）\n_EXTRA_DATA = {json.dumps({k: v[:5] for k, v in extra_arrays.items()})}  # 示例头5条\n\n"

        path.write_text(header + code, encoding="utf-8")
        return path

    def _register(self, proposal: FactorProposal, ic: float):
        self._registry[proposal.key] = {
            "name_cn":     proposal.name_cn,
            "type":        proposal.type,
            "source":      proposal.source,
            "params":      proposal.params,
            "param_ranges": proposal.param_ranges,
            "ic_score":    round(ic, 4),
            "registered_at": time.strftime("%Y-%m-%d"),
        }
        _REGISTRY.write_text(json.dumps(self._registry, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _load_registry() -> dict:
        if _REGISTRY.exists():
            try:
                return json.loads(_REGISTRY.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}


# ── akshare 智能获取 ─────────────────────────────────────────────────

def _akshare_fetch_by_desc(ak, key: str, desc: str, symbol: str) -> list:
    """
    根据数据描述尝试用 akshare 获取。
    目前支持：市盈率(PE)、市净率(PB)、换手率、成交额等。
    失败时抛出异常。
    """
    key_lower = key.lower()
    desc_lower = desc.lower()

    # 市盈率 PE
    if any(x in key_lower or x in desc_lower for x in ["pe", "市盈率", "price_earning"]):
        code = symbol.replace("SH", "").replace("SZ", "")
        df = ak.stock_a_indicator_lg(symbol=code)
        if df is not None and "pe" in df.columns:
            return df["pe"].tolist()

    # 市净率 PB
    if any(x in key_lower or x in desc_lower for x in ["pb", "市净率", "price_book"]):
        code = symbol.replace("SH", "").replace("SZ", "")
        df = ak.stock_a_indicator_lg(symbol=code)
        if df is not None and "pb" in df.columns:
            return df["pb"].tolist()

    # 换手率
    if any(x in key_lower or x in desc_lower for x in ["turnover", "换手率"]):
        code = symbol.replace("SH", "").replace("SZ", "")
        df = ak.stock_a_indicator_lg(symbol=code)
        if df is not None and "turnover_rate" in df.columns:
            return df["turnover_rate"].tolist()

    raise ValueError(f"暂不支持自动获取 '{key}'（{desc}），需要手动实现")
