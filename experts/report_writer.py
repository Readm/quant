"""
report_writer.py — 结果输出层（快照 / 报告生成 / 保存 / 打印）
"""

import json
from datetime import datetime
from pathlib import Path

from experts.meta_monitor import RoundSnapshot


def make_snapshot(rnd, all_evals, _unused, debate, risk_results, sent, regime) -> RoundSnapshot:
    """将本轮数据整理成 RoundSnapshot，供 MetaMonitor 记录"""
    elim_causes: dict = {}
    for e in (all_evals or []):
        if e.decision == "REJECT":
            key = (e.elimination_note or getattr(e, 'reason', '') or "?")[:20]
            elim_causes[key] = elim_causes.get(key, 0) + 1

    avg_var   = sum(r.var_99 for r in (risk_results or [])) / max(len(risk_results), 1)
    all_ev    = list(all_evals or [])
    top_score = max([e.composite for e in all_ev], default=0.0)
    avg_score = sum(e.composite for e in all_ev) / max(len(all_ev), 1)
    all_pass  = [e for e in (all_evals or []) if e.decision != "REJECT"]

    return RoundSnapshot(
        round_num          = rnd,
        top_score          = round(top_score, 1),
        avg_score          = round(avg_score, 1),
        total_candidates   = len(all_ev),
        accepted_count     = len(all_pass),
        rejected_count     = len(all_ev) - len(all_pass),
        trend_count        = len(all_pass),
        mr_count           = 0,
        debate_winner      = debate.winner if debate else "TIE",
        trend_win_streak   = 0,
        mr_win_streak      = 0,
        sentiment_label    = (sent.get("sentiment_label", "NEUTRAL") if sent else "NEUTRAL"),
        sentiment_score    = sent.get("sentiment_score", 0.0) if sent else 0.0,
        sentiment_conf     = sent.get("confidence", 0.0) if sent else 0.0,
        sentiment_enabled  = False,  # TODO: news_sentiment 未启用
        market_regime      = (regime.name if regime else "UNKNOWN"),
        avg_var99          = round(avg_var, 3),
        elimination_causes = elim_causes,
    )


def generate_final_report(round_reports: list, top_n: int, symbols: list) -> dict:
    """汇总所有轮次，生成最终报告 dict"""
    all_evals = []
    for rp in round_reports:
        all_evals.extend(getattr(rp, "all_evals", []))
    all_evals.sort(key=lambda x: x.composite, reverse=True)

    # 去重：同一策略名只保留评分最高的
    seen, global_top = set(), []
    for e in all_evals:
        key = (e.strategy_name, getattr(e, 'strategy_type', 'combo'))
        if key not in seen:
            seen.add(key)
            global_top.append(e)
        if len(global_top) >= top_n:
            break
    for e in global_top:
        e.weight = getattr(e, "weight", 0.0)

    # 收敛方向
    if len(round_reports) >= 2:
        r1  = round_reports[0];  r2 = round_reports[-1]
        ev1 = getattr(r1, "all_evals", [])
        ev2 = getattr(r2, "all_evals", [])
        s1  = max([e.composite for e in ev1], default=0)
        s2  = max([e.composite for e in ev2], default=0)
        delta    = round(s2 - s1, 1)
        conv_dir = "↑改善" if delta > 3 else ("↓下降" if delta < -3 else "→平稳")
        converged = getattr(r2, "converged", False)
    else:
        s1 = s2 = delta = 0; conv_dir = "→首轮"; converged = False

    best = all_evals[0] if all_evals else None
    sugg = []
    if best and best.composite >= 60:
        sugg.append({
            "risk_level": "进取型",
            "strategies": [{"name": s.strategy_name} for s in global_top[:3]],
            "action": f"综合分={best.composite}，可小资金实盘验证（≤30%）",
        })

    # ===== 添加 rounds 字段（每轮详细策略数据）=====
    rounds_data = []
    for rp in round_reports:
        all_round_evals = list(getattr(rp, "all_evals", []) or [])
        
        round_item = {
            "round_num": getattr(rp, "round_num", len(rounds_data) + 1),
            "top_score": getattr(rp, "top_score", 0),
            "avg_score": getattr(rp, "avg_score", 0),
            "total_candidates": getattr(rp, "total_candidates", len(all_round_evals)),
            "accepted_count": getattr(rp, "accepted_count", 0),
            "debate_winner": getattr(rp, "debate_winner", "TIE"),
            "sentiment_label": getattr(rp, "sentiment_label", "NEUTRAL"),
            "market_regime": getattr(rp, "market_regime", "UNKNOWN"),
            "strategies": [
                {
                    "name": e.strategy_name,
                    "type": e.strategy_type,
                    "score": e.composite,
                    "ann": e.annualized_return,
                    "sharpe": e.sharpe_ratio,
                    "dd": e.max_drawdown_pct,
                    "decision": e.decision,
                    "alpha": getattr(e, "alpha", 0.0),
                    "win_rate": getattr(e, "win_rate", 0.0),
                    "total_trades": getattr(e, "total_trades", 0),
                    "sortino": getattr(e, "sortino_score", 0.0),
                    "calmar": getattr(e, "calmar_score", 0.0),
                    "ir_score": getattr(e, "ir_score", 0.0),
                }
                for e in all_round_evals
            ],
        }
        rounds_data.append(round_item)
    
    raw = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_rounds": len(round_reports),
        "symbols":      symbols,
        "data_note":    "⚠️ 纯实盘数据，已移除合成数据",
        "rounds": rounds_data,  # 每轮详细策略数据
        "global_top": [
            {
                "rank":   i + 1,
                "name":   e.strategy_name,
                "type":   e.strategy_type,
                "score":  e.composite,
                "ann":    e.annualized_return,
                "sharpe": e.sharpe_ratio,
                "dd":     e.max_drawdown_pct,
                "weight": float(w) if isinstance((w := getattr(e, "weight", 0.0)), (int, float)) else 0.0,
            }
            for i, e in enumerate(global_top)
        ],
        "convergence": {
            "round1_score": s1,
            "final_score":  s2,
            "delta":        delta,
            "direction":    conv_dir,
            "converged":    converged,
        },
        "suggestions": sugg,
    }
    return to_serializable(raw)


