#!/usr/bin/env python3
"""validate_dashboard_data.py — 验证 Dashboard 迭代数据完整性"""
import json, sys
from pathlib import Path

data_dir = Path(__file__).parent / 'dashboard' / 'src' / 'data' / 'iterations'
errors = []

for f in sorted(data_dir.glob('iter_*.json')):
    d = json.loads(f.read_text())
    rounds = d.get('rounds', [])
    if not rounds:
        errors.append(f'{f.name}: 无轮次数据')
        continue
    
    # 检查每轮是否有 alpha 数据
    missing_alpha = 0
    total = 0
    for r in rounds:
        for s in r.get('strategies', []):
            total += 1
            if s.get('alpha', 0) == 0:
                missing_alpha += 1
    
    zero_pct = missing_alpha / max(total, 1) * 100
    status = '✅' if zero_pct < 30 else '⚠️' if zero_pct < 60 else '❌'
    print(f'{status} {f.name}: {len(rounds)}r {total}s alpha_zero={zero_pct:.0f}%')

if errors:
    print('\n❌ ERRORS:')
    for e in errors:
        print(f'  {e}')
    sys.exit(1)
else:
    print('\n✅ All dashboard data valid')
