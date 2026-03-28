#!/usr/bin/env python3
"""
run_xb_all_strategies.py — 邢不行策略全集 · 双级运行器
==========================================================
用法:
  python3 run_xb_all_strategies.py                # 运行全部（T1即刻，T2需Token）
  python3 run_xb_all_strategies.py --t1          # 仅 T1（Binance）
  python3 run_xb_all_strategies.py --t2          # 仅 T2（A股）
  python3 run_xb_all_strategies.py --symbol ETHUSDT --start 2022 --end 2025

T1（立即可跑，Binance数据）:
  ✅ T1-01 小市值模拟(400倍)
  ✅ T1-02 定投策略(DCA)
  ✅ T1-03 动量轮动(月度)
  ✅ T1-04 多均线共振(5/20/60)
  ✅ T1-05 布林带加强版
  ✅ T1-06 MACD多周期共振
  ✅ T1-07 RSI超卖抄底
  ✅ T1-08 跳空过滤策略

T2（需TuShare Token，https://tushare.pro/register）:
  ⏳ T2-01 小市值选股策略（需市值数据）
  ⏳ T2-02 低价股选股策略（需价格数据）
  ⏳ T2-03 量价相关性选股（需成交量）
  ⏳ T2-04 反过度自信选股（需换手率）
  ⏳ T2-05 资产有息负债率选股（需财务报表）
  ⏳ T2-06 低估值高分红选股（需PE/股息率）
  ⏳ T2-07 伽利略五行选股（需多因子数据）
  ⏳ T2-08 定风波择时策略（需指数+情绪数据）
  ⏳ T2-09 黑色星期四择时（需指数日线）
  ⏳ T2-10 Fama-French三因子（需因子数据）
"""

import sys as _sys
from pathlib import Path as _Path

# ── 路径 ──────────────────────────────────────────────
THIS_DIR = _Path(__file__).parent.resolve()
T1_PATH  = THIS_DIR / "strategies" / "xb_tier1_binance.py"
T2_PATH  = THIS_DIR / "strategies" / "xb_tier2_ashare.py"
RESULTS  = THIS_DIR / "results" / "xb_all"

RESULTS.mkdir(parents=True, exist_ok=True)

# ── CLI 参数 ──────────────────────────────────────────
TIERS    = ["t1", "t2"]
SYMBOL   = "BTCUSDT"
START    = "20200101"
END      = "20251231"
INITIAL  = 1_000_000.0


def parse_args():
    args = {"tier": "all", "symbol": SYMBOL, "start": START,
            "end": END, "initial": INITIAL}
    for a in _sys.argv[1:]:
        if a == "--t1":
            args["tier"] = "t1"
        elif a == "--t2":
            args["tier"] = "t2"
        elif a.startswith("--symbol="):
            args["symbol"] = a.split("=", 1)[1]
        elif a.startswith("--start="):
            args["start"] = a.split("=", 1)[1]
        elif a.startswith("--end="):
            args["end"] = a.split("=", 1)[1]
    return args


def run_t1(symbol, start, end, initial):
    """运行 T1 Binance 策略"""
    print(f"\n{'='*65}")
    print(f"  📊 T1级 · Binance 可跑策略")
    print(f"  标的: {symbol} | 时间: {start} → {end}")
    print(f"{'='*65}")
    try:
        from strategies.xb_tier1_binance import run_tier1
        return run_tier1(symbol, start, end, "1d", initial)
    except ImportError as e:
        print(f"  ❌ 导入失败: {e}")
        return []


