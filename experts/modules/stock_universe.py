"""
stock_universe.py — 股票池管理（ST过滤、上市时间过滤）
=====================================================
目前维护一份静态元数据表。后续可接入 AKShare/Tushare 自动更新。
"""
from datetime import datetime

# ── 静态元数据（可扩展为更大的股票池）─────────────────────────────
_STOCK_META: dict = {
    "SH000300": {"name": "沪深300指数", "is_st": False, "listing_date": "2005-04-08"},
    "SH600519": {"name": "贵州茅台",     "is_st": False, "listing_date": "2001-08-27"},
    "SH600036": {"name": "招商银行",     "is_st": False, "listing_date": "2002-04-09"},
    "SH601318": {"name": "中国平安",     "is_st": False, "listing_date": "2007-03-01"},
    "SZ000858": {"name": "五粮液",       "is_st": False, "listing_date": "1998-04-27"},
    # 扩充池（后续数据接入后取消注释）
    # "SH600000": {"name": "浦发银行",   "is_st": False, "listing_date": "1999-11-10"},
    # "SH601166": {"name": "兴业银行",   "is_st": False, "listing_date": "2007-02-05"},
    # "SZ000002": {"name": "万科A",      "is_st": False, "listing_date": "1991-01-29"},
    # "SH600276": {"name": "恒瑞医药",   "is_st": False, "listing_date": "2000-10-18"},
    # "SZ300750": {"name": "宁德时代",   "is_st": False, "listing_date": "2018-06-11"},
}


def filter_universe(
    symbols: list,
    exclude_st: bool = True,
    min_listing_days: int = 252,
    reference_date: str = None,
) -> list:
    """
    对给定股票池做过滤，返回通过条件的标的列表。

    参数:
        symbols          — 待过滤的股票代码列表
        exclude_st       — 是否排除 ST/PT 股票（默认 True）
        min_listing_days — 最少上市交易日（默认 252，约一年）
        reference_date   — 基准日期字符串 YYYY-MM-DD（默认今日）

    返回:
        通过过滤的股票代码列表（保持原顺序）
    """
    ref = (datetime.strptime(reference_date, "%Y-%m-%d")
           if reference_date else datetime.today())

    result = []
    for sym in symbols:
        meta = _STOCK_META.get(sym)
        if meta is None:
            # 未知标的：元数据缺失时默认通过，方便接入新数据源
            result.append(sym)
            continue
        if exclude_st and meta.get("is_st", False):
            continue
        listing = meta.get("listing_date")
        if listing:
            listed = datetime.strptime(listing, "%Y-%m-%d")
            if (ref - listed).days < min_listing_days:
                continue
        result.append(sym)
    return result


def get_stock_name(symbol: str) -> str:
    return _STOCK_META.get(symbol, {}).get("name", symbol)


def register_stock(symbol: str, name: str, is_st: bool, listing_date: str) -> None:
    """运行时动态注册新标的元数据（不持久化）。"""
    _STOCK_META[symbol] = {
        "name": name,
        "is_st": is_st,
        "listing_date": listing_date,
    }
