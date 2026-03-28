"""
ts_operators.py — QLib风格时间序列算子（纯NumPy）
================================================
实现 QLib Alpha158 所用的全部 ts_* 算子：
  ts_delay, ts_mean, ts_std, ts_sum, ts_max, ts_min
  ts_rank, ts_argmax, ts_argmin, ts_quantile, ts_slope
  ts_corr, ts_rsquare, ts_resi, ts_greater, ts_less,
  ts_log, ts_abs, ts_delta, ts_product
Each returns a list of the same length as input.
"""

import math
from typing import List

def _rolling_view(arr: list, window: int) -> List[tuple]:
    """返回 (idx, window_values) 列表"""
    n = len(arr)
    return [(i, arr[i-window+1:i+1]) for i in range(window-1, n)]

def ts_delay(series: List[float], n: int) -> List[float]:
    """向后移位 n"""
    return [float("nan")] * n + series[:-n]

def ts_mean(series: List[float], n: int) -> List[float]:
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        w = series[i-n+1:i+1]
        out.append(sum(w) / n)
    return out

def ts_std(series: List[float], n: int) -> List[float]:
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        w = series[i-n+1:i+1]
        m = sum(w) / n
        v = sum((x-m)**2 for x in w) / n
        out.append(math.sqrt(v))
    return out

def ts_sum(series: List[float], n: int) -> List[float]:
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        out.append(sum(series[i-n+1:i+1]))
    return out

def ts_max(series: List[float], n: int) -> List[float]:
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        out.append(max(series[i-n+1:i+1]))
    return out

def ts_min(series: List[float], n: int) -> List[float]:
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        out.append(min(series[i-n+1:i+1]))
    return out

def ts_argmax(series: List[float], n: int) -> List[float]:
    """返回 n 天内最大值的相对位置（0-based within window）"""
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        w = series[i-n+1:i+1]
        out.append(float(w.index(max(w))))  # relative position
    return out

def ts_argmin(series: List[float], n: int) -> List[float]:
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        w = series[i-n+1:i+1]
        out.append(float(w.index(min(w))))
    return out

def ts_rank(series: List[float], n: int) -> List[float]:
    """滚动窗口内排名的百分位（0~1）"""
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        w = series[i-n+1:i+1]
        sorted_w = sorted(w)
        val = series[i]
        rank = sorted_w.index(val) / max(len(sorted_w)-1, 1)
        out.append(rank)
    return out

def ts_quantile(series: List[float], n: int, q: float) -> List[float]:
    """滚动窗口分位数（q=0.8 即80分位）"""
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        w = sorted(series[i-n+1:i+1])
        idx = q * (len(w)-1)
        lo = int(idx)
        hi = min(lo+1, len(w)-1)
        out.append(w[lo]*(hi-lo) + w[hi]*(idx-lo) if lo != hi else w[lo])
    return out

def ts_slope(series: List[float], n: int) -> List[float]:
    """
    滚动窗口线性回归斜率（单位：per step）
    简化版：使用首尾差/n
    """
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        w = series[i-n+1:i+1]
        x = list(range(n))
        xm, ym = sum(x)/n, sum(w)/n
        num = sum((x[j]-xm)*(w[j]-ym) for j in range(n))
        den = sum((x[j]-xm)**2 for j in range(n))
        out.append(num/(den+1e-10))
    return out

def ts_rsquare(series: List[float], n: int) -> List[float]:
    """滚动窗口线性回归 R^2"""
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        w = series[i-n+1:i+1]
        x = list(range(n))
        xm, ym = sum(x)/n, sum(w)/n
        num = sum((x[j]-xm)*(w[j]-ym) for j in range(n))
        den = sum((x[j]-xm)**2 for j in range(n))
        slope = num/(den+1e-10)
        pred = [xm + slope*(xj-xm) for xj in x]
        ss_res = sum((w[j]-pred[j])**2 for j in range(n))
        ss_tot = sum((w[j]-ym)**2 for j in range(n))
        out.append(1 - ss_res/(ss_tot+1e-10))
    return out

def ts_resi(series: List[float], n: int) -> List[float]:
    """滚动回归残差（最新值 - 回归预测值）"""
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        w = series[i-n+1:i+1]
        x = list(range(n))
        xm, ym = sum(x)/n, sum(w)/n
        num = sum((x[j]-xm)*(w[j]-ym) for j in range(n))
        den = sum((x[j]-xm)**2 for j in range(n))
        slope = num/(den+1e-10)
        pred = xm + slope*(n-1-xm)  # predict last value
        out.append(w[-1] - pred)
    return out

def ts_corr(a: List[float], b: List[float], n: int) -> List[float]:
    """滚动相关系数"""
    assert len(a) == len(b)
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(a)):
        x = a[i-n+1:i+1]
        y = b[i-n+1:i+1]
        xm, ym = sum(x)/n, sum(y)/n
        num = sum((x[j]-xm)*(y[j]-ym) for j in range(n))
        dx = math.sqrt(sum((v-xm)**2 for v in x))
        dy = math.sqrt(sum((v-ym)**2 for v in y))
        out.append(num/(dx*dy+1e-10) if dx*dy > 1e-10 else 0.0)
    return out

def ts_delta(series: List[float], n: int) -> List[float]:
    """一阶差分：series - ts_delay(series, n)"""
    d = ts_delay(series, n)
    return [float("nan")]*n + [series[i] - d[i] for i in range(n, len(series))]

def ts_product(series: List[float], n: int) -> List[float]:
    """滚动乘积"""
    out = [float("nan")] * (n-1)
    for i in range(n-1, len(series)):
        p = 1.0
        for v in series[i-n+1:i+1]:
            p *= v
        out.append(p)
    return out

def ts_log(series: List[float]) -> List[float]:
    return [math.log(max(v, 1e-10)) for v in series]

def ts_abs(series: List[float]) -> List[float]:
    return [abs(v) for v in series]

def ts_greater(a: List[float], b: List[float]) -> List[float]:
    """a > b → 1.0 : 0.0"""
    return [1.0 if a[i] > b[i] else 0.0 for i in range(len(a))]

def ts_less(a: List[float], b: List[float]) -> List[float]:
    """a < b → 1.0 : 0.0"""
    return [1.0 if a[i] < b[i] else 0.0 for i in range(len(a))]

def rank(series: List[float]) -> List[float]:
    """横截面排名（整个序列）"""
    n = len(series)
    valid = [(v, i) for i, v in enumerate(series) if not math.isnan(v)]
    if not valid: return [float("nan")]*n
    sorted_v = sorted(valid, key=lambda x: x[0])
    result = [float("nan")]*n
    for r, (v, i) in enumerate(sorted_v):
        result[i] = r / max(len(sorted_v)-1, 1)
    return result

def ts_normalize(series: List[float], n: int) -> List[float]:
    """(series - rolling_mean) / rolling_std"""
    m = ts_mean(series, n)
    s = ts_std(series, n)
    return [float("nan")]*n + [(series[i]-m[i])/(s[i]+1e-10) if not math.isnan(m[i]) else float("nan") for i in range(n, len(series))]
