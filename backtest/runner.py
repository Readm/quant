#!/usr/bin/env python3
"""runner.py - 完整回测运行器（v2，修复所有参数问题）"""
import sys, json, math, random, uuid
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))
from backtest.local_data import load_multiple, print_summary
from experts.modules.risk_engine import RiskExpert
from experts.modules.regime import MarketRegimeExpert
from experts.specialists.expert1a_trend import TrendExpert
from experts.specialists.expert1b_mean_reversion import MeanReversionExpert
from experts.evaluator import Evaluator
from experts.debate_manager import DebateManager

# 策略模板
TREND_TPLS = [
    {"key": "ma_cross",  "name": "双均线交叉",  "params": {"fast": 20,  "slow": 60}},
    {"key": "macd",      "name": "MACD趋势",    "params": {"fp": 12,   "sp": 26, "sig": 9}},
    {"key": "momentum",  "name": "动量突破",    "params": {"lookback": 20, "threshold": 0.05}},
    {"key": "adx_trend", "name": "ADX趋势确认", "params": {"adx_thr": 25,  "atr_mult": 2.0}},
]
MR_TPLS = [
    {"key": "rsi",       "name": "RSI均值回归",  "params": {"period": 14, "lower": 30, "upper": 70}},
    {"key": "bollinger", "name": "布林带回归",   "params": {"period": 20, "std_mult": 2.0}},
    {"key": "vol_surge", "name": "成交量异常",   "params": {"vol_ma": 20, "threshold": 2.0}},
]


def jitter(params, rng, pct=0.35):
    """对参数字典加随机扰动"""
    out = {}
    for k, v in params.items():
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, int) and v > 0:
            out[k] = max(1, int(v + v * pct * rng.choice([-1, 1])))
        elif isinstance(v, float) and v != 0:
            out[k] = round(v * (1 + pct * rng.choice([-1, 1])), 4)
        else:
            out[k] = v
    return out


