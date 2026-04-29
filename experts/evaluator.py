"""
evaluator.py — Expert2 评估专家（风险调整收益评分体系 v2.0）
================================================================
评分体系：
  1. PBO 门控：过拟合概率 > 0.6 → REJECT，> 0.3 → composite ×0.85
  2. 四维度质量评分：
     - Sortino (0.30)：只惩罚下行风险的风险调整收益
     - Calmar  (0.25)：年化收益/最大回撤，衡量"痛苦收益率"
     - IR      (0.25)：信息比率，相对基准的超额收益效率
     - DD      (0.20)：最大回撤控制（纯风控安全网）
  3. 结构化反馈输出（StructuredFeedback）
  4. 候选多样性检测

变更记录：
  - v2.0: 从 Sharpe/Return/DD 三维 → Sortino/Calmar/IR/DD 四维
  - 去掉 excellence_bonus（hack），PBO 改为门控而非线性加权
  - _s_ret 改为相对收益评分（策略年化 - 基准年化）
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional

from experts.structured_feedback import (
    StructuredFeedback, Weakness, AdjustmentDirection,
    FeedbackHistory
)

# ── 硬过滤门槛 v5.3: 放宽淘汰,让多样性策略有机会 ──
MIN_ANNUAL_RETURN = -2.0
MIN_SHARPE        = 0.05
MIN_TRADES        = 1        # v5.3: 3→1, 放宽交易次数限制
SOFT_MIN_TRADES   = 5        # v5.3: 建议最低(供meta-expert参考)
MAX_DRAWDOWN      = 35.0     # v5.7: 25→35, A股组合回撤天然偏高, 放宽硬过滤

# ── PBO 门控阈值 ───────────────────────────
PBO_HARD_REJECT   = 0.50   # PBO > 此值 → REJECT（v5.1: 从0.45回调）
PBO_SOFT_DISCOUNT = 0.30   # PBO > 此值 → composite ×0.85

# ── 打分权重 v5.1: Alpha翻倍 ───────────────
W_SORTINO  = 0.26   # v5.8: 提升Sortino权重, 更强调下行风险调整
W_CALMAR   = 0.20   # v5.8: 微调Calmar
W_IR       = 0.18   # 不变
W_DRAWDOWN = 0.18   # 不变
W_ALPHA    = 0.18   # v5.8: 降低Alpha权重(0.24→0.18), 配合线性缩放不过度奖励高Alpha

# ── 默认基准映射 ───────────────────────────
DEFAULT_BENCHMARK = {
    "SH": "SH000300",   # A股默认基准：沪深300
    "SZ": "SZ399001",   # A股备选基准：深证成指
    "SPY": "SPY",       # 美股默认基准
    "QQQ": "QQQ",       # 纳斯达克
    "BTCUSDT": "BTCUSDT",  # 加密货币：自身
    "ETHUSDT": "ETHUSDT",
}


@dataclass
class EvalResult:
    # 身份
    strategy_id: str; strategy_name: str; strategy_type: str
    params: dict; tags: list

    # 原始指标
    total_return: float; annualized_return: float
    sharpe_ratio: float; max_drawdown_pct: float
    win_rate: float; profit_factor: float
    total_trades: int

    # 维度分（0~100）
    sortino_score: float; calmar_score: float
    ir_score: float; drawdown_score: float
    composite: float

    # 决策
    decision: str            # ACCEPT / REJECT / CONDITIONAL
    reason: str              # 人类可读原因
    feedback: str            # 人类可读反馈（给生成专家）
    elimination_note: str = ""
    weight: float = 0.0      # 组合权重（由 _build_portfolio 填充）

    # ── PBO 过拟合评估 ───────────────
    pbo_score: float = 0.0
    pbo_label: str = ""
    pbo_multiplier: float = 1.0   # 1.0=可信, 0.85=可疑, 0=过拟合

    # ── 相对收益 ─────────────────────
    benchmark_ann_return: float = 0.0   # 基准年化收益
    alpha: float = 0.0                     # 超额收益

    # ── 模板标识 ─────────────────────
    template_key: str = ""

    # ── 样本外收益 ───────────────────
    oos_annualized_return: float = 0.0

    # ── 结构化反馈 ───────────────────
    structured_feedback: Optional[StructuredFeedback] = None


class Evaluator:
    """
    Expert2：策略评估 + 结构化反馈输出。
    v2.0：四维度评分（Sortino/Calmar/IR/DD）+ PBO门控。
    """

    def __init__(self, benchmark_daily_returns: list = None):
        """
        Args:
            benchmark_daily_returns: 基准日收益率列表。
                用于计算 IR（信息比率）和相对收益。
                A股默认使用沪深300日收益。
        """
        self.name = "Evaluator"
        self.history: List[dict] = []
        self.fb_history: FeedbackHistory = FeedbackHistory()
        self.benchmark_returns = benchmark_daily_returns or []
        # 动态门槛（元专家可调整）
        self.ACCEPT_THRESHOLD = 45
        self.CONDITIONAL_THRESHOLD = 25
        # v5.3: 模板多样性追踪 — 鼓励使用不同因子
        self._template_rounds: dict = {}  # template_key → 最近出现在Top的轮次
        self._current_round = 0
        self._last_top3 = []  # v5.6: 上一轮Top-3类型，用于反垄断

    def _diversity_bonus(self, template_key: str) -> float:
        """给长期未进入Top的模板加分，鼓励探索。越久没出现，加分越多。"""
        if not template_key:
            return 0.0
        last_seen = self._template_rounds.get(template_key, -999)
        gap = self._current_round - last_seen
        if gap <= 2:
            return 0.0       # 最近出现过，不加分
        elif gap <= 4:
            return 2.0       # 4轮没出现，小加分
        elif gap <= 8:
            return 5.0       # 8轮没出现
        else:
            return 8.0       # 长期未出现，大加分

    def _monopoly_suppression(self, template_type: str, strategy_name: str = "") -> float:
        """
        v5.6: 反垄断加分（Iter11: 回应评价师）。
        如果Top-3全部是趋势类策略（对照策略名判断），给均值回归类策略+3分强制干预。
        """
        if not template_type:
            return 0.0
        # 用策略名判断类型（strategy_type字段全是"combo"）
        TREND_KW = ["RVI", "ROC", "KDJ", "Elder", "Aroon", "动量", "MACD", "ADX", "Donchian", "TRIX", "Ichimoku", "KST"]
        MR_KW = ["布林", "RSI", "OBOS", "均值回归", "MFI", "量价背离", "成交量"]
        def _classify(name: str) -> str:
            name = name or ""
            if any(kw in name for kw in TREND_KW):
                return "trend"
            if any(kw in name for kw in MR_KW):
                return "mean_reversion"
            return "unknown"
        # 判断当前轮Top-3的分类
        top3_names = [v.get("name", "") for v in getattr(self, "_last_top3", [])]
        top3_classes = [_classify(n) for n in top3_names]
        if len(top3_classes) < 3:
            return 0.0
        all_trend = all(c == "trend" for c in top3_classes)
        is_mr = _classify(strategy_name) == "mean_reversion"
        if all_trend and is_mr:
            return 3.0
        return 0.0

    # ── 核心评估 ─────────────────────────

    def evaluate(self, report, template_key: str = "") -> EvalResult:
        """评估单个 BacktestReport，输出 EvalResult。"""
        r          = report
        ann_ret    = getattr(r, "annualized_return", 0.0)
        sharpe     = getattr(r, "sharpe_ratio", 0.0)
        dd         = getattr(r, "max_drawdown_pct", 0.0)
        wr         = getattr(r, "win_rate", 0.0)
        pf         = getattr(r, "profit_factor", 0.0)
        n_trades   = getattr(r, "total_trades", 0)
        params     = getattr(r, "params", {})
        tags       = getattr(r, "tags", [])
        sid        = getattr(r, "strategy_id", "")
        sname      = getattr(r, "strategy_name", "")
        stype      = getattr(r, "strategy_type", "unknown")
        sortino    = getattr(r, "sortino_ratio", 0.0)
        calmar     = getattr(r, "calmar_ratio", 0.0)
        daily_rets = getattr(r, "daily_returns", []) or []

        # ── 1. 硬性过滤 ────────────────────────
        elim_reasons = []
        if ann_ret < MIN_ANNUAL_RETURN:
            elim_reasons.append(f"年化{ann_ret:.1f}% < {MIN_ANNUAL_RETURN}%目标线")
        if sharpe < MIN_SHARPE:
            elim_reasons.append(f"夏普{sharpe:.2f} < {MIN_SHARPE}门槛")
        if n_trades < MIN_TRADES:
            elim_reasons.append(f"交易{n_trades}次 < {MIN_TRADES}次（数据不足）")
        if dd > MAX_DRAWDOWN:
            elim_reasons.append(f"回撤{dd:.1f}% > {MAX_DRAWDOWN}%上限")

        is_rejected = bool(elim_reasons)
        elim_note   = "【淘汰】" + "；".join(elim_reasons)

        # ── 2. PBO 门控 ──────────────────────
        pbo_multiplier, pbo_label = self._pbo_gate(r)
        if pbo_multiplier == 0.0:
            # PBO 严重过拟合 → 直接 REJECT
            elim_reasons.append(f"PBO过拟合风险过高（{pbo_label}）")
            is_rejected = True
            elim_note = "【淘汰】" + "；".join(elim_reasons)

        # ── 3. 四维度打分 ─────────────────────
        sortino_s = self._s_sortino(sortino)
        calmar_s  = self._s_calmar(calmar)
        dd_s      = self._s_dd(dd)

        # IR：需要基准日收益
        ir_s, benchmark_ann, alpha = self._compute_ir_score(daily_rets)

        # v5.8: Alpha 线性缩放 — alpha 是超额年化(0~200%), 直接映射到 0~100
        # 旧版 alpha*5 导致 alpha>20% 后全部封顶 100, 失去区分度
        alpha_scaled = max(0, min(100, alpha))  # alpha=86.5% → 86.5分

        raw_composite = (
            sortino_s * W_SORTINO
            + calmar_s  * W_CALMAR
            + ir_s      * W_IR
            + dd_s      * W_DRAWDOWN
            + alpha_scaled * W_ALPHA
        )

        # v5.3: 模板多样性奖励
        diversity_bonus = self._diversity_bonus(template_key)
        raw_composite += diversity_bonus

        # v5.5: 交易可靠性调整 — 阶梯式约束（Iter10: 强化惩罚力度）
        n_trades_warning = False
        if n_trades >= 20:
            raw_composite += 5.0      # 交易充分，高度可信
        elif n_trades >= 10:
            raw_composite += 2.0      # 较充分
        elif n_trades >= 5:
            raw_composite += 1.0      # 基本可信
        elif n_trades <= 2:
            raw_composite = raw_composite * 0.5   # 1-2笔，统计不可靠，直接打五折
            n_trades_warning = True

        # ── PBO 折扣 ──────────────────────
        composite = min(100.0, round(raw_composite * pbo_multiplier, 1))

        # ── 4. 决策 ────────────────────────────
        if is_rejected:
            decision = "REJECT"
            reason   = elim_note
        elif n_trades_warning and composite >= self.ACCEPT_THRESHOLD:
            # Iter10: 1-2笔交易即使评分高也降级为待观察（统计不可靠）
            decision = "CONDITIONAL"
            reason   = (f"⚠️ 交易量不足（{n_trades}笔），降为待观察（综合分={composite}，"
                        f"Sortino={sortino:.2f} Calmar={calmar:.2f}，Alpha={alpha:+.1f}%）")
        elif composite >= self.ACCEPT_THRESHOLD:
            decision = "ACCEPT"
            reason   = (f"✅ 纳入（综合分={composite}，Sortino={sortino:.2f} "
                        f"Calmar={calmar:.2f}，Alpha={alpha:+.1f}%，IR={ir_s:.0f}分）")
        elif composite >= self.CONDITIONAL_THRESHOLD:
            decision = "CONDITIONAL"
            reason   = f"⚠️ 待观察（综合分={composite}，建议优化参数）"
        else:
            decision = "REJECT"
            reason   = f"❌ 综合分过低（{composite}），{elim_note}"
            is_rejected = True

        # ── 5. 结构化反馈 ────────────────────
        fb_text  = self._make_feedback(ann_ret, sharpe, dd, wr, pf, n_trades)
        raw_note = elim_note if is_rejected else reason

        weakness, adj_dir, adj_param, adj_mag, adj_unit = self._diagnose_and_prescribe(
            ann_ret, sharpe, dd, wr, pf, n_trades, is_rejected, sid
        )

        regime_map  = {"trend": "STRONG_TREND", "mean_reversion": "SIDEWAYS"}
        rec_regime  = regime_map.get(stype, "WEAK_TREND")
        pos_advice  = ("低配" if dd > 20 else "标配" if dd > 10 else "高配")
        alternatives = {
            "trend":          ["RSI均值回归", "布林带回归"],
            "mean_reversion": ["动量突破", "ADX趋势确认"],
        }.get(stype, [])

        sfb = StructuredFeedback(
            strategy_id=sid, strategy_name=sname, strategy_type=stype,
            template_key=template_key, weakness=weakness, weakness_desc=raw_note,
            ann_return=ann_ret, sharpe_ratio=sharpe, max_drawdown=dd,
            win_rate=wr, profit_factor=pf, total_trades=n_trades, composite=composite,
            adjustment=adj_dir, adjustment_param=adj_param,
            adjustment_magnitude=adj_mag, adjustment_unit=adj_unit,
            recommended_regime=rec_regime, position_advice=pos_advice,
            alternative_strategies=alternatives, raw_reason=raw_note,
            feedback_text=fb_text,
        )

        self.history.append({"strategy_id": sid, "composite": composite,
                              "decision": decision, "ann_ret": ann_ret})
        self.fb_history.add(sfb)

        return EvalResult(
            strategy_id=sid, strategy_name=sname, strategy_type=stype,
            params=params, tags=tags,
            total_return=getattr(r, "total_return", 0.0),
            annualized_return=ann_ret, sharpe_ratio=sharpe,
            max_drawdown_pct=dd, win_rate=wr, profit_factor=pf,
            total_trades=n_trades,
            sortino_score=round(sortino_s, 1), calmar_score=round(calmar_s, 1),
            ir_score=round(ir_s, 1), drawdown_score=round(dd_s, 1),
            composite=composite,
            decision=decision, reason=reason, feedback=fb_text,
            elimination_note=elim_note,
            pbo_score=0.0, pbo_label=pbo_label, pbo_multiplier=pbo_multiplier,
            benchmark_ann_return=round(benchmark_ann, 2), alpha=round(alpha, 2),
            template_key=template_key,
            oos_annualized_return=getattr(r, "oos_annualized_return", 0.0),
            structured_feedback=sfb,
        )

    def evaluate_batch(self, reports: list) -> List[EvalResult]:
        """批量评估并按综合分降序排列。每轮递增追踪轮次。"""
        self._current_round += 1
        results = [self.evaluate(r, template_key=getattr(r, "template_key", "")) for r in reports]
        results.sort(key=lambda x: x.composite, reverse=True)
        # v5.3: 追踪Top-3使用的模板, 下一轮给未使用模板加分
        for r in results[:3]:
            tk = getattr(r, "template_key", "") or ""
            if tk:
                self._template_rounds[tk] = self._current_round
        # v5.6: 存储Top-3类型用于反垄断加分
        self._last_top3 = [
            {"type": r.strategy_type, "name": r.strategy_name, "template_key": getattr(r, "template_key", "") or ""}
            for r in results[:3]
        ]
        return results

    # ══════════════════════════════════════════
    #  PBO 门控（可信度判断，不是线性加权）
    # ══════════════════════════════════════════

    def _pbo_gate(self, report) -> tuple:
        """
        PBO 门控 v2.0 — 收益序列洗牌法（MCS test）。
        不需要信号函数、参数网格或外部依赖。
        
        原理：
          洗牌策略的日收益序列 N 次（破坏时序相关性），
          每次计算洗牌后的 Sharpe。
          PBO = 洗牌 Sharpe 超过实际 Sharpe 的概率。
        
          如果超过 30% 的随机洗牌都能打败实际策略 → 策略过拟合。
        
        Returns
        -------
        (multiplier, label)
          0.0  → 严重过拟合，直接 REJECT
          0.85 → 可疑，打折
          1.0  → 可信，不打折
        """
        import math, random
        
        daily_rets = getattr(report, "daily_returns", None)
        if not daily_rets or len(daily_rets) < 60:
            return 1.0, "数据不足（<60天），跳过"
        
        n = len(daily_rets)
        
        # 计算实际 Sharpe
        mean = sum(daily_rets) / n
        var = sum((r - mean) ** 2 for r in daily_rets) / (n - 1) if n > 1 else 1e-10
        actual_sharpe = mean / (math.sqrt(var) + 1e-10) * math.sqrt(252)
        
        # 如果 Sharpe <= 0，不需要 PBO（反正不赚钱）
        if actual_sharpe <= 0:
            return 1.0, f"Sharpe={actual_sharpe:.2f}（负收益，跳过PBO）"
        
        # 洗牌 300 次
        N_SHUFFLE = 300
        beat_count = 0
        shuffled = daily_rets[:]
        for _ in range(N_SHUFFLE):
            random.shuffle(shuffled)
            s_mean = sum(shuffled) / n
            s_var = sum((r - s_mean) ** 2 for r in shuffled) / (n - 1) if n > 1 else 1e-10
            shuf_sharpe = s_mean / (math.sqrt(s_var) + 1e-10) * math.sqrt(252)
            if shuf_sharpe >= actual_sharpe:
                beat_count += 1
        
        pbo_val = beat_count / N_SHUFFLE
        
        # 评分:
        # PBO = 0.30 意味着 30% 的随机洗牌都能打败实际策略 → 置信度低
        if pbo_val >= 0.50:
            return 0.0, f"PBO洗牌={pbo_val:.0%}（严重过拟合: {beat_count}/{N_SHUFFLE}次洗牌胜出）"
        elif pbo_val >= 0.30:
            return 0.85, f"PBO洗牌={pbo_val:.0%}（可疑: {beat_count}/{N_SHUFFLE}次洗牌胜出）"
        else:
            return 1.0, f"PBO洗牌={pbo_val:.0%}（可信: {beat_count}/{N_SHUFFLE}次洗牌胜出）"

    # ══════════════════════════════════════════
    #  四维度打分函数（0~100）
    # ══════════════════════════════════════════

    @staticmethod
    def _s_sortino(s: float) -> float:
        """Sortino 比率评分。"""
        if s >= 3.0: return 100.0
        if s >= 2.0: return 85 + (s - 2.0) * 15
        if s >= 1.0: return 60 + (s - 1.0) * 25
        if s >= 0.5: return 35 + (s - 0.5) * 50
        if s >= 0.0: return 10 + s * 50
        return max(0.0, 10 + s * 30)

    @staticmethod
    def _s_calmar(c: float) -> float:
        """Calmar 比率评分（年化/最大回撤）。"""
        if c >= 3.0: return 100.0
        if c >= 2.0: return 80 + (c - 2.0) * 20
        if c >= 1.0: return 55 + (c - 1.0) * 25
        if c >= 0.5: return 30 + (c - 0.5) * 50
        if c >= 0.0: return c * 60
        return 0.0

    def _compute_ir_score(self, daily_rets: list) -> tuple:
        """
        计算信息比率评分。
        返回 (ir_score, benchmark_ann_return, alpha)。

        IR = E[策略日收益 - 基准日收益] / std(策略日收益 - 基准日收益)
        无基准时退化为夏普率（基准视为0收益）。
        """
        if not daily_rets:
            return 0.0, 0.0, 0.0

        n_avail = len(daily_rets)
        if self.benchmark_returns:
            n = min(n_avail, len(self.benchmark_returns))
        else:
            n = n_avail

        if n < 30:
            return 0.0, 0.0, 0.0

        strats = daily_rets[:n]
        # 无基准时以0为基准（退化为夏普），保证IR评分不为0
        benchs = self.benchmark_returns[:n] if self.benchmark_returns else [0.0] * n

        # 超额日收益
        excess = [s - b for s, b in zip(strats, benchs)]
        mean_excess = sum(excess) / n

        # 跟踪误差
        if n > 1:
            te = math.sqrt(sum((e - mean_excess) ** 2 for e in excess) / (n - 1))
        else:
            te = 1e-9

        ir = mean_excess / (te + 1e-9)

        # 年化
        ann_excess = mean_excess * 252
        ann_bench  = (sum(benchs) / n * 252) if self.benchmark_returns else 0.0

        return self._s_ir(ir), round(ann_bench * 100, 2), round(ann_excess * 100, 2)

    @staticmethod
    def _s_ir(ir: float) -> float:
        """信息比率评分。IR > 1.0 已经是优秀水平。"""
        if ir >= 2.0: return 100.0
        if ir >= 1.0: return 75 + (ir - 1.0) * 25
        if ir >= 0.5: return 45 + (ir - 0.5) * 60
        if ir >= 0.0: return 15 + ir * 60
        return max(0.0, 15 + ir * 40)

    @staticmethod
    def _s_dd(d: float) -> float:
        """最大回撤评分（0~100）。v5.7: 更陡的惩罚曲线, 对高回撤大幅扣分。"""
        if d <= 10: return 100.0
        if d <= 15: return 85.0
        if d <= 20: return 65.0
        if d <= 25: return 45.0
        if d <= 30: return 25.0
        if d <= 35: return 10.0     # 硬上限边缘, 几乎不贡献分
        return max(0.0, 15 - (d - 35) * 1.5)

    # ══════════════════════════════════════════
    #  弱点诊断 + 处方
    # ══════════════════════════════════════════

    @staticmethod
    def _diagnose_and_prescribe(ann, sharpe, dd, wr, pf, n_trades,
                                 is_rejected, sid: str = "") -> tuple:
        import random as _rnd
        _r = _rnd.Random(hash(sid) ^ hash(f"{ann:.1f}{sharpe:.2f}"))

        options = {
            "LOW_SHARPE": [
                (Weakness.LOW_SHARPE, AdjustmentDirection.TIGHTEN_STOP_LOSS, "atr_mult",   0.6,  "倍"),
                (Weakness.LOW_SHARPE, AdjustmentDirection.ADD_FILTER,        "threshold",  0.03, "%"),
                (Weakness.LOW_SHARPE, AdjustmentDirection.DECREASE_LOOKBACK, "fast",       -5,   "天"),
                (Weakness.LOW_SHARPE, AdjustmentDirection.INCREASE_LOOKBACK, "slow",        15,  "天"),
            ],
            "HIGH_DRAWDOWN": [
                (Weakness.HIGH_DRAWDOWN, AdjustmentDirection.DECREASE_POSITION, "position",   0.6,  "%"),
                (Weakness.HIGH_DRAWDOWN, AdjustmentDirection.TIGHTEN_STOP_LOSS, "atr_mult",   0.5,  "倍"),
                (Weakness.HIGH_DRAWDOWN, AdjustmentDirection.ADD_FILTER,        "threshold",  0.05, "%"),
                (Weakness.HIGH_DRAWDOWN, AdjustmentDirection.INCREASE_LOOKBACK, "slow",        20,  "天"),
            ],
            "LOW_RETURN": [
                (Weakness.LOW_RETURN, AdjustmentDirection.DECREASE_LOOKBACK,  "fast",       -8,   "天"),
                (Weakness.LOW_RETURN, AdjustmentDirection.INCREASE_LOOKBACK,  "lookback",    10,  "天"),
                (Weakness.LOW_RETURN, AdjustmentDirection.WIDEN_STOP_LOSS,    "atr_mult",   1.5,  "倍"),
                (Weakness.LOW_RETURN, AdjustmentDirection.REMOVE_FILTER,      "threshold", -0.02, "%"),
            ],
            "LOW_WIN_RATE": [
                (Weakness.LOW_WIN_RATE, AdjustmentDirection.DECREASE_LOOKBACK, "period",   -8,   "天"),
                (Weakness.LOW_WIN_RATE, AdjustmentDirection.ADD_FILTER,        "threshold", 0.04, "%"),
                (Weakness.LOW_WIN_RATE, AdjustmentDirection.TIGHTEN_STOP_LOSS, "atr_mult",  0.7,  "倍"),
                (Weakness.LOW_WIN_RATE, AdjustmentDirection.INCREASE_LOOKBACK, "slow",       10,  "天"),
            ],
            "LOW_PF": [
                (Weakness.LOW_PROFIT_FACTOR, AdjustmentDirection.TIGHTEN_STOP_LOSS, "atr_mult",  0.6,  "倍"),
                (Weakness.LOW_PROFIT_FACTOR, AdjustmentDirection.WIDEN_STOP_LOSS,   "atr_mult",  1.4,  "倍"),
                (Weakness.LOW_PROFIT_FACTOR, AdjustmentDirection.DECREASE_LOOKBACK, "fast",       -5,   "天"),
                (Weakness.LOW_PROFIT_FACTOR, AdjustmentDirection.ADD_FILTER,        "threshold",  0.03, "%"),
            ],
            "FEW_TRADES": [
                (Weakness.FEW_TRADES, AdjustmentDirection.ADD_FILTER,         "threshold", -0.02, "%"),
                (Weakness.FEW_TRADES, AdjustmentDirection.DECREASE_LOOKBACK,  "fast",       -10,  "天"),
                (Weakness.FEW_TRADES, AdjustmentDirection.REMOVE_FILTER,      "threshold", -0.03, "%"),
                (Weakness.FEW_TRADES, AdjustmentDirection.WIDEN_STOP_LOSS,    "atr_mult",   1.3,  "倍"),
            ],
        }

        def pick(key):
            return _r.choice(options[key])

        if sharpe < MIN_SHARPE:       return pick("LOW_SHARPE")[0], *pick("LOW_SHARPE")[1:]
        if dd > MAX_DRAWDOWN:          return pick("HIGH_DRAWDOWN")[0], *pick("HIGH_DRAWDOWN")[1:]
        if ann < MIN_ANNUAL_RETURN:    return pick("LOW_RETURN")[0], *pick("LOW_RETURN")[1:]
        if wr < 40:                    return pick("LOW_WIN_RATE")[0], *pick("LOW_WIN_RATE")[1:]
        if pf < 1.3:                   return pick("LOW_PF")[0], *pick("LOW_PF")[1:]
        if n_trades < MIN_TRADES:      return pick("FEW_TRADES")[0], *pick("FEW_TRADES")[1:]
        if is_rejected:
            return Weakness.OVERFITTED, AdjustmentDirection.DIVERSIFY, "", 0, ""
        return Weakness.NONE, AdjustmentDirection.NONE, "", 0, ""

    @staticmethod
    def _make_feedback(ann, sharpe, dd, wr, pf, n_trades) -> str:
        tips = []
        if sharpe < 0.5:  tips.append("收紧出场条件减少假信号")
        if dd > 20:        tips.append("降低单笔仓位至≤10%")
        if wr < 40:       tips.append("缩短持仓周期或加入趋势过滤")
        if pf < 1.3:      tips.append("优化止盈止损比，减少赢转亏")
        if n_trades < 5:  tips.append("放宽入场条件增加交易频率")
        if not tips:      tips.append("指标良好，可适度扩大仓位")
        return "；".join(tips)

    # ── 多样性检测 ────────────────────────
    def need_diversify(self) -> bool:
        return self.fb_history.suggest_diversify()

    def get_structured_feedback_for(self, strategy_type: str) -> List[dict]:
        fbs = self.fb_history.get_for_type(strategy_type)
        return [fb.to_simple_dict() for fb in fbs]

    # ── 报告打印 ───────────────────────────
    @staticmethod
    def print_batch_report(results: List[EvalResult], round_num: int):
        accepted    = [r for r in results if r.decision == "ACCEPT"]
        conditional = [r for r in results if r.decision == "CONDITIONAL"]
        rejected    = [r for r in results if r.decision == "REJECT"]

        print(f"\n{'='*68}")
        print(f"  Expert2 评估报告 — 第 {round_num} 轮（v2.0 Sortino/Calmar/IR/DD）")
        print(f"{'='*68}")
        print(f"\n📊 结果：纳入 {len(accepted)} | 待观察 {len(conditional)} | 淘汰 {len(rejected)}")
        print(f"   硬过滤：年化<{MIN_ANNUAL_RETURN}% | 夏普<{MIN_SHARPE} | "
              f"交易<{MIN_TRADES}次 | 回撤>{MAX_DRAWDOWN}%\n")

        if accepted:
            print("✅ 纳入策略：")
            for r in accepted:
                sf = r.structured_feedback
                print(f"   · {r.strategy_name}（{r.strategy_type}）| "
                      f"trades={r.total_trades} ann={r.annualized_return:+.1f}% "
                      f"sharpe={r.sharpe_ratio:.2f} dd={r.max_drawdown_pct:.1f}% | "
                      f"Sortino={r.sortino_score:.0f}分 Calmar={r.calmar_score:.0f}分 | "
                      f"Alpha={r.alpha:+.1f}% | IR={r.ir_score:.0f}分 | 综合分={r.composite}")
                if sf:
                    print(f"     → 结构化反馈: 弱点={sf.weakness.value} | "
                          f"调整方向={sf.adjustment.value} | "
                          f"参数={sf.adjustment_param} {sf.adjustment_magnitude:+.1f}{sf.adjustment_unit}")
                print(f"     反馈：{r.feedback}")

        if conditional:
            print("\n⚠️ 待观察：")
            for r in conditional:
                print(f"   · {r.strategy_name} | 综合分={r.composite} | {r.reason}")

        if rejected:
            print(f"\n❌ 淘汰（{len(rejected)}个）：")
            for r in rejected[:10]:
                print(f"   · {r.strategy_name}({r.strategy_type}) | "
                      f"trades={r.total_trades} ann={r.annualized_return:+.1f}% "
                      f"sharpe={r.sharpe_ratio:.2f} dd={r.max_drawdown_pct:.1f}% | {r.elimination_note}")
                sf = r.structured_feedback
                if sf:
                    print(f"     → 需调整: {sf.adjustment.value} "
                          f"参数={sf.adjustment_param} "
                          f"幅度={sf.adjustment_magnitude:+.1f}{sf.adjustment_unit}")
            if len(rejected) > 10:
                print(f"   … 还有 {len(rejected) - 10} 个被拒策略")

        print(f"\n{'='*68}")


# ══════════════════════════════════════════════════════════════
#  工具函数：从收盘价序列计算基准日收益
# ══════════════════════════════════════════════════════════════

def compute_benchmark_returns(closes: list) -> list:
    """从收盘价序列计算日收益率列表。"""
    if not closes or len(closes) < 2:
        return []
    returns = []
    for i in range(1, len(closes)):
        if closes[i-1] > 0:
            returns.append(closes[i] / closes[i-1] - 1)
        else:
            returns.append(0.0)
    return returns
