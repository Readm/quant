"""
local_data.py — 本地缓存读取器（离线回测）
数据来源:
  data/tushare/daily CSV 格式，由 fetch_tushare.py 填充
"""
import csv, math, pickle
from pathlib import Path
from typing import Optional, Dict, List


def _tushare_symbol_to_path(symbol: str) -> Optional[Path]:
    """将 SH600519 / SZ000858 等格式映射到 tushare CSV 路径。"""
    sym = symbol.upper()
    base = Path("data/tushare/daily")
    # SH600519 → 600519.SH.csv
    if sym.startswith("SH") and len(sym) > 2:
        p = base / f"{sym[2:]}.SH.csv"
        if p.exists():
            return p
    # SZ000858 → 000858.SZ.csv
    if sym.startswith("SZ") and len(sym) > 2:
        p = base / f"{sym[2:]}.SZ.csv"
        if p.exists():
            return p
    # BJ920000 → 920000.BJ.csv
    if sym.startswith("BJ") and len(sym) > 2:
        p = base / f"{sym[2:]}.BJ.csv"
        if p.exists():
            return p
    # 已是 600519.SH 格式
    p = base / f"{symbol}.csv"
    if p.exists():
        return p
    return None


def _ind_cache_path(csv_path: Path, n: int) -> Path:
    """缓存路径含 n，避免不同窗口长度的缓存冲突。n=0 表示全量。"""
    return csv_path.with_name(f"{csv_path.stem}.{n}.ind.pkl")


def _load_daily_basic(symbol: str) -> Optional[dict]:
    """加载 daily_basic CSV（PE/PB/换手率/市值），返回 {trade_date: {key: val}}。"""
    base = Path("data/tushare/daily_basic")
    csv_path = base / f"{symbol}.csv"
    if not csv_path.exists():
        return None
    out = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["trade_date"]] = {
                "pe":            _safe_float(r.get("pe")),
                "pe_ttm":        _safe_float(r.get("pe_ttm")),
                "pb":            _safe_float(r.get("pb")),
                "turnover_rate": _safe_float(r.get("turnover_rate")),
                "volume_ratio":  _safe_float(r.get("volume_ratio")),
                "dv_ratio":      _safe_float(r.get("dv_ratio")),
                "total_mv":      _safe_float(r.get("total_mv")),
                "circ_mv":       _safe_float(r.get("circ_mv")),
            }
    return out if out else None


def _load_moneyflow(symbol: str) -> Optional[dict]:
    """加载 moneyflow CSV（资金流向），返回 {trade_date: {key: val}}。"""
    base = Path("data/tushare/moneyflow")
    csv_path = base / f"{symbol}.csv"
    if not csv_path.exists():
        return None
    out = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[r["trade_date"]] = {
                "buy_elg_amount": _safe_float(r.get("buy_elg_amount")),
                "sell_elg_amount":_safe_float(r.get("sell_elg_amount")),
                "buy_lg_amount":  _safe_float(r.get("buy_lg_amount")),
                "sell_lg_amount": _safe_float(r.get("sell_lg_amount")),
                "net_mf_amount":  _safe_float(r.get("net_mf_amount")),
                "net_mf_vol":     _safe_float(r.get("net_mf_vol")),
            }
    return out if out else None


def _safe_float(v) -> Optional[float]:
    """安全转换 float，空值/非数值返回 None。"""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None
def _load_tushare_csv(csv_path: Path, n: int = 0) -> Optional[dict]:
    """从 tushare CSV 加载 OHLCV，升序返回。先切片再计算指标，缓存到 .N.ind.pkl。"""
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "date":    r["trade_date"],
                "open":    float(r["open"]),
                "high":    float(r["high"]),
                "low":     float(r["low"]),
                "close":   float(r["close"]),
                "vol":     float(r["vol"]),
                "pct_chg": float(r["pct_chg"]) if r.get("pct_chg") else 0.0,
            })
    if not rows:
        return None
    rows.sort(key=lambda r: r["date"])  # tushare 降序，转升序

    # 先切片，再计算指标（避免对全量 2700+ 行做无效计算）
    if n > 0 and len(rows) > n:
        rows = rows[-n:]

    ind_path = _ind_cache_path(csv_path, n)
    if (ind_path.exists() and
            ind_path.stat().st_mtime >= csv_path.stat().st_mtime):
        with open(ind_path, "rb") as _f:
            ind = pickle.load(_f)
    else:
        from backtest.indicators import compute_indicators
        ind = compute_indicators({
            "closes":  [r["close"] for r in rows],
            "highs":   [r["high"]  for r in rows],
            "lows":    [r["low"]   for r in rows],
            "volumes": [r["vol"]   for r in rows],
        })
        with open(ind_path, "wb") as _f:
            pickle.dump(ind, _f, protocol=pickle.HIGHEST_PROTOCOL)

    closes  = [r["close"] for r in rows]
    returns = [0.0] + [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
    dates_raw = [r["date"] for r in rows]  # YYYYMMDD for extension lookup
    dates   = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in dates_raw]

    # ── 加载扩展数据（daily_basic / moneyflow）─────────────────
    # 转为按时间索引的数组 ext["pe"][t]，因子函数直接用
    symbol = csv_path.stem
    basic = _load_daily_basic(symbol)
    money = _load_moneyflow(symbol)
    ext_arrays = {}
    if basic or money:
        # 收集所有可能的 key
        all_keys = set()
        sample = basic or money
        sample_date = next(iter(sample))
        if basic:
            all_keys.update(basic[sample_date].keys())
        if money:
            all_keys.update(money[sample_date].keys())
        # 构建数组
        for k in sorted(all_keys):
            vals = []
            for raw_date in dates_raw:
                v = None
                if basic and raw_date in basic:
                    v = basic[raw_date].get(k)
                if v is None and money and raw_date in money:
                    v = money[raw_date].get(k)
                vals.append(v)
            if any(v is not None for v in vals):
                ext_arrays[k] = vals

    return {
        "symbol":     csv_path.stem,
        "dates":      dates,
        "opens":      [r["open"]    for r in rows],
        "highs":      [r["high"]    for r in rows],
        "lows":       [r["low"]     for r in rows],
        "closes":     closes,
        "volumes":    [r["vol"]     for r in rows],
        "pct_chgs":   [r["pct_chg"] for r in rows],
        "returns":    returns,
        "indicators": ind,
        "extensions": ext_arrays,
        "source":     f"tushare:{csv_path.name}",
        "count":      len(rows),
    }


def load_symbol(symbol: str, n: int = 0) -> Optional[dict]:
    """从 tushare CSV 加载 OHLCV。"""
    csv_path = _tushare_symbol_to_path(symbol)
    if csv_path:
        return _load_tushare_csv(csv_path, n)
    print(f"[local_data] Not found: {symbol}")
    return None

def load_multiple(symbols: List[str], n: int = 0) -> Dict[str,dict]:
    out = {}
    for sym in symbols:
        d = load_symbol(sym, n)
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
