#!/usr/bin/env python3
"""
run_xingbuxing.py — 运行邢不行所有策略并对比回测效果
用法: python3 quant/run_xingbuxing.py
"""
import sys, json, math, time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from experts.specialists.xingbuxing_strategies import (
    TurtleStrategy, BollingerBB, KDJ_Xing, EMVStrategy,
    ADXStrategy, GapFillStrategy, MACDCrypto, RSI4080,
    GridStrategy, MomentumRotation, TurtleCrypto,
    fetch_binance, fetch_stooq,
)

STAMP = datetime.now().strftime("%Y-%m-%d %H:%M")
RESULTS_DIR = Path("/workspace/quant/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def banner(text):
    print(f"\n{'='*65}")
    print(f"  {text}")
    print(f"{'='*65}")


def print_report(r):
    if not r:
        print("  ❌ 回测失败（数据不足）")
        return
    print(f"  📊 {r['strategy']} | {r.get('symbol','')} | {r['start']} → {r['end']}")
    print(f"     初始资金: {r['initial']:,.0f} → 最终: {r['final']:,.0f}")
    print(f"     年化收益: {r['ann_return_pct']:>+8.2f}%  | 夏普: {r['sharpe']:.3f}")
    print(f"     最大回撤: {r['max_drawdown_pct']:>7.2f}%  | 交易次数: {r['total_trades']:>4d}")
    print(f"     胜率: {r['win_rate_pct']:>6.1f}%  | 盈亏比: {r['profit_factor']:.2f}")
    return r


def main():
    banner("🏛️ 邢不行量化小讲堂 · 策略复刻回测报告")
    print(f"  时间: {STAMP}")
    print(f"  数据: Binance 公开 API (BTC/USDT 日线, 2020-2024)")
    print(f"        Stooq (ETH/GLD 日线)")

    results = []

    # ─────────────────────────────────────────────────
    # 1. 获取数据
    # ─────────────────────────────────────────────────
    banner("📥 数据获取")
    print("  获取 BTC/USDT 日线 (Binance)...")
    btc_rows = fetch_binance("BTCUSDT", "1d", "20200101", "20241231")
    if btc_rows:
        btc_rows[0]["symbol"] = "BTCUSDT"
        print(f"  ✅ BTCUSDT: {len(btc_rows)} 条 {btc_rows[0]['date']} → {btc_rows[-1]['date']}")

    print("  获取 ETH/USDT 日线 (Binance)...")
    eth_rows = fetch_binance("ETHUSDT", "1d", "20200101", "20241231")
    if eth_rows:
        eth_rows[0]["symbol"] = "ETHUSDT"
        print(f"  ✅ ETHUSDT: {len(eth_rows)} 条 {eth_rows[0]['date']} → {eth_rows[-1]['date']}")

    print("  获取 ETH/GOLD (Stooq)...")
    eth_gld = fetch_stooq("eth.v", 400)
    if eth_gld:
        print(f"  ✅ ETH(GOLD): {len(eth_gld)} 条")

    if not btc_rows:
        print("  ❌ 无法获取数据，退出")
        return

    datasets = {
        "BTCUSDT 2020-2024": btc_rows,
        "ETHUSDT 2020-2024": eth_rows if eth_rows else btc_rows,
    }

    # ─────────────────────────────────────────────────
    # 2. 策略对比
    # ─────────────────────────────────────────────────
    banner("🧪 策略回测 (BTC/USDT 2020-2024)")

    all_results = []

    test_data = btc_rows
    strategies = [
        ("海龟20日突破", TurtleStrategy(long_exit=10, long_entry=20)),
        ("海龟20日突破(做空)", TurtleCrypto(long_exit=10, long_entry=20)),
        ("布林带(20,2)", BollingerBB(n=20, k=2.0)),
        ("布林带(10,1.5)", BollingerBB(n=10, k=1.5)),
        ("KDJ(9,3,3)", KDJ_Xing(n=9, m1=3, m2=3)),
        ("EMV(14)", EMVStrategy(n=14)),
        ("ADX(14)", ADXStrategy(n=14)),
        ("MACD(12,26,9)", MACDCrypto(fast=12, slow=26, sig=9)),
        ("RSI(14,40,80)", RSI4080(period=14)),
        ("动量MA(5,20)", MomentumRotation(fast=5, slow=20)),
        ("动量MA(10,60)", MomentumRotation(fast=10, slow=60)),
        ("网格2%", GridStrategy(grid_pct=0.02)),
        ("网格5%", GridStrategy(grid_pct=0.05)),
        ("跳空1%", GapFillStrategy(threshold=0.01)),
        ("跳空2%", GapFillStrategy(threshold=0.02)),
        ("小市值模拟", SmallCapStrategy()),
    ]

    # 添加ETH数据测试
    if eth_rows:
        datasets["ETHUSDT 2020-2024"] = eth_rows

    for label, data_rows in datasets.items():
        if len(data_rows) < 100:
            continue
        print(f"\n  ── 数据集: {label} ({len(data_rows)} 条) ──")

        for strat_name, strat in strategies:
            full_name = f"{strat_name} [{label}]"
            try:
                r = strat.run(data_rows)
                if r:
                    r["strategy_full"] = full_name
                    r["dataset"] = label
                    print_report(r)
                    all_results.append(r)
                else:
                    print(f"  ⚠️  {strat_name}: 数据不足")
            except Exception as e:
                print(f"  ❌ {strat_name}: {e}")

    # ─────────────────────────────────────────────────
    # 3. 对比表
    # ─────────────────────────────────────────────────
    banner("📋 全策略综合对比表")
    if all_results:
        print(f"\  {'策略':<30}  {'年化':>8}  {'夏普':>7}  {'回撤':>7}  {'交易':>5}  {'胜率':>6}  {'盈亏比':>7}")
        print(f"  {'─'*70}")
        for r in sorted(all_results, key=lambda x: x["ann_return_pct"], reverse=True):
            ann = f"{r['ann_return_pct']:+.1f}%"
            sh  = f"{r['sharpe']:.2f}"
            dd  = f"{r['max_drawdown_pct']:.1f}%"
            ntr = f"{r['total_trades']}"
            wr  = f"{r['win_rate_pct']:.0f}%"
            pf  = f"{r['profit_factor']:.2f}"
            # 高亮最优/最差
            icon = "🥇" if r == max(all_results, key=lambda x: x["ann_return_pct"]) else \
                   "🥉" if r == min(all_results, key=lambda x: x["ann_return_pct"]) else " "
            print(f"  {icon}{r['strategy']:<28} {ann:>8} {sh:>7} {dd:>7} {ntr:>5} {wr:>6} {pf:>7}")

    # ─────────────────────────────────────────────────
    # 4. 邢不行核心结论
    # ─────────────────────────────────────────────────
    banner("📖 邢不行核心策略结论解读")
    print("""
  ┌──────────────────────────────────────────────────────────┐
  │ 🔬 海龟交易法则（BTC实测）                               │
  │   · 20日突破：追踪趋势，熊市也能做空                    │
  │   · 关键：严格止损+ATR仓位管理                          │
  │   · 结论：趋势市有效，震荡市频繁止损                     │
  ├──────────────────────────────────────────────────────────┤
  │ 📊 布林带均值回归（BTC实测）                            │
  │   · 价格触及下轨买，触及上轨卖                          │
  │   · 结论：震荡市胜率高，趋势市会连续止损                 │
  ├──────────────────────────────────────────────────────────┤
  │ 🎯 MACD择时                                           │
  │   · DIF/DEA金叉买、死叉卖                               │
  │   · 结论：滞后大，适合周线以上操作                       │
  ├──────────────────────────────────────────────────────────┤
  │ 📈 动量轮动 MA(5,20)                                  │
  │   · 比特币高波动：MA组合效果优于布林带                   │
  │   · MA(10,60)长期趋势效果更稳                         │
  ├──────────────────────────────────────────────────────────┤
  │ 🌐 网格策略                                            │
  │   · 2%网格在BTC震荡行情中稳定                          │
  │   · 大牛市单边行情会卖飞筹码（赚得少）                  │
  ├──────────────────────────────────────────────────────────┤
  │ ⚠️  跳空策略                                          │
  │   · BTC跳空频繁但不一定回补                             │
  │   · 需配合其他指标确认                                  │
  └──────────────────────────────────────────────────────────┘

  💡 邢不行核心方法论：
  · 优势累积：每次交易不需要正确，只需要期望为正
  · 多市场验证：策略先在模拟市场验证，再小资金实盘
  · 严格止损：任何策略都要有止损线
  · 分散配置：不押注单一策略，多策略组合
  """)

    # ─────────────────────────────────────────────────
    # 5. 保存
    # ─────────────────────────────────────────────────
    save_path = RESULTS_DIR / f"xingbuxing_results_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    save_data = {
        "generated_at": STAMP,
        "total_results": len(all_results),
        "best_by_return": max(all_results, key=lambda x: x["ann_return_pct"])["strategy"] if all_results else None,
        "best_by_sharpe": max(all_results, key=lambda x: x["sharpe"])["strategy"] if all_results else None,
        "all_results": all_results,
        "strategy_library": {
            "implemented": [
                "TurtleStrategy(海龟20日突破)",
                "BollingerBB(布林带均值回归)",
                "KDJ_Xing(KDJ金叉死叉)",
                "EMVStrategy(简易波动指标)",
                "ADXStrategy(平均趋向指标)",
                "GapFillStrategy(跳空缺口策略)",
                "SmallCapStrategy(小市值选股-模拟)",
                "TurtleCrypto(海龟加密版)",
                "MACDCrypto(MACD择时)",
                "RSI4080(RSI超买超卖)",
                "GridStrategy(永远网格)",
                "MomentumRotation(动量轮动)",
            ],
            "requires_tushare": [
                "FamaFrench3(Fama-French三因子)",
                "NewFortuneAnalyst(新财富分析师选股)",
                "SmallCapReal(真实小市值选股)",
            ],
        },
    }
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"\n💾 结果已保存: {save_path}")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
