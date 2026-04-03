"""
research_expert.py — 因子发现专家
====================================
流程：
  1. 搜索 arxiv（最新论文优先，跳过已读）
  2. 支持自定义 URL / PDF 文件输入
  3. LLM 从摘要中提取因子提案
  4. 判断数据是否已有
  5. 已有 → 直接生成代码；未有 → 尝试一次 akshare 获取，失败写 TODO
  6. 沙盒测试通过 → 注册到因子库

已有数据（无需额外获取）：
  closes, highs, lows, volumes, opens
  indicators: rsi14, macd_hist, adx, bb_upper, bb_lower, bb_mid
"""

import json
import math
import os
import re
import ssl
import sys
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# WSL2 环境下 arxiv SSL 证书验证可能失败，使用宽松上下文
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE
_OPENER = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_SSL_CTX))

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
_SEEN_FILE  = _LIB_DIR / "seen_papers.json"   # 已读论文 ID 记录，避免重复

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


# ── arxiv 搜索（最新优先）────────────────────────────────────────────

def search_arxiv(query: str, max_results: int = 8,
                 skip_ids: set = None) -> list[dict]:
    """
    返回 [{title, abstract, arxiv_id, published}]。
    - 限定 cat:q-fin 量化金融类别，过滤无关领域论文
    - sortBy=submittedDate 保证拿到最新论文
    - 自动重试 2 次以应对网络抖动
    skip_ids: 已处理过的 arxiv ID，自动跳过。
    """
    # 构建 arxiv 搜索条件
    # 前3个关键词用 abs: 匹配 + 量化金融子类别过滤
    # 注意：括号需 URL 编码；cat:q-fin 不匹配子类别
    words = [w for w in query.split() if len(w) > 2][:3]
    parts = [f"abs:{w}" for w in words]
    # 轮换使用 q-fin 子类别（避免括号编码问题）
    _QFIN_CATS = ["q-fin.PM", "q-fin.TR", "q-fin.ST", "q-fin.MF"]
    cat_idx = hash(query) % len(_QFIN_CATS)
    parts.append(f"cat:{_QFIN_CATS[cat_idx]}")
    search_query = "+AND+".join(parts)
    url = (f"https://export.arxiv.org/api/query"
           f"?search_query={search_query}"
           f"&max_results={max_results}"
           f"&sortBy=submittedDate&sortOrder=descending")

    xml = None
    for attempt in range(3):
        try:
            with _OPENER.open(url, timeout=20) as r:
                xml = r.read().decode("utf-8")
            break
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
            else:
                print(f"  [研究专家] arxiv 请求失败: {e}")
                return []

    if not xml:
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml)
    skip_ids = skip_ids or set()
    papers = []
    for entry in root.findall("atom:entry", ns):
        title     = _get_text(entry.find("atom:title",     ns))
        abstract  = _get_text(entry.find("atom:summary",   ns))
        arxiv_id  = _get_text(entry.find("atom:id",        ns))
        published = _get_text(entry.find("atom:published", ns))
        if not arxiv_id:
            continue
        if arxiv_id in skip_ids:
            print(f"  [研究专家] 跳过已读: {arxiv_id[-40:]}")
            continue
        papers.append({
            "title":     title.strip().replace("\n", " "),
            "abstract":  abstract.strip()[:1500],
            "arxiv_id":  arxiv_id,
            "published": published[:10],   # YYYY-MM-DD
        })
    return papers


def _get_text(element, default: str = "") -> str:
    """安全地从 XML Element 取文本，避免 ET 的 bool 陷阱"""
    return (element.text or "").strip() if element is not None else default


# ── URL 网页获取 ─────────────────────────────────────────────────────

