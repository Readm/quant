"""
structured_feedback.py — 结构化反馈协议
=========================================
解决自然语言反馈的歧义问题，让 Expert1 能精确理解和响应反馈。

设计原则：
- 每个字段都是机器可解析的，不是自然语言
- 附带原始原因供人类阅读
- 可序列化，方便存储和传递
"""

from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class Weakness(Enum):
    """策略弱点类型（互斥，每个策略只有一个主要弱点）"""
    LOW_SHARPE          = "low_sharpe"           # 夏普比率过低
    HIGH_DRAWDOWN       = "high_drawdown"        # 最大回撤超限
    LOW_RETURN          = "low_return"           # 年化收益率不足
    LOW_WIN_RATE        = "low_win_rate"         # 胜率过低
    LOW_PROFIT_FACTOR   = "low_profit_factor"    # 盈亏比不足
    FEW_TRADES          = "few_trades"          # 交易次数过少
    OVERFITTED          = "overfitted"           # 疑似过拟合
    REGIME_MISMATCH     = "regime_mismatch"      # 策略与市场状态不匹配
    CORRELATION_HIGH    = "correlation_high"     # 与其他策略高度相关
    NONE                = "none"                 # 无明显弱点


class AdjustmentDirection(Enum):
    """参数调整方向"""
    INCREASE_LOOKBACK   = "increase_lookback"    # 增加回看周期
    DECREASE_LOOKBACK   = "decrease_lookback"    # 减少回看周期
    TIGHTEN_STOP_LOSS   = "tighten_stop_loss"    # 收紧止损
    WIDEN_STOP_LOSS     = "widen_stop_loss"      # 放宽止损
    INCREASE_POSITION   = "increase_position"    # 增加仓位
    DECREASE_POSITION   = "decrease_position"    # 减少仓位
    ADD_FILTER          = "add_filter"           # 增加过滤条件
    REMOVE_FILTER       = "remove_filter"       # 减少过滤条件
    SWITCH_REGIME       = "switch_regime"        # 切换适应市场状态
    DIVERSIFY           = "diversify"            # 增加策略多样性（生成时）
    NONE                = "none"                 # 无需调整


