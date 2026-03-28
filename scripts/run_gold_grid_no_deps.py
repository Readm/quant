"""
run_gold_grid_local.py
黄金网格策略回测（均值回归版）
均值回归网格：价格偏离格口→均值回复时平仓
"""
import random, math, os
from datetime import date, timedelta

INITIAL_CASH = 1_000_000
GRID_N       = 10          # 初始网格格数
GRID_PCT     = 0.08        # 每格占用 8% 资金
GRID_STEP_PCT = 0.015      # 每格间距 1.5%

# ── 合成数据 ─────────────────────────────────────────
print("📊 生成黄金合成数据（GBM，2022-01 至 2024-12）...")
random.seed(42)
d0 = date(2022, 1, 1)
d1 = date(2024, 12, 31)
p  = 380.0
mu, sigma = 0.0004, 0.008   # 轻微向上趋势
prices = []
while d0 <= d1:
    if d0.weekday() < 5:
        p *= math.exp(mu + sigma * random.gauss(0, 1))
        c = p
        prices.append(dict(
            date=d0,
            open=round(c*(1+random.uniform(-0.002, 0.002)), 2),
            high=round(c*(1+abs(random.gauss(0,0.002))), 2),
            low=round(c*(1-abs(random.gauss(0,0.002))), 2),
            close=round(c, 2),
        ))
    d0 += timedelta(days=1)

print(f"  {prices[0]['date']} → {prices[-1]['date']}，共 {len(prices)} 交易日")

