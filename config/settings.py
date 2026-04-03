"""
config/settings.py — 全局配置
所有敏感信息通过环境变量或本文件配置
"""

import os
from pathlib import Path

# ── 项目路径 ──────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent.resolve()

# ── 资金配置 ──────────────────────────────────────────
INITIAL_CASH = 1_000_000          # 初始资金（元）
CASH_RESERVE  = 50_000             # 预留现金（不投入交易的备用金）

# ── 市场开关 ──────────────────────────────────────────
MARKETS = {
    "stocks":  True,   # A股
    "crypto":  True,   # 加密货币
    "futures": True,   # 期货
}

# ── 数据源 Token ──────────────────────────────────────
# Tushare Pro（https://tushare.pro）— Token 仅从 .env 读取，不写默认值
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

# CCXT（加密货币，填写你的 Binance/OKX API Key）
CRYPTO_EXCHANGE = os.getenv("CRYPTO_EXCHANGE", "binance")  # binance / okx
CRYPTO_API_KEY  = os.getenv("CRYPTO_API_KEY", "")
CRYPTO_SECRET   = os.getenv("CRYPTO_SECRET", "")

# ── 券商配置 ──────────────────────────────────────────
# A股：老虎证券（OpenAPI）
STOCK_BROKER = {
    "name":    "tiger",
    "account": os.getenv("TIGER_ACCOUNT", ""),
    "token":   os.getenv("TIGER_TOKEN", ""),
}

# 期货：VeighNa（CTP）
FUTURES_BROKER = {
    "name":     "veighna",
    "ctp_front": os.getenv("CTP_FRONT", "tcp://127.0.0.1:20002"),
    "broker_id": os.getenv("CTP_BROKER", ""),
    "user":      os.getenv("CTP_USER", ""),
    "password":  os.getenv("CTP_PASSWORD", ""),
}

# ── 风控参数 ──────────────────────────────────────────
RISK = {
    # 仓位限制
    "max_position_pct":    0.20,   # 单品种最大占总资产 20%
    "max_total_leverage":  1.0,    # 总杠杆不超过 1x（不高频，不加杠杆）
    "max_single_order_pct": 0.05,  # 单笔订单不超过总资产 5%

    # 回撤控制
    "max_drawdown_pct":     0.15,   # 最大回撤 15% 时触发全仓止损
    "daily_loss_stop_pct": 0.03,   # 单日亏损 3% 时停止交易

    # A股特色
    "cn_single_limit_loss": 0.09,   # A股单日跌超 9% 止损（接近涨跌停）
    "cn_margin_of_safety": True,    # 涨停不买，跌停不卖

    # 加密货币特色
    "crypto_max_holding_pct": 0.30, # 加密货币单币种最大 30%
    "crypto_stop_loss_pct":  0.05,  # 止损 5%

    # 期货特色
    "futures_max_margin_pct": 0.40, # 期货保证金占总资产不超过 40%
    "futures_stop_loss_pct": 0.03,  # 止损 3%
}

# ── 数据存储 ──────────────────────────────────────────
DATA_DIR   = BASE_DIR / "data"
PARQUET_DIR = DATA_DIR  / "parquet"
LOG_DIR    = BASE_DIR  / "logs"

for _d in [DATA_DIR, PARQUET_DIR, LOG_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── 交易成本（A股，供所有回测模块统一引用）─────────────
TRADING_COST = {
    "buy":  0.0003 + 0.0005,          # 佣金(万3) + 滑点(万5) = 0.08%
    "sell": 0.0003 + 0.0005 + 0.0010, # 同上 + 印花税(千1)   = 0.18%
}

# ── 回测参数 ──────────────────────────────────────────
BACKTEST = {
    "start":       "2022-01-01",
    "end":         "2024-12-31",
    "commission": {
        "stocks":  0.0008,   # A股：万8（含佣金+过户费）
        "crypto":  0.0010,   # 加密：0.1%（Maker/Taker 平均）
        "futures": 0.0002,   # 期货：万2（单边）
    },
    "slippage": {
        "stocks":  0.0005,   # A股滑点：万一
        "crypto":  0.0005,   # 加密滑点：万一
        "futures": 0.0002,   # 期货滑点：万一
    },
}

# ── 日志配置 ──────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # DEBUG / INFO / WARNING
LOG_FORMAT = "json"  # "json" → 结构化日志 / "text" → 文本日志
