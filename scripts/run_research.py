#!/usr/bin/env python3
"""
run_research.py — 独立因子研究管线
=====================================
从 arxiv 搜索论文 → LLM 提取因子提案 → 生成代码 → 沙盒测试 → 注册到因子库

使用方式：
  python3 scripts/run_research.py
  python3 scripts/run_research.py --queries "momentum factor A-share" "order flow imbalance"
  python3 scripts/run_research.py --papers 6 --symbols SH600519 SH600036

产出：
  experts/factor_library/factors/{key}.py     — 通过测试的因子代码
  experts/factor_library/registry.json        — 因子注册表
  experts/factor_library/TODO/{key}_data.md   — 需人工处理的数据需求
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from experts.researchers.research_expert import ResearchExpert

# ── 默认搜索查询（涵盖不同方向）────────────────────────────────────
DEFAULT_QUERIES = [
    "momentum factor stock return",
    "order flow imbalance equity",
    "earnings surprise alpha factor",
    "volume price reversal",
    "machine learning equity factor",
    "sentiment factor stock market",
    "intraday pattern overnight return",
]


def main():
    parser = argparse.ArgumentParser(description="因子研究管线")
    parser.add_argument("--queries", nargs="+", default=None,
                        help="搜索查询（默认使用内置7个查询中的前3个）")
    parser.add_argument("--papers",  type=int, default=4,
                        help="每个查询获取的论文数量（默认4）")
    parser.add_argument("--symbols", nargs="+", default=["SH600519", "SH600036"],
                        help="用于沙盒测试的标的（默认 SH600519 SH600036）")
    parser.add_argument("--all-queries", action="store_true",
                        help="使用全部7个默认查询（运行时间较长）")
    parser.add_argument("--urls", nargs="+", default=[],
                        help="自定义 URL 列表（网页/论文链接）")
    parser.add_argument("--pdfs", nargs="+", default=[],
                        help="本地 PDF 文件路径列表")
    args = parser.parse_args()

    queries = args.queries
    if not queries:
        queries = DEFAULT_QUERIES if args.all_queries else DEFAULT_QUERIES[:3]

    print("=" * 60)
    print("  因子研究管线")
    print(f"  查询: {len(queries)} 个  |  每查询论文: {args.papers} 篇")
    print(f"  测试标的: {args.symbols}")
    if args.urls:
        print(f"  自定义 URL: {len(args.urls)} 个")
    if args.pdfs:
        print(f"  本地 PDF:  {len(args.pdfs)} 个")
    print("=" * 60)

    _t0 = time.perf_counter()
    researcher = ResearchExpert(symbols=args.symbols)
    results = researcher.run(
        queries=queries,
        papers_per_query=args.papers,
        urls=args.urls,
        pdfs=args.pdfs,
    )
    dt = time.perf_counter() - _t0

    # ── 汇总 ────────────────────────────────────────────────────────
    registered  = [r for r in results if r.status == "registered"]
    todos       = [r for r in results if r.status == "todo_written"]
    failed      = [r for r in results if r.status == "sandbox_fail"]
    skipped     = [r for r in results if r.status == "skipped"]

    print("\n" + "=" * 60)
    print("  研究结果汇总")
    print("=" * 60)
    print(f"  ✅ 注册成功:  {len(registered)} 个")
    print(f"  📝 TODO待处理: {len(todos)} 个")
    print(f"  ❌ 沙盒失败:  {len(failed)} 个")
    print(f"  ⏭ 已存在跳过: {len(skipped)} 个")
    print(f"  总耗时: {dt:.1f}s")

    if registered:
        print("\n✅ 新注册因子：")
        for r in registered:
            p = r.proposal
            print(f"  [{p.type}] {p.name_cn} ({p.key})  IC={r.ic_score:.3f}")
            print(f"    文件: {r.factor_file}")

    if todos:
        print("\n📝 需要补充数据（查看 TODO 文件）：")
        for r in todos:
            p = r.proposal
            print(f"  {p.name_cn} ({p.key})")
            print(f"    缺失数据: {list(p.extra_data_desc.keys())}")
            print(f"    TODO: {r.todo_file}")

    if failed:
        print("\n❌ 测试失败：")
        for r in failed:
            print(f"  {r.proposal.name_cn} ({r.proposal.key}): {r.error[:80]}")

    if registered:
        print("\n💡 已注册的因子可在下次 run_iteration.py 时自动加载")
        print("   无需重启，直接运行迭代即可使用新因子")

    return len(registered)


if __name__ == "__main__":
    sys.exit(0 if main() >= 0 else 1)
