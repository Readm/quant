"""
run_iteration.py — 多专家迭代回测，输出详细日志供看板展示
=============================================================
用法：
  python3 scripts/run_iteration.py
  python3 scripts/run_iteration.py --symbols SPY BTCUSDT --rounds 3 --days 300

输出：
  dashboard/src/data/iteration_log.json
"""
import sys, json, math, argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

OUT_PATH = Path("dashboard/src/data/iteration_log.json")


# ── 工具函数 ──────────────────────────────────────────────────────

def daily_returns_to_equity(daily_returns: list, n_points: int = 80) -> list[dict]:
    """把 daily_returns 压缩为等间距采样的 equity 曲线（以 100 为基准）"""
    if not daily_returns:
        return []
    equity = 100.0
    curve = [{"i": 0, "v": round(equity, 2)}]
    for r in daily_returns:
        equity *= (1 + r)
        curve.append(round(equity, 2))

    if len(curve) <= n_points:
        return [{"i": i, "v": v} for i, v in enumerate(curve)]

    step = len(curve) / n_points
    sampled = []
    for k in range(n_points):
        idx = min(int(k * step), len(curve) - 1)
        sampled.append({"i": idx, "v": curve[idx]})
    sampled.append({"i": len(curve) - 1, "v": curve[-1]})
    return sampled


def safe_float(v, default=0.0) -> float:
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except Exception:
        return default


def eval_to_dict(e) -> dict:
    """EvalResult → 可序列化 dict"""
    dr = getattr(e, "daily_returns", None) or []
    return {
        "id":            getattr(e, "strategy_id",   ""),
        "name":          getattr(e, "strategy_name", ""),
        "type":          getattr(e, "strategy_type", ""),
        "template":      getattr(e, "template_key",  ""),
        "params":        getattr(e, "params",        {}),
        "decision":      getattr(e, "decision",      ""),
        "score":         safe_float(getattr(e, "composite",        0)),
        "ann_return":    safe_float(getattr(e, "annualized_return", 0)),
        "sharpe":        safe_float(getattr(e, "sharpe_ratio",      0)),
        "max_drawdown":  safe_float(getattr(e, "max_drawdown_pct",  0)),
        "win_rate":      safe_float(getattr(e, "win_rate",          0)),
        "total_trades":  int(getattr(e, "total_trades", 0)),
        "feedback":      getattr(e, "feedback_text",  "") or getattr(e, "feedback", ""),
        "weakness":      str(getattr(e, "weakness",   "") or ""),
        "adjustment":    str(getattr(e, "adjustment", "") or ""),
        "adj_param":     str(getattr(e, "adjustment_param", "") or ""),
        "reason":        getattr(e, "reason",         ""),
        "equity_curve":  daily_returns_to_equity(dr),
    }


def debate_to_dict(d) -> dict:
    """DebateResult → dict"""
    if not d:
        return {}

    strategy_verdicts = []
    for sv in (getattr(d, "strategy_verdicts", None) or []):
        strategy_verdicts.append({
            "strategy_id":   sv.strategy_id,
            "strategy_name": sv.strategy_name,
            "composite":     safe_float(sv.composite),
            "verdict":       sv.verdict,
            "confidence":    safe_float(sv.confidence),
            "weight_advice": safe_float(sv.weight_advice),
            "pros":          list(sv.pros  or []),
            "cons":          list(sv.cons  or []),
            "analysis":      sv.analysis   or "",
        })

    return {
        "winner":            getattr(d, "winner",         "TIE"),
        "trend_weight":      safe_float(getattr(d, "trend_weight",   0.5)),
        "mr_weight":         safe_float(getattr(d, "mr_weight",      0.5)),
        "verdict_reason":    getattr(d, "verdict_reason", ""),
        "final_advice":      getattr(d, "final_advice",   ""),
        "strategy_verdicts": strategy_verdicts,
    }


# ── 打补丁：在 orchestrator 每轮结束时记录详细日志 ──────────────

class InstrumentedOrchestrator:
    """包装 Orchestrator，在每轮结束后捕获详细数据"""

    def __init__(self, symbols, n_days, seed, max_rounds, top_n):
        from experts.orchestrator import Orchestrator
        self.orc = Orchestrator(symbols, n_days=n_days, seed=seed,
                                max_rounds=max_rounds, top_n=top_n)
        self.round_logs = []

    def run(self):
        result = self.orc.run()

        # 从 round_reports 提取每轮详细数据
        for rp in self.orc.round_reports:
            rnd = getattr(rp, "round_num", len(self.round_logs) + 1)

            t_evals  = getattr(rp, "trend_evals",  []) or []
            mr_evals = getattr(rp, "mr_evals",     []) or []
            selected = getattr(rp, "final_selected",[]) or []
            debate   = getattr(rp, "debate_result", None)
            holdout  = getattr(rp, "holdout_results",[]) or []

            selected_names = {getattr(e, "strategy_name", "") for e in selected}

            # Build strategy_id → daily_returns map from backtest reports
            t_reports  = getattr(rp, "trend_reports",  []) or []
            mr_reports = getattr(rp, "mr_reports",     []) or []
            dr_map = {getattr(r, "strategy_id", ""): getattr(r, "daily_returns", []) or []
                      for r in t_reports + mr_reports}

            strategies = []
            for e in t_evals + mr_evals:
                d = eval_to_dict(e)
                # Inject equity curve from backtest report
                sid = d.get("id", "")
                dr = dr_map.get(sid, [])
                d["equity_curve"] = daily_returns_to_equity(dr)
                d["selected"] = d["name"] in selected_names
                strategies.append(d)

            # 按 score 降序
            strategies.sort(key=lambda x: x["score"], reverse=True)

            self.round_logs.append({
                "round":      rnd,
                "strategies": strategies,
                "debate":     debate_to_dict(debate),
                "holdout":    holdout,
                "selected":   list(selected_names),
                "converged":  getattr(rp, "converged", False),
            })

        return result, self.round_logs


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["SPY", "BTCUSDT"])
    parser.add_argument("--days",    type=int,  default=300)
    parser.add_argument("--rounds",  type=int,  default=20)
    parser.add_argument("--seed",    type=int,  default=2026)
    parser.add_argument("--out",     default=str(OUT_PATH))
    args = parser.parse_args()

    print("=" * 60)
    print(f"  迭代回测 · {args.symbols} · {args.rounds} 轮 · {args.days} 天")
    print("=" * 60)

    orc = InstrumentedOrchestrator(
        args.symbols, n_days=args.days, seed=args.seed,
        max_rounds=args.rounds, top_n=4
    )
    final_report, round_logs = orc.run()

    out = {
        "run_at":      datetime.now().isoformat(),
        "symbols":     args.symbols,
        "days":        args.days,
        "total_rounds": len(round_logs),
        "rounds":      round_logs,
        "global_top":  final_report.get("global_top", []),
        "convergence": final_report.get("convergence", {}),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 详细日志已写入 {out_path}")
    print(f"   {len(round_logs)} 轮 · {sum(len(r['strategies']) for r in round_logs)} 个候选策略")
    print("   运行 npm run build 重新构建看板")


if __name__ == "__main__":
    main()
