#!/usr/bin/env python3
"""
黄金网格策略回测 — 完整可独立运行版本
无需 akshare/pandas/matplotlib，仅需 numpy
"""
import os, math

# ── numpy 可用性 ─────────────────────────────────────
try:
    import numpy as np
except ImportError:
    print("❌ 需要 numpy: pip install numpy")
    raise SystemExit(1)

try:
    import pandas as pd
    HAS_PD = True
except ImportError:
    HAS_PD = False
    pd = None

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    plt = None

# ── 参数 ──────────────────────────────────────────────
INITIAL_CASH   = 1_000_000
GRID_COUNT     = 10
RISK_FREE_RATE = 0.03       # 无风险利率（年化，用于夏普比）
POSITION_SIZE  = 1          # 每格1手（1手=1000克）
COMMISSION     = 0.0003     # 手续费双边 0.03%

np.random.seed(42)
print(f"  numpy ✅  |  pandas {'✅' if HAS_PD else '❌'}  |  matplotlib {'✅' if HAS_MPL else '❌'}")
print("⚠️  使用合成数据演示（2022-01-03 → 2024-12-31）")

# ── 1. 生成合成黄金数据 ────────────────────────────────
# 模拟黄金期货走势：随机游走 + 轻微趋势
n = 252 * 3 + 5          # ~3年交易日
raw = np.random.randn(n) * 1.5
trend = np.linspace(0, 8, n)  # 轻微长期上涨趋势
noise = np.cumsum(raw + 0.01) + trend
prices = 380 + noise

# 生成 OHLC
opens  = prices * (1 + np.random.randn(n) * 0.002)
highs  = np.maximum(prices, opens) * (1 + np.abs(np.random.randn(n)) * 0.003)
lows   = np.minimum(prices, opens) * (1 - np.abs(np.random.randn(n)) * 0.003)

# 生成交易日序列
if HAS_PD:
    all_dates = pd.date_range("2022-01-01", "2024-12-31", freq="B")
    dates = all_dates[:n]
else:
    dates = list(range(n))

print(f"\n📊 数据: {len(prices)} 个交易日")
print(f"  价格区间: ¥{prices.min():.2f} ~ ¥{prices.max():.2f}")

# ── 2. 网格设置 ───────────────────────────────────────
min_p = prices.min()
max_p = prices.max()
grid_step = (max_p - min_p) / GRID_COUNT
grid_levels = [min_p + i * grid_step for i in range(GRID_COUNT + 1)]
entry_price = float(prices[0])

print(f"\n📐 网格参数")
print(f"  入场价:   ¥{entry_price:.2f}")
print(f"  最高价:   ¥{max_p:.2f}")
print(f"  最低价:   ¥{min_p:.2f}")
print(f"  网格间距: ¥{grid_step:.2f} / {GRID_COUNT}格")
print(f"  每手:     {POSITION_SIZE} 手 = {POSITION_SIZE*1000}克")

# ── 3. 回测引擎（修复：方向感知，避免同日买卖对冲）───────
# 策略：
#   买入信号：前一日收 <= 网格价 AND 当日低价 <= 网格价（价格上穿/触及网格）
#   卖出信号：前一日收 >= 网格价 AND 当日高价 >= 网格价（价格下穿/触及网格）
#   仅网格区间内有效

cash = float(INITIAL_CASH)
lots = {l: 0 for l in grid_levels}    # 持仓手数
trades = []

prev = float(prices[0])
for i in range(n):
    o, h, l, c = float(opens[i]), float(highs[i]), float(lows[i]), float(prices[i])

    for lvl in grid_levels:
        bought = lots[lvl]

        # 买入：价格从下方触及网格，且未持仓
        if not bought and l <= lvl <= h and prev <= lvl:
            cost = lvl * 1000 * POSITION_SIZE
            fee  = cost * COMMISSION
            if cash >= cost + fee:
                lots[lvl] = POSITION_SIZE
                cash -= (cost + fee)
                trades.append({"i": i, "a": "BUY",  "p": lvl, "f": fee})

        # 卖出：价格从上方触及网格，且有持仓
        elif bought and l <= lvl <= h and prev >= lvl:
            rev   = lvl * 1000 * bought
            fee   = rev * COMMISSION
            cash += (rev - fee)
            lots[lvl] = 0
            trades.append({"i": i, "a": "SELL", "p": lvl, "f": fee})

    prev = c

# ── 4. Equity 曲线（重新逐日模拟，记录每日净值）──────────
eq_curve = []
cash4 = float(INITIAL_CASH)
lots4 = {l: 0 for l in grid_levels}
prev4 = float(prices[0])

for i in range(n):
    o, h, l, c = float(opens[i]), float(highs[i]), float(lows[i]), float(prices[i])

    for lvl in grid_levels:
        if not lots4[lvl] and l <= lvl <= h and prev4 <= lvl:
            cost = lvl * 1000 * POSITION_SIZE
            fee  = cost * COMMISSION
            if cash4 >= cost + fee:
                lots4[lvl] = POSITION_SIZE
                cash4 -= (cost + fee)

        elif lots4[lvl] and l <= lvl <= h and prev4 >= lvl:
            rev   = lvl * 1000 * lots4[lvl]
            fee   = rev * COMMISSION
            cash4 += (rev - fee)
            lots4[lvl] = 0

    prev4 = c
    # 盘中持仓按收盘价估值
    pos_val = sum(lvl * 1000 * q for lvl, q in lots4.items())
    eq_curve.append(cash4 + pos_val)

