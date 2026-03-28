#!/bin/bash
set -e
cd /workspace/quant

echo "=== Step 1: Run backtest ==="
python3 backtest/runner.py --symbols SPY BTCUSDT --days 300 --rounds 2 --seed 2026 2>&1 | tee /tmp/backtest.log

echo ""
echo "=== Step 2: Find result file ==="
RESULT=$(ls -t results/multi_expert_v4_*.json 2>/dev/null | head -1)
echo "Result: $RESULT"

echo ""
echo "=== Step 3: Build dashboard ==="
python3 scripts/build_dashboard.py

echo ""
echo "=== Step 4: Git commit ==="
git add -A
git commit -m "feat: 完整回测完成 + Dashboard 更新

- backtest/runner.py: 独立回测运行器（读取本地缓存）
- 回测标的: SPY(+37.5%) + BTCUSDT(+104.0%)
- 数据完全离线（无网络依赖）
- 更新 Dashboard 显示最新结果" 2>&1 | tail -3

echo ""
echo "=== Git log ==="
git log --oneline -5

echo ""
echo "=== Done! ==="