@dataclass
class StructuredFeedback:
    """
    结构化反馈——Expert2 评估专家输出，供 Expert1 迭代使用。
    
    设计：机器可解析字段 + 人类可读字段 二合一
    """
    # ── 身份 ───────────────────────────────
    strategy_id:    str
    strategy_name:  str
    strategy_type:  str          # "trend" | "mean_reversion"
    template_key:   str          # "ma_cross" | "rsi" | ...

    # ── 弱点诊断（核心）────────────────────
    weakness:       Weakness
    weakness_desc:  str           # 人类可读描述，如 "夏普=0.21，远低于0.3门槛"

    # ── 量化指标 ──────────────────────────
    ann_return:     float        # 年化收益率 (%)
    sharpe_ratio:   float
    max_drawdown:   float        # 最大回撤 (%)
    win_rate:       float        # 胜率 (%)
    profit_factor:  float
    total_trades:   int
    composite:      float        # 综合分 0~100

    # ── 建议调整（精确指令）────────────────
    adjustment:         AdjustmentDirection
    adjustment_param:   str           # 建议调整的参数名，如 "period" | "threshold"
    adjustment_magnitude: float       # 调整幅度（比例），如 +0.2 / ×1.5 / +5
    adjustment_unit:    str           # 单位："%" | "倍" | "天" | "绝对值"

    # ── 市场状态适配 ─────────────────────
    recommended_regime: str           # 推荐的市场状态，如 "STRONG_TREND"
    position_advice:    str           # 仓位建议："低配" | "标配" | "高配"

    # ── 替代方案 ─────────────────────────
    alternative_strategies: List[str]  # 如果当前策略类型持续失败，建议尝试的其他类型

    # ── 原始评估原因 ──────────────────────
    raw_reason:     str           # Expert2 原始淘汰/纳入原因（人类可读）
    feedback_text:  str           # 给人类看的反馈文本

    def to_simple_dict(self) -> dict:
        """转换为简化字典，供 Expert1 直接使用"""
        return {
            "strategy_id":   self.strategy_id,
            "strategy_name": self.strategy_name,
            "strategy_type": self.strategy_type,
            "template_key":  self.template_key,
            "weakness":      self.weakness.value,
            "adjustment":    self.adjustment.value,
            "param":         self.adjustment_param,
            "magnitude":     self.adjustment_magnitude,
            "unit":          self.adjustment_unit,
            "recommended_regime": self.recommended_regime,
            "position_advice":    self.position_advice,
        }

    @staticmethod
    def from_eval_result(eval_result, template_key: str = "") -> "StructuredFeedback":
        """
        从 EvalResult（Expert2 输出）自动转换为结构化反馈。
        这是自动化桥接——不需要 Expert2 单独实现结构化输出。
        """
        r = eval_result
        weakness_map = {
            "SHARPE":    Weakness.LOW_SHARPE,
            "年化":      Weakness.LOW_RETURN,
            "回撤":      Weakness.HIGH_DRAWDOWN,
            "胜率":      Weakness.LOW_WIN_RATE,
            "盈亏":      Weakness.LOW_PROFIT_FACTOR,
            "交易次数":  Weakness.FEW_TRADES,
        }

        # 识别主要弱点
        raw = r.elimination_note or r.reason or ""
        detected_weakness = Weakness.NONE
        for key, w in weakness_map.items():
            if key in raw.upper():
                detected_weakness = w
                break
        if r.composite < 30:
            detected_weakness = Weakness.OVERFITTED

        # 确定调整方向
        adj_map = {
            Weakness.LOW_SHARPE:       (AdjustmentDirection.TIGHTEN_STOP_LOSS, "atr_mult", 0.5, "倍"),
            Weakness.HIGH_DRAWDOWN:     (AdjustmentDirection.DECREASE_POSITION,  "position", 0.7, "%"),
            Weakness.LOW_RETURN:        (AdjustmentDirection.INCREASE_LOOKBACK, "period",   5,   "天"),
            Weakness.LOW_WIN_RATE:      (AdjustmentDirection.DECREASE_LOOKBACK, "period",   -5,  "天"),
            Weakness.FEW_TRADES:        (AdjustmentDirection.ADD_FILTER,        "threshold", -0.2, "%"),
            Weakness.OVERFITTED:        (AdjustmentDirection.DIVERSIFY,           "",         0,   ""),
            Weakness.NONE:               (AdjustmentDirection.NONE,                "",         0,   ""),
        }
        adj_dir, adj_param, adj_mag, adj_unit = adj_map.get(detected_weakness, (AdjustmentDirection.NONE, "", 0, ""))

        # 推荐市场状态
        regime_map = {
            "trend":          "STRONG_TREND",
            "mean_reversion": "SIDEWAYS",
        }
        rec_regime = regime_map.get(r.strategy_type, "WEAK_TREND")
        pos_advice = "低配" if r.max_drawdown_pct > 20 else ("标配" if r.max_drawdown_pct > 10 else "高配")

        # 备选策略
        alternatives = {
            "trend":           ["均值回归RSI", "布林带回归"],
            "mean_reversion":  ["动量突破", "ADX趋势确认"],
        }.get(r.strategy_type, [])

        return StructuredFeedback(
            strategy_id=r.strategy_id,
            strategy_name=r.strategy_name,
            strategy_type=r.strategy_type,
            template_key=template_key,
            weakness=detected_weakness,
            weakness_desc=r.elimination_note or r.reason or "无明显弱点",
            ann_return=r.annualized_return,
            sharpe_ratio=r.sharpe_ratio,
            max_drawdown=r.max_drawdown_pct,
            win_rate=r.win_rate,
            profit_factor=r.profit_factor,
            total_trades=r.total_trades,
            composite=r.composite,
            adjustment=adj_dir,
            adjustment_param=adj_param,
            adjustment_magnitude=adj_mag,
            adjustment_unit=adj_unit,
            recommended_regime=rec_regime,
            position_advice=pos_advice,
            alternative_strategies=alternatives,
            raw_reason=r.elimination_note or r.reason,
            feedback_text=r.feedback,
        )


# ─────────────────────────────────────────────
#  反馈历史记录（用于多样性分析）
# ─────────────────────────────────────────────

class FeedbackHistory:
    """
    管理所有历史反馈，用于：
    - 检测反复被拒绝的策略类型
    - 追踪参数调整轨迹
    - 为下一轮生成提供多样性信号
    """

    def __init__(self):
        self.entries: List[StructuredFeedback] = []

    def add(self, fb: StructuredFeedback):
        self.entries.append(fb)

    def get_for_type(self, strategy_type: str) -> List[StructuredFeedback]:
        return [e for e in self.entries if e.strategy_type == strategy_type]

    def get_rejected_types(self, min_rejects: int = 2) -> List[str]:
        """返回被反复拒绝的策略类型列表"""
        from collections import Counter
        rejected = [e.strategy_type for e in self.entries
                    if e.weakness != Weakness.NONE]
        counts = Counter(rejected)
        return [t for t, c in counts.items() if c >= min_rejects]

    def suggest_diversify(self) -> bool:
        """如果某类型被拒绝3次以上，建议生成多样化策略"""
        return len(self.get_rejected_types(3)) > 0
