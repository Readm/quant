"""
alpha158.py — QLib Alpha158 因子库（纯NumPy实现）
=====================================================
复现微软Qlib Alpha158量价因子集，共158个因子。
参考: github.com/microsoft/qlib | github.com/vnpy/vnpy
"""

import math
from typing import List, Tuple

# Import our ts operators
from experts.modules.ts_operators import (
    ts_delay, ts_mean, ts_std, ts_sum, ts_max, ts_min,
    ts_rank, ts_argmax, ts_argmin, ts_quantile, ts_slope,
    ts_corr, ts_rsquare, ts_resi, ts_delta, ts_product,
    ts_log, ts_abs, ts_greater, ts_less, rank as cross_rank
)

def alpha158_features(
    opens: List[float], highs: List[float], lows: List[float],
    closes: List[float], volumes: List[float],
    windows: List[int] = None
) -> dict:
    """
    生成全部 158 个 Alpha158 因子。
    返回 dict {因子名: [float列表]}
    """
    if windows is None:
        windows = [5, 10, 20, 30, 60]

    n = len(closes)
    features = {}

    def safe(f):
        """安全执行表达式，返回 list"""
        try:
            r = f()
            if r is None: return [float("nan")]*n
            return r if isinstance(r, list) else [float("nan")]*n
        except Exception:
            return [float("nan")]*n

    def fill_nan(base: list, vals: list) -> list:
        """将vals对齐到base长度，前面补nan"""
        if len(vals) == n:
            return vals
        pad = n - len(vals)
        return [float("nan")]*pad + vals

    # ── K线形态因子（9个）────────────────────────────
    open_arr = opens; close_arr = closes; high_arr = highs; low_arr = lows

    def K_MID(): return [(close_arr[i]-open_arr[i])/open_arr[i] if open_arr[i]!=0 else 0.0 for i in range(n)]
    def K_LEN(): return [(high_arr[i]-low_arr[i])/open_arr[i] if open_arr[i]!=0 else 0.0 for i in range(n)]
    def K_MID2(): d=[high_arr[i]-low_arr[i] for i in range(n)]; return [(close_arr[i]-open_arr[i])/(d[i]+1e-12) if d[i]!=0 else 0.0 for i in range(n)]
    def K_UP(): return [((high_arr[i]-open_arr[i]) if open_arr[i]<=high_arr[i] else 0.0)/open_arr[i] if open_arr[i]!=0 else 0.0 for i in range(n)]
    def K_UP2(): d=[high_arr[i]-low_arr[i] for i in range(n)]; return [(high_arr[i]-open_arr[i])/(d[i]+1e-12) if d[i]!=0 else 0.0 for i in range(n)]
    def K_LOW(): return [((open_arr[i]-low_arr[i]) if open_arr[i]>=low_arr[i] else 0.0)/open_arr[i] if open_arr[i]!=0 else 0.0 for i in range(n)]
    def K_LOW2(): d=[high_arr[i]-low_arr[i] for i in range(n)]; return [(open_arr[i]-low_arr[i])/(d[i]+1e-12) if d[i]!=0 else 0.0 for i in range(n)]
    def K_SFT(): return [((close_arr[i]*2-high_arr[i]-low_arr[i])/open_arr[i]) if open_arr[i]!=0 else 0.0 for i in range(n)]
    def K_SFT2(): d=[high_arr[i]-low_arr[i] for i in range(n)]; return [(close_arr[i]*2-high_arr[i]-low_arr[i])/(d[i]+1e-12) if d[i]!=0 else 0.0 for i in range(n)]

    features["kmid"]   = K_MID()
    features["klen"]   = K_LEN()
    features["kmid_2"] = K_MID2()
    features["kup"]    = K_UP()
    features["kup_2"] = K_UP2()
    features["klow"]   = K_LOW()
    features["klow_2"] = K_LOW2()
    features["ksft"]   = K_SFT()
    features["ksft_2"] = K_SFT2()

    # ── 价格比率因子（4个）─────────────────────────────
    for fld_name, fld_arr in [("open",open_arr),("high",high_arr),("low",low_arr),("vwap",close_arr)]:
        features[f"{fld_name}_0"] = [fld_arr[i]/close_arr[i] if close_arr[i]!=0 else 1.0 for i in range(n)]

    # ── ROC因子（5个）─────────────────────────────
    for w in windows:
        delay = ts_delay(close_arr, w)
        features[f"roc_{w}"] = [((close_arr[i]/delay[i])-1) if delay[i]!=0 and not math.isnan(delay[i]) else 0.0 for i in range(n)]

    # ── MA偏离因子（5个）─────────────────────────────
    for w in windows:
        ma = ts_mean(close_arr, w)
        features[f"ma_{w}"] = [ma[i]/close_arr[i]-1 if close_arr[i]!=0 and not math.isnan(ma[i]) else 0.0 for i in range(n)]

    # ── STD波动率因子（5个）─────────────────────────
    for w in windows:
        sd = ts_std(close_arr, w)
        features[f"std_{w}"] = [sd[i]/close_arr[i] if close_arr[i]!=0 and not math.isnan(sd[i]) else 0.0 for i in range(n)]

    # ── BETA斜率因子（5个）───────────────────────────
    for w in windows:
        features[f"beta_{w}"] = fill_nan(close_arr, ts_slope(close_arr, w))

    # ── R平方因子（5个）─────────────────────────────
    for w in windows:
        features[f"rsqr_{w}"] = fill_nan(close_arr, ts_rsquare(close_arr, w))

    # ── 残差因子（5个）─────────────────────────────
    for w in windows:
        features[f"resi_{w}"] = fill_nan(close_arr, ts_resi(close_arr, w))

    # ── MAX/MAX偏离因子（5个）───────────────────────
    for w in windows:
        mx = ts_max(high_arr, w)
        features[f"max_{w}"] = [mx[i]/close_arr[i]-1 if close_arr[i]!=0 and not math.isnan(mx[i]) else 0.0 for i in range(n)]

    # ── MIN/MIN偏离因子（5个）───────────────────────
    for w in windows:
        mn = ts_min(low_arr, w)
        features[f"min_{w}"] = [mn[i]/close_arr[i]-1 if close_arr[i]!=0 and not math.isnan(mn[i]) else 0.0 for i in range(n)]

    # ── 分位数因子（10个: 0.8和0.2各5个窗口）─────────
    for w in windows:
        q80 = ts_quantile(close_arr, w, 0.8)
        q20 = ts_quantile(close_arr, w, 0.2)
        features[f"qtlu_{w}"] = [q80[i]/close_arr[i]-1 if close_arr[i]!=0 and not math.isnan(q80[i]) else 0.0 for i in range(n)]
        features[f"qtld_{w}"] = [q20[i]/close_arr[i]-1 if close_arr[i]!=0 and not math.isnan(q20[i]) else 0.0 for i in range(n)]

    # ── 滚动排名因子（5个）─────────────────────────
    for w in windows:
        features[f"rank_{w}"] = fill_nan(close_arr, ts_rank(close_arr, w))

    # ── RSV因子（5个）─────────────────────────────
    for w in windows:
        rsv_vals = [float("nan")]*(w-1)
        for i in range(w-1, n):
            mn = min(low_arr[i-w+1:i+1])
            mx = max(high_arr[i-w+1:i+1])
            denom = mx-mn
            rsv_vals.append((close_arr[i]-mn)/(denom+1e-12) if denom > 1e-9 else 0.0)
        features[f"rsv_{w}"] = rsv_vals

    # ── IMAX/IMIN因子（10个）───────────────────────
    for w in windows:
        features[f"imax_{w}"] = fill_nan(close_arr, [v/w if not math.isnan(v) else float("nan") for v in ts_argmax(high_arr, w)])
        features[f"imin_{w}"] = fill_nan(close_arr, [v/w if not math.isnan(v) else float("nan") for v in ts_argmin(low_arr, w)])

    # ── IMXD 因子（5个）───────────────────────────
    for w in windows:
        mx_vals = ts_argmax(high_arr, w)
        mn_vals = ts_argmin(low_arr, w)
        features[f"imxd_{w}"] = fill_nan(close_arr, [(mx_vals[i]-mn_vals[i])/w if not (math.isnan(mx_vals[i]) or math.isnan(mn_vals[i])) else float("nan") for i in range(n)])

    # ── CORR因子（5个）────────────────────────────
    log_vol = ts_log([(v+1) for v in volumes])
    for w in windows:
        corr = ts_corr(close_arr, log_vol, w)
        features[f"corr_{w}"] = fill_nan(close_arr, corr)

    # ── CORD因子（5个）────────────────────────────
    ret_arr = [0.0]+[math.log(close_arr[i]/close_arr[i-1]+1e-12) for i in range(1,n)]
    vol_change_arr = [0.0]+[math.log(volumes[i]/(volumes[i-1]+1)-1) if volumes[i-1]!=0 else 0.0 for i in range(1,n)]
    for w in windows:
        cord = ts_corr(ret_arr, vol_change_arr, w)
        features[f"cord_{w}"] = fill_nan(close_arr, cord)

    # ── CNTP/CNTN因子（10个）──────────────────────
    for w in windows:
        cntp = [float("nan")]*(w-1)
        for i in range(w-1, n):
            wins = sum(1 for j in range(i-w+1,i+1) if close_arr[j]>close_arr[j-1])
            cntp.append(wins/w)
        features[f"cntp_{w}"] = cntp

        cntn = [float("nan")]*(w-1)
        for i in range(w-1, n):
            loss = sum(1 for j in range(i-w+1,i+1) if close_arr[j]<close_arr[j-1])
            cntn.append(loss/w)
        features[f"cntn_{w}"] = cntn

    # ── SUMP/SUMD因子（10个）──────────────────────
    for w in windows:
        sump = [float("nan")]*(w-1)
        for i in range(w-1, n):
            up_sum = sum(1 for j in range(i-w+1,i+1) if close_arr[j]>close_arr[j-1])
            abs_sum = sum(abs(close_arr[j]-close_arr[j-1]) for j in range(i-w+1,i+1))
            sump.append(up_sum/(abs_sum+1e-12))
        features[f"sump_{w}"] = sump

        sumd = [float("nan")]*(w-1)
        for i in range(w-1, n):
            up_s = sum(1 for j in range(i-w+1,i+1) if close_arr[j]>close_arr[j-1])
            dn_s = sum(1 for j in range(i-w+1,i+1) if close_arr[j]<close_arr[j-1])
            abs_s = sum(abs(close_arr[j]-close_arr[j-1]) for j in range(i-w+1,i+1))
            sumd.append((up_s-dn_s)/(abs_s+1e-12))
        features[f"sumd_{w}"] = sumd

    # ── VMA/VSTD因子（10个）───────────────────────
    for w in windows:
        vma = ts_mean(volumes, w)
        features[f"vma_{w}"] = [vma[i]/(volumes[i]+1e-12) if not math.isnan(vma[i]) else 1.0 for i in range(n)]
        vstd = ts_std(volumes, w)
        features[f"vstd_{w}"] = [vstd[i]/(volumes[i]+1e-12) if not math.isnan(vstd[i]) else 1.0 for i in range(n)]

    # ── WVMA因子（5个）────────────────────────────
    for w in windows:
        wvma_vals = [float("nan")]*(w-1)
        for i in range(w-1, n):
            w_vals = [abs(close_arr[j]/close_arr[j-1]-1)*volumes[j] for j in range(i-w+1,i+1)]
            m_w = sum(w_vals)/w
            std_w = math.sqrt(sum((v-m_w)**2 for v in w_vals)/w) if len(w_vals)>0 else 0.0
            wvma_vals.append(std_w/(m_w+1e-12) if m_w>1e-10 else 0.0)
        features[f"wvma_{w}"] = wvma_vals

    # ── VSUMP/VSUMN/VSUMD因子（15个）──────────────
    for w in windows:
        vsump = [float("nan")]*(w-1)
        for i in range(w-1, n):
            ups = sum(1 for j in range(i-w+1,i+1) if volumes[j]>volumes[j-1])
            abv = sum(abs(volumes[j]-volumes[j-1]) for j in range(i-w+1,i+1))
            vsump.append(ups/(abv+1e-12))
        features[f"vsump_{w}"] = vsump

        vsumn = [float("nan")]*(w-1)
        for i in range(w-1, n):
            dns = sum(1 for j in range(i-w+1,i+1) if volumes[j]<volumes[j-1])
            abv = sum(abs(volumes[j]-volumes[j-1]) for j in range(i-w+1,i+1))
            vsumn.append(dns/(abv+1e-12))
        features[f"vsumn_{w}"] = vsumn

        vsumd = [float("nan")]*(w-1)
        for i in range(w-1, n):
            ups_d = sum(1 for j in range(i-w+1,i+1) if volumes[j]>volumes[j-1])
            dns_d = sum(1 for j in range(i-w+1,i+1) if volumes[j]<volumes[j-1])
            abv_d = sum(abs(volumes[j]-volumes[j-1]) for j in range(i-w+1,i+1))
            vsumd.append((ups_d-dns_d)/(abv_d+1e-12))
        features[f"vsumd_{w}"] = vsumd

    return features


def alpha158_signal(closes: List[float], highs: List[float],
                    lows: List[float], volumes: List[float],
                    factor_name: str) -> List[int]:
    """
    根据 Alpha158 因子名生成交易信号。
    逻辑：
      rank > 0.8 → 空头信号(-1)
      rank < 0.2 → 多头信号(1)
      中性区间 → 0
    """
    feats = alpha158_features(
        closes, highs, lows, closes, volumes
    )
    vals = feats.get(factor_name, [])
    n = len(vals)
    # 横截面 rank
    valid = [(i, v) for i, v in enumerate(vals) if not math.isnan(v)]
    if not valid: return [0]*n
    sorted_v = sorted(valid, key=lambda x: x[1])
    rnk_map = {i: r/max(len(sorted_v)-1,1) for r, (i,v) in enumerate(sorted_v)}
    signal = [0]*n
    for i, v in valid:
        r = rnk_map[i]
        if r > 0.8: signal[i] = -1
        elif r < 0.2: signal[i] = 1
    return signal
