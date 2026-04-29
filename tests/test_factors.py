"""
test_factors.py — 因子实现质量测试

覆盖:
  1. 每个因子输出非固定值（在多个股票×日期的数据集上至少有2个不同值）
  2. 任意两个因子在大量日期和股票上输出不完全相同
  3. 所有因子能通过 generate_signal 正常调用，不抛异常
  4. 因子信号至少在某些样本上产生非零值（即确实产生交易信号）
"""

import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from factors.signals import generate_signal

# ── 测试数据：3只股票 × 800天 OHLCV ──────────────────────────────
# 使用不同趋势特征确保因子能产生差异
import random
random.seed(42)

def _make_stock_data(start_price: float, trend: float, vol: float, n: int = 800):
    """生成模拟股票数据，用于因子测试
    在上涨趋势中，收盘价偏向区间上沿；下跌趋势中偏向区间下沿
    """
    closes = []
    highs = []
    lows = []
    volumes = []
    price = start_price
    for i in range(n):
        change = random.gauss(trend / n, vol)
        price *= (1 + change)
        closes.append(price)
        daily_range = abs(random.gauss(0, vol * 0.8))
        # 收盘价在高-low中的相对位置随趋势方向偏移
        if trend > 0:
            close_pos = 0.6 + random.random() * 0.3  # 偏向区间上沿
        elif trend < 0:
            close_pos = 0.1 + random.random() * 0.3  # 偏向区间下沿
        else:
            close_pos = 0.2 + random.random() * 0.6  # 均匀分布
        h = price + daily_range * (1 - close_pos)
        l = price - daily_range * close_pos
        highs.append(max(h, l, price))
        lows.append(min(h, l, price))
        volumes.append(random.randint(1000000, 50000000))
    return closes, highs, lows, volumes

# 股票1：平稳（低波动，微弱趋势）
STOCK1_CLOSES, STOCK1_HIGHS, STOCK1_LOWS, STOCK1_VOLS = \
    _make_stock_data(10.0, 0.05, 0.015)

# 股票2：上涨趋势（高波动）
STOCK2_CLOSES, STOCK2_HIGHS, STOCK2_LOWS, STOCK2_VOLS = \
    _make_stock_data(20.0, 0.5, 0.03)

# 股票3：下跌趋势（中波动）
STOCK3_CLOSES, STOCK3_HIGHS, STOCK3_LOWS, STOCK3_VOLS = \
    _make_stock_data(50.0, -0.3, 0.02)

# ── 所有被测试的因子名称 ──────────────────────────────────────────
FACTOR_NAMES = [
    "force_index", "ppo", "accdist", "accumulation_distribution_signal",
    "volume_price_trend", "mass_index", "ergodic_oscillator", "signal_horizon",
    "ultraspline", "ultraband_signal", "chanlun_bi", "chanlun_tao",
    "mfi_signal", "rvi_signal", "kdwave", "multi_roc_signal", "obos_composite",
    "elder_ray_signal",
]

# 每只股票的测试数据元组
STOCKS = [
    ("stock1_flat", STOCK1_CLOSES, STOCK1_HIGHS, STOCK1_LOWS, STOCK1_VOLS),
    ("stock2_up",   STOCK2_CLOSES, STOCK2_HIGHS, STOCK2_LOWS, STOCK2_VOLS),
    ("stock3_down", STOCK3_CLOSES, STOCK3_HIGHS, STOCK3_LOWS, STOCK3_VOLS),
]


# ═══════════════════════════════════════════════════════════════════
# 测试 1: 每个因子输出非固定值
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("factor_name", FACTOR_NAMES)
def test_factor_is_not_constant(factor_name):
    """每个因子在3只股票×800天上至少有2个不同输出值"""
    for stock_name, closes, highs, lows, vols in STOCKS:
        sig = generate_signal(factor_name, closes, highs, lows, vols)
        if len(sig) != len(closes):
            raise AssertionError(
                f"{factor_name} on {stock_name}: "
                f"output length {len(sig)} != expected {len(closes)}"
            )
        uniq = set(sig)
        if len(uniq) < 2:
            raise AssertionError(
                f"{factor_name} on {stock_name}: "
                f"CONSTANT (only {uniq})"
            )


# ═══════════════════════════════════════════════════════════════════
# 测试 2: 所有因子无异常调用
# ═══════════════════════════════════════════════════════════════════

def test_all_factors_work_without_exception():
    """所有因子能在generate_signal下正常调用"""
    for factor_name in FACTOR_NAMES:
        for stock_name, closes, highs, lows, vols in STOCKS:
            try:
                sig = generate_signal(factor_name, closes, highs, lows, vols)
                assert len(sig) == len(closes), \
                    f"{factor_name} on {stock_name}: length mismatch"
            except Exception as e:
                raise AssertionError(
                    f"{factor_name} on {stock_name} crashed: {e}"
                )


# ═══════════════════════════════════════════════════════════════════
# 测试 3: 是否有因子恒为0（完全不产生信号）
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("factor_name", FACTOR_NAMES)
def test_factor_produces_some_nonzero(factor_name):
    """每个因子至少在某些样本上产生非零信号"""
    all_zero = True
    for stock_name, closes, highs, lows, vols in STOCKS:
        sig = generate_signal(factor_name, closes, highs, lows, vols)
        nonzero = sum(1 for v in sig if v != 0)
        if nonzero > 0:
            all_zero = False
            break
    if all_zero:
        raise AssertionError(
            f"{factor_name}: all-zero output on all 3 stocks"
        )


# ═══════════════════════════════════════════════════════════════════
# 测试 4: 任意两个因子输出不完全相同
# ═══════════════════════════════════════════════════════════════════

def test_no_two_factors_are_identical():
    """任意两个因子在全部3只股票×800天上输出不完全相同"""
    for stock_name, closes, highs, lows, vols in STOCKS:
        results: dict[str, tuple] = {}
        for fn in FACTOR_NAMES:
            sig = generate_signal(fn, closes, highs, lows, vols)
            results[fn] = tuple(sig)

        fn_list = list(results.keys())
        for i in range(len(fn_list)):
            for j in range(i + 1, len(fn_list)):
                if results[fn_list[i]] == results[fn_list[j]]:
                    raise AssertionError(
                        f"IDENTICAL on {stock_name}: "
                        f"{fn_list[i]} == {fn_list[j]}"
                    )


# ═══════════════════════════════════════════════════════════════════
# 测试 5: 同样因子在不同股票上产生不同信号（敏感性检验）
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("factor_name", FACTOR_NAMES)
def test_factor_differs_across_stocks(factor_name):
    """同一因子在不同股票上输出不同（验证因子对数据敏感）"""
    signals_on_stocks = []
    for stock_name, closes, highs, lows, vols in STOCKS:
        sig = generate_signal(factor_name, closes, highs, lows, vols)
        signals_on_stocks.append(tuple(sig))

    # 至少两只股票上的输出有差异
    diffs = sum(
        1 for i in range(len(signals_on_stocks))
        for j in range(i + 1, len(signals_on_stocks))
        if signals_on_stocks[i] != signals_on_stocks[j]
    )
    if diffs == 0:
        raise AssertionError(
            f"{factor_name}: identical output on all 3 stocks "
            f"(not sensitive to data)"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
