"""
Auto-generated factor: 成交量情绪代理因子
Key: volume_sentiment_proxy
Type: trend
Source: http://arxiv.org/abs/1709.08621v1
Description: 基于文献发现成交量的变化可作为比特币市场情绪的有效代理指标，情绪因子与价格正相关，成交量放大反映市场情绪增强。
Formula: volume_sentiment = (volume - rolling_mean(volume, n)) / rolling_std(volume, n)
"""

TEMPLATE_KEY  = "volume_sentiment_proxy"
TEMPLATE_NAME = "成交量情绪代理因子"
STRATEGY_TYPE = "trend"
DEFAULT_PARAMS = {"window": 20}
PARAM_RANGES   = {"window": [10, 60]}
REQUIRED_DATA  = ["volumes"]

import math
def compute_score(closes, data, indicators, extensions, params, t):
    window = int(params.get("window", 20))
    volumes = data.get("volumes", [])
    if t < window or len(volumes) <= t:
        return 0.0
    window_volumes = volumes[t-window+1:t+1]
    mean = sum(window_volumes) / window
    variance = sum((v - mean) ** 2 for v in window_volumes) / window
    std = math.sqrt(variance)
    if std == 0.0:
        return 0.0
    current_volume = volumes[t]
    score = (current_volume - mean) / std
    return float(score)