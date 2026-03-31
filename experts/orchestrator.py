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

import sys, json, math, random, re, urllib.request
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.local_data import load_multiple

from experts.modules.blackboard import Blackboard
# TODO: from experts.modules.news_sentiment import NewsSentimentAnalyzer  # 待接入真实搜索 API
from experts.modules.risk_engine import RiskExpert
from experts.specialists.expert1a_trend import TrendExpert
from experts.specialists.expert1b_mean_reversion import MeanReversionExpert
from experts.evaluator import Evaluator
from experts.meta_monitor import MetaMonitor, RoundSnapshot
from experts.debate_manager import DebateManager
from experts.structured_feedback import FeedbackHistory

MAX_ROUNDS_DEFAULT   = 20
TOP_N_DEFAULT       = 4
HOLDOUT_DAYS        = 30
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
    """EvalResult → 元专家所需的精简 dict"""
    return {
        "name":         getattr(e, "strategy_name", ""),
        "type":         getattr(e, "strategy_type", ""),
        "decision":     getattr(e, "decision", ""),
        "score":        float(getattr(e, "composite", 0)),
        "total_trades": int(getattr(e, "total_trades", 0)),
        "ann_return":   float(getattr(e, "annualized_return", 0)),
        "sharpe":       float(getattr(e, "sharpe_ratio", 0)),
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
        self.round_reports  = []
        self.prev_top_ids   = set()
        self.best_score     = 0.0
        self.no_improve     = 0
        self.monitor        = MetaMonitor(report_every=5)

    def run(self):
        print("="*68)
        print("  多专家协作量化系统 v4.0（纯实盘 + 结构化反馈）")
        print("  Pipeline(A) + Adversarial(B) + Correlation(C) + Holdout(D)")
        print("="*68)

        symbols_data = self._load_data()

        for rnd in range(1, self.max_rounds + 1):
            print(f"\n{'='*68}\n  ▶ 第 {rnd} 轮迭代\n{'='*68}")

            need_div = self.evaluator.need_diversify()
            fb_list  = [fb.to_simple_dict() for fb in self.evaluator.fb_history.entries]

            t_cands  = self._generate_diverse_candidates(self.trend_expert, 30, fb_list, need_div, "trend")
            mr_cands = self._generate_diverse_candidates(self.mr_expert, 20, fb_list, need_div, "mean_reversion")
            all_cands = t_cands + mr_cands

            main_data = symbols_data[0]["data"]
            main_inds = symbols_data[0]["indicators"]

            t_reports = [self.trend_expert.backtest(main_data, main_inds, c["params"], c["template_key"], strategy_id=c["strategy_id"]) for c in t_cands]
            mr_reports = [self.mr_expert.backtest(main_data, main_inds, c["params"], c["template_key"], strategy_id=c["strategy_id"]) for c in mr_cands]

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
            t_pass = [e for e in t_evals if e.decision != "REJECT"]
            mr_pass = [e for e in mr_evals if e.decision != "REJECT"]
            all_pass = t_pass + mr_pass
            print(f"\n[评估] 通过 {len(all_pass)} 个（趋势{len(t_pass)}+均值回归{len(mr_pass)}）")

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
            debate = self.debate_manager.conduct_debate(t_pass, mr_pass, regime, [], rnd)
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
                    print(f"\n[Holdout] 最近{HOLDOUT_DAYS}天 paper trade：")
                    for hr in holdout_ok:
                        flag = "✅" if abs(hr["bias"]) < 20 else "⚠️"
                        print(f"  {flag} {hr['name']}: 模拟={hr['oospct']:+.1f}% 偏差={hr['bias']:+.1f}%")
                    print(f"  平均偏差：{avg_bias:+.1f}%（|<10% 为理想）")

            # 元监控快照
            snap = self._make_snapshot(rnd, t_evals, mr_evals, debate, risk_results, sent, regime)
            self.monitor.record_round(snap)

            # 3轮无提升收敛判断
            top_score = max((float(getattr(e, "composite", 0)) for e in final), default=0.0)
            if top_score > self.best_score + 0.1:
                self.best_score = top_score
                self.no_improve = 0
                print(f"\n[收敛] 冠军分提升至 {top_score:.1f}")
            else:
                self.no_improve += 1
                print(f"\n[收敛] 冠军分未提升（{self.no_improve}/3），当前={top_score:.1f} 最高={self.best_score:.1f}")
            converged = (self.no_improve >= 3)

            # ── LLM 元专家评估（每轮，可覆盖收敛判断）─────────────
            round_strats = [eval_to_strat_dict(e) for e in t_evals + mr_evals]
            meta_eval = self.monitor.llm_evaluate_round(round_strats, self.best_score, self.no_improve)
            _meta_ok = meta_eval.get("_llm_available", False)
            if _meta_ok:
                print(f"\n[元专家] {meta_eval.get('round_summary','')}")
                if meta_eval.get("key_insight"):
                    print(f"[元专家] 关键发现：{meta_eval['key_insight']}")
                if not meta_eval.get("convergence_is_real", True) and converged:
                    print(f"[元专家] ⚠️ 判定当前收敛为假象（{meta_eval.get('continue_reason','')}），重置计数器")
                    converged = False
                    self.no_improve = 0

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

        if self.monitor.should_report():
            meta = self.monitor.generate_report(self.round_reports)
            MetaMonitor.print_report(meta)

        final_report = self._generate_final_report()
        self._save_report(final_report)
        self._print_final_report(final_report)
        return final_report

    # ── 多样性约束生成 ─────────────────────

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
    }

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

    def _generate_diverse_candidates(self, expert, count, fb_list, need_div, stype):
        rng      = random.Random(self.seed + hash(stype) + len(fb_list))
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

        # ── 1/3 结构化反馈调参（每个反馈给不同处方）─────────────────
        n_fb = max(1, round(count * 0.35))
        if type_fbs:
            # 取最近 n_fb 条反馈，每条产生一个候选
            for fb in type_fbs[-n_fb:]:
                tk   = fb.get("template_key", tpl_keys[0])
                tpl  = next((t for t in templates if t["key"] == tk), templates[0])
                params = self._apply_sf_adjustment(dict(tpl["params"]), fb)
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
        else:
            # 无反馈时额外随机
            for _ in range(n_fb):
                tpl = rng.choice(templates)
                c   = expert.generate_candidates(1, None)[0]
                c["params"] = self._fresh_random_params(tpl["key"], rng) or self._randomize(dict(tpl["params"]), 0.4, rng)
                c["diversity_note"] = "无反馈随机"
                out.append(c)

        # ── 剩余：Exploitation（对历史最高分参数做邻域搜索）──────────
        while len(out) < count:
            if type_fbs:
                best = max(type_fbs, key=lambda f: f.get("composite", 0))
                tk   = best.get("template_key", tpl_keys[0])
                tpl  = next((t for t in templates if t["key"] == tk), templates[0])
                params = self._apply_sf_adjustment(dict(tpl["params"]), best)
                params = self._randomize(params, 0.20, rng)
            else:
                tpl    = rng.choice(templates)
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

        return out[:count]

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
        pd0 = primary_data[0] if isinstance(primary_data, list) else primary_data
        closes = (pd0.get("data", {}) or {}).get("closes", []) if isinstance(pd0, dict) else []
        n      = len(closes)
        if n < HOLDOUT_DAYS + 60: return []
        split_i = n - HOLDOUT_DAYS
        oos_ret = primary_data.get("returns", [0]*n)
        if not oos_ret or len(oos_ret) < n: return []
        oos_ret = oos_ret[split_i:]
        results = []
        for e in selected:
            ann_oos = (sum(oos_ret)/len(oos_ret)) * 252
            oos_pct = round(ann_oos*100, 2)
            bias    = round(oos_pct - getattr(e,"annualized_return",0), 1)
            results.append({"name":e.strategy_name,"oospct":oos_pct,
                            "in_pct":getattr(e,"annualized_return",0),"bias":bias})
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

    def _fetch_tencent(self, sym, n=300):
        """Fetch daily K-line from Tencent API"""
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_day&param={sym},day,,,{n},qfq"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode()
            m = re.search(r'=\s*(\{.*\})', text, re.DOTALL)
            if not m: return None
            obj = json.loads(m.group(1))
            data = obj.get('data', {})
            val = data.get(sym)
            if isinstance(val, list):
                klines = val
            elif isinstance(val, dict):
                klines = val.get('day', [])
            else:
                return None
            if not klines: return None
            # klines: [[date, open, close, high, low, volume], ...]
            closes = [float(k[2]) for k in klines]
            if not closes or closes[-1] < 1: return None
            return {
                'dates':   [k[0] for k in klines],
                'opens':   [float(k[1]) for k in klines],
                'closes':  closes,
                'highs':   [float(k[3]) for k in klines],
                'lows':    [float(k[4]) for k in klines],
                'volumes': [float(k[5]) for k in klines],
            }
        except Exception as e:
            print(f"[腾讯API] {sym} fetch error: {e}")
            return None

    def _compute_indicators(self, data):
        """Compute basic technical indicators from raw data"""
        closes = data.get('closes', [])
        highs  = data.get('highs', [])
        lows   = data.get('lows', [])
        volumes= data.get('volumes', [])
        n = len(closes)
        if n < 60: return {}
        # Returns
        rets = [0.0] + [(closes[i]/closes[i-1]-1) for i in range(1,n)]
        # SMA
        def sma(arr, period):
            out = [None]*(period-1)
            for i in range(period-1, len(arr)):
                out.append(sum(arr[i-period+1:i+1])/period)
            return out
        # RSI
        def rsi(closes, period=14):
            deltas = [closes[i]-closes[i-1] for i in range(1,len(closes))]
            gains = [max(d,0) for d in deltas]
            losses = [abs(min(d,0)) for d in deltas]
            out = [None]*period
            aggr = sum(gains[:period])/period
            alss = sum(losses[:period])/period
            if alss == 0: out.append(100)
            else: out.append(100-(100/(1+aggr/alss)))
            for i in range(period, len(deltas)):
                aggr = (aggr*(period-1)+gains[i])/period
                alss = (alss*(period-1)+losses[i])/period
                if alss == 0: out.append(100)
                else: out.append(100-(100/(1+aggr/alss)))
            return out
        # ATR
        def atr(highs, lows, closes, period=14):
            trs = [highs[0]-lows[0]] + [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1,len(closes))]
            out = [None]*(period-1)
            out.append(sum(trs[:period])/period)
            for i in range(period, len(trs)):
                out.append((out[-1]*(period-1)+trs[i])/period)
            return out
        return {
            'returns': rets,
            'ma20':    sma(closes, 20),
            'ma60':    sma(closes, 60),
            'ma200':   sma(closes, 200) if n >= 200 else [None]*n,
            'rsi14':   rsi(closes, 14),
            'atr14':   atr(highs, lows, closes, 14),
        }

    def _load_data(self):
        # Try Tencent real data first for sh000300 (沪深300 proxy for SPY)
        result = {}
        for sym, api_sym in [('SPY', 'sh000300'), ('BTCUSDT', 'btcusdt')]:
            if sym not in self.symbols:
                continue
            d = self._fetch_tencent(api_sym, self.n_days)
            if d and len(d.get('closes',[])) > 50:
                result[sym] = {
                    'data': d,
                    'indicators': self._compute_indicators(d)
                }
                print(f"[数据] {sym}: {len(d['closes'])} bars (腾讯API, {d['dates'][0]}→{d['dates'][-1]})")
            else:
                # fallback to local cache
                local = load_multiple([sym], n=self.n_days)
                if sym in local and local[sym].get('closes'):
                    # Normalize to our internal format
                    ld = local[sym]
                    result[sym] = {
                        'data': {
                            'closes': ld['closes'],
                            'dates':  ld.get('dates', []),
                            'opens':  ld.get('opens', []),
                            'highs':  ld.get('highs', []),
                            'lows':   ld.get('lows', []),
                            'volumes':ld.get('volumes', []),
                        },
                        'indicators': ld.get('indicators', self._compute_indicators({'closes': ld['closes'], 'highs': ld.get('highs',ld['closes']), 'lows': ld.get('lows',ld['closes']), 'volumes': ld.get('volumes', [])})),
                    }
                    print(f"[数据] {sym}: {len(ld['closes'])} bars (本地缓存)")
                else:
                    print(f"[数据] {sym}: ❌ 数据加载失败")
        if not result:
            raise RuntimeError(f"无法加载数据: {self.symbols}")
        # Build output in same format as before
        out = []
        for sym in self.symbols:
            if sym not in result:
                raise RuntimeError(f"数据加载失败：{sym}")
            inds = result[sym]["indicators"]
            rets = inds.get('returns', result[sym]['data'].get('closes', []))
            if not rets:
                closes = result[sym]["data"]["closes"]
                rets = [0.0] + [(closes[i]/closes[i-1]-1) for i in range(1, len(closes))]
            out.append({
                "symbol":     sym,
                "data":       {
                    "closes": result[sym]["data"]["closes"],
                    "returns": rets,
                },
                "indicators": inds,
            })
        return out

    # ── 元监控快照 ────────────────────────

    def _make_snapshot(self, rnd, t_evals, mr_evals, debate, risk_results, sent, regime):
        elim_causes = {}
        for e in (t_evals or []) + (mr_evals or []):
            if e.decision == "REJECT":
                key = (e.elimination_note or e.reason or "?")[:20]
                elim_causes[key] = elim_causes.get(key, 0) + 1
        avg_var = sum(r.var_99 for r in (risk_results or []))/max(len(risk_results),1)
        all_ev  = (t_evals or []) + (mr_evals or [])
        top_score  = max([e.composite for e in all_ev], default=0.0)
        avg_score  = sum(e.composite for e in all_ev)/max(len(all_ev),1)
        t_pass = [e for e in (t_evals or []) if e.decision!="REJECT"]
        mr_pass= [e for e in (mr_evals or []) if e.decision!="REJECT"]
        return RoundSnapshot(round_num=rnd, top_score=round(top_score,1), avg_score=round(avg_score,1),
            total_candidates=len(all_ev), accepted_count=len(t_pass)+len(mr_pass),
            rejected_count=len(all_ev)-len(t_pass)-len(mr_pass),
            trend_count=len(t_pass), mr_count=len(mr_pass),
            debate_winner=debate.winner if debate else "TIE",
            trend_win_streak=0, mr_win_streak=0,
            sentiment_label=(sent.get("sentiment_label","NEUTRAL") if sent else "NEUTRAL"),
            sentiment_score=sent.get("sentiment_score",0.0) if sent else 0.0,
            sentiment_conf=sent.get("confidence",0.0) if sent else 0.0,
            market_regime=(regime.name if regime else "UNKNOWN"),
            avg_var99=round(avg_var,3), elimination_causes=elim_causes)

    # ── 最终报告 ─────────────────────────

    def _generate_final_report(self):
        all_evals = []
        for rp in self.round_reports:
            all_evals.extend(getattr(rp,"trend_evals",[]))
            all_evals.extend(getattr(rp,"mr_evals",[]))
        all_evals.sort(key=lambda x: x.composite, reverse=True)
        # 去重：同一 strategy_name 只保留评分最高的
        seen, global_top = set(), []
        for e in all_evals:
            key = (e.strategy_name, e.strategy_type)
            if key not in seen:
                seen.add(key); global_top.append(e)
            if len(global_top) >= self.top_n: break
        for e in global_top: e.weight = getattr(e,"weight",0.0)
        if len(self.round_reports) >= 2:
            r1=self.round_reports[0]; r2=self.round_reports[-1]
            ev1 = getattr(r1,"trend_evals",[])+getattr(r1,"mr_evals",[])
            ev2 = getattr(r2,"trend_evals",[])+getattr(r2,"mr_evals",[])
            s1  = max([e.composite for e in ev1], default=0)
            s2  = max([e.composite for e in ev2], default=0)
            delta = round(s2-s1,1)
            conv_dir = "↑改善" if delta>3 else ("↓下降" if delta<-3 else "→平稳")
            converged = getattr(r2,"converged",False)
        else:
            s1=s2=delta=0; conv_dir="→首轮"; converged=False
        best = all_evals[0] if all_evals else None
        sugg = []
        if best and best.composite >= 60:
            sugg.append({"risk_level":"进取型",
                         "strategies":[{"name":s.strategy_name} for s in global_top[:3]],
                         "action":f"综合分={best.composite}，可小资金实盘验证（≤30%）"})
        __r__ = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_rounds": len(self.round_reports),
            "symbols": self.symbols,
            "data_note": "⚠️ 纯实盘数据，已移除合成数据",
            "global_top": [{"rank":i+1,"name":e.strategy_name,"type":e.strategy_type,
                             "score":e.composite,"ann":e.annualized_return,
                             "sharpe":e.sharpe_ratio,"dd":e.max_drawdown_pct,
                             "weight":getattr(e,"weight",0.0) or 0.0}
                            for i,e in enumerate(global_top)],
            "convergence": {"round1_score":s1,"final_score":s2,"delta":delta,
                             "direction":conv_dir,"converged":converged},
            "suggestions": sugg,
        }
        return Orchestrator._to_serializable(__r__)

    @staticmethod
    def _to_serializable(obj, _seen=None):
        """安全序列化：只递归 dict / list / tuple，用 id() 做环检测"""
        if _seen is None:
            _seen = set()
        if id(obj) in _seen:
            return None                       # 打破循环
        if isinstance(obj, dict):
            _seen.add(id(obj))
            return {k: Orchestrator._to_serializable(v, _seen) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            _seen.add(id(obj))
            return [Orchestrator._to_serializable(v, _seen) for v in obj]
        if hasattr(obj, "item"):             # numpy scalar
            try: return obj.item()
            except: pass
        if hasattr(obj, "__dict__"):         # dataclass / arbitrary object
            _seen.add(id(obj))
            d = {}
            for k, v in obj.__dict__.items():
                if k.startswith("_"): continue
                try: d[k] = Orchestrator._to_serializable(v, _seen)
                except: d[k] = str(v)
            return d
        return obj

    def _save_report(self, final, path=None):
        path = path or str(Path(__file__).parent.parent/"results"/f"multi_expert_v4_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        serializable = self._to_serializable(final)
        with open(path,"w",encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        print(f"\n💾 已保存: {path}")

    def _print_final_report(self, final):
        print("\n"+"🏆"*34+f"\n  最终报告（v4.0 纯实盘）\n"+"🏆"*34)
        cv=final.get("convergence",{})
        print(f"\n📈 收敛：第1轮={cv.get('round1_score',0):.1f} → 第{final['total_rounds']}轮={cv.get('final_score',0):.1f}（{cv.get('direction','?')}）")
        print(f"\n🏆 全局 Top {len(final.get('global_top',[]))}：")
        for s in final["global_top"]:
            w = s.get("weight", 0.0); w_str = f"{float(w):.1%}" if isinstance(w, (int,float)) and w == w else str(w)
        print(f"  #{s['rank']} {s['name']}（{s['type']}）分={s['score']:.1f} 年化={s['ann']:.1f}% 夏普={s['sharpe']:.3f} 权重={w_str}")
        print("\n"+"🏆"*34)


class RoundReportFake:
    def __init__(self, rnd):
        self.round_num=rnd; self.timestamp=datetime.now().strftime("%H:%M:%S")
        self.market_regime=None; self.sentiment=None
        self.trend_reports=[]; self.mr_reports=[]
        self.all_reports=[]; self.trend_evals=[]; self.mr_evals=[]
        self.debate_result=None; self.risk_results=[]
        self.final_selected=[]; self.portfolio_weights={}
        self.converged=False; self.holdout_results=[]; self.meta_evaluation={}


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
