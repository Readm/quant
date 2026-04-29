#!/usr/bin/env python3
"""validate_dashboard_data.py — 验证 Dashboard 迭代数据完整性"""
import json, sys
from pathlib import Path

status = True

for label, data_dir in [
    ("src/data", Path(__file__).parent.parent / 'dashboard' / 'src' / 'data' / 'iterations'),
    ("public/data", Path(__file__).parent.parent / 'dashboard' / 'public' / 'data' / 'iterations'),
]:
    if not data_dir.exists():
        print(f"  ⚠️ {label}: {data_dir} 目录不存在")
        continue
    for f in sorted(data_dir.glob('*.json')):
        if f.name == 'index.json':
            continue
        try:
            d = json.loads(f.read_text())
        except Exception as e:
            print(f'❌ {label}/{f.name}: JSON 解析失败 - {e}')
            status = False
            continue
        rounds = d.get('rounds', [])
        if not rounds:
            print(f'❌ {label}/{f.name}: 无轮次数据')
            status = False
            continue
        total_strats = sum(len(r.get('strategies',[])) for r in rounds)
        missing_ec = sum(1 for r in rounds for s in r.get('strategies',[]) if 'equity_curve' not in s)
        if missing_ec == total_strats:
            # 旧格式数据，不含 equity_curve 字段 — 兼容通过
            print(f'⚠️ {label}/{f.name}: 旧格式({total_strats}s, 无equity_curve), {len(rounds)}r')
        elif missing_ec > 0:
            print(f'❌ {label}/{f.name}: {missing_ec}/{total_strats} 策略缺少 equity_curve')
            status = False
        else:
            print(f'✅ {label}/{f.name}: {len(rounds)}r {total_strats}s')

if not status:
    sys.exit(1)
else:
    print('\n✅ All dashboard data valid')