eq_arr   = np.array(eq_curve, dtype=float)
n_days   = len(eq_arr)
years    = n_days / 252

# ── 5. 统计指标 ────────────────────────────────────────
total_ret   = (eq_arr[-1] / INITIAL_CASH - 1) * 100
ann_ret     = ((eq_arr[-1] / INITIAL_CASH) ** (1 / years) - 1) * 100 if years > 0 else 0

# 最大回撤
peak       = np.maximum.accumulate(eq_arr)
dd_arr     = (peak - eq_arr) / peak
max_dd     = dd_arr.max() * 100
max_dd_day = int(np.argmax(dd_arr))

# 夏普比（日收益，年化）
daily_ret  = np.diff(eq_arr) / eq_arr[:-1]
sharpe     = ((daily_ret.mean() - RISK_FREE_RATE/252) / daily_ret.std() * math.sqrt(252)) if daily_ret.std() > 0 else 0

buy_t  = [t for t in trades if t["a"] == "BUY"]
sell_t = [t for t in trades if t["a"] == "SELL"]
total_fees = sum(t["f"] for t in trades)

# 平仓收益（所有持仓按最终收盘价平仓）
final_close = float(prices[-1])
close_pnl   = sum(lvl * 1000 * q for lvl, q in lots4.items())
final_equity = cash4 + close_pnl - close_pnl * COMMISSION

print(f"\n{'='*50}")
print(f"  📈 黄金网格策略回测报告")
print(f"{'='*50}")
print(f"  数据范围:  2022-01-03 → 2024-12-31")
print(f"  初始资金:  ¥{INITIAL_CASH:,.0f}")
print(f"  期末资产:  ¥{eq_arr[-1]:,.0f}（盘中持仓按收盘价估值）")
print(f"  平仓资产:  ¥{final_equity:,.0f}（最终收盘价平仓）")
print(f"  总收益率:   {total_ret:+.2f}%")
print(f"  年化收益率: {ann_ret:+.2f}%")
print(f"  最大回撤:   {max_dd:.2f}%  (第{max_dd_day}个交易日)")
print(f"  夏普比率:   {sharpe:.2f}")
print(f"  买入次数:   {len(buy_t)} 次")
print(f"  卖出次数:  {len(sell_t)} 次")
print(f"  总交易次数: {len(trades)} 次")
print(f"  手续费合计: ¥{total_fees:,.2f}")
print(f"  剩余持仓:  {sum(q for q in lots4.values())} 手")
print(f"{'='*50}")

# ── 6. 生成图表 ────────────────────────────────────────
results_dir = os.path.join(os.path.dirname(__file__), "..", "results")
os.makedirs(results_dir, exist_ok=True)

date_arr = dates if HAS_PD else None

if HAS_MPL:
    print("\n🎨 生成图表（matplotlib）...")
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), facecolor="#0d1117")
    fig.suptitle("黄金网格策略回测 | 2022–2024", color="white",
                 fontsize=14, fontweight="bold", y=0.98)
    C = {"bg":"#0d1117","grid":"#21262d","cyan":"#58a6ff",
         "green":"#3fb950","red":"#f85149","yellow":"#d29922",
         "text":"#e6edf3","dim":"#7d8590"}
    for ax in axes:
        ax.set_facecolor(C["bg"])
        ax.tick_params(colors=C["dim"])
        ax.title.set_color(C["text"])
        ax.grid(True, color=C["grid"], lw=0.5)

    dr = pd.date_range("2022-01-01","2024-12-31",freq="B")[:n]

    # 图1：价格 + 网格
    ax1 = axes[0]
    ax1.plot(dr, prices, color=C["cyan"], lw=1.2, label="收盘价")
    for lvl in grid_levels:
        ax1.axhline(lvl, color=C["yellow"], lw=0.6, ls="--", alpha=0.5)
    ax1.axhline(entry_price, color=C["green"], lw=1.2, label=f"入场 ¥{entry_price:.0f}")
    ax1.set_ylabel("¥/克", color=C["dim"])
    ax1.legend(facecolor=C["bg"], edgecolor=C["grid"], labelcolor=C["text"], fontsize=8)
    ax1.set_title("黄金期货 AU 日线 + 网格", color=C["text"])
    for t in trades[:30]:
        col = C["green"] if t["a"]=="BUY" else C["red"]
        ax1.scatter(dr[t["i"]], t["p"], color=col, marker=["^","v"][t["a"]=="SELL"], s=30, zorder=5)

    # 图2：净值曲线
    ax2 = axes[1]
    ax2.fill_between(dr, eq_arr, INITIAL_CASH, where=eq_arr>=INITIAL_CASH,
                     color=C["green"], alpha=0.25, label="盈利")
    ax2.fill_between(dr, eq_arr, INITIAL_CASH, where=eq_arr<INITIAL_CASH,
                     color=C["red"], alpha=0.25, label="亏损")
    ax2.plot(dr, eq_arr, color=C["cyan"], lw=1.5, label="净值")
    ax2.axhline(INITIAL_CASH, color=C["dim"], lw=1, ls="--", alpha=0.6)
    ax2.set_ylabel("¥", color=C["dim"])
    ax2.legend(facecolor=C["bg"], edgecolor=C["grid"], labelcolor=C["text"], fontsize=8)
    ax2.set_title("账户净值曲线", color=C["text"])

    # 图3：回撤
    ax3 = axes[2]
    ax3.fill_between(dr, dd_arr*100, color=C["red"], alpha=0.4, label="回撤")
    ax3.plot(dr, dd_arr*100, color=C["red"], lw=1)
    ax3.set_ylabel("%", color=C["red"])
    ax3.set_title(f"回撤（最大 {max_dd:.1f}%）", color=C["text"])
    ax3.set_xlabel("日期", color=C["dim"])

    for ax in axes:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", color=C["dim"])

    plt.tight_layout(rect=[0,0,1,0.96])
    out_png = os.path.join(results_dir, "gold_grid_backtest.png")
    plt.savefig(out_png, dpi=150, facecolor=C["bg"], bbox_inches="tight")
    plt.close()
    print(f"  ✅ PNG → {out_png}")