def run_backtest(symbols, n_days=300, max_rounds=2, seed=42):
    # ── 加载本地数据 ─────────────────────────
    results = load_multiple(symbols)
    print_summary(results)
    prim = list(results.values())[0]
    closes  = prim["closes"]
    returns = prim["returns"]
    volumes = prim.get("volumes", [1e9] * len(closes))
    inds    = prim["indicators"]
    data_d  = {"closes": closes, "returns": returns, "volumes": volumes}

    rng  = random.Random(seed)
    trend = TrendExpert(seed=seed)
    mr    = MeanReversionExpert(seed=seed+1)
    eval_ = Evaluator()
    deb   = DebateManager()
    risk  = RiskExpert()
    deb.risk_expert = risk
    regim = MarketRegimeExpert()

    round_reports = []
    all_global    = []

    for rnd in range(1, max_rounds + 1):
        print(f"\n{'='*60}\n  Round {rnd}/{max_rounds}\n{'='*60}")

        # ── 生成候选 + 回测 ──────────────────
        t_cands, t_reports = [], []
        for i, tpl in enumerate(TREND_TPLS * 2):
            p  = jitter(tpl["params"], rng)
            cid = f"tr_{uuid.uuid4().hex[:6]}"
            r   = trend.backtest(data_d, inds, p, tpl["key"])
            r.strategy_id   = cid
            r.strategy_type = "trend"
            t_cands.append({"strategy_id": cid, "strategy_name": tpl["name"],
                             "strategy_type": "trend", "template_key": tpl["key"],
                             "params": p, "tags": [tpl["name"]]})
            t_reports.append(r)

        mr_cands, mr_reports = [], []
        for i, tpl in enumerate(MR_TPLS * 2):
            p   = jitter(tpl["params"], rng)
            cid = f"mr_{uuid.uuid4().hex[:6]}"
            r   = mr.backtest(data_d, p, tpl["key"])
            r.strategy_id   = cid
            r.strategy_type = "mean_reversion"
            mr_cands.append({"strategy_id": cid, "strategy_name": tpl["name"],
                              "strategy_type": "mean_reversion", "template_key": tpl["key"],
                              "params": p, "tags": [tpl["name"]]})
            mr_reports.append(r)

        all_cands = t_cands + mr_cands
        all_reports = t_reports + mr_reports

        # ── Expert2 评估（传 BacktestReport 对象！） ─
        all_evals  = eval_.evaluate_batch(all_reports)  # ← 传报告不是候选
        Evaluator.print_batch_report(all_evals, rnd)

        t_evals  = eval_.evaluate_batch(t_reports)
        mr_evals = eval_.evaluate_batch(mr_reports)
        t_pass   = [e for e in t_evals  if e.decision != "REJECT"]
        mr_pass  = [e for e in mr_evals if e.decision != "REJECT"]
        all_pass = t_pass + mr_pass
        n_pass   = len(all_pass)
        print(f"\n[评估] 通过 {n_pass}/{len(all_reports)}（含回测修正）")

        if not all_pass:
            print("  ⚠️  无候选通过，降低硬过滤门槛")
            # 临时放宽：接受所有有交易记录的
            t_pass = [e for e in t_evals if e.total_trades >= 1]
            mr_pass = [e for e in mr_evals if e.total_trades >= 1]
            all_pass = t_pass + mr_pass
            print(f"  → 放宽至交易≥1次：通过 {len(all_pass)} 个")

        # ── 市场状态 ──────────────────────────
        regime = regim.detect(data_d, inds)   # ← data_d 有 returns
        regime_name = getattr(regime, "name", "?") if regime else "?"
        print(f"\n[市场] {regime_name}")

        # ── 辩论 ──────────────────────────────
        debate = deb.conduct_debate(t_pass, mr_pass, regime, [], rnd)
        DebateManager.print_debate(debate, rnd)

        # ── 风控 ─────────────────────────────
        risk_map = {}
        if all_pass:
            risk_results = risk.analyze_batch([
                (e.strategy_name, e.params,
                 e.daily_returns if hasattr(e, "daily_returns") and e.daily_returns else [],
                 max(e.total_trades, 1)) for e in all_pass])
            risk_map = {r.strategy_name: r.risk_rating for r in risk_results}
            for r in risk_results:
                ico = {"LOW": "L", "MEDIUM": "M", "HIGH": "H", "VERY_HIGH": "VH"}.get(r.risk_rating, "?")
                print(f"  [{ico}] {r.strategy_name}: {r.risk_rating} VaR99={r.var_99}%")

        # ── 组合权重 ─────────────────────────
        tw = debate.trend_weight if debate else 0.5
        mw = debate.mr_weight    if debate else 0.5
        max_pos = (regime.max_position_pct if regime else 0.50)

        def allocate(items, bw):
            if not items: return {}
            total = sum(e.composite for e in items) or 1
            out = {}
            for e in items:
                w = bw * (e.composite / total)
                if risk_map.get(e.strategy_name) == "HIGH":      w *= 0.7
                elif risk_map.get(e.strategy_name) == "MEDIUM":  w *= 0.9
                out[e.strategy_id] = round(w, 4)
            return out

        trend_items = [e for e in all_pass if e.strategy_type == "trend"]
        mr_items    = [e for e in all_pass if e.strategy_type == "mean_reversion"]
        tw_map = allocate(trend_items, tw)
        mw_map = allocate(mr_items,    mw)
        all_ids = set(tw_map) | set(mw_map)
        total_w = sum(tw_map.get(s, 0) + mw_map.get(s, 0) for s in all_ids) or 1
        normed   = {sid: round((tw_map.get(sid, 0) + mw_map.get(sid, 0)) / total_w * max_pos, 4)
                    for sid in all_ids}

        final = sorted(all_pass, key=lambda e: e.composite, reverse=True)[:4]
        for e in final:
            e.weight = normed.get(e.strategy_id, 0.0)

        print(f"\n[结果] Top {len(final)}:")
        for e in final:
            w = float(getattr(e, "weight", 0.0))
            print(f"  {e.strategy_name}({e.strategy_type}) "
                  f"score={e.composite} ann={e.annualized_return:.1f}% "
                  f"Sharpe={e.sharpe_ratio:.2f} weight={w:.1%}")

        all_global.extend(final)
        round_reports.append({"round": rnd, "final": final,
                               "debate": debate, "regime": regime_name})

    # ── 全局排名 ────────────────────────────
    all_global.sort(key=lambda e: e.composite, reverse=True)
    top4 = all_global[:4]
    for e in top4:
        e.weight = float(getattr(e, "weight", 0.0))

    if len(round_reports) >= 2:
        s1 = max(e.composite for e in round_reports[0]["final"]) if round_reports[0]["final"] else 0
        s2 = max(e.composite for e in round_reports[-1]["final"]) if round_reports[-1]["final"] else 0
        delta    = round(s2 - s1, 1)
        conv_dir = "improving" if delta > 3 else ("degrading" if delta < -3 else "stable")
        converged = abs(s2 - s1) < 1
    else:
        s1 = s2 = delta = 0; conv_dir = "first_round"; converged = False

    report = {
        "generated_at": datetime.now().isoformat(),
        "total_rounds": len(round_reports),
        "symbols": symbols,
        "data_note": "Real market data from local cache (Stooq.com) - fully offline",
        "global_top": [{
            "rank": i+1,
            "name": e.strategy_name, "type": e.strategy_type,
            "score": float(e.composite),
            "ann": float(e.annualized_return),
            "sharpe": float(e.sharpe_ratio),
            "dd": float(e.max_drawdown_pct),
            "weight": round(float(getattr(e, "weight", 0.0)), 3),
        } for i, e in enumerate(top4)],
        "convergence": {
            "round1_score": round(s1, 1),
            "final_score": round(s2, 1),
            "delta": delta,
            "direction": conv_dir,
            "converged": converged,
        },
        "suggestions": [{
            "risk_level": "进取型" if (top4 and top4[0].composite >= 60) else "稳健型",
            "action": f"Top={top4[0].composite:.0f}，可小资金验证" if top4 else "无有效策略",
        }],
    }
    return report


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=["SPY", "BTCUSDT"])
    p.add_argument("--days",   type=int, default=300)
    p.add_argument("--rounds", type=int, default=2)
    p.add_argument("--seed",   type=int, default=42)
    args = p.parse_args()
    print("="*60 + "\n  Backtest Runner v2\n" + "="*60)
    report = run_backtest(args.symbols, args.days, args.rounds, args.seed)
    pth = Path(f"results/multi_expert_v4_{datetime.now().strftime('%Y%m%d_%H%M')}.json")
    pth.parent.mkdir(exist_ok=True, parents=True)
    with open(pth, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {pth}")
    print(json.dumps(report["global_top"], indent=2, ensure_ascii=False))
