#!/usr/bin/env python3
"""
fetch_tushare.py — Tushare 批量数据下载（2000积分版）
=====================================================
下载 A 股量化研究所需的核心数据到 data/tushare/ 目录。

数据类型：
  daily        — 日线行情 (OHLCV + 成交额)
  adj_factor   — 复权因子
  daily_basic  — 每日指标 (PE/PB/换手率/市值)
  moneyflow    — 个股资金流向 (主力/大单净流入)
  stk_limit    — 每日涨跌停价格
  index_daily  — 指数日线 (沪深300/中证500/上证)
  fina_basic   — 财务指标摘要 (ROE/毛利率, 季度)

使用方式：
  python3 scripts/fetch_tushare.py                           # 默认4支股票，全部类型
  python3 scripts/fetch_tushare.py --symbols 600519.SH 600036.SH
  python3 scripts/fetch_tushare.py --start 20150101          # 自定义起始日期
  python3 scripts/fetch_tushare.py --types daily daily_basic # 只下载指定类型
  python3 scripts/fetch_tushare.py --csi300                  # 下载沪深300成分股（慢）

配置：.env 文件中 TUSHARE_TOKEN=your_token

限速：2000积分上限 200次/分钟，本脚本默认 170次/分钟（留安全余量）
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── 加载 .env ────────────────────────────────────────────────────────
def _load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

_load_env()

# ── 配置 ────────────────────────────────────────────────────────────
RATE_LIMIT  = 170                 # 每分钟请求数（2000积分上限200，留余量）
MIN_INTERVAL = 60.0 / RATE_LIMIT  # ~0.35 秒/请求

_ROOT    = Path(__file__).parent.parent
DATA_DIR = _ROOT / "data" / "tushare"
TODAY    = datetime.today().strftime("%Y%m%d")

# 默认下载标的（现有4支 A 股）
DEFAULT_SYMBOLS = [
    "600519.SH",  # 贵州茅台
    "600036.SH",  # 招商银行
    "601318.SH",  # 中国平安
    "000858.SZ",  # 五粮液
]

# 指数
INDEX_SYMBOLS = [
    "000300.SH",  # 沪深300
    "000905.SH",  # 中证500
    "000001.SH",  # 上证指数
]

# 支持的数据类型
ALL_TYPES = ["daily", "adj_factor", "daily_basic", "moneyflow", "stk_limit",
             "index_daily", "fina_basic"]


# ── 限速器 ───────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, calls_per_minute: int = RATE_LIMIT):
        self._interval = 60.0 / calls_per_minute
        self._last = 0.0
        self._count = 0

    def wait(self):
        elapsed = time.time() - self._last
        wait_time = self._interval - elapsed
        if wait_time > 0:
            time.sleep(wait_time)
        self._last = time.time()
        self._count += 1

    @property
    def count(self):
        return self._count


_limiter = RateLimiter()


def _call(fn, **kwargs):
    """带限速的 Tushare API 调用，自动重试一次"""
    _limiter.wait()
    try:
        df = fn(**kwargs)
        return df
    except Exception as e:
        msg = str(e)
        # 频率超限：等待再重试
        if "每分钟" in msg or "limit" in msg.lower() or "频" in msg:
            print(f"    ⚠ 频率超限，等待 30s...")
            time.sleep(30)
            _limiter.wait()
            return fn(**kwargs)
        raise


# ── 保存工具 ─────────────────────────────────────────────────────────
def _save_csv(df, path: Path):
    """保存 DataFrame 为 CSV，追加不重复"""
    if df is None or df.empty:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        import pandas as pd
        existing = pd.read_csv(path, dtype=str)
        # 合并去重（按所有列）
        combined = pd.concat([existing, df.astype(str)], ignore_index=True)
        # 用 trade_date / ann_date / end_date 作为去重键（取其中存在的）
        dup_cols = [c for c in ("trade_date", "ann_date", "end_date") if c in combined.columns]
        if dup_cols:
            combined = combined.drop_duplicates(subset=dup_cols + (["ts_code"] if "ts_code" in combined.columns else []))
        combined.to_csv(path, index=False)
        return len(df)
    else:
        df.to_csv(path, index=False)
        return len(df)


# ── 各数据类型下载函数 ────────────────────────────────────────────────

def fetch_daily(pro, ts_code: str, start_date: str, end_date: str) -> int:
    """日线行情：open/high/low/close/vol/amount/change/pct_chg"""
    path = DATA_DIR / "daily" / f"{ts_code}.csv"
    df = _call(pro.daily, ts_code=ts_code, start_date=start_date, end_date=end_date)
    n = _save_csv(df, path)
    return n


def fetch_adj_factor(pro, ts_code: str, start_date: str, end_date: str) -> int:
    """复权因子"""
    path = DATA_DIR / "adj_factor" / f"{ts_code}.csv"
    df = _call(pro.adj_factor, ts_code=ts_code, start_date=start_date, end_date=end_date)
    n = _save_csv(df, path)
    return n


def fetch_daily_basic(pro, ts_code: str, start_date: str, end_date: str) -> int:
    """每日指标：PE/PB/换手率/总市值/流通市值"""
    path = DATA_DIR / "daily_basic" / f"{ts_code}.csv"
    df = _call(pro.daily_basic, ts_code=ts_code, start_date=start_date, end_date=end_date)
    n = _save_csv(df, path)
    return n


def fetch_moneyflow(pro, ts_code: str, start_date: str, end_date: str) -> int:
    """个股资金流向：主力/大单/中单/小单净流入金额和比率"""
    path = DATA_DIR / "moneyflow" / f"{ts_code}.csv"
    df = _call(pro.moneyflow, ts_code=ts_code, start_date=start_date, end_date=end_date)
    n = _save_csv(df, path)
    return n


def fetch_stk_limit(pro, ts_code: str, start_date: str, end_date: str) -> int:
    """每日涨跌停价格：up_limit / down_limit"""
    path = DATA_DIR / "stk_limit" / f"{ts_code}.csv"
    df = _call(pro.stk_limit, ts_code=ts_code, start_date=start_date, end_date=end_date)
    n = _save_csv(df, path)
    return n


def fetch_index_daily(pro, ts_code: str, start_date: str, end_date: str) -> int:
    """指数日线"""
    path = DATA_DIR / "index_daily" / f"{ts_code}.csv"
    df = _call(pro.index_daily, ts_code=ts_code, start_date=start_date, end_date=end_date)
    n = _save_csv(df, path)
    return n


def fetch_fina_basic(pro, ts_code: str, start_date: str, end_date: str) -> int:
    """财务指标（季报）：ROE/毛利率/净利率/EPS/每股净资产"""
    path = DATA_DIR / "fina_basic" / f"{ts_code}.csv"
    try:
        df = _call(pro.fina_indicator, ts_code=ts_code,
                   fields="ts_code,ann_date,end_date,roe,grossprofit_margin,"
                          "netprofit_margin,eps,bps,debt_to_assets,current_ratio")
        # 按 ann_date 过滤
        if df is not None and not df.empty and "ann_date" in df.columns:
            df = df[(df["ann_date"] >= start_date) & (df["ann_date"] <= end_date)]
        n = _save_csv(df, path)
        return n
    except Exception as e:
        print(f"    ⚠ fina_basic 失败（可能权限不足）: {e}")
        return 0


# 类型→函数映射
_FETCHERS = {
    "daily":       fetch_daily,
    "adj_factor":  fetch_adj_factor,
    "daily_basic": fetch_daily_basic,
    "moneyflow":   fetch_moneyflow,
    "stk_limit":   fetch_stk_limit,
    "index_daily": fetch_index_daily,
    "fina_basic":  fetch_fina_basic,
}


# ── 获取沪深300成分股 ─────────────────────────────────────────────────

def get_csi300_symbols(pro) -> list[str]:
    """获取最新沪深300成分股列表"""
    print("  获取沪深300成分股...")
    _limiter.wait()
    df = pro.index_weight(index_code="000300.SH", trade_date=TODAY)
    if df is None or df.empty:
        # fallback: 用上一个交易日
        _limiter.wait()
        df = pro.index_weight(index_code="000300.SH")
    if df is None or df.empty:
        print("  ⚠ 无法获取成分股，使用默认标的")
        return DEFAULT_SYMBOLS
    symbols = df["con_code"].tolist()
    print(f"  获取到 {len(symbols)} 只成分股")
    return symbols


# ── 元数据下载 ────────────────────────────────────────────────────────

def fetch_metadata(pro):
    """下载股票基本信息和交易日历（元数据）"""
    meta_dir = DATA_DIR / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)

    # 股票基本信息
    print("  下载股票基本信息...")
    _limiter.wait()
    df = pro.stock_basic(exchange="", list_status="L",
                         fields="ts_code,symbol,name,area,industry,market,list_date")
    if df is not None and not df.empty:
        df.to_csv(meta_dir / "stock_basic.csv", index=False)
        print(f"    ✅ stock_basic: {len(df)} 只股票")

    # 交易日历（近10年）
    print("  下载交易日历...")
    _limiter.wait()
    df = pro.trade_cal(exchange="SSE", start_date="20150101", end_date=TODAY)
    if df is not None and not df.empty:
        df.to_csv(meta_dir / "trade_cal.csv", index=False)
        print(f"    ✅ trade_cal: {len(df)} 条记录")


# ── 主流程 ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Tushare 批量数据下载（2000积分版）")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="股票代码列表，如 600519.SH 000858.SZ")
    parser.add_argument("--start",   default="20180101",
                        help="起始日期 YYYYMMDD（默认 20180101）")
    parser.add_argument("--end",     default=TODAY,
                        help=f"结束日期 YYYYMMDD（默认 {TODAY}）")
    parser.add_argument("--types",   nargs="+", default=None,
                        choices=ALL_TYPES,
                        help=f"数据类型（默认全部）: {' '.join(ALL_TYPES)}")
    parser.add_argument("--csi300",     action="store_true",
                        help="下载完整沪深300成分股（约300只）")
    parser.add_argument("--all-ashare", action="store_true",
                        help="下载全部A股（约5500只，预计2~3小时）")
    parser.add_argument("--no-meta",    action="store_true",
                        help="跳过元数据下载（stock_basic / trade_cal）")
    args = parser.parse_args()

    # 检查 Token
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        print("❌ 请在 .env 文件中设置 TUSHARE_TOKEN")
        print("   获取地址: https://tushare.pro → 我的信息 → 接口TOKEN")
        sys.exit(1)

    import tushare as ts
    ts.set_token(token)
    pro = ts.pro_api()

    dtypes = args.types or ALL_TYPES

    print("=" * 60)
    print("  Tushare 数据下载")
    print(f"  日期范围: {args.start} → {args.end}")
    print(f"  数据类型: {dtypes}")
    print(f"  限速:     {RATE_LIMIT} 次/分钟")
    print("=" * 60)

    t0 = time.perf_counter()
    total_rows = 0
    errors = []

    # ── 元数据 ──────────────────────────────────────────────────────
    if not args.no_meta:
        print("\n[1/3] 下载元数据")
        try:
            fetch_metadata(pro)
        except Exception as e:
            print(f"  ⚠ 元数据下载失败: {e}")

    # ── 确定股票列表 ────────────────────────────────────────────────
    if args.all_ashare:
        print("\n获取全部 A 股列表...")
        _limiter.wait()
        df_basic = pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,market")
        symbols = df_basic["ts_code"].tolist()
        print(f"  共 {len(symbols)} 只 A 股")
    elif args.csi300:
        symbols = get_csi300_symbols(pro)
    elif args.symbols:
        symbols = args.symbols
    else:
        symbols = DEFAULT_SYMBOLS

    # ── 股票数据 ────────────────────────────────────────────────────
    print(f"\n[2/3] 下载股票数据（{len(symbols)} 只）")
    stock_dtypes = [t for t in dtypes if t != "index_daily"]

    for i, sym in enumerate(symbols, 1):
        # 断点续传：检查所有类型是否已全部下载
        existing = [t for t in stock_dtypes
                    if (DATA_DIR / t / f"{sym}.csv").exists()]
        if len(existing) == len(stock_dtypes):
            print(f"  [{i}/{len(symbols)}] {sym} ✓ 已完成，跳过")
            continue

        print(f"  [{i}/{len(symbols)}] {sym}")
        for dtype in stock_dtypes:
            path = DATA_DIR / dtype / f"{sym}.csv"
            if path.exists():
                print(f"    {dtype:15s} 已存在")
                continue
            fetcher = _FETCHERS[dtype]
            try:
                n = fetcher(pro, sym, args.start, args.end)
                total_rows += n
                status = f"{n}行" if n > 0 else "空"
                print(f"    {dtype:15s} {status}")
            except Exception as e:
                err = f"{sym}/{dtype}: {str(e)[:80]}"
                errors.append(err)
                print(f"    {dtype:15s} ❌ {str(e)[:60]}")

    # ── 指数数据 ────────────────────────────────────────────────────
    if "index_daily" in dtypes:
        print(f"\n[3/3] 下载指数数据（{len(INDEX_SYMBOLS)} 个）")
        for sym in INDEX_SYMBOLS:
            print(f"  {sym}")
            try:
                n = fetch_index_daily(pro, sym, args.start, args.end)
                total_rows += n
                print(f"    index_daily    {n}行")
            except Exception as e:
                err = f"{sym}/index_daily: {str(e)[:80]}"
                errors.append(err)
                print(f"    ❌ {str(e)[:60]}")

    # ── 汇总 ────────────────────────────────────────────────────────
    dt = time.perf_counter() - t0
    print("\n" + "=" * 60)
    print(f"  完成！总行数: {total_rows:,}  API调用: {_limiter.count}  耗时: {dt:.0f}s")
    print(f"  数据目录: {DATA_DIR}")
    if errors:
        print(f"\n  ⚠ {len(errors)} 个错误:")
        for e in errors:
            print(f"    {e}")
    print("=" * 60)


if __name__ == "__main__":
    main()