else:
    # ── 无 matplotlib：用 PIL 生成 PNG ─────────────────
    try:
        from PIL import Image, ImageDraw, ImageFont
        HAS_PIL = True
    except ImportError:
        HAS_PIL = False

    print("\n🎨 生成图表（HTML+SVG）...")

    # SVG 版本（跨平台，无需依赖）
    step = max(1, n // 600)
    si   = list(range(0, n, step))
    s_dates = [str(dates[i])[:10] if not isinstance(dates[i], int) else f"D{i}" for i in si]
    s_close  = [float(prices[i]) for i in si]
    s_eq     = [float(eq_arr[i]) for i in si]
    s_dd     = [float(dd_arr[i]*100) for i in si]

    def poly_path(vals, vmin, vmax, W, H):
        pts = []
        for i, v in enumerate(vals):
            x = i / max(len(vals)-1, 1) * W
            y = H - (v - vmin) / max(vmax - vmin, 1e-9) * H
            pts.append(f"{x:.1f},{y:.1f}")
        return "M " + " L ".join(pts)

    def poly_fill(vals, vmin, vmax, W, H, baseline=None):
        pts = []
        for i, v in enumerate(vals):
            x = i / max(len(vals)-1, 1) * W
            y = H - (v - vmin) / max(vmax - vmin, 1e-9) * H
            pts.append(f"{x:.1f},{y:.1f}")
        bl = baseline if baseline is not None else H
        return f"M {pts[0]} L " + " L ".join(pts[1:]) + f" L {pts[-1].split(',')[0]},{bl:.1f} Z"

    W, H = 900, 200
    C2 = {"cyan":"#58a6ff","green":"#3fb950","red":"#f85149",
          "yellow":"#d29922","gray":"#7d8590","white":"#e6edf3","bg":"#0d1117","bg2":"#161b22"}

    def grid_lines(vmin, vmax, H, color="#21262d"):
        lines = []
        for i in range(5):
            y = H * i / 4
            lines.append(f'<line x1="0" y1="{y:.0f}" x2="{W}" y2="{y:.0f}" stroke="{color}" stroke-width="0.5"/>')
        return "\n    ".join(lines)

    svg_charts = []

    # Chart 1: price
    p_min, p_max = min(s_close), max(s_close)
    svg_charts.append(f"""
    <div class="chart">
      <h2>📈 黄金收盘价 + 网格线（¥/克）</h2>
      <div class="legend"><span style="color:{C2['cyan']}">● 收盘价</span><span style="color:{C2['yellow']}">- - 网格线</span><span style="color:{C2['green']}">— 入场价</span></div>
      <svg width="{W+20}" height="{H+40}">
        <rect width="{W+20}" height="{H+40}" fill="{C2['bg']}"/>
        {grid_lines(p_min, p_max, H)}
        <polyline points="{poly_path(s_close, p_min, p_max, W, H)}" fill="none" stroke="#58a6ff" stroke-width="1.5"/>
        {''.join('<line x1="0" y1="' + str(int(H-(lv-p_min)/max(p_max-p_min,1)*H)) + '" x2="' + str(W) + '" y2="' + str(int(H-(lv-p_min)/max(p_max-p_min,1)*H)) + '" stroke="#d29922" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.6"/>' for lv in grid_levels)}
        <line x1="0" y1="''' + str(int(H-(entry_price-p_min)/max(p_max-p_min,1)*H)) + '''" x2="''' + str(W) + '''" y2="''' + str(int(H-(entry_price-p_min)/max(p_max-p_min,1)*H)) + '''" stroke="#3fb950" stroke-width="1.2"/>
        <text x="5" y="15" fill="#7d8590" font-size="10">¥''' + f'{p_max:.0f}' + '''</text>
        <text x="5" y="''' + str(H-2) + '''" fill="#7d8590" font-size="10">¥''' + f'{p_min:.0f}' + '''</text>
      </svg>
    </div>""")

    # Chart 2: equity
    e_min, e_max = min(s_eq)*0.999, max(s_eq)*1.001
    svg_charts.append(f"""
    <div class="chart">
      <h2>💰 账户净值（¥）</h2>
      <div class="legend"><span style="color:{C2['green']}">■ 盈利</span><span style="color:{C2['red']}">■ 亏损</span><span style="color:{C2['cyan']}">● 净值</span></div>
      <svg width="{W+20}" height="{H+40}">
        <rect width="{W+20}" height="{H+40}" fill="{C2['bg']}"/>
        {grid_lines(e_min, e_max, H)}
        <path d="{poly_fill([max(v,INITIAL_CASH) for v in s_eq], e_min, e_max, W, H)}" fill="{C2['green']}" opacity="0.2"/>
        <path d="{poly_fill([min(v,INITIAL_CASH) for v in s_eq], e_min, e_max, W, H)}" fill="{C2['red']}" opacity="0.2"/>
        <polyline points="{poly_path(s_eq, e_min, e_max, W, H)}" fill="none" stroke="{C2['cyan']}" stroke-width="1.5"/>
        <line x1="0" y1="{H-(INITIAL_CASH-e_min)/max(e_max-e_min,1)*H:.0f}" x2="{W}" y2="{H-(INITIAL_CASH-e_min)/max(e_max-e_min,1)*H:.0f}" stroke="{C2['gray']}" stroke-width="1" stroke-dasharray="4,2"/>
      </svg>
    </div>""")

    # Chart 3: drawdown
    d_max = max(s_dd) + 1
    svg_charts.append(f"""
    <div class="chart">
      <h2>📉 回撤（%，最大 {max_dd:.1f}%）</h2>
      <svg width="{W+20}" height="{H+40}">
        <rect width="{W+20}" height="{H+40}" fill="{C2['bg']}"/>
        <polyline points="{poly_path(s_dd, 0, d_max, W, H)}" fill="{C2['red']}" opacity="0.3" stroke="{C2['red']}" stroke-width="1"/>
      </svg>
    </div>""")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>黄金网格策略回测</title>
<style>
body{{background:{C2['bg']};color:{C2['white']};font-family:sans-serif;margin:0;padding:20px}}
h1{{color:{C2['white']};font-size:18px;margin-bottom:16px}}
.kpi{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px}}
.kpi div{{background:{C2['bg2']};border:1px solid #21262d;border-radius:6px;padding:14px;text-align:center}}
.kpi .v{{font-size:22px;font-weight:bold;color:{C2['cyan']}}}
.kpi .l{{font-size:11px;color:{C2['gray']};margin-top:4px}}
.chart{{background:{C2['bg2']};border:1px solid #21262d;border-radius:8px;padding:12px;margin-bottom:14px}}
.chart h2{{color:{C2['white']};font-size:13px;margin:0 0 8px 0}}
.legend{{display:flex;gap:16px;font-size:11px;margin-bottom:6px;color:{C2['gray']}}}
table{{width:100%;border-collapse:collapse;margin-top:12px;font-size:12px}}
th,td{{padding:6px 10px;border-bottom:1px solid #21262d;text-align:left;color:{C2['gray']}}}
th{{color:{C2['cyan']}}}
.footer{{margin-top:16px;font-size:11px;color:{C2['gray']}}}
</style></head>
<body>
<h1>🥇 黄金网格策略回测 | 2022–2024（合成数据）</h1>

<div class="kpi">
  <div><div class="v">{total_ret:+.1f}%</div><div class="l">总收益率</div></div>
  <div><div class="v">{ann_ret:+.1f}%</div><div class="l">年化收益率</div></div>
  <div><div class="v">{max_dd:.1f}%</div><div class="l">最大回撤</div></div>
  <div><div class="v">{sharpe:.2f}</div><div class="l">夏普比率</div></div>
</div>

{"".join(svg_charts)}

<div class="chart">
  <h2>📋 交易记录（前20笔）</h2>
  <table>
    <tr><th>日期</th><th>方向</th><th>价格(¥)</th><th>手续费(¥)</th></tr>
    {''.join(f'<tr><td>{str(dates[t["i"]])[:10]}</td><td style="color:{"#3fb950" if t["a"]=="BUY" else "#f85149"}">{t["a"]}</td><td>{t["p"]:.2f}</td><td>{t["f"]:.2f}</td></tr>' for t in trades[:20])}
  </table>
</div>

<div class="footer">初始资金 ¥1,000,000 | 网格数量 {GRID_COUNT} | 每格1手(1000克) | 手续费双边{COMMISSION*100:.2f}%</div>
</body></html>"""

    out_html = os.path.join(results_dir, "gold_grid_backtest.html")
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✅ HTML → {out_html}")

    # 尝试 PIL
    if HAS_PIL:
        try:
            print("  🎨 用 PIL 生成 PNG...")
            W2, H2 = 920, 260
            bg   = (13, 17, 23)
            cyan = (88, 166, 255)
            green= (63, 185, 80)
            red  = (248, 81, 73)
            yellow=(210, 153, 34)
            gray = (125, 133, 144)
            white= (230, 237, 243)
            grid_c=(33, 38, 45)

            img = Image.new("RGB", (W2, 720), bg)
            d   = ImageDraw.Draw(img)

            def fnt(size=11):
                try: return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
                except: return ImageFont.load_default()

            def draw_poly(draw, pts, fill=None, outline=None, width=1):
                for i in range(len(pts)-1):
                    draw.line([pts[i], pts[i+1]], fill=outline or fill, width=width)

            def chart_region(draw, y0, chart_h, vals, vmin, vmax, line_col, fill_col=None, hline_val=None, hline_col=None):
                pts = []
                for i, v in enumerate(vals):
                    x = int(i / max(len(vals)-1, 1) * W2)
                    y = int(y0 + chart_h - (v - vmin) / max(vmax - vmin, 1e-9) * chart_h)
                    pts.append((x, y))
                for i in range(len(pts)-1):
                    draw.line([pts[i], pts[i+1]], fill=line_col, width=1)
                if fill_col:
                    bl = y0 + chart_h
                    poly = pts + [(pts[-1][0], bl), (pts[0][0], bl)]
                    draw.polygon(poly, fill=fill_col)
                if hline_val is not None:
                    hy = int(y0 + chart_h - (hline_val - vmin) / max(vmax - vmin, 1e-9) * chart_h)
                    draw.line([(0, hy), (W2, hy)], fill=hline_col or gray, width=1)
                return pts

            # Title
            draw_text = lambda draw, xy, txt, fill=white, sz=13: draw.text(xy, txt, fill=fill, font=fnt(sz))
            draw_text(draw, (10,8),  "Gold Grid Strategy Backtest | 2022-2024", white, 14)

            # KPI row
            kpis = [(f"{total_ret:+.1f}%","Total Return"),(f"{ann_ret:+.1f}%","Annual"),(f"{max_dd:.1f}%","Max DD"),(f"{sharpe:.2f}","Sharpe")]
            for ki, (val, lbl) in enumerate(kpis):
                x = 10 + ki * 232
                draw.rectangle([x, 35, x+215, 78], fill=(22,27,34), outline=grid_c)
                draw.text((x+108, 43), val, fill=cyan, font=fnt(18))
                draw.text((x+108, 64), lbl, fill=gray, font=fnt(10))

            # Chart 1: price
            draw_text(draw, (10, 88), "Gold Price (CNY/g) + Grid Lines", white, 12)
            s2 = max(1, n//W2)
            pc = [float(prices[i]) for i in range(0, n, s2)]
            pts = chart_region(draw, 112, 150, pc, float(min_p), float(max_p), cyan)
            for lvl in grid_levels:
                ly = int(112 + 150 - (lvl-min_p)/(max_p-min_p+1e-9)*150)
                draw.line([(0,ly),(W2,ly)], fill=yellow, width=0)
            epy = int(112 + 150 - (entry_price-min_p)/(max_p-min_p+1e-9)*150)
            draw.line([(0,epy),(W2,epy)], fill=green, width=1)

            # Chart 2: equity
            draw_text(draw, (10, 275), "Account Equity (CNY)", white, 12)
            pe = [float(eq_arr[i]) for i in range(0, n, s2)]
            e_min2, e_max2 = min(pe)*0.999, max(pe)*1.001
            chart_region(draw, 300, 150, pe, e_min2, e_max2, cyan, fill_col=(63,185,80,50))
            heqy = int(300 + 150 - (INITIAL_CASH-e_min2)/(e_max2-e_min2+1e-9)*150)
            draw.line([(0,heqy),(W2,heqy)], fill=gray, width=1, dashed=[4,2])

            # Chart 3: drawdown
            draw_text(draw, (10, 463), f"Drawdown (Max {max_dd:.1f}%)", white, 12)
            pd2 = [float(dd_arr[i]*100) for i in range(0, n, s2)]
            dmx = max(pd2)+1
            chart_region(draw, 488, 150, pd2, 0, dmx, red, fill_col=(248,81,73,40))

            # Footer
            draw_text(draw, (10, 648), f"Synthetic data | {len(trades)} trades | Fee: ¥{total_fees:.2f} | Grid: {GRID_COUNT} levels", gray, 10)

            out_pil = os.path.join(results_dir, "gold_grid_backtest.png")
            img.save(out_pil)
            print(f"  ✅ PNG → {out_pil}")
        except Exception as e:
            print(f"  ⚠️  PIL 失败: {e}")

# ── 6b. 纯 Python PNG 图表（无需 matplotlib/PIL）─────────
def make_png_chart(eq_arr, prices, grid_levels, entry_price,
                   dd_arr, max_dd, results_dir):
    import struct, zlib

    def write_png(pixels, fp):
        h, w = len(pixels), len(pixels[0])
        def chunk(cid, data):
            c = cid + data
            return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        sig = b'\x89PNG\r\n\x1a\n'
        ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
        raw = b''
        for row in pixels:
            raw += b'\x00' + b''.join(struct.pack('BBB', *px) for px in row)
        encoded = zlib.compress(raw, 6)
        with open(fp, 'wb') as f:
            f.write(sig)
            f.write(chunk(b'IHDR', ihdr))
            f.write(chunk(b'IDAT', encoded))
            f.write(chunk(b'IEND', b''))

    def px(x, y, w, h, x0, y0, x1, y1, x_val, vmin, vmax):
        """Map data coords to pixel coords, clipped to chart region."""
        nx = (x_val - x0) / max(x1 - x0, 1e-9)
        ny = 1 - (y_val - vmin) / max(y1 - vmin, 1e-9)
        return (int(nx * (w-1)), int(ny * (h-1)))

    W, H = 920, 760
    BG   = (13, 17, 23)
    CYAN = (88, 166, 255)
    GREEN= (63, 185, 80)
    RED  = (248, 81, 73)
    YEL  = (210, 153, 34)
    GRAY = (125, 133, 144)
    WHITE= (230, 237, 243)
    GRID = (33, 38, 45)
    BG2  = (22, 27, 34)

    # Init canvas
    canvas = [[BG for _ in range(W)] for _ in range(H)]

    def setpx(x, y, color):
        if 0 <= x < W and 0 <= y < H:
            canvas[y][x] = color

    def hline(y, color, x0=0, x1=W):
        for x in range(x0, min(x1, W)):
            canvas[y][x] = color

    def vline(x, color, y0=0, y1=H):
        for y in range(y0, min(y1, H)):
            canvas[y][x] = color

    def draw_text(x, y, text, color, size=10):
        """Very simple 5x7 pixel font for digits and letters."""
        font = {
            '0':[(0,1,1,0),(1,0,0,1),(1,0,0,1),(1,0,0,1),(0,1,1,0)],
            '1':[(0,1,0,0),(1,1,0,0),(0,1,0,0),(0,1,0,0),(1,1,1,0)],
            '2':[(0,1,1,0),(1,0,0,1),(0,0,1,0),(0,1,0,0),(1,1,1,0)],
            '3':[(1,1,1,0),(0,0,1,0),(0,1,1,0),(0,0,1,0),(1,1,1,0)],
            '4':[(1,0,1,0),(1,0,1,0),(1,1,1,0),(0,0,1,0),(0,0,1,0)],
            '5':[(1,1,1,0),(1,0,0,0),(1,1,1,0),(0,0,0,1),(1,1,1,0)],
            '6':[(0,1,1,0),(1,0,0,0),(1,1,1,0),(1,0,0,1),(0,1,1,0)],
            '7':[(1,1,1,0),(0,0,0,1),(0,0,1,0),(0,1,0,0),(0,1,0,0)],
            '8':[(0,1,1,0),(1,0,0,1),(0,1,1,0),(1,0,0,1),(0,1,1,0)],
            '9':[(0,1,1,0),(1,0,0,1),(0,1,1,1),(0,0,0,1),(0,1,1,0)],
            '+':[(0,0,0,0),(0,1,0,0),(1,1,1,0),(0,1,0,0),(0,0,0,0)],
            '-':[(0,0,0,0),(0,0,0,0),(1,1,1,0),(0,0,0,0),(0,0,0,0)],
            '%':[(1,0,1,0),(0,1,0,0),(0,1,0,0),(0,0,1,0),(1,0,1,0)],
            '.':[(0,0,0,0),(0,0,0,0),(0,0,0,0),(0,0,0,0),(0,1,0,0)],
            '¥':[(0,1,0,0),(1,1,1,0),(0,1,0,0),(0,1,0,0),(0,1,0,0)],
            ':':[(0,0,0,0),(0,1,0,0),(0,0,0,0),(0,1,0,0),(0,0,0,0)],
            'K':[(1,0,0,1),(1,0,1,0),(1,1,0,0),(1,0,1,0),(1,0,0,1)],
            'M':[(1,1,1,1,1),(1,0,0,0,1),(1,0,0,0,1),(1,0,0,0,1),(1,0,0,0,1)],
            'D':[(1,1,1,0),(1,0,0,1),(1,0,0,1),(1,0,0,1),(1,1,1,0)],
            'G':[(0,1,1,1,0),(1,0,0,0,1),(1,0,1,0,1),(1,0,0,1,1),(0,1,1,0,1)],
            'r':[(0,0,0,0),(1,1,0,0),(1,0,1,0),(1,0,0,0),(1,0,0,0)],
            'e':[(0,1,1,0),(1,0,0,1),(1,1,1,1),(1,0,0,0),(0,1,1,1)],
            't':[(0,1,0,0),(1,1,1,0),(0,1,0,0),(0,1,0,0),(0,0,1,0)],
            'n':[(0,0,0,0),(1,1,0,0),(1,0,1,0),(1,0,0,1),(1,0,0,1)],
            's':[(0,1,1,1),(1,0,0,0),(0,1,0,0),(0,0,1,0),(1,1,1,0)],
            'a':[(0,0,0,0),(0,1,1,0),(0,0,0,1),(0,1,1,1),(1,0,0,1)],
            'p':[(0,0,0,0),(1,1,0,0),(1,0,0,1),(1,1,0,0),(1,0,0,0)],
            'x':[(0,0,0,0),(1,0,1,0),(0,1,0,0),(1,0,1,0),(0,0,0,0)],
            'i':[(0,1,0,0),(0,0,0,0),(0,1,0,0),(0,1,0,0),(0,1,0,0)],
            'o':[(0,1,1,0),(1,0,0,1),(1,0,0,1),(1,0,0,1),(0,1,1,0)],
            'l':[(0,1,0,0),(0,1,0,0),(0,1,0,0),(0,1,0,0),(0,1,1,0)],
            ' ':[(0,0,0,0),(0,0,0,0),(0,0,0,0),(0,0,0,0),(0,0,0,0)],
            '/':[(0,0,0,0,0),(0,0,0,0,1),(0,0,0,1,0),(0,0,1,0,0),(0,1,0,0,0)],
            'R':[(1,1,1,0,0),(1,0,0,1,0),(1,1,1,0,0),(1,0,1,0,0),(1,0,0,1,0)],
            'A':[(0,1,1,0,0),(1,0,0,1,0),(1,1,1,1,0),(1,0,0,1,0),(1,0,0,1,0)],
            'P':[(1,1,1,0,0),(1,0,0,1,0),(1,1,1,0,0),(1,0,0,0,0),(1,0,0,0,0)],
            'L':[(1,0,0,0,0),(1,0,0,0,0),(1,0,0,0,0),(1,0,0,0,0),(1,1,1,0,0)],
            'T':[(1,1,1,0,0),(0,1,0,0,0),(0,1,0,0,0),(0,1,0,0,0),(0,1,0,0,0)],
        }

        def render_char(ch, cx, cy, col, sz=1):
            g = font.get(ch, font[' '])
            for row in range(5):
                for col2 in range(len(g[row])):
                    if g[row][col2]:
                        for dy in range(sz):
                            for dx in range(sz):
                                setpx(cx + col2*sz + dx, cy + row*sz + dy, col)

        for i, ch in enumerate(text):
            render_char(ch, x + i * 6 * size // 10, y, color, size // 10 or 1)

    def fillrect(x0, y0, x1, y1, color):
        for y in range(max(0,y0), min(H,y1)):
            for x in range(max(0,x0), min(W,x1)):
                canvas[y][x] = color

    def plot_line(pts, color, width=1, anti=False):
        for i in range(len(pts)-1):
            x0,y0 = pts[i]; x1,y1 = pts[i+1]
            dx = x1-x0; dy = y1-y0
            steps = max(abs(dx), abs(dy), 1)
            for s in range(steps):
                t = s/steps
                x = int(x0 + dx*t); y = int(y0 + dy*t)
                for w in range(width):
                    setpx(x+w, y, color)

    def plot_poly(vals, x0, y0, x1, y1, vmin, vmax, color):
        pts = []
        for i, v in enumerate(vals):
            nx = i / max(len(vals)-1, 1)
            ny = 1 - (v - vmin) / max(vmax - vmin, 1e-9)
            pts.append((int(x0 + nx*(x1-x0)), int(y0 + ny*(y1-y0))))
        plot_line(pts, color, width=1)
        return pts

    # ---- Title ----
    draw_text(10, 12, "Gold Grid Strategy Backtest | 2022-2024", WHITE, 12)

    # ---- KPI boxes ----
    kpis = [
        (f"+{total_ret:.1f}%" if total_ret>=0 else f"{total_ret:.1f}%","Total Return"),
        (f"{ann_ret:+.1f}%","Annual"),
        (f"{max_dd:.1f}%","Max DD"),
        (f"{sharpe:.2f}","Sharpe"),
    ]
    for ki, (val, lbl) in enumerate(kpis):
        bx = 10 + ki*232
        fillrect(bx, 34, bx+218, 77, BG2)
        draw_text(bx+109-len(val)*3, 42, val, CYAN, 16)
        draw_text(bx+109-len(lbl)*3, 62, lbl, GRAY, 9)

    # ---- Chart 1: Price + grid ----
    draw_text(10, 88, "Gold Price (CNY/g) + Grid Lines", WHITE, 11)
    CX0, CY0, CW, CH = 50, 108, 860, 150
    fillrect(CX0-1, CY0-1, CX0+CW+1, CY0+CH+1, GRID)
    p_min_p = float(min(prices)); p_max_p = float(max(prices))
    for lvl in grid_levels:
        ly = int(CY0 + CH - (lvl-p_min_p)/max(p_max_p-p_min_p,1e-9)*CH)
        for x in range(CX0, CX0+CW):
            canvas[ly][x] = (80, 60, 30)
    s1 = max(1, n//CW)
    sp = [float(prices[i]) for i in range(0, n, s1)]
    plot_poly(sp, CX0, CY0, CX0+CW, CY0+CH, p_min_p, p_max_p, CYAN)
    epy2 = int(CY0 + CH - (entry_price-p_min_p)/max(p_max_p-p_min_p,1e-9)*CH)
    for x in range(CX0, CX0+CW): canvas[epy2][x] = GREEN
    draw_text(CX0+CW-40, CY0+2, f"{p_max_p:.0f}", GRAY, 8)
    draw_text(CX0+CW-40, CY0+CH-12, f"{p_min_p:.0f}", GRAY, 8)

    # ---- Chart 2: Equity ----
    draw_text(10, 270, "Account Equity (CNY)", WHITE, 11)
    CY0, CH = 290, 150
    fillrect(CX0-1, CY0-1, CX0+CW+1, CY0+CH+1, GRID)
    e_min2 = float(min(eq_arr))*0.999; e_max2 = float(max(eq_arr))*1.001
    s2 = max(1, n//CW)
    se = [float(eq_arr[i]) for i in range(0, n, s2)]
    # Fill above baseline
    for i in range(len(se)-1):
        nx = i / max(len(se)-1, 1)
        x0 = int(CX0 + nx*(CW-1))
        x1 = int(CX0 + (i+1)/max(len(se)-1, 1)*(CW-1))
        for x in range(x0, x1+1):
            t = (x-x0)/(x1-x0+1e-9)
            v = se[i]*(1-t) + se[i+1]*t
            y = int(CY0 + CH - (v-e_min2)/max(e_max2-e_min2,1e-9)*CH)
            if v >= INITIAL_CASH:
                for yy in range(y, CY0+CH): canvas[yy][x] = (40, 100, 50)
            else:
                for yy in range(CY0, y): canvas[yy][x] = (100, 30, 30)
    plot_poly(se, CX0, CY0, CX0+CW, CY0+CH, e_min2, e_max2, CYAN)
    heq = int(CY0 + CH - (INITIAL_CASH-e_min2)/max(e_max2-e_min2,1e-9)*CH)
    for x in range(CX0, CX0+CW): canvas[heq][x] = GRAY
    draw_text(CX0+CW-45, CY0+2, f"{e_max2:,.0f}", GRAY, 8)
    draw_text(CX0+CW-45, CY0+CH-12, f"{e_min2:,.0f}", GRAY, 8)

    # ---- Chart 3: Drawdown ----
    draw_text(10, 452, f"Drawdown (Max {max_dd:.1f}%)", WHITE, 11)
    CY0, CH = 472, 140
    fillrect(CX0-1, CY0-1, CX0+CW+1, CY0+CH+1, GRID)
    s3 = max(1, n//CW)
    sd = [float(dd_arr[i]*100) for i in range(0, n, s3)]
    dmx = max(sd)+1
    # Fill
    for i in range(len(sd)-1):
        nx0 = int(i / max(len(sd)-1, 1) * (CW-1))
        nx1 = int((i+1) / max(len(sd)-1, 1) * (CW-1))
        for x in range(nx0, nx1+1):
            t = (x-nx0)/(nx1-nx0+1e-9)
            v = sd[i]*(1-t) + sd[i+1]*t
            y = int(CY0 + CH - v/dmx*CH)
            for yy in range(y, CY0+CH):
                canvas[yy][CX0+x] = (80, 25, 25)
    plot_poly(sd, CX0, CY0, CX0+CW, CY0+CH, 0, dmx, RED)
    draw_text(CX0+CW-35, CY0+2, f"{dmx:.1f}%", GRAY, 8)
    draw_text(CX0+CW-35, CY0+CH-12, "0%", GRAY, 8)

    # ---- Footer ----
    draw_text(10, 648, f"Synthetic data | {len(trades)} trades | Fee: ¥{total_fees:.0f} | Grid: {GRID_COUNT} levels x 1 lot (1000g)", GRAY, 9)

    write_png(canvas, os.path.join(results_dir, "gold_grid_backtest.png"))
    print(f"  ✅ PNG → {os.path.join(results_dir, 'gold_grid_backtest.png')}")

make_png_chart(eq_arr, prices, grid_levels, entry_price, dd_arr, max_dd, results_dir)

# ── 7. 保存报告 ────────────────────────────────────────
report_path = os.path.join(results_dir, "gold_grid_report.txt")
with open(report_path, "w", encoding="utf-8") as f:
    f.write(f"黄金网格策略回测报告\n")
    f.write(f"{'='*50}\n")
    f.write(f"数据范围:  2022-01-03 → 2024-12-31 ({n_days} 交易日)\n")
    f.write(f"初始资金:  ¥{INITIAL_CASH:,.0f}\n")
    f.write(f"期末资产:  ¥{eq_arr[-1]:,.0f}\n")
    f.write(f"平仓资产:  ¥{final_equity:,.0f}\n")
    f.write(f"总收益率:  {total_ret:+.2f}%\n")
    f.write(f"年化收益率:{ann_ret:+.2f}%\n")
    f.write(f"最大回撤:  {max_dd:.2f}%\n")
    f.write(f"夏普比率:  {sharpe:.2f}\n")
    f.write(f"买入次数:  {len(buy_t)}\n")
    f.write(f"卖出次数: {len(sell_t)}\n")
    f.write(f"总交易次数: {len(trades)}\n")
    f.write(f"手续费合计: ¥{total_fees:,.2f}\n")
    f.write(f"\n网格参数:\n")
    f.write(f"  网格数量: {GRID_COUNT}\n")
    f.write(f"  网格间距: ¥{grid_step:.2f}\n")
    f.write(f"  入场价:   ¥{entry_price:.2f}\n")
    f.write(f"  手续费:   双边 {COMMISSION*100:.2f}%\n")
    f.write(f"\n交易记录（前30笔）:\n")
    f.write(f"{'日期':<14} {'方向':<6} {'价格(¥)':<10} {'手续费(¥)':<10}\n")
    for t in trades[:30]:
        d_str = str(dates[t["i"]])[:10] if not isinstance(dates[t["i"]], int) else f"Day{t['i']}"
        f.write(f"{d_str:<14} {t['a']:<6} {t['p']:<10.2f} {t['f']:<10.2f}\n")

print(f"\n  📄 报告 → {report_path}")