# ── 建立初始网格 ───────────────────────────────────────
entry = prices[0]["close"]
step  = entry * GRID_STEP_PCT
GRID  = [round(entry + (i - GRID_N//2) * step, 2) for i in range(GRID_N + 1)]

print(f"\n📐 初始网格（{len(GRID)}格，间距{GRID_STEP_PCT*100:.1f}%）")
print(f"  入场价: ¥{entry:.2f}  区间: ¥{min(GRID):.2f}～¥{max(GRID):.2f}")

# ── 回测状态 ───────────────────────────────────────────
# holdings: {格口价格: 数量(克)}
# position_avg: 加权平均入场价
holdings, pos_avg = {}, 0.0
cash  = float(INITIAL_CASH)
trades, equity = [], []

def total_equity(c, holdings):
    return c + sum(q * c for q in holdings.values())

for row in prices:
    d, c, h, lo = row["date"], row["close"], row["high"], row["low"]

    # ── 核心网格逻辑 ─────────────────────────────────
    # 每个格口：偏离→回归触发一次
    triggered_sell = []

    for lvl in sorted(GRID):
        qty = holdings.get(lvl, 0)

        # 买入条件：价格跌穿格口（下轨），且无持仓
        if qty <= 0 and lo <= lvl <= h and cash >= lvl * 1000 * GRID_PCT:
            sz   = math.floor(cash * GRID_PCT / (lvl * 1000))
            if sz > 0:
                cost = sz * lvl * 1000
                cash -= cost
                holdings[lvl] = holdings.get(lvl, 0) + sz
                pos_avg = (pos_avg * (sum(holdings.values()) - sz) + lvl * sz) / max(sum(holdings.values()), 1)
                trades.append((d, "BUY", lvl, sz))

        # 卖出条件：价格反弹触及格口（上轨），且持有
        elif qty > 0 and lo <= lvl <= h and c >= lvl:
            proceeds = qty * lvl * 1000
            cash += proceeds
            trades.append((d, "SELL", lvl, qty))
            triggered_sell.append(lvl)

    for lvl in triggered_sell:
        holdings[lvl] = 0

    # 动态扩格（趋势突破时扩展网格上沿）
    if c > max(GRID):
        GRID.append(round(c + (len(GRID) % 3 + 1) * step, 2))
    if c < min(GRID):
        GRID.append(round(c - (len(GRID) % 3 + 1) * step, 2))

    # 权益记录
    eq = total_equity(c, holdings)
    equity.append(dict(date=d, equity=eq, cash=cash,
                       pos_g=sum(holdings.values()),
                       close=c))

# ── 统计 ──────────────────────────────────────────────
eq_v  = [e["equity"] for e in equity]
feq   = eq_v[-1]
tret  = (feq - INITIAL_CASH) / INITIAL_CASH * 100
yr    = len(prices) / 252
arex  = ((feq / INITIAL_CASH) ** (1 / yr) - 1) * 100 if yr > 0 else 0

peak, mxd = INITIAL_CASH, 0.0
for eq in eq_v:
    if eq > peak: peak = eq
    dd = (peak - eq) / peak
    if dd > mxd: mxd = dd

dre = [math.log(eq_v[i]/eq_v[i-1]) for i in range(1,len(eq_v)) if eq_v[i-1]>0]
mr   = sum(dre)/len(dre) if dre else 0
sr   = math.sqrt(sum((r-mr)**2 for r in dre)/len(dre)) if dre else 0
shrp = (mr/sr*math.sqrt(252)) if sr>0 else 0

buys  = [t for t in trades if t[1]=="BUY"]
sells = [t for t in trades if t[1]=="SELL"]

print(f"\n{'═'*52}")
print(f"  黄金网格策略回测报告  |  2022-01-03 → 2024-12-31")
print(f"{'═'*52}")
print(f"  初始资金:    ¥{INITIAL_CASH:>14,.0f}")
print(f"  期末资产:    ¥{feq:>14,.0f}")
print(f"  总收益率:    {tret:>+13.2f}%")
print(f"  年化收益率:  {arex:>+13.2f}%")
print(f"  最大回撤:    {mxd*100:>+13.2f}%")
print(f"  夏普比率:    {shrp:>+13.2f}")
print(f"  总交易次数:  {len(trades):>14}  笔")
print(f"  买入次数:   {len(buys):>14}  笔")
print(f"  卖出次数:   {len(sells):>14}  笔")
print(f"{'═'*52}")

# ── ASCII 权益曲线 ─────────────────────────────────────
print("\n📈 权益曲线（ASCII）")
W, H = 72, 14
ev   = eq_v[::max(1, len(eq_v)//400)]
mn, mx = min(ev), max(ev)
rng  = mx - mn if mx != mn else 1
canvas = [[" "] * W for _ in range(H)]
for i, v in enumerate(ev):
    col = min(int((i/(len(ev)-1))*(W-1)), W-1)
    row = max(0, min(H-1, H-1 - int((v-mn)/rng*(H-1))))
    for r in range(row, H):
        canvas[r][col] = "█"
    canvas[H-1][col] = "▄"

ym = [mx - i*(rng/(H-1)) for i in range(H)]
for r in range(H):
    lbl = f"{ym[r]:>9.0f}" if r%3==0 else " "*9
    print(lbl + "│" + "".join(canvas[r]))
print(" "*9 + "└" + "─"*W)
d_s, d_e = str(prices[0]["date"]), str(prices[-1]["date"])
print(" "*8 + d_s + " "*(W - 4 - len(d_s) - len(d_e)) + d_e)

# ── 交易记录 ───────────────────────────────────────────
print(f"\n📋 交易记录（前15笔）")
print(f"  {'日期':<12} {'方向':<5} {'格口':>8} {'数量(克)':>10}  {'金额':>12}")
print(f"  {'-'*52}")
for d, action, lvl, sz in trades[:15]:
    amt = sz * lvl * 1000
    print(f"  {str(d):<12} {action:<5} ¥{lvl:>8.2f}  {sz*1000:>10,}g  ¥{amt:>12,.0f}")
if len(trades) > 15:
    print(f"  ... 共 {len(trades)} 笔")

# ── 保存 ───────────────────────────────────────────────
os.makedirs("/workspace/quant/results", exist_ok=True)
csv_path = "/workspace/quant/results/gold_grid_equity.csv"
with open(csv_path, "w") as f:
    f.write("date,equity,cash,close\n")
    for e in equity:
        f.write(f"{e['date']},{e['equity']:.2f},{e['cash']:.2f},{e['close']:.2f}\n")
print(f"\n✅ equity CSV → {csv_path}")
