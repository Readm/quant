"""
run_iteration.py — 多专家迭代回测，输出详细日志供看板展示
=============================================================
用法：
  python3 scripts/run_iteration.py
  python3 scripts/run_iteration.py --symbols SPY BTCUSDT --rounds 3 --days 300

输出：
  dashboard/src/data/iteration_log.json
"""
import sys, json, math, argparse, re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

ITERATIONS_DIR = Path("dashboard/src/data/iterations")
OUT_PATH = Path("dashboard/src/data/iteration_log.json")  # kept for compat


def _make_thread_id(name: str, symbols: list, ts: str) -> str:
    """Generate a filesystem-safe thread ID."""
    if name:
        slug = re.sub(r'[^\w\u4e00-\u9fff]+', '_', name).strip('_')[:24]
    else:
        slug = '_'.join(s.lower().replace('sh', '').replace('sz', '') for s in symbols)[:24]
    return f"{slug}_{ts}"


def _update_index(entry: dict):
    """Upsert thread entry in iterations/index.json (replace by id if exists)."""
    ITERATIONS_DIR.mkdir(parents=True, exist_ok=True)
    idx_path = ITERATIONS_DIR / "index.json"
    existing = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else []
    existing = [e for e in existing if e.get("id") != entry["id"]]
    existing.append(entry)
    # Sort by run_at descending (newest first)
    existing.sort(key=lambda e: e.get("run_at", ""), reverse=True)
    idx_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 工具函数 ──────────────────────────────────────────────────────

def daily_returns_to_equity(daily_returns: list, n_points: int = 80) -> list[dict]:
    """把 daily_returns 压缩为等间距采样的 equity 曲线（以 100 为基准）"""
    if not daily_returns:
        return []
    equity = 100.0
    curve = [100.0]
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
    except (TypeError, ValueError):
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
        "alpha":         safe_float(getattr(e, "alpha",             0)),
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

        # 提取基准收益曲线（供看板绘制基准线）
        bench_rets = getattr(self.orc.evaluator, 'benchmark_returns', []) or []
        bench_equity = daily_returns_to_equity(bench_rets)

        # 从 round_reports 提取每轮详细数据
        for rp in self.orc.round_reports:
            rnd = getattr(rp, "round_num", len(self.round_logs) + 1)

            all_evals = getattr(rp, "all_evals",  []) or []
            selected  = getattr(rp, "final_selected",[]) or []
            debate    = getattr(rp, "debate_result", None)
            holdout   = getattr(rp, "holdout_results",[]) or []

            selected_names = {getattr(e, "strategy_name", "") for e in selected}

            # Build strategy_id → daily_returns map from backtest reports
            all_reports = getattr(rp, "all_reports", []) or []
            dr_map = {getattr(r, "strategy_id", ""): getattr(r, "daily_returns", []) or []
                      for r in all_reports}

            strategies = []
            for e in all_evals:
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
                "round":            rnd,
                "strategies":       strategies,
                "debate":           debate_to_dict(debate),
                "holdout":          holdout,
                "selected":         list(selected_names),
                "converged":        getattr(rp, "converged", False),
                "meta_evaluation":  getattr(rp, "meta_evaluation", {}),
                "benchmark_equity": bench_equity,
            })

        return result, self.round_logs


# ── Main ──────────────────────────────────────────────────────────