def to_serializable(obj, _seen=None):
    """安全序列化：递归 dict/list/tuple，用 id() 做环检测"""
    if _seen is None:
        _seen = set()
    if id(obj) in _seen:
        return None
    if isinstance(obj, dict):
        _seen.add(id(obj))
        return {k: to_serializable(v, _seen) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        _seen.add(id(obj))
        return [to_serializable(v, _seen) for v in obj]
    if hasattr(obj, "item"):          # numpy scalar
        return obj.item()
    if hasattr(obj, "__dict__"):      # dataclass / arbitrary object
        _seen.add(id(obj))
        d = {}
        for k, v in obj.__dict__.items():
            if k.startswith("_"):
                continue
            try:
                d[k] = to_serializable(v, _seen)
            except Exception as e:
                print(f"[序列化] 字段 {k} 无法序列化 ({type(v).__name__}): {e}")
                d[k] = str(v)
        return d
    return obj


def save_report(final: dict, path: str = None) -> str:
    """将报告写入 results/ 目录，返回文件路径"""
    if path is None:
        ts   = datetime.now().strftime("%Y%m%d_%H%M")
        path = str(Path(__file__).parent.parent / "results" / f"multi_expert_v4_{ts}.json")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_serializable(final), f, ensure_ascii=False, indent=2)
    print(f"\n💾 已保存: {path}")
    return path


def print_final_report(final: dict) -> None:
    """控制台打印最终报告摘要"""
    print("\n" + "🏆" * 34 + f"\n  最终报告（v4.0 纯实盘）\n" + "🏆" * 34)
    cv = final.get("convergence", {})
    print(f"\n📈 收敛：第1轮={cv.get('round1_score', 0):.1f} → "
          f"第{final['total_rounds']}轮={cv.get('final_score', 0):.1f}"
          f"（{cv.get('direction', '?')}）")
    print(f"\n🏆 全局 Top {len(final.get('global_top', []))}：")
    for s in final["global_top"]:
        w     = s.get("weight", 0.0)
        w_str = f"{float(w):.1%}" if isinstance(w, (int, float)) and w == w else str(w)
        print(f"  #{s['rank']} {s['name']}（{s['type']}）"
              f"分={s['score']:.1f} 年化={s['ann']:.1f}% "
              f"夏普={s['sharpe']:.3f} 权重={w_str}")
    print("\n" + "🏆" * 34)
