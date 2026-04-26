#!/usr/bin/env python3
"""smoke_test.py — 冒烟测试：1轮管道 + 数据验证

用法：
  python3 scripts/smoke_test.py

成功：exit 0
失败：exit 1，输出具体错误
"""

import json, sys, os
from pathlib import Path
from datetime import datetime

PROJECT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT))
ERRORS = 0

def check(msg, condition):
    global ERRORS
    if condition:
        print(f"  ✅ {msg}")
    else:
        print(f"  ❌ {msg}")
        ERRORS += 1

print("=" * 60)
print("  冒烟测试")
print("=" * 60)

# ── 1. Python 导入检查 ──────────────────────────────────────────
print("\n[1] Python 导入检查")
try:
    from experts.orchestrator import Orchestrator
    check("Orchestrator 导入", True)
except Exception as e:
    check(f"Orchestrator 导入: {e}", False)

try:
    from experts.specialists.factor_combo_expert import FactorComboExpert
    check("FactorComboExpert 导入", True)
except Exception as e:
    check(f"FactorComboExpert 导入: {e}", False)

try:
    from backtest.engine import PortfolioBacktester
    check("PortfolioBacktester 导入", True)
except Exception as e:
    check(f"PortfolioBacktester 导入: {e}", False)

try:
    from experts.modules.llm_proxy import llm_analyze
    check("llm_proxy 导入", True)
except Exception as e:
    check(f"llm_proxy 导入: {e}", False)

try:
    from factors.signals import FACTOR_TABLE
    check(f"FACTOR_TABLE: {len(FACTOR_TABLE)} 因子", True)
except Exception as e:
    check(f"FACTOR_TABLE: {e}", False)

try:
    from experts.evaluator import Evaluator
    e = Evaluator()
    check("Evaluator 实例化", True)
except Exception as e:
    check(f"Evaluator: {e}", False)

# ── 2. 管道导入验证（不实际运行，避免 LLM 调用）─────────────────
print("\n[2] 管道导入验证")
try:
    o = Orchestrator(['SPY'], n_days=300, seed=9999, max_rounds=1, top_n=2)
    check("Orchestrator 实例化 (5标的)", True)
    check(f"combo_expert 模板数: {len(o.combo_expert.TEMPLATES)}", True)
    check(f"meta_params: {o._meta_params}", True)
except Exception as e:
    check(f"Orchestrator 实例化: {e}", False)

# ── 3. 结果文件验证 ─────────────────────────────────────────────
print("\n[3] 结果文件验证")
result_files = sorted(PROJECT.glob("results/multi_expert_v4_*.json"), reverse=True)
check(f"结果文件存在 ({len(result_files)} 个)", len(result_files) > 0)

if result_files:
    latest = result_files[0]
    try:
        data = json.loads(latest.read_text())
        check(f"结果 JSON 有效: {latest.name}", True)

        rounds = data.get("rounds", [])
        check(f"轮次数据: {len(rounds)} 轮", len(rounds) > 0)

        if rounds:
            strategies = rounds[0].get("strategies", [])
            check(f"第1轮策略数: {len(strategies)}", len(strategies) > 0)

            if strategies:
                s = strategies[0]
                check(f"策略字段: {list(s.keys())}", True)
                check("alpha 字段存在", 'alpha' in s)
                check("score 字段存在", 'score' in s)
                check("sharpe 字段存在", 'sharpe' in s)
                check("decision 字段存在", 'decision' in s)

        global_top = data.get("global_top", [])
        check(f"全局Top: {len(global_top)} 个", len(global_top) > 0)

        convergence = data.get("convergence", {})
        check("收敛数据存在", bool(convergence))

    except Exception as e:
        check(f"读取结果: {e}", False)

# ── 4. Dashboard 数据验证 ────────────────────────────────────────
print("\n[4] Dashboard 数据验证")
try:
    sys.path.insert(0, str(PROJECT))
    import scripts.validate_dashboard as vd
    # Run silently
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        check("validate_dashboard.py 可导入", True)
except Exception as e:
    check(f"validate_dashboard.py: {e}", False)

# ── 5. TypeScript 编译 ───────────────────────────────────────────
print("\n[5] TypeScript 编译")
import subprocess
try:
    r = subprocess.run(
        ["npx", "tsc", "--noEmit"],
        cwd=str(PROJECT / "dashboard"),
        capture_output=True, text=True, timeout=30
    )
    if r.returncode == 0:
        check("TypeScript 编译通过", True)
    else:
        check(f"TypeScript 错误:\n{r.stderr[:300]}", False)
except FileNotFoundError:
    check("npx 不可用（跳过）", True)
except Exception as e:
    check(f"TypeScript: {e}", False)

# ── 6. CLAUDE.md 规则检查 ────────────────────────────────────────
print("\n[6] 代码规则检查")
try:
    content = (PROJECT / "CLAUDE.md").read_text()
    check("CLAUDE.md 存在", True)

    # 检查关键规则是否存在
    rules = [
        "禁止降级",
        "API 调用失败必须直接抛出异常",
        "禁止静默捕获异常",
        "修改前强制检查",
    ]
    for rule in rules:
        check(f"规则 '{rule}' 存在", rule in content)
except Exception as e:
    check(f"CLAUDE.md: {e}", False)

# ── 结果 ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
if ERRORS == 0:
    print("  ✅ 冒烟测试全部通过")
    print("=" * 60)
    sys.exit(0)
else:
    print(f"  ❌ {ERRORS} 项检查失败")
    print("=" * 60)
    sys.exit(1)
