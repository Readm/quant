"""
run_pipeline.py - 采集 -> 缓存 -> 回测 完整工作流
每步自动 git commit，可追溯。
"""
import sys, subprocess, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def gcommit(msg):
    r = subprocess.run(["git","add","-A"],capture_output=True,cwd="/workspace/quant")
    r = subprocess.run(["git","commit","-m",msg],capture_output=True,text=True,cwd="/workspace/quant")
    tag = r.stdout.strip().split("\n")[-1] if r.stdout else ""
    ok = "nothing to commit" not in r.stdout and r.returncode==0
    print(f"  {'git: '+tag[:8] if ok else 'no changes'}")
    return tag[:8] if ok else ""

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--symbols",nargs="+",default=["SPY","BTCUSDT"])
    p.add_argument("--days",type=int,default=300)
    p.add_argument("--rounds",type=int,default=2)
    p.add_argument("--seed",type=int,default=2026)
    args = p.parse_args()
    print("="*62+"\n  Quant Pipeline v4.0 (local cache)\n"+"="*62)
    gcommit("chore: pipeline start")
    print("\n[1] Loading local data...")
    from backtest.local_data import load_multiple, print_summary
    results = load_multiple(args.symbols, n=args.days)
    if not results:
        print("ERROR: no data. Run: python3 -m scripts.collectors.stooq_collector")
        return
    print_summary(results)
    gcommit("data: updated local cache")
    print("\n[2] Running multi-expert backtest...")
    from experts.orchestrator import Orchestrator
    syms = list(results.keys())
    n_days = min(args.days, min(results[s]["count"] for s in syms))
    report = Orchestrator(syms, n_days=n_days, seed=args.seed,
                          max_rounds=args.rounds, top_n=4).run()
    top = ",".join(s["name"] for s in report.get("global_top",[])[:3])
    gcommit(f"results: backtest done Top=[{top}]")
    print("\nDone! git log --oneline for history")
    print(json.dumps(report.get("global_top",[]),indent=2,ensure_ascii=False))

if __name__=="__main__": main()
