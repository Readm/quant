"""
local_data.py — 本地缓存读取器（离线回测）
数据来源: data/raw/  由 scripts/collectors/stooq_collector.py 填充
"""
import json, math
from pathlib import Path
from typing import Optional, Dict, List

def load_symbol(symbol: str, data_dir: str = "/workspace/quant/data/raw", n: int = 0) -> Optional[dict]:
    """从本地缓存加载，去重后按日期升序返回"""
    files = sorted(Path(data_dir).glob(f"{symbol.upper()}_*.json"), reverse=True)
    if not files:
        print(f"[local_data] Not found: {symbol} in {data_dir}"); return None
    d = json.load(open(files[0]))
    rows = d.get("rows", [])
    if not rows: return None
    rows.sort(key=lambda r: r["date"])
    if n > 0 and len(rows) > n: rows = rows[-n:]
    closes = [r["close"] for r in rows]
    returns = [0.0] + [(closes[i]-closes[i-1])/closes[i-1] for i in range(1,len(closes))]
    try:
        from experts.modules.market_data import compute_indicators
        ind = compute_indicators(closes,
                                  [r["high"] for r in rows],
                                  [r["low"]  for r in rows])
    except Exception:
        ind = {}
    return {
        "symbol":  symbol,
        "dates":   [r["date"]  for r in rows],
        "opens":   [r["open"]  for r in rows],
        "highs":   [r["high"]  for r in rows],
        "lows":    [r["low"]   for r in rows],
        "closes":  closes,
        "volumes": [r["vol"]   for r in rows],
        "returns": returns,
        "indicators": ind,
        "source":  f"cache:{files[0].name}",
        "count":   len(rows),
    }

def load_multiple(symbols: List[str], data_dir: str = "/workspace/quant/data/raw", n: int = 0) -> Dict[str,dict]:
    out = {}
    for sym in symbols:
        d = load_symbol(sym, data_dir, n)
        if d: out[sym] = d
    return out

def print_summary(results: dict):
    print(f"\n{'='*62}\n  Data Summary ({len(results)} symbols)\n{'='*62}")
    for sym, data in results.items():
        c = data["closes"]; r = data["returns"]; n = len(c)
        mu  = sum(r)/max(len(r),1)*252*100
        vol = math.sqrt(sum((x-sum(r)/max(len(r),1))**2 for x in r)/max(len(r),1))*math.sqrt(252)*100
        chg = (c[-1]/c[0]-1)*100
        peak = max(c); pj = c.index(peak)
        dd   = (peak-min(c[pj:]))/peak*100
        print(f"  {sym:<12} {n:>3}days {data['source']:<20} "
              f"{c[0]:>10.2f}->{c[-1]:>10.2f} {chg:>+7.1f}%  "
              f"Ann.{mu:>+7.1f}%  Vol.{vol:>5.1f}%  DD.{dd:>5.1f}%")
    print(f"{'='*62}\n")
