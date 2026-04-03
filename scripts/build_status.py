"""
build_status.py — 扫描项目，生成 dashboard/src/data/status.json
在每次构建前运行，让看板显示真实的系统状态。

用法：
  python3 scripts/build_status.py
"""
import sys, json, os, glob, importlib, traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

OUT_PATH = Path("dashboard/src/data/status.json")
# ── 1. Data Layer ────────────────────────────────────────────────
def scan_data():
    files = sorted(glob.glob("data/raw/*.json"))
    symbols = []
    for f in files:
        if os.path.basename(f).startswith("_"):
            continue
        try:
            d = json.load(open(f))
            rows = d.get("rows", [])
            if not rows:
                continue
            closes = [r["close"] for r in rows]
            symbols.append({
                "symbol":     d["symbol"],
                "source":     d.get("source", ""),
                "count":      len(rows),
                "start":      rows[0]["date"],
                "end":        rows[-1]["date"],
                "last_close": round(closes[-1], 2),
                "change_pct": round((closes[-1] / closes[0] - 1) * 100, 1),
            })
        except Exception as e:
            print(f"  [数据扫描] {os.path.basename(f)} 解析失败: {e}")
            continue
    return {
        "status":  "ok" if symbols else "empty",
        "count":   len(symbols),
        "symbols": symbols,
    }
# ── 2. Factor Library ────────────────────────────────────────────
def scan_factors():
    errors = []
    factor_count = 0
    factor_table_count = 0

    try:
        from factors.signals import FACTOR_TABLE
        factor_table_count = len(FACTOR_TABLE)
        factors_list = list(FACTOR_TABLE.keys())
    except Exception as e:
        errors.append(str(e))
        factors_list = []

    # count exported symbols
    try:
        import factors as F
        factor_count = len([k for k in dir(F) if not k.startswith("_")])
    except Exception as e:
        errors.append(str(e))

    files = [os.path.basename(f) for f in glob.glob("factors/*.py")
             if not os.path.basename(f).startswith("_")]

    return {
        "status":       "ok" if not errors else "error",
        "errors":       errors,
        "files":        files,
        "export_count": factor_count,
        "factor_table": factor_table_count,
        "factor_ids":   factors_list[:10],   # sample
    }
# ── 3. Strategy Library ──────────────────────────────────────────
def scan_strategies():
    errors = []
    modules = []
    strat_files = (
        glob.glob("strategies/*.py") +
        glob.glob("experts/specialists/*.py")
    )
    for f in strat_files:
        name = os.path.basename(f).replace(".py", "")
        if name.startswith("_"):
            continue
        mod_path = f.replace("/", ".").replace(".py", "")
        try:
            importlib.import_module(mod_path)
            modules.append({"name": name, "status": "ok"})
        except Exception as e:
            modules.append({"name": name, "status": "error", "error": str(e)})
            errors.append(f"{name}: {e}")

    ok = sum(1 for m in modules if m["status"] == "ok")
    return {
        "status":  "ok" if not errors else "warn",
        "total":   len(modules),
        "ok":      ok,
        "errors":  errors[:5],
        "modules": modules,
    }
# ── 4. Expert System ─────────────────────────────────────────────
def scan_experts():
    errors = []
    modules = []
    expert_files = (
        glob.glob("experts/*.py") +
        glob.glob("experts/modules/*.py")
    )
    for f in expert_files:
        name = os.path.basename(f).replace(".py", "")
        if name.startswith("_"):
            continue
        mod_path = f.replace("/", ".").replace(".py", "")
        try:
            importlib.import_module(mod_path)
            modules.append({"name": name, "status": "ok"})
        except Exception as e:
            modules.append({"name": name, "status": "error", "error": str(e)[:80]})
            errors.append(f"{name}: {str(e)[:80]}")

    ok = sum(1 for m in modules if m["status"] == "ok")
    return {
        "status":  "ok" if ok == len(modules) else "warn",
        "total":   len(modules),
        "ok":      ok,
        "errors":  errors[:5],
        "modules": modules,
    }
# ── 5. Backtest Engines ──────────────────────────────────────────
def scan_backtest():
    engines = []
    for mod_name, label in [
        ("backtest.local_data",       "local_data"),
        
        ("backtest.engine",         "engine"),
    ]:
        try:
            importlib.import_module(mod_name)
            engines.append({"name": label, "status": "ok"})
        except Exception as e:
            engines.append({"name": label, "status": "error", "error": str(e)[:80]})

    ok = sum(1 for e in engines if e["status"] == "ok")
    return {
        "status":  "ok" if ok == len(engines) else "warn",
        "engines": engines,
    }
# ── 6. Config ────────────────────────────────────────────────────
def scan_config():
    try:
        from config.settings import INITIAL_CAPITAL, MAX_DRAWDOWN, COMMISSION_RATE
        return {
            "status":          "ok",
            "initial_capital": INITIAL_CAPITAL,
            "max_drawdown":    MAX_DRAWDOWN,
            "commission_rate": COMMISSION_RATE,
        }
    except Exception as e:
        try:
            from config import settings as S
            return {"status": "ok", "note": str(vars(S))[:200]}
        except Exception as e2:
            return {"status": "error", "error": str(e2)}
# ── Main ─────────────────────────────────────────────────────────
def main():
    print("Scanning project status...")

    status = {
        "generated_at": datetime.now().isoformat(),
        "data":       scan_data(),
        "factors":    scan_factors(),
        "strategies": scan_strategies(),
        "experts":    scan_experts(),
        "backtest":   scan_backtest(),
        "config":     scan_config(),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    print(f"  Written to {OUT_PATH}")
    print(f"  Data:       {status['data']['count']} symbols ({status['data']['status']})")
    print(f"  Factors:    {status['factors']['factor_table']} in table, {status['factors']['export_count']} exports ({status['factors']['status']})")
    print(f"  Strategies: {status['strategies']['ok']}/{status['strategies']['total']} modules ok")
    print(f"  Experts:    {status['experts']['ok']}/{status['experts']['total']} modules ok")
    print(f"  Backtest:   {status['backtest']['status']}")
if __name__ == "__main__":
    main()
