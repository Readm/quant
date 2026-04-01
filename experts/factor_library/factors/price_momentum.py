"""
Auto-generated factor: 价格动量因子
Key: price_momentum
Type: trend
Source: http://arxiv.org/abs/2412.12350v1
Description: 计算过去N个交易日的累计收益率作为动量因子，用于捕捉股价的中期趋势倾向。动量效应表明过去表现良好的股票未来倾向于继续表现良好。
Formula: momentum = (close_t / close_{t-N}) - 1
"""

TEMPLATE_KEY  = "price_momentum"
TEMPLATE_NAME = "价格动量因子"
STRATEGY_TYPE = "trend"
DEFAULT_PARAMS = {"lookback": 20}
PARAM_RANGES   = {"lookback": [5, 60]}
REQUIRED_DATA  = ["closes"]

import math
def compute_score(closes, data, indicators, extensions, params, t):
    lookback = params.get('lookback', 20)
    if t < lookback or len(closes) <= t:
        return 0.0
    return (closes[t] / closes[t - lookback]) - 1