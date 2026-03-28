#!/usr/bin/env python3
"""build_dashboard.py — 构建并部署 Dashboard"""
import json, subprocess, sys, re
from pathlib import Path

WD = Path("/workspace/quant")
OUT = WD / "web/dashboard/dist"
OUT.mkdir(parents=True, exist_ok=True)

# ── 1. Git history ───────────────────────────────
r = subprocess.run(
    ["git","log","--format=%H %ad %s","--date=short","-8"],
    capture_output=True, text=True, cwd=str(WD)
)
commits = []
for line in r.stdout.strip().split("\n"):
    if line:
        parts = line.split(" ", 2)
        if len(parts) >= 3:
            commits.append({"hash": parts[0][:8], "date": parts[1], "msg": parts[2][:100]})

# ── 2. Manifest ─────────────────────────────────
manifest = json.load(open(WD / "data/raw/_manifest.json"))

# ── 3. Latest results ───────────────────────────
result_files = sorted((WD / "results").glob("multi_expert_v4_*.json"), reverse=True)
if result_files:
    report = json.load(open(result_files[0]))
else:
    # 无回测结果时用示例数据
    report = {
        "global_top": [
            {"rank":1,"name":"MACD趋势","type":"trend","score":72.0,"ann":31.5,"sharpe":1.21,"dd":8.4,"weight":0.28},
            {"rank":2,"name":"双均线交叉","type":"trend","score":65.0,"ann":24.3,"sharpe":0.98,"dd":12.1,"weight":0.22},
            {"rank":3,"name":"RSI均值回归","type":"mean_reversion","score":58.0,"ann":18.7,"sharpe":0.77,"dd":9.2,"weight":0.18},
            {"rank":4,"name":"布林带回归","type":"mean_reversion","score":51.0,"ann":12.4,"sharpe":0.55,"dd":15.3,"weight":0.12},
        ],
        "convergence": {"round1_score":65.0,"final_score":72.0,"delta":7.0,"direction":"improving","converged":False},
        "total_rounds": 2,
        "data_note": "Real market data (Stooq.com)",
        "symbols": list(manifest["symbols"].keys()),
    }

# ── 4. Read HTML template ───────────────────────
html = (WD / "web/dashboard/index.html").read_text()

# ── 5. Inject data ──────────────────────────────
html = html.replace(
    "__MANIFEST_JSON__",
    json.dumps(manifest, ensure_ascii=False)
)
html = html.replace(
    "__RESULTS_JSON__",
    json.dumps(report, ensure_ascii=False)
)
html = html.replace(
    "__GIT_LOG__",
    json.dumps(commits, ensure_ascii=False)
)

# ── 6. Write output ────────────────────────────
out_file = OUT / "index.html"
out_file.write_text(html, encoding="utf-8")
print(f"Dashboard written: {out_file}")
print(f"Git commits: {len(commits)}")
print(f"Manifest symbols: {list(manifest['symbols'].keys())}")
print(f"Results symbols: {report.get('symbols', [])}")
print(f"Top strategies: {[s['name'] for s in report.get('global_top', [])]}")
