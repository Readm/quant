"""
bear_researcher.py — 熊市研究员（看空Agent）
参考 TradingAgents Bear Researcher 架构
"""
from dataclasses import dataclass
from typing import List
import random


@dataclass
class BearCase:
    strategy_name: str
    failure_modes: List[str]
    downside_risks: List[str]
    market_headwinds: List[str]
    max_drawdown_risk: float
    stop_loss_needed: bool
    confidence: float
    summary: str


class BearResearcher:
    """专门挖掘策略潜在风险的研究员"""

    def __init__(self, seed: int = 43):
        self.name = "BearResearcher"
        self._rng = random.Random(seed)

    def research(self, strategy_name: str, params: dict,
                market_regime: str, ann_ret: float,
                sharpe: float, max_dd: float,
                regime_confidence: float = 0.8) -> BearCase:
        prompt = self._build_prompt(
            strategy_name, params, market_regime,
            ann_ret, sharpe, max_dd, regime_confidence
        )
        try:
            from experts.modules.llm_proxy import llm_analyze
            analysis = llm_analyze(
                prompt=prompt,
                task="bear_case",
                schema={
                    "type": "object",
                    "properties": {
                        "failure_modes": {"type": "array", "items": {"type": "string"}},
                        "downside_risks": {"type": "array", "items": {"type": "string"}},
                        "market_headwinds": {"type": "array", "items": {"type": "string"}},
                        "max_drawdown_risk": {"type": "number"},
                        "stop_loss_needed": {"type": "boolean"},
                        "confidence": {"type": "number"},
                        "summary": {"type": "string"}
                    },
                    "required": ["failure_modes", "downside_risks", "market_headwinds",
                                 "max_drawdown_risk", "stop_loss_needed", "confidence", "summary"]
                }
            )
            return BearCase(
                strategy_name=strategy_name,
                failure_modes=analysis.get("failure_modes", []),
                downside_risks=analysis.get("downside_risks", []),
                market_headwinds=analysis.get("market_headwinds", []),
                max_drawdown_risk=analysis.get("max_drawdown_risk", 0.0),
                stop_loss_needed=analysis.get("stop_loss_needed", True),
                confidence=analysis.get("confidence", 0.5),
                summary=analysis.get("summary", ""),
            )
        except Exception:
            return self._rule_based_bear_case(strategy_name, params, market_regime, ann_ret, sharpe, max_dd)

    def _rule_based_bear_case(self, strategy_name, params, regime, ann_ret, sharpe, max_dd) -> BearCase:
        regime_name = getattr(regime, "name", regime) if hasattr(regime, "name") else regime
        s_type = params.get("strategy_type", "trend")

        failure_map = {
            "trend":        ["趋势突然反转导致高位被套", "ADX假突破触发错误信号", "均线钝化产生滞后"],
            "mean_reversion": ["强趋势市场中均值回归失效", "布林带被突破后持续单边", "RSI超买后继续上涨"],
        }
        headwinds_map = {
            "STRONG_TREND": ["均值回归策略与趋势对抗，风险大于收益"],
            "SIDEWAYS":     ["趋势策略在震荡市中反复止损"],
            "HIGH_VOL":     ["高波动导致假信号增加，趋势策略失效率上升"],
        }

        failures  = failure_map.get(s_type, ["参数不适配当前市场"])
        headwinds = headwinds_map.get(regime_name, ["市场状态不确定"])
        dd_risk   = min(max_dd / 30.0, 1.0) if max_dd > 0 else 0.2
        conf      = min(max(1 - dd_risk, 0.2), 0.8)
        first_fail = failures[0] if failures else "参数不适配"

        return BearCase(
            strategy_name=strategy_name,
            failure_modes=failures,
            downside_risks=[f"历史最大回撤: {max_dd:.1f}%", "若超过历史均值需警惕策略失效"],
            market_headwinds=headwinds,
            max_drawdown_risk=round(dd_risk, 2),
            stop_loss_needed=(max_dd > 5.0),
            confidence=round(conf, 2),
            summary=f"{strategy_name} 主要风险在于{first_fail}，建议设置止损防止超预期回撤。",
        )

    @staticmethod
    def _build_prompt(strategy_name, params, regime, ann_ret, sharpe, max_dd, conf):
        return (
            f"你是量化交易的【熊市研究员】。分析以下策略的潜在风险和看空逻辑：\n\n"
            f"策略名: {strategy_name}\n"
            f"参数: {params}\n"
            f"市场状态: {regime}\n"
            f"年化收益: {ann_ret:+.2f}%\n"
            f"夏普比率: {sharpe:.3f}\n"
            f"最大回撤: {max_dd:.2f}%\n\n"
            f"请输出该策略的看空案例，包括："
            f"失效模式、下跌风险、市场逆风、最大回撤风险评估、是否需要止损、置信度、总结。"
        )

    def format_bear_case(self, bc: BearCase) -> str:
        lines = [
            f"[{self.name}] 看空案例: {bc.strategy_name} (置信度={bc.confidence:.0%})",
        ]
        for f in bc.failure_modes:
            lines.append(f"  失效: {f}")
        for d in bc.downside_risks:
            lines.append(f"  风险: {d}")
        for h in bc.market_headwinds:
            lines.append(f"  逆风: {h}")
        lines.append(f"  回撤风险: {bc.max_drawdown_risk:.2f} | 需止损: {'是' if bc.stop_loss_needed else '否'}")
        lines.append(f"  摘要: {bc.summary}")
        return "\n".join(lines)