def _load_a_share_symbols(min_amount_wan: float = 1000.0) -> list:
    """从本地 tushare/daily 读取所有 A 股，过滤日均成交额 < min_amount_wan 万元的个股。
    tushare amount 列单位为千元，1000万/day = 100,000 千元。
    流动性基于训练期（排除最后 OOS_DAYS 天）计算，消除未来函数。
    """
    import csv as _csv
    from pathlib import Path as _P
    from experts.orchestrator import OOS_DAYS
    files = sorted(_P("data/tushare/daily").glob("*.csv"))
    if min_amount_wan <= 0:
        return [f.stem for f in files]
    threshold = min_amount_wan * 100  # 万元 → 千元
    qualified = []
    for f in files:
        with open(f, newline="", encoding="utf-8") as fh:
            rows = list(_csv.DictReader(fh))
        rows.sort(key=lambda r: r.get("trade_date", ""))
        if not rows:
            continue
        # 排除最后 OOS_DAYS 行（样本外期），仅用训练期数据评估流动性
        train_rows = rows[:-OOS_DAYS] if len(rows) > OOS_DAYS + 60 else rows[:60]
        recent = train_rows[-60:] if len(train_rows) >= 60 else train_rows
        amounts = [float(r.get("amount") or 0) for r in recent if r.get("amount")]
        if amounts and sum(amounts) / len(amounts) >= threshold:
            qualified.append(f.stem)
    return qualified


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["SPY", "BTCUSDT"])
    parser.add_argument("--universe", default="",
                        help="'a_shares' 自动加载所有本地 A 股，覆盖 --symbols")
    parser.add_argument("--min_amount", type=float, default=1000.0,
                        help="最低日均成交额（万元），用于 --universe a_shares 流动性过滤，默认 1000 万")
    parser.add_argument("--days",    type=int,  default=900,
                        help="加载历史 K 线数（0=全量）。含 OOS_DAYS=252，训练期≈days-252")
    parser.add_argument("--rounds",  type=int,  default=20)
    parser.add_argument("--seed",    type=int,  default=2026)
    parser.add_argument("--name",    default="",
                        help="Thread display name, e.g. 'A股核心' or '加密货币'. "
                             "Auto-generated from symbols if omitted.")
    parser.add_argument("--out",     default="",
                        help="Override output path (optional, normally auto-determined)")
    args = parser.parse_args()

    if args.universe == "a_shares":
        print(f"[universe] 扫描 A 股流动性（阈值 {args.min_amount:.0f} 万/日）...")
        args.symbols = _load_a_share_symbols(args.min_amount)
        if not args.name:
            args.name = "A股核心"
        print(f"[universe] 过滤后剩余 {len(args.symbols)} 只 A 股")

    ts         = datetime.now().strftime("%Y%m%d_%H%M")
    thread_id  = _make_thread_id(args.name, args.symbols, ts)
    name       = args.name or " · ".join(args.symbols)
    run_at     = datetime.now().isoformat()

    ITERATIONS_DIR.mkdir(parents=True, exist_ok=True)
    thread_path = ITERATIONS_DIR / f"{thread_id}.json"
    out_path    = Path(args.out) if args.out else thread_path

    print("=" * 60)
    print(f"  迭代回测 [{name}]")
    print(f"  标的: {args.symbols}  轮次上限: {args.rounds}  数据: {args.days}天")
    print(f"  Thread: {thread_id}")
    print("=" * 60)

    orc = InstrumentedOrchestrator(
        args.symbols, n_days=args.days, seed=args.seed,
        max_rounds=args.rounds, top_n=4
    )
    final_report, round_logs = orc.run()

    out = {
        "thread_id":   thread_id,
        "name":        name,
        "run_at":      run_at,
        "symbols":     args.symbols,
        "days":        args.days,
        "total_rounds": len(round_logs),
        "rounds":      round_logs,
        "global_top":  final_report.get("global_top", []),
        "convergence": final_report.get("convergence", {}),
        "meta_architecture_review": final_report.get("meta_architecture_review", {}),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Also overwrite the legacy path for backward compat
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Update index
    best_score = max((s["score"] for r in round_logs for s in r["strategies"]), default=0.0)
    last_round = round_logs[-1] if round_logs else {}
    # 全量 universe 时只在 index 存代表性摘要
    index_symbols = (
        ["A股全量"]
        if args.universe == "a_shares"
        else args.symbols
    )
    _update_index({
        "id":           thread_id,
        "name":         name,
        "symbols":      index_symbols,
        "run_at":       run_at,
        "total_rounds": len(round_logs),
        "days":         args.days,
        "best_score":   round(best_score, 1),
        "converged":    last_round.get("converged", False),
    })

    print(f"\n✅ Thread [{name}] 已写入 {out_path}")
    print(f"   {len(round_logs)} 轮 · {sum(len(r['strategies']) for r in round_logs)} 个候选策略")
    print(f"   索引已更新: {ITERATIONS_DIR / 'index.json'}")
    
    # 同步到 public/data/（生产环境运行时 fetch）
    import shutil
    public_dir = Path(__file__).parent.parent / 'dashboard' / 'public' / 'data' / 'iterations'
    public_dir.mkdir(parents=True, exist_ok=True)
    for f in ITERATIONS_DIR.glob('*.json'):
        shutil.copy2(f, public_dir / f.name)


if __name__ == "__main__":
    main()
