"""
Auto-generated factor: 情绪-价格动量交互因子
Key: sentiment_price_momentum
Type: trend
Source: http://arxiv.org/abs/1709.08621v1
Description: 根据文献中情绪因子与比特币价格的正相关关系，构建成交量变化与价格动量的交互项，捕捉情绪驱动的价格趋势强度。
Formula: sentiment_momentum = pct_change(closes, period) * normalized_volume_change
"""

TEMPLATE_KEY  = "sentiment_price_momentum"
TEMPLATE_NAME = "情绪-价格动量交互因子"
STRATEGY_TYPE = "trend"
DEFAULT_PARAMS = {"price_period": 5, "volume_window": 20}
PARAM_RANGES   = {"price_period": [1, 20], "volume_window": [10, 60]}
REQUIRED_DATA  = ["closes", "volumes"]

import math
def compute_score(closes, data, indicators, extensions, params, t):
    price_period = int(params.get('price_period', 5))
    volume_window = int(params.get('volume_window', 20))
    if t < price_period or t < volume_window:
        return 0.0
    volumes = data.get('volumes', [])
    if not volumes or len(volumes) <= t:
        return 0.0
    price_change = (closes[t] - closes[t - price_period]) / closes[t - price_period]
    volume_change = volumes[t] - volumes[t - 1]
    recent_volumes = volumes[t - volume_window:t]
    if len(recent_volumes) < 2:
        return 0.0
    mean_vol = sum(recent_volumes) / len(recent_volumes)
    variance = sum((v - mean_vol) ** 2 for v in recent_volumes) / len(recent_volumes)
    std_vol = math.sqrt(variance)
    if std_vol == 0:
        return 0.0
    normalized_volume_change = volume_change / std_vol
    score = price_change * normalized_volume_change
    return float(score)