def fetch_from_url(url: str) -> Optional[dict]:
    """
    从网页 URL 提取文本摘要（纯文本，去除 HTML 标签）。
    返回 {title, abstract, arxiv_id} 格式以兼容后续流程。
    """
    print(f"  [研究专家] 获取 URL: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _OPENER.open(req, timeout=20) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [研究专家] URL 获取失败: {e}")
        return None

    # 提取 <title>
    title_m = re.search(r"<title[^>]*>([^<]+)</title>", raw, re.I)
    title = title_m.group(1).strip() if title_m else url

    # 去除 HTML 标签，清理空白
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()

    return {
        "title":     title[:200],
        "abstract":  text[:1500],
        "arxiv_id":  f"url:{url[:80]}",   # 伪 ID，用于去重
        "published": time.strftime("%Y-%m-%d"),
    }


# ── PDF 文件读取 ─────────────────────────────────────────────────────

def fetch_from_pdf(path: str) -> Optional[dict]:
    """
    从本地 PDF 文件提取文本。
    依次尝试 pdfplumber → pypdf。
    """
    pdf_path = Path(path)
    if not pdf_path.exists():
        print(f"  [研究专家] PDF 文件不存在: {path}")
        return None

    print(f"  [研究专家] 读取 PDF: {pdf_path.name}")
    text = ""

    # 方案 1: pdfplumber（最准确）
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages[:10])
    except ImportError:
        pass
    except Exception as e:
        print(f"  [研究专家] pdfplumber 失败: {e}")

    # 方案 2: pypdf
    if not text.strip():
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(pdf_path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages[:10])
        except ImportError:
            pass
        except Exception as e:
            print(f"  [研究专家] pypdf 失败: {e}")

    if not text.strip():
        print(f"  [研究专家] PDF 文本提取失败（请安装 pdfplumber 或 pypdf）")
        return None

    text = re.sub(r"\s+", " ", text).strip()
    return {
        "title":     pdf_path.stem[:200],
        "abstract":  text[:1500],
        "arxiv_id":  f"pdf:{pdf_path.name}",
        "published": time.strftime("%Y-%m-%d"),
    }


# ── LLM 提取因子提案 ─────────────────────────────────────────────────

