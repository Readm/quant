"""
config/markets.py — 市场配置
包含各市场交易时间、保证金系数、合约乘数等
"""

# ── A股（上海/深圳证券交易所）─────────────────────────────
STOCKS = {
    "name":      "A股",
    "timezone":  "Asia/Shanghai",
    "trading_hours": [
        # T日交易日时间段
        ("09:30", "11:30"),  # 上午盘
        ("13:00", "15:00"),  # 下午盘
    ],
    "exercise_hours": [
        # 日内择时（提前30分钟检查信号）
        ("14:50", "15:00"),
    ],
    "settlement":     "T+1",      # 当日买入，次日才能卖出
    "tick_size":      0.01,       # 最小价格变动（元）
    "commission":     0.0008,     # 印花税（卖）+ 佣金（双向）
    "stamp_duty":     0.001,      # 印花税仅卖出收取
    "max_up":         0.10,       # 涨停幅度 10%（ST 5%）
    "max_down":       0.10,       # 跌停幅度 10%
}

# ── 加密货币（Binance 现货）─────────────────────────────
CRYPTO = {
    "name":       "加密货币",
    "exchange":   "binance",
    "timezone":   "UTC",
    "trading_hours": [
        # 无休市，全天可交易
        ("00:00", "23:59"),
    ],
    "settlement": "T+0",          # 随时买卖
    "symbols": {
        # 可交易标的配置
        "BTCUSDT": {"name": "Bitcoin",   "vol_target": 0.30},
        "ETHUSDT": {"name": "Ethereum",  "vol_target": 0.25},
        "BNBUSDT": {"name": "BNB",        "vol_target": 0.15},
        "SOLUSDT": {"name": "Solana",     "vol_target": 0.20},
    },
    "leverage":   1.0,            # 不加杠杆
    "maker_fee":  0.0010,        # Binance 现货 Maker 0.1%
    "taker_fee":  0.0010,        # Taker 0.1%
}

# ── 国内期货（商品期货）────────────────────────────────
FUTURES = {
    "name":       "商品期货",
    "timezone":   "Asia/Shanghai",
    "trading_hours": [
        # 日盘
        ("09:00",  "10:15"),
        ("10:30",  "11:30"),
        ("13:30",  "15:00"),
        # 夜盘（次日）
        ("21:00",  "23:00"),   # 黄金、白银、原油等
    ],
    "settlement": "T+0",
    "instruments": {
        # 合约乘数 × 保证金比例（实数，可动态调整）
        "IF": {"name": "沪深300股指",  "multiplier": 300,  "margin_rate": 0.12},
        "IC": {"name": "中证500股指",  "multiplier": 200,  "margin_rate": 0.12},
        "IM": {"name": "中证1000股指", "multiplier": 200,  "margin_rate": 0.12},
        "AU": {"name": "黄金期货",     "multiplier": 1000, "margin_rate": 0.10},
        "AG": {"name": "白银期货",     "multiplier": 15,   "margin_rate": 0.12},
        "CU": {"name": "铜期货",       "multiplier": 5,    "margin_rate": 0.10},
        "RU": {"name": "橡胶期货",     "multiplier": 10,   "margin_rate": 0.12},
        "M":  {"name": "豆粕期货",     "multiplier": 10,   "margin_rate": 0.08},
    },
}

# ── 日内择时时间窗口（提前信号检查）────────────────────
# 每个市场可以单独设置日内信号窗口
INTRADAY_WINDOWS = {
    "stocks":  ["14:50"],   # A股收盘前10分钟
    "crypto":  ["08:00", "20:00"],  # 加密货币 UTC 8:00 / 20:00
    "futures": ["14:55", "21:05"], # 期货收盘前/夜盘开盘
}
