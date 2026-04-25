"""
orchestrator.py — 多专家迭代系统 v4.0（全面改进版）
=====================================================
主要改进：
  ✅ 完全移除合成数据（彻底删除 generate_synthetic）
  ✅ 结构化反馈协议（StructuredFeedback）取代模糊字符串
  ✅ 多样性约束生成（30%随机探索 + 30%反馈优化 + 40% exploitation）
  ✅ 策略相关性校验（ρ>0.75 则降低权重）
  ✅ Paper Trade 验证（holdout 窗口模拟实盘）
  ✅ 三专家辩论（Trend + MeanReversion + Regime）
"""

import sys, json, math, random, os, time
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))

from experts.modules.blackboard import Blackboard
from experts.modules.risk_engine import RiskExpert
from experts.specialists.expert1a_trend import TrendExpert
from experts.specialists.expert1b_mean_reversion import MeanReversionExpert
from experts.evaluator import Evaluator
from experts.meta_monitor import MetaMonitor, RoundSnapshot
from experts.debate_manager import DebateManager
from experts.structured_feedback import FeedbackHistory
from experts.data_loader import (
    load_symbols_data, compute_benchmark_for_symbols, compute_indicators,
)
from experts.report_writer import (
    make_snapshot, generate_final_report, to_serializable,
    save_report, print_final_report,
)

# ── 并行回测 worker（模块级，可被 ProcessPoolExecutor pickle）─────
_worker_symbols_data = None
_worker_sym_list     = None

def _init_backtest_worker(symbols_data, sym_list):
    """每个 worker 进程初始化一次，共享 symbols_data 避免重复序列化。"""
    global _worker_symbols_data, _worker_sym_list
    _worker_symbols_data = symbols_data
    _worker_sym_list     = sym_list

def _backtest_one_cand(args):
    """
    组合回测：对所有标的做因子打分 → 选 Top-N → 持仓回测。
    返回 PortfolioBacktester 生成的 BacktestReport。
    """
    from backtest.engine import PortfolioBacktester
    expert, cand = args
    pp = cand.get("portfolio_params", {})
    bt = PortfolioBacktester(
        symbols_data=_worker_symbols_data,
        expert=expert,
        candidate=cand,
        portfolio_params=pp,
    )
    try:
        return bt.run(oos_days=OOS_DAYS)
    except Exception as e:
        import sys as _sys
        raise type(e)(
            f"[{cand.get('template_key')} params={cand.get('params')}] {e}"
        ).with_traceback(_sys.exc_info()[2]) from e

_N_BT_WORKERS = max(1, (os.cpu_count() or 4))

MAX_ROUNDS_DEFAULT   = 20
TOP_N_DEFAULT       = 4
HOLDOUT_DAYS        = 30
OOS_DAYS            = 252   # 样本外验证期（约1年），从每次回测末尾截出
CORR_THRESHOLD      = 0.75


# ── 相关性矩阵 ───────────────────────────────

def compute_correlation_matrix(reports):
    n = len(reports)
    if n < 2: return {}
    def get_rets(r):
        dr = getattr(r, "daily_returns", None)
        return dr[-100:] if dr and len(dr) >= 10 else []
    rets_list = [get_rets(r) for r in reports]
    min_len   = min(len(r) for r in rets_list)
    if min_len < 10:
        return {}
    rets_list = [r[:min_len] for r in rets_list]
    def pearson_r(x, y):
        n = len(x); mx=sum(x)/n; my=sum(y)/n
        num=sum((xi-mx)*(yi-my) for xi,yi in zip(x,y))
        dx=math.sqrt(sum((xi-mx)**2 for xi in x))
        dy=math.sqrt(sum((yi-my)**2 for yi in y))
        return num/(dx*dy+1e-9)
    corr_map = {}
    for i in range(n):
        for j in range(i+1, n):
            rho = pearson_r(rets_list[i], rets_list[j])
            if abs(rho) > 0.5:
                corr_map[(reports[i].strategy_id, reports[j].strategy_id)] = round(rho, 3)
    return corr_map


def apply_correlation_penalty(portfolio, reports, corr_map):
    if not corr_map: return portfolio
    for (id_a, id_b), rho in corr_map.items():
        if rho > CORR_THRESHOLD and id_b in portfolio and portfolio[id_b] > 0:
            old = portfolio[id_b]
            portfolio[id_b] = round(old * 0.5, 4)
            print(f"  [相关性] {id_a[:12]}<->{id_b[:12]} ρ={rho:.2f}，降低权重 {old:.1%}->{portfolio[id_b]:.1%}")
    return portfolio


def eval_to_strat_dict(e) -> dict:
    """EvalResult → 元专家所需的精简 dict（含被拒原因和关键指标）"""
    return {
        "name":         getattr(e, "strategy_name", ""),
        "type":         getattr(e, "strategy_type", ""),
        "decision":     getattr(e, "decision", ""),
        "score":        round(float(getattr(e, "composite", 0)), 1),
        "total_trades": int(getattr(e, "total_trades", 0)),
        "ann_return":   round(float(getattr(e, "annualized_return", 0)), 1),
        "sharpe":       round(float(getattr(e, "sharpe_ratio", 0)), 2),
        "max_dd":       round(float(getattr(e, "max_drawdown_pct", 0)), 1),
        "sortino":      round(float(getattr(e, "sortino_score", 0)), 1),
        "calmar":       round(float(getattr(e, "calmar_score", 0)), 1),
        "alpha":        round(float(getattr(e, "alpha", 0)), 1),
        "elim_note":    (getattr(e, "elimination_note", "") or "")[:60],
    }


