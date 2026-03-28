"""
regime.py — 市场状态专家
"""
import math
from dataclasses import dataclass
from typing import List


@dataclass
class MarketRegime:
    name: str
    confidence: float
    adx_score: float
    vol_ratio: float
    trend_dir: str
    recommended_strategies: List[str]
    portfolio_tilt: str
    max_position_pct: float
    explanation: str


class MarketRegimeExpert:
    def detect(self, data: dict, indicators: dict) -> MarketRegime:
        closes = data["closes"]
        n = len(closes)
        adx_vals = indicators.get("adx", [30.0] * n)
        adx_recent = adx_vals[-20:] if len(adx_vals) >= 20 else adx_vals
        adx = sum(adx_recent) / len(adx_recent) if adx_recent else 25.0
        recent_returns = data["returns"][-60:] if len(data["returns"]) >= 60 else data["returns"]
        hist_returns = data["returns"][-252:] if len(data["returns"]) >= 252 else data["returns"]
        current_vol = self._vol(recent_returns)
        hist_vol = self._vol(hist_returns)
        vol_ratio = current_vol / (hist_vol + 1e-9)
        ma20 = indicators.get("ma20", [100]*n)
        ma60 = indicators.get("ma60", [100]*n)
        ma20_last = ma20[-1] if ma20 else 100
        ma20_prev = ma20[-10] if len(ma20) >= 10 else ma20_last
        if ma20_last > ma60[-1] and ma20_last > ma20_prev:
            trend_dir = "UP"
        elif ma20_last < ma60[-1] and ma20_last < ma20_prev:
            trend_dir = "DOWN"
        else:
            trend_dir = "NEUTRAL"
        mom20 = (closes[-1] / (closes[-20] + 1e-9) - 1) if len(closes) >= 20 else 0.0
        regime_name, confidence = self._classify(adx, vol_ratio)
        rec_strats, tilt, max_pos = self._adapt(regime_name, adx, vol_ratio, trend_dir)
        explanation = self._explain(regime_name, confidence, adx, vol_ratio, trend_dir, mom20, max_pos)
        return MarketRegime(
            name=regime_name, confidence=round(confidence, 3),
            adx_score=round(adx, 2), vol_ratio=round(vol_ratio, 2),
            trend_dir=trend_dir, recommended_strategies=rec_strats,
            portfolio_tilt=tilt, max_position_pct=max_pos, explanation=explanation,
        )

    def _classify(self, adx, vol_ratio):
        if adx > 40 and vol_ratio > 2.0:
            return "CRISIS", min(1.0, 0.5 + adx / 200)
        if vol_ratio > 1.8:
            return "HIGH_VOL", min(1.0, 0.5 + vol_ratio / 4)
        if adx >= 30:
            return "STRONG_TREND", min(1.0, 0.5 + (adx - 25) / 40)
        if adx >= 20:
            return "WEAK_TREND", min(1.0, 0.4 + adx / 50)
        return "SIDEWAYS", min(1.0, 0.5 + (25 - adx) / 50)

    def _adapt(self, regime, adx, vol_ratio, trend_dir):
        if regime == "CRISIS":
            return (["均值回归", "防御型"], "清仓或低配", 0.10)
        if regime == "HIGH_VOL":
            return (["均值回归", "短周期趋势"], "降低总仓位", 0.30)
        if regime == "STRONG_TREND":
            return (["趋势跟踪", "MACD", "动量突破"], f"增配{trend_dir}方向", 0.60)
        if regime == "WEAK_TREND":
            return (["双均线", "RSI均值回归"], "均衡配置", 0.45)
        return (["RSI均值回归", "布林带"], "以均值回归为主", 0.40)

    def _explain(self, regime, confidence, adx, vol_ratio, trend_dir, mom20, max_pos):
        regime_cn = {"STRONG_TREND":"强趋势","WEAK_TREND":"弱趋势","SIDEWAYS":"震荡","HIGH_VOL":"高波动","CRISIS":"危机"}.get(regime, regime)
        lines = [
            f"市场状态：【{regime_cn}】（置信度={confidence:.0%}）",
            f"  证据1：ADX={adx:.1f}（趋势强度）",
            f"  证据2：波动率比={vol_ratio:.2f}（当前/历史均值）",
            f"  证据3：20日动量={mom20:+.1%}",
            f"  策略适配：推荐 [{'/'.join(self._adapt(regime, adx, vol_ratio, trend_dir)[0])}]",
            f"  仓位建议：总仓位不超过 {max_pos:.0%}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _vol(returns):
        n = len(returns)
        if n < 2: return 0.02
        m = sum(returns) / n
        return math.sqrt(sum((r-m)**2 for r in returns) / (n-1))
