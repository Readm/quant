"""
data_loader.py — 数据加载与指标预计算层
"""

import json, re, urllib.request
from pathlib import Path

from backtest.local_data import load_multiple
from backtest.indicators import compute_indicators
from experts.evaluator import compute_benchmark_returns

_TENCENT_MAP = {'SPY': 'sh000300', 'BTCUSDT': 'btcusdt', 'ETHUSDT': 'ethusdt'}


def fetch_tencent(sym: str, n: int = 300) -> dict | None:
    """从腾讯行情 API 拉取日K（前复权）"""
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?_var=kline_day&param={sym},day,,,{n},qfq")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode()
        m = re.search(r'=\s*(\{.*\})', text, re.DOTALL)
        if not m:
            return None
        obj = json.loads(m.group(1))
        val = obj.get('data', {}).get(sym)
        if isinstance(val, list):
            klines = val
        elif isinstance(val, dict):
            klines = val.get('day', [])
        else:
            return None
        if not klines:
            return None
        closes = [float(k[2]) for k in klines]
        if not closes or closes[-1] < 1:
            return None
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



def compute_benchmark_for_symbols(
    symbols_data: list,
    benchmark_sym: str = None,
) -> list:
    """从 symbols_data 列表中提取基准收益率序列"""
    if benchmark_sym and symbols_data:
        for sd in symbols_data:
            if sd.get("symbol") == benchmark_sym:
                closes = sd.get("data", {}).get("closes", [])
                return compute_benchmark_returns(closes)

    # 优先用沪深300指数 CSV
    import pandas as _pd
    idx_path = (Path(__file__).parent.parent / "data" / "tushare"
                / "index_daily" / "000300.SH.csv")
    if idx_path.exists():
        df = _pd.read_csv(idx_path, dtype={"trade_date": str}).sort_values("trade_date")
        if symbols_data:
            strat_dates = set(symbols_data[0].get("data", {}).get("dates", []))
            if strat_dates:
                df = df[df["trade_date"].isin(strat_dates)]
        closes = df["close"].tolist()
        if len(closes) > 50:
            print(f"[基准] 使用沪深300(000300.SH)，{len(closes)} 个交易日")
            return compute_benchmark_returns(closes)

    # 兜底：用第一个标的
    if symbols_data:
        closes = symbols_data[0].get("data", {}).get("closes", [])
        return compute_benchmark_returns(closes)
    return []


def _load_one(sym: str, n_days: int) -> tuple:
    """加载单个标的，返回 (sym, data_dict | None)"""
    api_sym = _TENCENT_MAP.get(sym)
    if api_sym:
        d = fetch_tencent(api_sym, n_days)
        if d and len(d.get('closes', [])) > 50:
            return sym, {'data': d, 'indicators': compute_indicators(d)}
    local = load_multiple([sym], n=n_days)
    if sym in local and local[sym].get('closes'):
        ld = local[sym]
        d = {k: ld.get(k, []) for k in ('closes', 'dates', 'opens', 'highs', 'lows', 'volumes')}
        inds = ld.get('indicators') or compute_indicators(d)
        return sym, {'data': d, 'indicators': inds}
    return sym, None


def load_symbols_data(symbols: list, n_days: int) -> list:
    """加载多标的 OHLCV，返回 orchestrator 所需的 list[dict] 格式。
    并行加载（ThreadPoolExecutor），tushare 指标结果缓存到磁盘。
    """
    import concurrent.futures
    result = {}
    workers = min(32, len(symbols))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_load_one, sym, n_days): sym for sym in symbols}
        for fut in concurrent.futures.as_completed(futures):
            sym, d = fut.result()
            if d:
                result[sym] = d
                closes = d['data']['closes']
                dates  = d['data'].get('dates', [])
                span   = f"{dates[0]}→{dates[-1]}" if dates else "?"
                src    = "腾讯API" if sym in _TENCENT_MAP else "本地缓存"
                print(f"[数据] {sym}: {len(closes)} bars ({src}, {span})")
            else:
                print(f"[数据] {sym}: ❌ 数据加载失败")

    if not result:
        raise RuntimeError(f"无法加载数据: {symbols}")

    out = []
    for sym in symbols:
        if sym not in result:
            continue
        raw_d  = result[sym]["data"]
        closes = raw_d["closes"]
        rets   = [0.0] + [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
        out.append({
            "symbol": sym,
            "data": {
                "closes":     closes,
                "returns":    rets,
                "opens":      raw_d.get("opens",      closes),
                "highs":      raw_d.get("highs",      closes),
                "lows":       raw_d.get("lows",       closes),
                "volumes":    raw_d.get("volumes",    [1e9] * len(closes)),
                "dates":      raw_d.get("dates",      []),
                "pct_chgs":   raw_d.get("pct_chgs",   []),
                "extensions": raw_d.get("extensions", {}),
            },
            "indicators": result[sym]["indicators"],
        })
    return out