class Orchestrator:
    def __init__(self, symbols, n_days=500, seed=2026,
                 max_rounds=MAX_ROUNDS_DEFAULT, top_n=TOP_N_DEFAULT):
        self.symbols    = symbols
        self.n_days     = n_days
        self.seed       = seed
        self.max_rounds = max_rounds
        self.top_n      = top_n
        self.bb             = Blackboard()
        self.risk_expert    = RiskExpert()
        self.trend_expert   = TrendExpert(seed=seed)
        self.mr_expert      = MeanReversionExpert(seed=seed+1)
        self.evaluator      = Evaluator()
        self.debate_manager = DebateManager()
        self.debate_manager.risk_expert = self.risk_expert
        self.fb_history     = FeedbackHistory()
        self._preloaded_feedback: list = []
        self.round_reports  = []
        self.prev_top_ids   = set()
        self.best_score     = 0.0
        self.no_improve     = 0
        self.monitor        = MetaMonitor(report_every=5)
        self._seen_cand_hashes: set = set()  # similarity dedup across all rounds
        self._best_ever: dict = {}           # template_key → {params, portfolio_params, score}
        self._champion_evals: list = []      # carried-over top EvalResults from previous round
        self._load_search_state()

        # ── 加载生成因子（插件注册）──────────────────────────────
        self._load_generated_factors()

        # ── 元专家动态参数 ──────────────────────────────────
        self._meta_params = {
            "trend_candidates": 30,
            "mr_candidates": 25,
            "accept_threshold": 45,
            "conditional_threshold": 25,
            "n_stocks_min": 2,
            "n_stocks_max": 5,
            "rebalance_options": [5, 10, 20, 60],
        }
        self._meta_history = {
            "total_candidates": 0,
            "total_accepted": 0,
            "total_rejected": 0,
        }

    def run(self):
        print("="*68)
        print("  多专家协作量化系统 v4.0（纯实盘 + 结构化反馈）")
        print("  Pipeline(A) + Adversarial(B) + Correlation(C) + Holdout(D)")
        print("="*68)

        symbols_data = load_symbols_data(self.symbols, self.n_days)

        # 设置评估基准（默认用第一个标的作为基准）
        benchmark_sym = None  # override in subclass if needed
        benchmark_rets = compute_benchmark_for_symbols(symbols_data, benchmark_sym)
        self.evaluator = Evaluator(benchmark_daily_returns=benchmark_rets)
        if benchmark_rets:
            print(f"[基准] {benchmark_sym or '第一个标的'}，{len(benchmark_rets)} 个日收益率")
        else:
            print(f"[基准] 无基准数据，IR 评分将默认为 0")

        _rnd_times: list = []  # profiling accumulator

        for rnd in range(1, self.max_rounds + 1):
            _t_rnd = time.perf_counter()
            print(f"\n{'='*68}\n  ▶ 第 {rnd} 轮迭代\n{'='*68}")

            need_div = self.evaluator.need_diversify()
            fb_list  = self._preloaded_feedback + [fb.to_simple_dict() for fb in self.evaluator.fb_history.entries]

            _dedup_rng = random.Random(self.seed + rnd * 7919)
            mp = self._meta_params
            t_n = mp["trend_candidates"]
            mr_n = mp["mr_candidates"]
            t_cands  = self._dedup_candidates(
                self._generate_diverse_candidates(self.trend_expert, t_n, fb_list, need_div, "trend", rnd),
                _dedup_rng)
            mr_cands = self._dedup_candidates(
                self._generate_diverse_candidates(self.mr_expert, mr_n, fb_list, need_div, "mean_reversion", rnd),
                _dedup_rng)
            all_cands = t_cands + mr_cands

            _t_bt = time.perf_counter()
            t_reports  = self._backtest_multi_symbol(self.trend_expert,  t_cands,  symbols_data)
            mr_reports = self._backtest_multi_symbol(self.mr_expert,     mr_cands, symbols_data)
            _dt_bt = time.perf_counter() - _t_bt

            # Register completed-backtest hashes (post-evaluation, authoritative)
            for c in t_cands + mr_cands:
                self._seen_cand_hashes.add(
                    self._cand_hash(c["template_key"], c["params"],
                                    c.get("portfolio_params", {}))
                )

            for r, c in zip(t_reports, t_cands):
                r.strategy_id   = c["strategy_id"]
                r.strategy_type = "trend"
            for r, c in zip(mr_reports, mr_cands):
                r.strategy_id   = c["strategy_id"]
                r.strategy_type = "mean_reversion"

            # 注入结构化反馈到候选元数据
            self._apply_sf_to_candidates(all_cands, t_reports, mr_reports)

            print(f"\n[生成] 趋势 {len(t_reports)} 个 + 均值回归 {len(mr_reports)} 个候选")

            # Expert2 评估
            all_reports = t_reports + mr_reports
            Evaluator.print_batch_report(self.evaluator.evaluate_batch(all_reports), rnd)
            t_evals = self.evaluator.evaluate_batch(t_reports)
            mr_evals = self.evaluator.evaluate_batch(mr_reports)

            # ── 注入冠军保留（Champion Elitism）──────────────────────
            # 将上一轮的冠军策略注入本轮评估列表，保证不因探索失败而退步
            # 用 strategy_id（含完整参数 hash）去重，防止同名不同参的变体踢掉真正冠军
            if self._champion_evals and rnd > 1:
                current_ids = {e.strategy_id for e in t_evals + mr_evals}
                injected = 0
                for ce in self._champion_evals:
                    if ce.strategy_id not in current_ids:
                        if getattr(ce, "strategy_type", "") == "trend":
                            t_evals.append(ce)
                        else:
                            mr_evals.append(ce)
                        current_ids.add(ce.strategy_id)
                        injected += 1
                if injected:
                    print(f"  [冠军保留] 注入 {injected} 个上轮冠军策略")

            t_pass = [e for e in t_evals if e.decision != "REJECT"]
            mr_pass = [e for e in mr_evals if e.decision != "REJECT"]
            all_pass = t_pass + mr_pass
            print(f"\n[评估] 通过 {len(all_pass)} 个（趋势{len(t_pass)}+均值回归{len(mr_pass)}）")

            # 更新 best-ever 注册表（跨轮次保留最优参数）
            id_to_cand = {c['strategy_id']: c for c in t_cands + mr_cands}
            for e in t_evals + mr_evals:
                if e.decision == 'REJECT':
                    continue
                cand = id_to_cand.get(e.strategy_id, {})
                tk = cand.get('template_key', '') or e.template_key
                if tk and e.composite > self._best_ever.get(tk, {}).get('score', -999):
                    self._best_ever[tk] = {
                        'params': dict(e.params),
                        'portfolio_params': dict(cand.get('portfolio_params', {})),
                        'score': e.composite,
                    }

            # 更新冠军注册表：保留 top-3 非REJECT策略用于下轮注入
            self._champion_evals = sorted(
                [e for e in t_evals + mr_evals if e.decision != "REJECT"],
                key=lambda e: float(e.composite), reverse=True
            )[:3]

            if not all_pass:
                print("  ⚠️ 无候选通过，跳过本轮"); continue

            # TODO: news_sentiment 尚未接入真实搜索 API，暂时跳过
            # 待实现：接入 SerpAPI / Bing Search API 获取真实新闻后再启用
            sent   = {"sentiment_score": 0.0, "sentiment_label": "NEUTRAL",
                      "confidence": 0.0, "top_stories": [], "market_tips": [],
                      "explanation": "news_sentiment 未启用（TODO）"}
            regime = None   # 移除 MarketRegimeExpert：策略不依赖实时市场判断
            self.bb.write("News", rnd, "sentiment", sent)

            # 对抗辩论
            _t_debate = time.perf_counter()
            debate = self.debate_manager.conduct_debate(t_pass, mr_pass, regime, [], rnd)
            _dt_debate = time.perf_counter() - _t_debate
            DebateManager.print_debate(debate, rnd)

            # 风险评估
            risk_results = self.risk_expert.analyze_batch([
                (e.strategy_name, e.params,
                 e.daily_returns if hasattr(e,"daily_returns") and e.daily_returns else [],
                 e.total_trades) for e in all_pass
            ])
            print(f"\n[风险]")
            for r in risk_results:
                ico = {"LOW":"L","MEDIUM":"M","HIGH":"H","VERY_HIGH":"VH"}.get(r.risk_rating,"?")
                print(f"  [{ico}] {r.strategy_name}: {r.risk_rating} VaR99={r.var_99}%")

            # 组合权重
            portfolio = self._build_portfolio(debate, all_pass, risk_results, regime)

            # 相关性校验
            corr_map = compute_correlation_matrix(all_pass)
            if corr_map:
                print(f"\n[相关性] 发现 {len(corr_map)} 对高相关策略")
                portfolio = apply_correlation_penalty(portfolio, all_pass, corr_map)

            final = list(portfolio.values())[:self.top_n]
            for e in final:
                e.weight = portfolio.get(e.strategy_id, 0.0)

            print(f"\n[结果] 入选 {len(final)} 个策略：")
            for e in final:
                w = float(e.weight) if isinstance(e.weight, (int, float)) and e.weight >= 0 else 0.0
                print(f"  · {e.strategy_name}({e.strategy_type}) 分={float(e.composite):.1f} 权重={w:.1%}")

            # Paper Trade 验证
            holdout_ok = []
            if rnd > 1:
                holdout_ok = self._holdout_validate(final, symbols_data[0], regime)
                if holdout_ok:
                    avg_bias = sum(r["bias"] for r in holdout_ok) / len(holdout_ok)
                    print(f"\n[OOS验证] 样本外{OOS_DAYS}天（Walk-Forward）：")
                    for hr in holdout_ok:
                        ok = hr["oospct"] > 0 and hr["bias"] > -abs(hr["in_pct"]) * 0.8
                        flag = "✅" if ok else "⚠️"
                        print(f"  {flag} {hr['name']}: "
                              f"样本外={hr['oospct']:+.1f}% | 训练内={hr['in_pct']:+.1f}% | "
                              f"衰减={hr['bias']:+.1f}%")
                    print(f"  平均OOS年化：{avg_bias + sum(r['in_pct'] for r in holdout_ok)/len(holdout_ok):+.1f}%"
                          f"  平均衰减：{avg_bias:+.1f}%")

            # 元监控快照
            snap = make_snapshot(rnd, t_evals, mr_evals, debate, risk_results, sent, regime)
            self.monitor.record_round(snap)

            # 收敛判断：基于 all_pass（不只是 final 前4名），5轮无提升才收敛
            NO_IMPROVE_THRESHOLD = 5
            top_score = max((float(getattr(e, "composite", 0)) for e in all_pass), default=0.0)
            if top_score > self.best_score + 0.1:
                self.best_score = top_score
                self.no_improve = 0
                print(f"\n[收敛] 冠军分提升至 {top_score:.1f}")
            else:
                self.no_improve += 1
                print(f"\n[收敛] 冠军分未提升（{self.no_improve}/{NO_IMPROVE_THRESHOLD}），"
                      f"当前最高={top_score:.1f} 历史={self.best_score:.1f}")
            converged = (self.no_improve >= NO_IMPROVE_THRESHOLD)

            # ── LLM 元专家评估（每轮，可覆盖收敛判断）─────────────
            round_strats = [eval_to_strat_dict(e) for e in t_evals + mr_evals]
            _t_meta = time.perf_counter()
            meta_eval = self.monitor.llm_evaluate_round(round_strats, self.best_score, self.no_improve)
            _dt_meta = time.perf_counter() - _t_meta
            _meta_ok = meta_eval.get("_llm_available", False)
            if meta_eval.get("_llm_failed"):
                print(f"\n[元专家] ❌ LLM失败（3次重试均失败）：{meta_eval.get('key_insight','')}")
                print(f"[元专家] 本轮收敛判断将完全依赖规则，无LLM干预")
            elif _meta_ok:
                print(f"\n[元专家] {meta_eval.get('round_summary','')}")
                if meta_eval.get("key_insight"):
                    print(f"[元专家] 关键发现：{meta_eval['key_insight']}")
                if not meta_eval.get("convergence_is_real", True) and converged:
                    print(f"[元专家] ⚠️ 判定当前收敛为假象（{meta_eval.get('continue_reason','')}），重置计数器")
                    converged = False
                    self.no_improve = 0

            # ── 元专家动态参数规划（为下一轮准备）─────────────
            self._meta_history["total_candidates"] += len(t_evals) + len(mr_evals)
            self._meta_history["total_accepted"] += len(t_pass) + len(mr_pass)
            self._meta_history["total_rejected"] += (len(t_evals) + len(mr_evals)) - (len(t_pass) + len(mr_pass))

            if rnd < self.max_rounds and not converged:
                _t_plan = time.perf_counter()
                round_data = {
                    "round": rnd,
                    "top_score": round(top_score, 1),
                    "accepted": len(t_pass) + len(mr_pass),
                    "rejected": (len(t_evals) + len(mr_evals)) - (len(t_pass) + len(mr_pass)),
                    "total": len(t_evals) + len(mr_evals),
                    "trend_accepted": len(t_pass),
                    "mr_accepted": len(mr_pass),
                    "zero_trade_count": sum(1 for e in t_evals + mr_evals if getattr(e, "total_trades", 0) == 0),
                    "avg_trades": sum(getattr(e, "total_trades", 0) for e in t_evals + mr_evals) / max(len(t_evals) + len(mr_evals), 1),
                    "avg_score": round(sum(e.composite for e in t_evals + mr_evals) / max(len(t_evals) + len(mr_evals), 1), 1),
                }
                plan = self.monitor.llm_plan_next_round(round_data, {
                    "best_score": self.best_score,
                    "no_improve": self.no_improve,
                    "completed_rounds": rnd,
                    **self._meta_history,
                })
                _dt_plan = time.perf_counter() - _t_plan

                if plan.get("_llm_available"):
                    new_params = plan.get("next_round_params", {})
                    old_t = self._meta_params["trend_candidates"]
                    old_mr = self._meta_params["mr_candidates"]
                    old_acc = self._meta_params["accept_threshold"]
                    self._meta_params.update(new_params)

                    # 同步更新 evaluator 的门槛
                    self.evaluator.ACCEPT_THRESHOLD = self._meta_params["accept_threshold"]
                    self.evaluator.CONDITIONAL_THRESHOLD = self._meta_params["conditional_threshold"]

                    # 同步更新 portfolio 搜索空间
                    self._PORTFOLIO_PARAM_RANGES["n_stocks"] = list(range(
                        self._meta_params["n_stocks_min"],
                        self._meta_params["n_stocks_max"] + 1
                    ))
                    if "rebalance_options" in new_params:
                        self._PORTFOLIO_PARAM_RANGES["rebalance_freq"] = new_params["rebalance_options"]

                    changes = []
                    if old_t != self._meta_params["trend_candidates"]:
                        changes.append(f"趋势候选 {old_t}→{self._meta_params['trend_candidates']}")
                    if old_mr != self._meta_params["mr_candidates"]:
                        changes.append(f"MR候选 {old_mr}→{self._meta_params['mr_candidates']}")
                    if abs(old_acc - self._meta_params["accept_threshold"]) > 0.1:
                        changes.append(f"ACCEPT门槛 {old_acc}→{self._meta_params['accept_threshold']}")
                    if changes:
                        print(f"\n[元专家-规划] 下轮参数调整: {'；'.join(changes)}")
                    print(f"[元专家-规划] 理由: {plan.get('reasoning', '')}")
                    if plan.get("traps_detected"):
                        print(f"[元专家-规划] 检测陷阱: {', '.join(plan['traps_detected'])}")
                else:
                    print(f"\n[元专家-规划] ⚠️ LLM不可用，保持当前参数")

                rp_meta_plan = plan
            else:
                _dt_plan = 0
                rp_meta_plan = {}

            _dt_rnd = time.perf_counter() - _t_rnd
            _rnd_times.append(_dt_rnd)
            print(f"\n[Profiling] 第{rnd}轮总耗时 {_dt_rnd:.1f}s  "
                  f"回测={_dt_bt:.1f}s  辩论={_dt_debate:.1f}s  元专家={_dt_meta:.1f}s  规划={_dt_plan:.1f}s")

            rp = RoundReportFake(rnd)
            rp.meta_evaluation = meta_eval
            rp.trend_evals   = t_evals
            rp.mr_evals      = mr_evals
            rp.trend_reports = t_reports
            rp.mr_reports    = mr_reports
            rp.final_selected = final
            rp.converged     = converged
            rp.debate_result = debate
            rp.holdout_results = holdout_ok
            self.round_reports.append(rp)

            if converged:
                print("\n✅ 冠军策略连续3轮未提升，已收敛"); break

        if _rnd_times:
            print(f"\n[Profiling] 总计 {len(_rnd_times)} 轮  "
                  f"总耗时={sum(_rnd_times):.1f}s  "
                  f"均值={sum(_rnd_times)/len(_rnd_times):.1f}s/轮  "
                  f"CPU核={_N_BT_WORKERS}")

        if self.monitor.should_report():
            meta = self.monitor.generate_report(self.round_reports)
            MetaMonitor.print_report(meta)

        # ── 元专家架构评审（终止后）─────────────────────────────
        print("\n" + "="*68)
        print("  🏗️ 元专家架构评审中...")
        print("="*68)

        arch_desc = """六层量化系统架构:
1. 数据层: Stooq.com(主) + akshare(A股备选)，支持本地缓存，300天历史K线
2. 因子库(factor_library.py): 32个技术因子，含缠论、Ichimoku、AD线等，支持10种template_key打分
3. 策略库: 趋势(10种template) + 均值回归(8种template)，每轮30+25候选，参数空间随机+反馈调参
4. 专家系统: E1A趋势/E1B均值回归/E1C公开策略收集/E2评估(PBO门控+Sortino/Calmar/IR/DD四维评分)/E3A+B LLM辩论(MiniMax API)/E4组合权重(相关性惩罚)/META元监控
5. 回测系统: PortfolioBacktester多股组合回测(因子打分→选股→权重分配→再平衡)，支持equal/score_weighted/vol_inverse三种权重方式
6. 看板系统: React Dashboard + GitHub Pages 自动部署

关键设计:
- 结构化反馈(StructuredFeedback): Weakness枚举+AdjustmentDirection枚举，机器可解析
- PBO过拟合检测: 概率>0.6拒绝，>0.3打折
- Walk-Forward验证: expanding/rolling/purged三种模式
- 元专家(MetaMonitor): LLM驱动的动态参数规划和收敛判断
- 组合回测: 多股持仓+跨截面因子排名+交易成本建模(买0.08%卖0.18%)"""
        arch_review = self.monitor.llm_architecture_review(arch_desc, {
            "total_rounds": len(self.round_reports),
            "best_score": round(self.best_score, 1),
            "total_candidates": self._meta_history["total_candidates"],
            "total_accepted": self._meta_history["total_accepted"],
            "total_rejected": self._meta_history["total_rejected"],
            "final_top": [
                {"name": e.strategy_name, "score": round(e.composite, 1),
                 "type": e.strategy_type, "trades": e.total_trades,
                 "ann": round(e.annualized_return, 1), "dd": round(e.max_drawdown_pct, 1)}
                for e in (self.round_reports[-1].final_selected if self.round_reports else [])
            ],
        })

        if arch_review.get("_llm_available"):
            rating = arch_review.get("overall_rating", "N/A")
            print(f"\n[架构评审] 总体评级: {rating}")
            print(f"[架构评审] 优势: {'；'.join(arch_review.get('strengths', [])[:3])}")
            print(f"[架构评审] 关键问题: {'；'.join(arch_review.get('critical_issues', [])[:3])}")
            print(f"[架构评审] 下次重点: {arch_review.get('next_iteration_focus', '')}")
            for prio in arch_review.get("improvement_priorities", [])[:5]:
                print(f"  [{prio.get('priority','?')}] {prio.get('area','')}: {prio.get('action','')} → {prio.get('impact','')}")
        else:
            print("\n[架构评审] ⚠️ LLM不可用，跳过架构评审")

        self._architecture_review = arch_review

        self._save_search_state()

        final_report = generate_final_report(self.round_reports, self.top_n, self.symbols)
        final_report["meta_architecture_review"] = arch_review
        save_report(final_report)
        print_final_report(final_report)
        return final_report

    # ── 搜索状态持久化 ────────────────────────────────────────────────

    _STATE_PATH = Path("results/search_state.json")

    def _load_search_state(self):
        if not self._STATE_PATH.exists():
            return
        try:
            state = json.loads(self._STATE_PATH.read_text(encoding="utf-8"))
            self._seen_cand_hashes = set(state.get("seen_hashes", []))
            self._best_ever = state.get("best_ever", {})
            self._preloaded_feedback = state.get("feedback_history", [])
            print(f"[搜索状态] 恢复: {len(self._seen_cand_hashes)} 个已探索 hash，"
                  f"{len(self._best_ever)} 个最优参数记录，"
                  f"{len(self._preloaded_feedback)} 条历史反馈")
        except Exception as e:
            print(f"[搜索状态] 加载失败，从空状态开始: {e}")

    def _save_search_state(self):
        self._STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        current_fb = self.evaluator.fb_history.to_serializable_list()
        merged_fb = (self._preloaded_feedback + current_fb)[-200:]
        state = {
            "saved_at":        datetime.now().isoformat(),
            "seen_hashes":     sorted(self._seen_cand_hashes),
            "best_ever":       self._best_ever,
            "feedback_history": merged_fb,
        }
        self._STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[搜索状态] 已保存: {len(self._seen_cand_hashes)} 个 hash，"
              f"{len(self._best_ever)} 个最优参数，"
              f"{len(merged_fb)} 条反馈历史 → {self._STATE_PATH}")

    # ── 多样性约束生成 ─────────────────────

    # ── 多标的回测（选股核心）─────────────────────────────────────
    def _backtest_multi_symbol(self, expert, cands, symbols_data):
        """
        每个候选策略在所有标的上独立回测，保留最佳标的结果。
        使用 ProcessPoolExecutor 并行（workers = CPU 核数）。
        symbols_data 通过 initializer 只序列化一次，避免重复 pickle 开销。
        """
        from concurrent.futures import ProcessPoolExecutor
        sym_list = (
            [sd["symbol"] for sd in symbols_data]
            if isinstance(symbols_data[0], dict) and "symbol" in symbols_data[0]
            else [f"sym{i}" for i in range(len(symbols_data))]
        )

        n_workers = min(_N_BT_WORKERS, len(cands))
        t0 = time.perf_counter()
        with ProcessPoolExecutor(
            max_workers=n_workers,
            initializer=_init_backtest_worker,
            initargs=(symbols_data, sym_list),
        ) as pool:
            raw = list(pool.map(_backtest_one_cand, [(expert, c) for c in cands]))
        dt = time.perf_counter() - t0
        print(f"  [Profiling] 回测 {len(cands)}个×{len(sym_list)}标的  "
              f"并行={n_workers}核  耗时={dt:.2f}s  "
              f"({dt/len(cands)*1000:.0f}ms/候选)")

        results = []
        for best_report, c in zip(raw, cands):
            if best_report is None:
                from experts.specialists.expert1a_trend import BacktestReport
                best_report = BacktestReport(
                    strategy_id=c["strategy_id"], strategy_name=c["strategy_name"])
            best_report.strategy_id   = c["strategy_id"]
            best_report.strategy_type = c["strategy_type"]
            best_report.template_key  = c.get("template_key", "")
            sym_tag = getattr(best_report, "_best_symbol", "")
            if sym_tag and sym_tag not in best_report.strategy_name:
                best_report.strategy_name = f"{best_report.strategy_name}({sym_tag})"
            results.append(best_report)
        return results

    # 全量参数搜索空间（宽范围随机探索）
    _PARAM_RANGES = {
        # ── 原有趋势策略 ─────────────────────────────────────────────
        "ma_cross":          {"fast": (5, 60),    "slow": (20, 250)},
        "macd":              {"fp":   (5, 20),    "sp":   (15, 60),  "sig": (5, 15)},
        "momentum":          {"lookback": (5, 80), "threshold": (0.01, 0.15)},
        "adx_trend":         {"adx_thr": (15, 40), "atr_mult": (1.0, 4.5)},
        # ── 新接入趋势策略（quant独有）────────────────────────────────
        "ichimoku_signal":   {"tenkan": (5, 20),  "kijun": (15, 55)},
        "kst":               {"r1": (5, 15),      "r2": (10, 20)},
        "trix":              {"period": (8, 30)},
        "donchian_breakout": {"period": (10, 60)},
        "aroon_signal":      {"period": (10, 50)},
        # ── 原有均值回归策略 ──────────────────────────────────────────
        "rsi":               {"period": (5, 30),   "lower": (15, 40), "upper": (60, 85)},
        "bband":             {"period": (10, 60),  "num_std": (1.2, 3.5)},
        "bollinger":         {"period": (10, 60),  "std_mult": (1.2, 3.5)},
        "vol_surge":         {"vol_ma": (10, 40),  "threshold": (1.5, 4.0)},
        # ── 新接入均值回归策略（quant独有）────────────────────────────
        "mfi_signal":        {"period": (7, 28),   "lower": (10, 35), "upper": (65, 90)},
        "rvi_signal":        {"period": (5, 20)},
        "kdwave":            {"fastk": (5, 18),    "slowk": (2, 6)},
        "multi_roc_signal":  {"p1": (5, 15),       "p2": (15, 30),    "p3": (25, 60)},
        "obos_composite":    {"period": (10, 40)},
        "elder_ray_signal":  {"ema_period": (8, 26)},
        # ── 创新趋势策略 ─────────────────────────────────────────────
        "smart_money":       {"period": (10, 40),   "vol_weight": (1.0, 3.0)},
        "gap_break":         {"min_gap_pct": (0.01, 0.05), "lookback": (5, 20)},
        "limit_board":       {"gain_thr": (0.05, 0.10),    "lookback": (5, 30)},
        "trend_composite":   {"ma_fast": (5, 20), "ma_slow": (20, 60), "mom_period": (10, 30), "vol_period": (10, 30)},
        # ── 创新均值回归策略 ──────────────────────────────────────────
        "lanban_fade":       {"limit_thr": (0.06, 0.10), "fade_days": (1, 7), "confirm_days": (1, 5)},
        "vol_price_diverge": {"lookback": (10, 40),     "sensitivity": (0.5, 2.0)},
        "multi_signal_combo":{"rsi_period": (7, 21), "rsi_lower": (25, 45), "bb_period": (10, 30), "vol_surge_thr": (1.2, 3.0)},
        "mean_rev_composite":{"period": (10, 40),     "z_enter": (1.0, 2.5), "z_exit": (0.2, 1.0)},
    }

    @staticmethod
    def _cand_hash(template_key: str, params: dict,
                   portfolio_params: dict = None) -> str:
        """Similarity hash: bucket continuous params to nearest 5% step.
        Includes portfolio_params so same strategy with different portfolio
        config is treated as a distinct candidate.
        """
        def _bucket(v):
            if isinstance(v, float): return round(v * 20) / 20  # 0.05 buckets
            if isinstance(v, int):   return round(v / 3) * 3     # nearest-3 buckets
            return v
        bucketed = {k: _bucket(v) for k, v in sorted(params.items())
                    if not str(k).startswith("pf_")}
        pp_key = ""
        if portfolio_params:
            pp_key = f"|N{portfolio_params.get('n_stocks',1)}" \
                     f"R{portfolio_params.get('rebalance_freq',20)}" \
                     f"{portfolio_params.get('weight_method','equal')[0]}"
        return f"{template_key}|{bucketed}{pp_key}"

    def _dedup_candidates(self, cands: list, rng: random.Random) -> list:
        """Remove candidates whose similarity hash already exists in _seen_cand_hashes.
        Replace duplicates with a fresh random candidate of the same template type.
        """
        templates_map = {t["key"]: t for t in
                         getattr(self.trend_expert, "TEMPLATES", []) +
                         getattr(self.mr_expert,    "TEMPLATES", [])}
        result = []
        for c in cands:
            pp = c.get("portfolio_params", {})
            h = self._cand_hash(c["template_key"], c["params"], pp)
            if h in self._seen_cand_hashes:
                tpl = templates_map.get(c["template_key"])
                replaced = False
                for _ in range(5):
                    fp = self._fresh_random_params(c["template_key"], rng) if tpl else {}
                    if not fp:
                        fp = self._randomize(dict(tpl["params"] if tpl else {}), 0.5, rng)
                    nh = self._cand_hash(c["template_key"], fp, pp)
                    if nh not in self._seen_cand_hashes:
                        nc = dict(c); nc["params"] = fp
                        nc["diversity_note"] = (c.get("diversity_note", "") or "") + "+去重"
                        result.append(nc)
                        self._seen_cand_hashes.add(nh)
                        replaced = True
                        break
                if not replaced:
                    result.append(c)
                    self._seen_cand_hashes.add(h)
            else:
                result.append(c)
                self._seen_cand_hashes.add(h)
        return result

    def _fresh_random_params(self, template_key: str, rng: random.Random) -> dict:
        """从宽范围均匀采样参数，远比 ±30% 扰动更多样"""
        ranges = self._PARAM_RANGES.get(template_key, {})
        if not ranges:
            return {}
        out = {}
        for k, (lo, hi) in ranges.items():
            if isinstance(lo, int) and isinstance(hi, int):
                out[k] = rng.randint(lo, hi)
            else:
                out[k] = round(rng.uniform(lo, hi), 4)
        # ma_cross: 保证 fast < slow
        if template_key == "ma_cross" and "fast" in out and "slow" in out:
            if out["fast"] >= out["slow"]:
                out["slow"] = out["fast"] + rng.randint(10, 80)
        return out

    def _generate_diverse_candidates(self, expert, count, fb_list, need_div, stype, rnd=1):
        rng      = random.Random(self.seed + hash(stype) + rnd * 1013)
        out      = []
        type_fbs = [f for f in fb_list if f.get("strategy_type") == stype]

        # 统计已尝试的 template_key，连续失败的降优先级
        failed_templates = {}
        for f in type_fbs:
            tk = f.get("template_key", "")
            w  = f.get("weakness", "none")
            if w not in ("none", "") and tk:
                failed_templates[tk] = failed_templates.get(tk, 0) + 1

        # 获取专家的所有模板
        templates = getattr(expert, "TEMPLATES", [])
        tpl_keys  = [t["key"] for t in templates]

        # Per-template cap: no single template can take more than 40% of slots
        _tpl_cap = max(2, round(count * 0.40 / max(len(tpl_keys), 1)))
        _tpl_count: dict = {}  # template_key → count in `out`

        def _tpl_ok(key):
            return _tpl_count.get(key, 0) < _tpl_cap

        def _pick_tpl_with_cap(preferred_key):
            """Return preferred if under cap, else next uncapped template by weight."""
            if _tpl_ok(preferred_key):
                return preferred_key
            # Fallback: pick first uncapped template (by failed_templates weight descending)
            for k in sorted(tpl_keys, key=lambda k: failed_templates.get(k, 0)):
                if _tpl_ok(k):
                    return k
            return preferred_key  # all capped, allow overflow

        # ── 1/3 宽范围随机探索（不依赖默认参数，全空间采样）──────────
        n_rand = max(1, round(count * 0.35))
        for i in range(n_rand):
            # 失败次数多的模板降采样频率
            weights = [max(0.05, 1.0 / (1 + failed_templates.get(k, 0) * 1.5))
                       for k in tpl_keys]
            total_w = sum(weights)
            weights = [w / total_w for w in weights]
            # 加权随机选模板
            pick_r  = rng.random()
            chosen_key = tpl_keys[-1]
            acc = 0.0
            for k, w in zip(tpl_keys, weights):
                acc += w
                if pick_r <= acc:
                    chosen_key = k
                    break
            chosen_key = _pick_tpl_with_cap(chosen_key)
            tpl  = next((t for t in templates if t["key"] == chosen_key), templates[i % len(templates)])
            fresh_params = self._fresh_random_params(tpl["key"], rng)
            if not fresh_params:
                fresh_params = self._randomize(dict(tpl["params"]), 0.5, rng)
            import uuid
            c = {
                "strategy_id":   f"{stype[:2]}_{uuid.uuid4().hex[:8]}",
                "strategy_type": stype,
                "strategy_name": tpl["name"],
                "template_key":  tpl["key"],
                "params":        fresh_params,
                "tags":          [tpl["name"]],
                "diversity_note": f"宽范围随机({tpl['key']})",
            }
            out.append(c)
            _tpl_count[tpl["key"]] = _tpl_count.get(tpl["key"], 0) + 1

        # ── 1/3 结构化反馈调参（每个反馈给不同处方）─────────────────
        n_fb = max(1, round(count * 0.35))
        if type_fbs:
            # 取分数最高的 n_fb 条反馈（而非最近的），每条产生一个候选
            top_fbs = sorted(type_fbs, key=lambda f: f.get("composite", 0), reverse=True)[:n_fb]
            for fb in top_fbs:
                tk   = _pick_tpl_with_cap(fb.get("template_key", tpl_keys[0]))
                tpl  = next((t for t in templates if t["key"] == tk), templates[0])
                # 以历史最优参数为基础（非模板默认值），保持参数进化方向
                base_params = dict(self._best_ever.get(tk, {}).get('params', tpl["params"]))
                params = self._apply_sf_adjustment(base_params, fb)
                # 再叠加小扰动，避免和默认值完全相同
                params = self._randomize(params, 0.15, rng)
                import uuid
                c = {
                    "strategy_id":   f"{stype[:2]}_{uuid.uuid4().hex[:8]}",
                    "strategy_type": stype,
                    "strategy_name": tpl["name"],
                    "template_key":  tpl["key"],
                    "params":        params,
                    "tags":          [tpl["name"]],
                    "diversity_note": f"反馈({fb.get('adjustment','?')}/{fb.get('param','?')})",
                }
                out.append(c)
                _tpl_count[tk] = _tpl_count.get(tk, 0) + 1
        else:
            # 无反馈时额外随机
            for _ in range(n_fb):
                tpl = rng.choice(templates)
                c   = expert.generate_candidates(1, None)[0]
                c["params"] = self._fresh_random_params(tpl["key"], rng) or self._randomize(dict(tpl["params"]), 0.4, rng)
                c["diversity_note"] = "无反馈随机"
                out.append(c)

        # ── 剩余：Exploitation（对历史最优参数做邻域搜索）──────────
        while len(out) < count:
            if type_fbs:
                # Pick highest-scoring feedback whose template is still under cap
                sorted_fbs = sorted(type_fbs, key=lambda f: f.get("composite", 0), reverse=True)
                best = next((f for f in sorted_fbs if _tpl_ok(f.get("template_key",""))), sorted_fbs[0])
                tk   = _pick_tpl_with_cap(best.get("template_key", tpl_keys[0]))
                tpl  = next((t for t in templates if t["key"] == tk), templates[0])
                # 以历史最优参数为基础（非模板默认值）
                base_params = dict(self._best_ever.get(tk, {}).get('params', tpl["params"]))
                params = self._apply_sf_adjustment(base_params, best)
                params = self._randomize(params, 0.20, rng)
            else:
                chosen = _pick_tpl_with_cap(rng.choice(tpl_keys))
                tpl    = next((t for t in templates if t["key"] == chosen), templates[0])
                params = self._fresh_random_params(tpl["key"], rng) or dict(tpl["params"])
            import uuid
            c = {
                "strategy_id":   f"{stype[:2]}_{uuid.uuid4().hex[:8]}",
                "strategy_type": stype,
                "strategy_name": tpl["name"],
                "template_key":  tpl["key"],
                "params":        params,
                "tags":          [tpl["name"]],
                "diversity_note": "Exploitation邻域",
            }
            out.append(c)
            _tpl_count[tpl["key"]] = _tpl_count.get(tpl["key"], 0) + 1

        # ── 为每个候选注入 portfolio_params（可变异的组合参数）──────
        for c in out:
            c["portfolio_params"] = self._sample_portfolio_params(
                c, rng, fb_list,
            )

        return out[:count]

    # ── 组合参数搜索空间 ─────────────────────────────────────────────
    _PORTFOLIO_PARAM_RANGES = {
        "n_stocks":         [2, 3, 5],              # 同时持仓数量（最低2只）
        "rebalance_freq":   [5, 10, 20, 60],         # 调仓间隔（交易日）
        "weight_method":    ["equal", "score_weighted", "vol_inverse"],
        "max_position_pct": (0.30, 1.00),            # 单股最大仓位
    }

    def _sample_portfolio_params(self, cand: dict, rng: random.Random,
                                  fb_list: list) -> dict:
        """
        为候选策略随机采样组合参数。
        有 50% 概率以历史最优组合参数为基础做小扰动（保持参数记忆）。
        """
        ranges = self._PORTFOLIO_PARAM_RANGES
        tk = cand.get("template_key", "")
        best_pp = self._best_ever.get(tk, {}).get('portfolio_params', {})

        if best_pp and rng.random() < 0.5:
            # 以历史最优组合参数为基础，做小幅扰动
            n_opts = ranges["n_stocks"]
            r_opts = ranges["rebalance_freq"]
            curr_n = best_pp.get('n_stocks', n_opts[0])
            curr_r = best_pp.get('rebalance_freq', r_opts[0])
            n_idx = n_opts.index(curr_n) if curr_n in n_opts else 0
            r_idx = r_opts.index(curr_r) if curr_r in r_opts else 0
            pp = {
                "n_stocks":         n_opts[max(0, min(len(n_opts)-1, n_idx + rng.randint(-1, 1)))],
                "rebalance_freq":   r_opts[max(0, min(len(r_opts)-1, r_idx + rng.randint(-1, 1)))],
                "weight_method":    best_pp.get('weight_method', rng.choice(ranges["weight_method"])),
                "max_position_pct": round(min(1.0, max(0.3,
                    best_pp.get('max_position_pct', 0.6) + rng.uniform(-0.1, 0.1))), 2),
            }
        else:
            # 全随机基础值
            pp = {
                "n_stocks":         rng.choice(ranges["n_stocks"]),
                "rebalance_freq":   rng.choice(ranges["rebalance_freq"]),
                "weight_method":    rng.choice(ranges["weight_method"]),
                "max_position_pct": round(rng.uniform(*ranges["max_position_pct"]), 2),
            }

        # 按历史反馈微调组合参数
        tk = cand.get("template_key", "")
        related_fbs = [f for f in (fb_list or []) if f.get("template_key") == tk]
        if related_fbs:
            best_fb = max(related_fbs, key=lambda f: f.get("composite", 0))
            weakness = best_fb.get("weakness", "")
            # 集中度风险 → 增加持仓数，降低单股仓位
            if "high_drawdown" in weakness or "concentration" in weakness:
                pp["n_stocks"] = min(5, pp["n_stocks"] + 1)
                pp["max_position_pct"] = max(0.3, pp["max_position_pct"] - 0.2)
            # 换手率太高 → 放宽调仓频率
            if "high_turnover" in weakness:
                pp["rebalance_freq"] = min(60, pp["rebalance_freq"] * 2)
            # 波动率高 → 尝试波动率倒数加权
            if "high_volatility" in weakness or "low_sharpe" in weakness:
                pp["weight_method"] = "vol_inverse"
            # 单一策略效果好 → 聚焦单股
            if "low_win_rate" not in weakness and best_fb.get("composite", 0) > 70:
                pp["n_stocks"] = max(1, pp["n_stocks"] - 1)

        return pp

    # ── 生成因子注册 ──────────────────────────────────────────────────

    def _load_generated_factors(self):
        """加载 factor_library 中已生成的因子，注册到专家模板和参数空间"""
        try:
            from experts.factor_library import (
                GENERATED_TEMPLATES, GENERATED_PARAM_RANGES
            )
            for tpl in GENERATED_TEMPLATES:
                key   = tpl["key"]
                stype = tpl.get("type", "trend")
                entry = {"key": key, "name": tpl["name"], "params": tpl.get("params", {})}
                if stype == "trend":
                    if not any(t["key"] == key for t in self.trend_expert.TEMPLATES):
                        self.trend_expert.TEMPLATES.append(entry)
                else:
                    if not any(t["key"] == key for t in self.mr_expert.TEMPLATES):
                        self.mr_expert.TEMPLATES.append(entry)
            for key, ranges in GENERATED_PARAM_RANGES.items():
                if key not in self._PARAM_RANGES:
                    self._PARAM_RANGES[key] = ranges
            if GENERATED_TEMPLATES:
                print(f"[因子库] 注册 {len(GENERATED_TEMPLATES)} 个生成因子到专家模板")
        except Exception as e:
            print(f"[因子库] 加载失败（首次运行时正常）: {e}")

    @staticmethod
    def _sf_to_text(sf):
        adj = sf.get("adjustment",""); param = sf.get("param",""); mag = sf.get("magnitude",0)
        return f"建议{adj}参数{param}" if adj and adj != "none" else ""

    @staticmethod
    def _randomize(params, fraction, rng):
        out = {}
        for k, v in params.items():
            if isinstance(v,(int,float)) and v != 0:
                out[k] = round(v + v*fraction*rng.choice([-1,1]), 4)
            else:
                out[k] = v
        return out

    @staticmethod
    def _apply_sf_adjustment(params, sf):
        p = dict(params)
        adj = sf.get("adjustment",""); pname = sf.get("param","")
        mag = sf.get("magnitude",0); unit = sf.get("unit","")
        if not pname or adj in ("none","diversify",""): return p
        if pname in p and mag != 0:
            if unit == "倍":   p[pname] = round(p[pname]*mag, 4)
            elif unit == "天": p[pname] = max(1, int(p[pname]+mag))
            else:              p[pname] = round(p[pname]*((100+mag)/100), 4)
        return p

    def _apply_sf_to_candidates(self, candidates, t_reports, mr_reports):
        m = {r.strategy_id: r for r in t_reports + mr_reports}
        for c in candidates:
            r = m.get(c["strategy_id"])
            if r and hasattr(r, "structured_feedback") and r.structured_feedback:
                c["_sf"] = r.structured_feedback.to_simple_dict()

    # ── Paper Trade ────────────────────────

    def _holdout_validate(self, selected, primary_data, regime):
        """读取引擎已计算好的 oos_annualized_return，构造 holdout 报告。"""
        results = []
        for e in selected:
            oos_pct = round(getattr(e, "oos_annualized_return", 0.0), 2)
            in_pct  = round(getattr(e, "annualized_return",     0.0), 2)
            bias    = round(oos_pct - in_pct, 1)
            results.append({"name": e.strategy_name, "oospct": oos_pct,
                            "in_pct": in_pct, "bias": bias})
        return results

    # ── 组合构建 ─────────────────────────

    def _build_portfolio(self, debate, pass_evals, risk_results, regime):
        risk_map = {r.strategy_name: r.risk_rating for r in risk_results}
        tw = debate.trend_weight; mw = debate.mr_weight
        max_pos = (regime.max_position_pct if regime else 0.50)
        def allocate(items, bw):
            if not items: return {}
            total = sum(e.composite for e,_ in items) or 1
            out = {}
            for e, risk in items:
                w = bw*(e.composite/total)
                if risk=="HIGH":     w*=0.7
                elif risk=="MEDIUM": w*=0.9
                out[e.strategy_id] = round(w,4)
            return out
        trend_items = [(e,risk_map.get(e.strategy_name,"MEDIUM")) for e in pass_evals if e.strategy_type=="trend"]
        mr_items    = [(e,risk_map.get(e.strategy_name,"MEDIUM")) for e in pass_evals if e.strategy_type=="mean_reversion"]
        tw_map = allocate(trend_items, tw)
        mw_map = allocate(mr_items, mw)
        all_ids = set(tw_map)|set(mw_map)
        total_w = sum(tw_map.get(s,0)+mw_map.get(s,0) for s in all_ids) or 1
        weights = {sid: round((tw_map.get(sid,0)+mw_map.get(sid,0))/total_w*max_pos, 4) for sid in all_ids}
        result  = {}
        for e in pass_evals:
            w = weights.get(e.strategy_id, 0.0)
            e.weight = float(w) if isinstance(w, float) else 0.0
            result[e.strategy_id] = e
        return result

    # ── 数据加载（实盘 + 腾讯API）───────────────









class RoundReportFake:
    def __init__(self, rnd):
        self.round_num=rnd; self.timestamp=datetime.now().strftime("%H:%M:%S")
        self.market_regime=None; self.sentiment=None
        self.trend_reports=[]; self.mr_reports=[]
        self.all_reports=[]; self.trend_evals=[]; self.mr_evals=[]
        self.debate_result=None; self.risk_results=[]
        self.final_selected=[]; self.portfolio_weights={}
        self.converged=False; self.holdout_results=[]; self.meta_evaluation={}
        self.meta_plan={}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--symbols",nargs="+",default=["AAPL","NVDA","BTCUSDT","ETHUSDT"])
    p.add_argument("--days",type=int,default=500)
    p.add_argument("--rounds",type=int,default=3)
    p.add_argument("--seed",type=int,default=2026)
    p.add_argument("--top-n",type=int,default=4)
    args = p.parse_args()
    print("🔵 多专家系统 v4.0 启动（仅使用实盘数据）")
    Orchestrator(args.symbols,args.days,args.seed,args.rounds,args.top_n).run()