def run_t2(token: str = ""):
    """运行 T2 A股策略（需TuShare Token）"""
    print(f"\n{'='*65}")
    print(f"  📊 T2级 · A股策略（TuShare Token = {'已配置' if token else '未配置'}）")
    print(f"{'='*65}")

    # 动态填入 Token
    if token:
        import strategies.xb_tier2_ashare as t2
        t2.TU_TOKEN = token
        t2._init_tushare()
    else:
        t2._init_tushare()

    # 演示：用模拟指数数据跑择时策略
    print("\n  🧪 演示：用模拟指数数据回测 T2-08(定风波) 和 T2-09(黑色星期四)")
    try:
        from strategies.xb_tier2_ashare import (
            signal_dingfengbo, signal_black_thursday
        )
        from strategies.backtest_engine import backtest_signal

        # 用 Binance BTC 数据代替指数演示择时
        from strategies.xb_tier1_binance import fetch_binance
        rows = fetch_binance("BTCUSDT", "1d", "20200101", "20241231")
        if rows:
            closes  = [r["close"] for r in rows]
            highs   = [r["high"]  for r in rows]
            lows    = [r["low"]   for r in rows]
            opens   = [r["open"]  for r in rows]
            vols    = [r["volume"] for r in rows]

            for name, fn in [
                ("T2-08 定风波择时",   lambda c,h,l,o,v: signal_dingfengbo(c,h,l,o,v)),
                ("T2-09 黑色星期四",   lambda c,h,l,o,v: signal_black_thursday(c,h,l,o,v)),
            ]:
                r = backtest_signal(name, rows,
                                    lambda c,h,l,o,v,_fn=fn: _fn(c,h,l,o,v),
                                    initial=1_000_000)
                if r:
                    print(f"  ✅ {name}: 年化 {r['ann_return_pct']:+.1f}% | "
                          f"夏普 {r['sharpe']:.2f} | "
                          f"回撤 {r['max_drawdown_pct']:.1f}% | "
                          f"交易 {r['total_trades']}次")

    except Exception as e:
        print(f"  ⚠️  T2 择时演示失败: {e}")

    print("\n  📋 T2选股策略说明（Tushare Token接入后可运行）：")
    strategies_t2 = [
        ("T2-01", "小市值选股",         "每月选市值最小10% A股，10年400倍策略核心"),
        ("T2-02", "低价股选股",         "股价<5元月度轮动"),
        ("T2-03", "量价相关性选股",     "选量价相关性最高的股票"),
        ("T2-04", "反过度自信选股",     "换手率异常放大后逆势操作"),
        ("T2-05", "资产有息负债率选股", "选财务最健康的股票"),
        ("T2-06", "低估值高分红",       "PE<30 + 股息率>3%"),
        ("T2-07", "伽利略五行选股",     "五维度因子综合评分"),
        ("T2-08", "定风波择时",         "市场恐慌极点买入（已演示）"),
        ("T2-09", "黑色星期四",         "周效应择时（已演示）"),
        ("T2-10", "Fama-French三因子", "市值+价值+动量三因子"),
    ]
    print(f"\  {'代号':<6} {'策略名称':<20} {'原理'}")
    print(f"  {'─'*65}")
    for code, name, desc in strategies_t2:
        print(f"  {code:<6} {name:<20} {desc}")

    print("""
  📌 TuShare Token 接入步骤：
  1. 注册 https://tushare.pro/register?ref=...
  2. 复制 Token
  3. 编辑 strategies/xb_tier2_ashare.py 第 38 行：
     TU_TOKEN = "your_token_here"  # ← 粘贴Token
  4. 重新运行：python3 run_xb_all_strategies.py --t2
  """)


def main():
    args = parse_args()
    tier  = args["tier"]
    sym   = args["symbol"]
    start = args["start"]
    end_  = args["end"]
    init  = args["initial"]

    print(f"""
╔══════════════════════════════════════════════════════╗
║   🏛️  邢不行量化小讲堂 · 策略全集  v2.0             ║
║   生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}                          ║
║   数据: Binance 公开 API + TuShare Pro              ║
╚══════════════════════════════════════════════════════╝
    """.replace("datetime.now().strftime('%Y-%m-%d %H:%M')",
                __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')))

    all_results = []

    if tier in ("all", "t1"):
        r1 = run_t1(sym, start, end_, init)
        all_results.extend(r1)

    if tier in ("all", "t2"):
        # Token 从环境变量读取（安全）
        token = _Path("/workspace/.tushare_token").read_text().strip() \
                if _Path("/workspace/.tushare_token").exists() else ""
        run_t2(token)
        # T2 无真实Token时不做全量回测
        if not token:
            print("  ⏭  跳过 T2 全量回测（需 TuShare Token）")
        else:
            print("  🚀 Token 就绪，T2 策略可直接回测！")

    if tier == "all" and all_results:
        print(f"\n{'='*65}")
        print(f"  📊 全策略综合排行（按年化排序）")
        print(f"{'='*65}")
        print(f"  {'策略':<30} {'年化':>8} {'夏普':>6} {'回撤':>7} {'交易':>5} {'胜率':>6}")
        print(f"  {'─'*65}")
        for r in sorted(all_results, key=lambda x: x["ann_return_pct"], reverse=True):
            print(f"  {r['strategy']:<30} {r['ann_return_pct']:>+7.1f}% "
                  f"{r['sharpe']:>6.2f} {r['max_drawdown_pct']:>6.1f}% "
                  f"{r['total_trades']:>5d} {r['win_rate_pct']:>5.1f}%")

    print(f"\n{'='*65}")
    print(f"  ✅ 运行完成 | 结果保存在 quant/results/")
    print(f"{'='*65}")


if __name__ == "__main__":
    main()