_EXTRACT_PROMPT = """
你是一名量化研究员，请从以下文献中提取可以实现为截面因子的策略。

【文献信息】
标题：{title}
内容摘要：{abstract}

【已有数据】
OHLCV: closes（收盘价列表）, highs, lows, volumes, opens
技术指标: rsi14, macd_hist, adx, bb_upper, bb_lower, bb_mid

【任务】
如果内容中包含可实现的量化因子，提取 1~2 个，输出 JSON 数组。
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

    items = result if isinstance(result, list) else result.get("factors", result.get("proposals", []))
    if not isinstance(items, list):
        return []

    proposals = []
    for item in items:
        if not isinstance(item, dict) or not item.get("key"):
            continue
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
    - 自动记录已读论文 ID，避免重复处理
    - 支持 URLs 和 PDF 文件输入
    """

    DEFAULT_QUERIES = [
        "momentum factor stock return",
        "order flow imbalance equity",
        "earnings surprise alpha factor",
        "volume price reversal",
        "machine learning equity factor",
        "sentiment factor stock market",
        "intraday pattern overnight return",
    ]

    def __init__(self, symbols: list[str] = None):
        self.symbols     = symbols or ["SH600519"]
        self._registry   = self._load_registry()
        self._seen_ids   = self._load_seen_ids()
        self._papers_meta = self._load_papers_meta()

    def run(
        self,
        queries: list[str] = None,
        papers_per_query: int = 4,
        urls: list[str] = None,
        pdfs: list[str] = None,
    ) -> list[ResearchResult]:
        from experts.researchers.factor_codegen import FactorCodegen
        from experts.researchers.sandbox_evaluator import SandboxEvaluator

        queries   = queries or self.DEFAULT_QUERIES[:2]
        urls      = urls or []
        pdfs      = pdfs or []
        codegen   = FactorCodegen()
        evaluator = SandboxEvaluator(self.symbols)
        results   = []
        new_seen  = set()

        # ── 1. arxiv 论文 ────────────────────────────────────────────
        for query in queries:
            print(f"\n  [研究专家] 搜索: {query}")
            papers = search_arxiv(query, max_results=papers_per_query,
                                  skip_ids=self._seen_ids)
            print(f"  [研究专家] 找到 {len(papers)} 篇新论文")

            for paper in papers:
                new_seen.add(paper["arxiv_id"])
                pub = paper.get("published", "")
                print(f"  [研究专家] 论文({pub}): {paper['title'][:60]}")
                batch = self._process_paper(paper, codegen, evaluator)
                results.extend(batch)

        # ── 2. 自定义 URLs ───────────────────────────────────────────
        for url in urls:
            paper = fetch_from_url(url)
            if not paper:
                continue
            if paper["arxiv_id"] in self._seen_ids:
                print(f"  [研究专家] 跳过已读 URL: {url[:60]}")
                continue
            new_seen.add(paper["arxiv_id"])
            batch = self._process_paper(paper, codegen, evaluator)
            results.extend(batch)

        # ── 3. 本地 PDF ──────────────────────────────────────────────
        for pdf in pdfs:
            paper = fetch_from_pdf(pdf)
            if not paper:
                continue
            if paper["arxiv_id"] in self._seen_ids:
                print(f"  [研究专家] 跳过已读 PDF: {pdf}")
                continue
            new_seen.add(paper["arxiv_id"])
            batch = self._process_paper(paper, codegen, evaluator)
            results.extend(batch)

        # 持久化已读记录
        self._seen_ids.update(new_seen)
        self._save_seen_ids()
        print(f"\n  [研究专家] 已累计记录 {len(self._seen_ids)} 篇已读文献")

        return results

    def _process_paper(self, paper: dict, codegen, evaluator) -> list[ResearchResult]:
        """提取因子并处理一篇论文，返回结果列表"""
        proposals = extract_proposals(paper)
        results = []
        for proposal in proposals:
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
        unknown_data = {
            k: v for k, v in proposal.extra_data_desc.items()
            if k and k not in KNOWN_DATA
        }
        extra_arrays: dict = {}

        if unknown_data:
            print(f"  [研究专家] 需要额外数据: {list(unknown_data.keys())}")
            ok, fetched, fail_msg = self._try_fetch_extra(unknown_data)
            if ok:
                extra_arrays = fetched
                print(f"  [研究专家] 额外数据获取成功: {list(fetched.keys())}")
            else:
                todo_path = self._write_todo(proposal, unknown_data, fail_msg)
                return ResearchResult(
                    proposal=proposal, status="todo_written",
                    todo_file=str(todo_path),
                    error=fail_msg,
                )

        code = codegen.generate(proposal, list(extra_arrays.keys()))
        if not code:
            return ResearchResult(
                proposal=proposal, status="sandbox_fail",
                error="代码生成失败",
            )

        ic, error = evaluator.test(code, proposal.key, extra_arrays)
        if error:
            return ResearchResult(
                proposal=proposal, status="sandbox_fail",
                error=error,
            )

        factor_path = self._write_factor(proposal, code, extra_arrays)
        self._register(proposal, ic)
        self._link_paper_to_factor(proposal.source, proposal.key)
        self._save_seen_ids()

        return ResearchResult(
            proposal=proposal, status="registered",
            factor_file=str(factor_path),
            ic_score=ic,
        )

    def _try_fetch_extra(self, unknown_data: dict) -> tuple[bool, dict, str]:
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
        for field_k, desc in unknown_data.items():
            lines.append(f"### `{field_k}`\n{desc}\n")
        if error:
            lines.append(f"\n## 自动获取失败原因\n```\n{error}\n```\n")
        lines += [
            "\n## 处理方式\n",
            "1. 确认数据来源（akshare/tushare/Wind/第三方API）\n",
            "2. 在 `experts/factor_library/adapters/` 中实现获取函数\n",
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
        if extra_arrays:
            sample = {k: v[:5] for k, v in extra_arrays.items()}
            header += f"# 预获取的额外数据（按需使用）\n_EXTRA_DATA = {json.dumps(sample)}  # 示例头5条\n\n"

        path.write_text(header + code, encoding="utf-8")
        return path

    def _register(self, proposal: FactorProposal, ic: float):
        self._registry[proposal.key] = {
            "name_cn":        proposal.name_cn,
            "type":           proposal.type,
            "source":         proposal.source,
            "source_paper_id": proposal.source,   # arxiv_id / url:… / pdf:…
            "params":         proposal.params,
            "param_ranges":   proposal.param_ranges,
            "ic_score":       round(ic, 4),
            "registered_at":  time.strftime("%Y-%m-%d"),
        }
        _REGISTRY.write_text(
            json.dumps(self._registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _load_registry() -> dict:
        if _REGISTRY.exists():
            try:
                return json.loads(_REGISTRY.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  [研究专家] registry.json 损坏，重置: {e}")
        return {}

    @staticmethod
    def _load_seen_ids() -> set:
        if _SEEN_FILE.exists():
            try:
                data = json.loads(_SEEN_FILE.read_text(encoding="utf-8"))
                return set(data.get("ids", []))
            except Exception as e:
                print(f"  [研究专家] seen_papers.json 损坏，重置: {e}")
        return set()

    @staticmethod
    def _load_papers_meta() -> dict:
        """加载 seen_papers.json 中的 papers 元数据（title, produced_factor 等）。"""
        if _SEEN_FILE.exists():
            try:
                data = json.loads(_SEEN_FILE.read_text(encoding="utf-8"))
                return data.get("papers", {})
            except Exception:
                pass
        return {}

    def _save_seen_ids(self):
        _SEEN_FILE.write_text(
            json.dumps(
                {"ids": sorted(self._seen_ids), "papers": self._papers_meta},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    def _link_paper_to_factor(self, paper_id: str, factor_key: str):
        """在 papers_meta 中记录论文产出了哪个因子（双向映射）。"""
        entry = self._papers_meta.setdefault(paper_id, {})
        existing = entry.get("produced_factor")
        if existing is None:
            entry["produced_factor"] = factor_key
        elif isinstance(existing, list):
            if factor_key not in existing:
                existing.append(factor_key)
        elif existing != factor_key:
            entry["produced_factor"] = [existing, factor_key]


# ── akshare 智能获取 ─────────────────────────────────────────────────

def _akshare_fetch_by_desc(ak, key: str, desc: str, symbol: str) -> list:
    """
    根据数据描述尝试用 akshare 获取。
    支持：PE、PB、换手率、成交额、市值。
    失败时抛出异常。
    """
    key_lower  = key.lower()
    desc_lower = desc.lower()

    def matches(*keywords) -> bool:
        return any(kw in key_lower or kw in desc_lower for kw in keywords)

    code = symbol.replace("SH", "").replace("SZ", "")

    if matches("pe", "市盈率", "price_earning", "p/e"):
        df = ak.stock_a_indicator_lg(symbol=code)
        if df is not None and "pe" in df.columns:
            return df["pe"].dropna().tolist()

    if matches("pb", "市净率", "price_book", "p/b"):
        df = ak.stock_a_indicator_lg(symbol=code)
        if df is not None and "pb" in df.columns:
            return df["pb"].dropna().tolist()

    if matches("turnover", "换手率", "turnover_rate"):
        df = ak.stock_a_indicator_lg(symbol=code)
        if df is not None and "turnover_rate" in df.columns:
            return df["turnover_rate"].dropna().tolist()

    if matches("market_cap", "市值", "total_mv", "capitalization"):
        df = ak.stock_a_indicator_lg(symbol=code)
        if df is not None and "total_mv" in df.columns:
            return df["total_mv"].dropna().tolist()

    if matches("amount", "成交额", "trade_amount"):
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if df is not None and "成交额" in df.columns:
            return df["成交额"].dropna().tolist()

    raise ValueError(f"暂不支持自动获取 '{key}'（{desc}），需要手动实现")
