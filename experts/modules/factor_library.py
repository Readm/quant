


from typing import Tuple, List

# ═══════════════════════════════════════════════════════════════════════
#  扩充因子库 · F17–F59（2026-03-28）
#  涵盖：Ichimoku · KST · TRIX · Donchian · Aroon · MFI · ADL
#       · CMF · ForceIndex · PPO · ROC多周期 · KDWav
#       · 缠论笔 / 线段简化 · OBOS · SignalHorizon · ElderRay
#       · Ergodic · MassIndex · AccDist · VPT · RVI
# ═══════════════════════════════════════════════════════════════════════


# ───────────────────────────────────────────────────────────────────
#  趋势类（Trend）
# ───────────────────────────────────────────────────────────────────

def ichimoku_cloud(highs: list, lows: list, closes: list,
                   tenkan: int = 9, kijun: int = 26, senkou_b: int = 52,
                   displacement: int = 26
                   ) -> Tuple[List[float], List[float], List[float], List[float], List[float]]:
    """
    Ichimoku Cloud（一目均衡表）
    返回 (tenkan_sen, kijun_sen, senkou_a, senkou_b, chikou_span)
    """
    # 保存参数期数（避免与同名局部列表冲突）
    tenkan_period   = tenkan
    kijun_period    = kijun
    senkou_b_period = senkou_b

    n = len(closes)
    def _mid(h_arr, l_arr, period, idx):
        if idx < period - 1: return float("nan")
        return (max(h_arr[idx-period+1:idx+1]) + min(l_arr[idx-period+1:idx+1])) / 2.0

    tenkan_line   = [float("nan")] * n
    kijun_line    = [float("nan")] * n
    senkou_a_line = [float("nan")] * n
    senkou_b_line = [float("nan")] * n
    chikou        = [float("nan")] * n

    for i in range(n):
        tenkan_line[i]   = _mid(highs, lows, tenkan_period, i)
        kijun_line[i]    = _mid(highs, lows, kijun_period, i)
        senkou_a_line[i] = (
            (tenkan_line[i] + kijun_line[i]) / 2.0
            if not (math.isnan(tenkan_line[i]) or math.isnan(kijun_line[i]))
            else float("nan")
        )
        senkou_b_line[i] = _mid(highs, lows, senkou_b_period, i)
        chikou[i]        = closes[i - displacement] if i >= displacement else float("nan")

    return tenkan_line, kijun_line, senkou_a_line, senkou_b_line, chikou


def ichimoku_signal(closes: list, highs: list, lows: list,
                    tenkan: int = 9, kijun: int = 26,
                    senkou_b: int = 52) -> List[int]:
    """
    Ichimoku 交易信号：1=多/-1=空/0=中性
    金叉(tenkan上穿kijun)+价格站上云顶 → 多；死叉 → 空
    """
    tenkan_s, kijun_s, senkou_a, senkou_b, _ = ichimoku_cloud(highs, lows, closes, tenkan, kijun, senkou_b)
    n = len(closes)
    signal = [0] * n
    for i in range(1, n):
        if math.isnan(tenkan_s[i]) or math.isnan(kijun_s[i]):
            continue
        # tenkan/kijun crossover
        above_prev = tenkan_s[i-1] >= kijun_s[i-1] if not math.isnan(tenkan_s[i-1]) else False
        above_now  = tenkan_s[i] >= kijun_s[i]
        # cloud top/bottom
        cloud_top = senkou_a[i] if not math.isnan(senkou_a[i]) else senkou_b[i]
        cloud_bot = senkou_b[i] if not math.isnan(senkou_b[i]) else senkou_a[i]
        price_above_cloud = closes[i] > cloud_top
        price_below_cloud = closes[i] < cloud_bot
        if above_now and not above_prev and price_above_cloud:
            signal[i] = 1
        elif not above_now and above_prev and price_below_cloud:
            signal[i] = -1
    return signal


def parabolic_sar(highs: list, lows: list, closes: list,
                  af_start: float = 0.02, af_step: float = 0.02,
                  af_max: float = 0.2) -> List[float]:
    """
    Parabolic SAR（抛物线止损转向）
    返回 SAR 值序列（用于生成信号：SAR<close→多，SAR>close→空）
    """
    n = len(closes)
    if n < 2: return [float("nan")] * n
    sar = [float("nan")] * n
    trend = 1  # 1=上涨，-1=下跌
    af = af_start
    ep = highs[0]  # 极值点
    sar[0] = lows[0]
    ep = highs[0]

    for i in range(1, n):
        prev_sar = sar[i-1]
        # SAR = prev_sar + af * (ep - prev_sar)
        sar[i] = prev_sar + af * (ep - prev_sar)
        if trend == 1:
            sar[i] = min(sar[i], sar[i-1] if i > 1 else sar[i])
            sar[i] = min(sar[i], lows[i-1], lows[i-2] if i > 2 else lows[i-1])
            if lows[i] < sar[i]:
                trend = -1
                sar[i] = ep
                ep = lows[i]
                af = af_start
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + af_step, af_max)
        else:  # trend == -1
            sar[i] = max(sar[i], sar[i-1] if i > 1 else sar[i])
            sar[i] = max(sar[i], highs[i-1], highs[i-2] if i > 2 else highs[i-1])
            if highs[i] > sar[i]:
                trend = 1
                sar[i] = ep
                ep = highs[i]
                af = af_start
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + af_step, af_max)

    return sar


def kst(closes: list,
        roc1: int = 10, roc2: int = 15, roc3: int = 20, roc4: int = 30,
        sma1: int = 10, sma2: int = 10, sma3: int = 10, sma4: int = 15
        ) -> Tuple[List[float], List[float]]:
    """
    KST (Know Sure Thing) — 多周期 ROC 平滑指标
    返回 (kst_line, signal_line)
    """
    def _rc(s, p):
        r = roc(s, p)
        return r

    def _ksma(s, p):
        vals = [v for v in _rc(s, p) if not math.isnan(v)]
        if len(vals) < p: return [float("nan")] * len(s)
        sm = sma(vals, p)
        # align
        offset = len(s) - len(sm)
        return [float("nan")] * offset + sm

    kst_vals = [float("nan")] * len(closes)
    for i in range(len(closes)):
        r1 = _rc(closes, roc1); r2 = _rc(closes, roc2)
        r3 = _rc(closes, roc3); r4 = _rc(closes, roc4)
        v1 = r1[i] if i < len(r1) and not math.isnan(r1[i]) else 0.0
        v2 = r2[i] if i < len(r2) and not math.isnan(r2[i]) else 0.0
        v3 = r3[i] if i < len(r3) and not math.isnan(r3[i]) else 0.0
        v4 = r4[i] if i < len(r4) and not math.isnan(r4[i]) else 0.0
        kst_vals[i] = v1 + 2*v2 + 3*v3 + 4*v4

    sig = sma(kst_vals, 9)
    return kst_vals, sig


def trix(closes: list, period: int = 15, signal: int = 9) -> Tuple[List[float], List[float]]:
    """
    TRIX（三重指数平滑）— 趋势过滤噪音
    返回 (trix_line, signal_line)
    """
    ema1 = ema(closes, period)
    ema2 = ema([v if not math.isnan(v) else 0.0 for v in ema1], period)
    ema3 = ema([v if not math.isnan(v) else 0.0 for v in ema2], period)
    trix_vals = [float("nan")] * len(closes)
    for i in range(1, len(closes)):
        prev = ema3[i-1] if not math.isnan(ema3[i-1]) else 0.0
        curr = ema3[i]   if not math.isnan(ema3[i])   else 0.0
        if abs(prev) > 1e-10:
            trix_vals[i] = ((curr - prev) / prev) * 100.0
    sig = sma(trix_vals, signal)
    return trix_vals, sig


def donchian_channel(highs: list, lows: list, period: int = 20
                    ) -> Tuple[List[float], List[float], List[float]]:
    """
    Donchian Channel（唐奇安通道）
    返回 (upper, middle, lower)
    """
    n = len(highs)
    upper, middle, lower = [float("nan")] * n, [float("nan")] * n, [float("nan")] * n
    for i in range(period - 1, n):
        upper[i]  = max(highs[i-period+1:i+1])
        lower[i]  = min(lows[i-period+1:i+1])
        middle[i] = (upper[i] + lower[i]) / 2.0
    return upper, middle, lower


def donchian_breakout(closes: list, highs: list, lows: list,
                     period: int = 20) -> List[int]:
    """
    Donchian 突破策略信号：1=上破上轨/0=持有/-1=下破下轨
    """
    upper, middle, lower = donchian_channel(highs, lows, period)
    n = len(closes)
    signal = [0] * n
    for i in range(period, n):
        if math.isnan(upper[i]) or math.isnan(lower[i]): continue
        if closes[i] > upper[i]:
            signal[i] = 1
        elif closes[i] < lower[i]:
            signal[i] = -1
    return signal


def aroon(highs: list, lows: list, period: int = 25
         ) -> Tuple[List[float], List[float]]:
    """
    Aroon 指标（阿朗）：(aroon_up, aroon_down)
    50以上：强势；50以下：弱势；交叉判断趋势转换
    """
    n = len(highs)
    aroon_up = [float("nan")] * n
    aroon_down = [float("nan")] * n
    for i in range(period - 1, n):
        _, up_idx   = _min_idx(highs[i-period+1:i+1])
        _, down_idx = _min_idx([ -v for v in lows[i-period+1:i+1]])
        aroon_up[i]   = 100.0 * (period - up_idx)   / period
        aroon_down[i]  = 100.0 * (period - down_idx) / period
    return aroon_up, aroon_down


def _min_idx(arr):
    """返回 (value, index) of minimum"""
    valid = [(v, i) for i, v in enumerate(arr) if not math.isnan(v)]
    if not valid: return float("nan"), -1
    return min(valid, key=lambda x: x[0])


def aroon_signal(closes: list, highs: list, lows: list, period: int = 25) -> List[int]:
    """
    Aroon 交叉信号：aroon_up 上穿 aroon_down → 多；下穿 → 空
    """
    up, down = aroon(highs, lows, period)
    n = len(closes)
    signal = [0] * n
    for i in range(1, n):
        if math.isnan(up[i]) or math.isnan(down[i]): continue
        above = up[i] > down[i]
        above_prev = up[i-1] > down[i-1] if not math.isnan(up[i-1]) else False
        if above and not above_prev:
            signal[i] = 1
        elif not above and above_prev:
            signal[i] = -1
    return signal


# ───────────────────────────────────────────────────────────────────
#  均值回归类（Mean Reversion）
# ───────────────────────────────────────────────────────────────────

def money_flow_index(highs: list, lows: list, closes: list,
                    volumes: list, period: int = 14) -> List[float]:
    """
    MFI（资金流量指标）
    价格+成交量确认的超买超卖，类似RSI但含成交量
    MFI>80 超买；MFI<20 超卖
    """
    n = min(len(closes), len(volumes), len(highs), len(lows))
    typical = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    raw_mf  = [typical[i] * volumes[i] for i in range(n)]

    mfi = [float("nan")] * n
    for i in range(period, n):
        pos_flow = sum(raw_mf[j] for j in range(i-period+1, i+1) if typical[j] > typical[j-1]) if i > 0 else 0.0
        neg_flow = sum(raw_mf[j] for j in range(i-period+1, i+1) if typical[j] < typical[j-1]) if i > 0 else 0.0
        if neg_flow == 0:
            mfi[i] = 100.0
        else:
            mr = pos_flow / neg_flow
            mfi[i] = 100.0 - 100.0 / (1.0 + mr)
    return mfi


def mfi_signal(closes: list, highs: list, lows: list,
              volumes: list, period: int = 14) -> List[int]:
    """MFI 超买超卖信号：>80 空/-1=超卖 1=超跌买入"""
    mfi_vals = money_flow_index(highs, lows, closes, volumes, period)
    n = len(mfi_vals)
    signal = [0] * n
    for i in range(period, n):
        v = mfi_vals[i]
        if math.isnan(v): continue
        if v > 80:
            signal[i] = -1  # 超买，空
        elif v < 20:
            signal[i] = 1   # 超卖，多
    return signal


def accdist(highs: list, lows: list, closes: list,
           volumes: list) -> List[float]:
    """
    AD（累积派发线）— 量价背离分析
    创新高+AD下降 → 主力出货；创新低+AD上升 → 主力吸筹
    """
    n = min(len(closes), len(volumes), len(highs), len(lows))
    ad = [float("nan")] * n
    accum = 0.0
    for i in range(n):
        if i == 0:
            ad[0] = 0.0
            continue
        if highs[i] != lows[i]:
            mf = 2.0 * closes[i] - lows[i] - highs[i]
            accum += volumes[i] * mf / (highs[i] - lows[i])
        ad[i] = accum
    return ad


def accumulation_distribution_signal(closes: list, highs: list,
                                   lows: list, volumes: list) -> List[int]:
    """AD 背离信号：价格创新高而AD下降→空；价格创新低而AD上升→多"""
    ad = accdist(highs, lows, closes, volumes)
    n = len(closes)
    signal = [0] * n
    for i in range(1, n):
        price_rising = closes[i] > closes[i-1]
        ad_rising    = ad[i] > ad[i-1] if not (math.isnan(ad[i]) or math.isnan(ad[i-1])) else False
        if price_rising and not ad_rising:
            signal[i] = -1   # 价涨量跌，背离，看空
        elif not price_rising and ad_rising:
            signal[i] = 1    # 价跌量涨，背离，看多
    return signal


def volume_price_trend(closes: list, volumes: list) -> List[float]:
    """
    VPT（成交量价格趋势）
    累加：(当日收益率 * 成交量) → 判断趋势强度
    """
    n = min(len(closes), len(volumes))
    vpt = [float("nan")] * n
    accum = 0.0
    for i in range(1, n):
        if closes[i-1] == 0:
            accum += 0.0
        else:
            accum += (closes[i] - closes[i-1]) / closes[i-1] * volumes[i]
        vpt[i] = accum
    return vpt


def rvi(highs: list, lows: list, closes: list, period: int = 10) -> List[float]:
    """
    RVI（相对活力指数）
    上涨日收在高位的比例；>50→多；<50→空
    """
    n = len(closes)
    rvi_vals = [float("nan")] * n
    for i in range(period, n):
        num = 0.0
        den = 1e-10
        for j in range(i-period+1, i+1):
            close_range = highs[j] - lows[j]
            if close_range > 1e-9:
                num += (closes[j] - lows[j]) / close_range
                den += 1.0
        rvi_vals[i] = (num / den) * 100.0
    return rvi_vals


def ergodic_oscillator(closes: list, highs: list, lows: list,
                      period: int = 20, smooth: int = 5) -> Tuple[List[float], List[float]]:
    """
    Ergodic Oscillator（遍历摆动指标）
    返回 (ergodic_line, signal_line)
    与 MACD 类似但基于 EMA 平滑
    """
    n = len(closes)
    signal = [0.0] * n
    # base: (close - sma) / (high - low)
    sma_c = sma(closes, period)
    for i in range(n):
        if math.isnan(sma_c[i]): continue
        hl = highs[i] - lows[i]
        signal[i] = (closes[i] - sma_c[i]) / (hl + 1e-10) if abs(hl) > 1e-10 else 0.0

    ergodic = [float("nan")] * n
    # rough EMA
    for i in range(smooth-1, n):
        window = [signal[j] for j in range(i-smooth+1, i+1) if not math.isnan(signal[j])]
        if window:
            ergodic[i] = sum(window) / len(window)

    sig_line = sma(ergodic, smooth)
    return ergodic, sig_line


def mass_index(highs: list, lows: list, ema_period: int = 9,
              ema2_period: int = 25) -> List[float]:
    """
    Mass Index（梅斯指标）
    高位反转信号：mass>27后跌穿26.5→趋势反转
    """
    at = atr(highs, lows, highs, ema_period)  # 复用atr，用highs作为closes简化
    # 重新算true range
    tr_vals = [float("nan")] * len(highs)
    for i in range(1, len(highs)):
        tr_vals[i] = max(highs[i]-lows[i],
                         abs(highs[i]-closes[i-1]) if i > 0 else 0.0,
                         abs(lows[i]-closes[i-1])  if i > 0 else 0.0)
    ema1 = ema(tr_vals, ema_period)
    ema2 = ema(ema1, ema2_period)
    n = len(highs)
    mass = [float("nan")] * n
    for i in range(ema2_period-1, n):
        if math.isnan(ema1[i]) or math.isnan(ema2[i]): continue
        mass[i] = ema1[i] / (ema2[i] + 1e-10)
    return mass


# ───────────────────────────────────────────────────────────────────
#  成交量 / 量价类（Volume & Momentum）
# ───────────────────────────────────────────────────────────────────

def force_index(closes: list, volumes: list, period: int = 13) -> List[float]:
    """
    Force Index（.force Index）
    衡量价格变动背后的成交量驱动力
    正值→多头力量；负值→空头力量
    """
    n = min(len(closes), len(volumes))
    fi = [float("nan")] * n
    fi[0] = 0.0
    for i in range(1, n):
        fi[i] = (closes[i] - closes[i-1]) * volumes[i]
    # EMA smooth
    fi_ema = ema(fi, period)
    return fi_ema


def elder_ray(closes: list, highs: list, lows: list,
             period: int = 13) -> Tuple[List[float], List[float]]:
    """
    Elder Ray（艾达透视指标）：(bull_power, bear_power)
    多头力道 = 最高价 - EMA；空头力道 = 最低价 - EMA
    EMA上升 + bull_power>0 → 多头信号
    """
    ema_val = ema(closes, period)
    n = len(closes)
    bull = [float("nan")] * n
    bear = [float("nan")] * n
    for i in range(n):
        if math.isnan(ema_val[i]): continue
        bull[i] = highs[i] - ema_val[i]
        bear[i] = lows[i]  - ema_val[i]
    return bull, bear


def elder_ray_signal(closes: list, highs: list, lows: list,
                    period: int = 13) -> List[int]:
    """Elder Ray 买入信号：EMA上升 + bull_power 由负转正"""
    bull, bear = elder_ray(closes, highs, lows, period)
    ema_val = ema(closes, period)
    n = len(closes)
    signal = [0] * n
    for i in range(1, n):
        if math.isnan(ema_val[i]) or math.isnan(bull[i]) or math.isnan(bull[i-1]): continue
        # EMA rising
        ema_rising = ema_val[i] > ema_val[i-1]
        bull_turning_up = bull[i] > 0 and bull[i-1] <= 0
        bear_turning_down = bear[i] < 0 and bear[i-1] >= 0
        if ema_rising and bull_turning_up:
            signal[i] = 1
        elif not ema_rising and bear_turning_down:
            signal[i] = -1
    return signal


def chaikin_oscillator(highs: list, lows: list, closes: list,
                      volumes: list, fast: int = 3, slow: int = 10) -> List[float]:
    """
    Chaikin Oscillator（蔡金振荡器）
    ADL 的 EMA 差值；上穿0→多；下穿0→空
    """
    # Accumulation/Distribution Line
    ad = accdist(highs, lows, closes, volumes)
    ad_ema_fast = ema(ad, fast)
    ad_ema_slow = ema(ad, slow)
    n = len(closes)
    co = [float("nan")] * n
    for i in range(n):
        f = ad_ema_fast[i] if not math.isnan(ad_ema_fast[i]) else 0.0
        s = ad_ema_slow[i] if not math.isnan(ad_ema_slow[i]) else 0.0
        co[i] = f - s
    return co


def chaikin_signal(closes: list, highs: list, lows: list,
                  volumes: list, fast: int = 3, slow: int = 10) -> List[int]:
    """Chaikin Oscillator 交叉信号"""
    co = chaikin_oscillator(highs, lows, closes, volumes, fast, slow)
    n = len(co)
    signal = [0] * n
    for i in range(1, n):
        if math.isnan(co[i]) or math.isnan(co[i-1]): continue
        if co[i] > 0 and co[i-1] <= 0:
            signal[i] = 1
        elif co[i] < 0 and co[i-1] >= 0:
            signal[i] = -1
    return signal


def ppo(closes: list, fast: int = 12, slow: int = 26,
       signal: int = 9) -> Tuple[List[float], List[float]]:
    """
    PPO（价格震荡百分比）— MACD的百分比版本
    (EMA_fast - EMA_slow) / EMA_slow * 100
    """
    ef = ema(closes, fast)
    es = ema(closes, slow)
    n = len(closes)
    ppo_vals = [float("nan")] * n
    for i in range(n):
        e = es[i] if not math.isnan(es[i]) else 0.0
        f = ef[i] if not math.isnan(ef[i]) else 0.0
        if abs(e) > 1e-10:
            ppo_vals[i] = (f - e) / e * 100.0
    sig = ema(ppo_vals, signal)
    return ppo_vals, sig


# ───────────────────────────────────────────────────────────────────
#  波幅类（Volatility）
# ───────────────────────────────────────────────────────────────────

def ultraspline(highs: list, lows: list, closes: list,
               lookback: int = 20) -> List[float]:
    """
    Ultra-Spline（波动率压缩爆发因子）
    波幅（最高-最低）/ 移动均值 → 波幅收缩至历史低位后爆发
    """
    n = len(highs)
    hml = [highs[i] - lows[i] for i in range(n)]
    hml_sma = sma(hml, lookback)
    out = [float("nan")] * n
    for i in range(n):
        if math.isnan(hml_sma[i]) or hml_sma[i] < 1e-10: continue
        out[i] = hml[i] / hml_sma[i]  # 比率，越小波幅越收缩
    return out


def ultraband_signal(closes: list, highs: list, lows: list,
                    period: int = 20, threshold: float = 0.5) -> List[int]:
    """
    Ultra-Band 突破：波幅收缩至threshold倍历史低位后入场
    布林带2.0倍以下 + ATR突破 → 爆发信号
    """
    upper, middle, lower = donchian_channel(highs, lows, period)
    bb_mid, bb_upper, bb_lower = bollinger_bands(closes, period, 2.0)
    bb_width = [float("nan")] * len(closes)
    for i in range(len(closes)):
        u = bb_upper[i] if not math.isnan(bb_upper[i]) else 0.0
        l = bb_lower[i] if not math.isnan(bb_lower[i]) else 0.0
        m = bb_mid[i]   if not math.isnan(bb_mid[i])   else 0.0
        if abs(u - l) > 1e-10:
            bb_width[i] = (u - l) / (m + 1e-10)
    at = atr(highs, lows, closes, period)
    n = len(closes)
    signal = [0] * n
    for i in range(period, n):
        bw = bb_width[i] if not math.isnan(bb_width[i]) else 1.0
        a = at[i] if not math.isnan(at[i]) else 0.0
        if bw < threshold and a > 0 and closes[i] > bb_upper[i]:
            signal[i] = 1
        elif closes[i] < bb_lower[i]:
            signal[i] = -1
    return signal


def signal_horizon(highs: list, lows: list, closes: list,
                  volumes: list, smooth: int = 5) -> Tuple[List[float], List[float]]:
    """
    Signal Horizon（信号地平线）
    趋势强度 = (close - rolling_low) / (rolling_high - rolling_low + 1e-10)
    强度突破均线 → 入场
    """
    n = len(closes)
    sh_vals = [float("nan")] * n
    for i in range(smooth, n):
        window_c = closes[i-smooth+1:i+1]
        window_h = highs[i-smooth+1:i+1]
        window_l = lows[i-smooth+1:i+1]
        lo = min(window_l); hi = max(window_h)
        if abs(hi - lo) < 1e-10:
            sh_vals[i] = 0.5
        else:
            sh_vals[i] = (closes[i] - lo) / (hi - lo)
    sig = sma(sh_vals, smooth)
    return sh_vals, sig


# ───────────────────────────────────────────────────────────────────
#  多周期动量类（Multi-Period Momentum）
# ───────────────────────────────────────────────────────────────────

def momentum_matrix(closes: list) -> dict:
    """
    动量矩阵：5个时间框架（5/10/20/60/120日）
    全部正 → 强劲多头；全部负 → 强劲空头；混合 → 震荡
    """
    periods = [5, 10, 20, 60, 120]
    result = {}
    for p in periods:
        vals = momentum(closes, p)
        valid = [v for v in vals if not math.isnan(v)]
        result[f"roc_{p}"] = valid[-1] if valid else float("nan")
    return result


def multi_roc_signal(closes: list,
                     periods: list = None) -> List[int]:
    """
    多周期ROC一致性信号
    短周期全部正 → 做多；长周期全部负 → 做空
    """
    if periods is None:
        periods = [5, 10, 20]
    n = len(closes)
    signal = [0] * n
    for i in range(max(periods), n):
        vals = []
        for p in periods:
            if i >= p:
                r = (closes[i] - closes[i-p]) / closes[i-p] if closes[i-p] != 0 else 0.0
                vals.append(r)
        if not vals: continue
        avg = sum(vals) / len(vals)
        if all(v > 0 for v in vals) and avg > 0.01:
            signal[i] = 1
        elif all(v < 0 for v in vals) and avg < -0.01:
            signal[i] = -1
    return signal


# ───────────────────────────────────────────────────────────────────
#  综合信号类（Composite）
# ───────────────────────────────────────────────────────────────────

def obos_composite(closes: list, volumes: list,
                  rsi_period: int = 14, atr_period: int = 14,
                  volume_ma: int = 20) -> Tuple[List[float], List[int]]:
    """
    OBOS（超买超卖综合指标）
    RSI + 成交量确认 → 综合超买超卖评分
    返回 (obos_score 0~100,  signal: 1/-1/0)
    """
    rsi_vals = rsi(closes, rsi_period)
    vr = volume_ratio(volumes, volume_ma)
    n = len(closes)
    obos = [float("nan")] * n
    for i in range(n):
        r = rsi_vals[i] if not math.isnan(rsi_vals[i]) else 50.0
        v = vr[i]       if not math.isnan(vr[i])       else 1.0
        # RSI已经是0-100，成交量比>1.5说明放量，确认趋势
        obos[i] = r if v < 1.5 else max(0, min(100, r * 1.1))  # 放量强化信号
    signal = [0] * n
    for i in range(n):
        o = obos[i]
        if math.isnan(o): continue
        if o > 75:
            signal[i] = -1
        elif o < 25:
            signal[i] = 1
    return obos, signal


def kdwave(highs: list, lows: list, closes: list,
         k_period: int = 9, d_period: int = 3) -> Tuple[List[float], List[float], List[int]]:
    """
    KDWav（KDJ波动波形）
    K/D 金叉 + 股价在中轨上方 → 多
    K/D 死叉 + 股价在中轨下方 → 空
    """
    k_vals, d_vals = stochastic(highs, lows, closes, k_period, d_period)
    bb_mid, _, _ = bollinger_bands(closes, 20, 2.0)
    n = len(closes)
    signal = [0] * n
    for i in range(1, n):
        if math.isnan(k_vals[i]) or math.isnan(d_vals[i]): continue
        kd_gold = k_vals[i] > d_vals[i] and k_vals[i-1] <= d_vals[i-1]
        kd_dead = k_vals[i] < d_vals[i] and k_vals[i-1] >= d_vals[i-1]
        above_bb = closes[i] > bb_mid[i] if not math.isnan(bb_mid[i]) else True
        if kd_gold and above_bb:
            signal[i] = 1
        elif kd_dead and not above_bb:
            signal[i] = -1
    return k_vals, d_vals, signal


# ───────────────────────────────────────────────────────────────────
#  缠论简化因子（ChanLun）
# ───────────────────────────────────────────────────────────────────



# ───────────────────────────────────────────────────────────────────
#  缠论简化因子（ChanLun）
# ───────────────────────────────────────────────────────────────────

def chanlun_bi(closes: list, period: int = 5) -> Tuple[List[int], List[float]]:
    """
    缠论笔（简化版）
    笔 = 连续N日内方向不变的价格段落
    返回 (笔方向序列: 1=向上笔/-1=向下笔/0=中性, 笔极值)
    """
    n = len(closes)
    direction = [0] * n
    extreme   = [float("nan")] * n

    if n < period * 2:
        return direction, extreme

    i = period
    current_dir = None   # None / 1 (up) / -1 (down)
    local_high  = closes[0]
    local_low   = closes[0]

    while i < n:
        window_h = max(closes[max(0, i-period):i])
        window_l = min(closes[max(0, i-period):i])

        if current_dir is None:
            if closes[i] > window_h:
                current_dir = 1
                local_high  = closes[i]
            elif closes[i] < window_l:
                current_dir = -1
                local_low   = closes[i]

        elif current_dir == 1:
            if closes[i] > local_high:
                local_high = closes[i]
            elif closes[i] < window_l:
                # 笔结束，标记为向上笔
                for j in range(i - period, i):
                    if j >= 0:
                        direction[j] = 1
                        extreme[j]   = local_high
                current_dir = -1
                local_low   = closes[i]

        elif current_dir == -1:
            if closes[i] < local_low:
                local_low = closes[i]
            elif closes[i] > window_h:
                # 笔结束，标记为向下笔
                for j in range(i - period, i):
                    if j >= 0:
                        direction[j] = -1
                        extreme[j]   = local_low
                current_dir = 1
                local_high   = closes[i]

        i += 1

    return direction, extreme


def chanlun_tao(directions: list, extremes: list) -> List[int]:
    """
    缠论套（笔的集合形成套）
    向上笔后出现向下笔 → 套方向切换
    返回 (套方向序列: 1/-1/0)
    """
    n = len(directions)
    tao = [0] * n
    current = 0
    for i in range(n):
        if directions[i] != 0:
            if current == 0:
                current = directions[i]
            elif directions[i] == -current:
                current = directions[i]
        tao[i] = current
    return tao


# ───────────────────────────────────────────────────────────────────
#  因子注册表（所有因子 ID → 函数名映射）
# ───────────────────────────────────────────────────────────────────

FACTOR_TABLE = {
    # ── 趋势类 ─────────────────────
    "F00": ("sma_cross",          "MA5上穿MA20",         ["closes"]),
    "F01": ("sma_cross",           "MA10上穿MA60",        ["closes"]),
    "F02": ("macd",               "MACD金叉",             ["closes"]),
    "F03": ("momentum",            "3月动量正",           ["closes"]),
    "F04": ("atr_breakout",        "ATR20日突破",         ["highs","lows","closes"]),
    "F05": ("price_above_sma20",   "价格>20日均线",      ["closes"]),
    # ── 均值回归类 ─────────────────
    "F06": ("rsi_oversold",       "RSI超卖25",           ["closes"]),
    "F07": ("rsi_oversold",       "RSI超卖30",           ["closes"]),
    "F08": ("rsi_oversold",        "RSI<40买入",          ["closes"]),
    "F09": ("bollinger_lower",     "布林下轨买入",        ["closes"]),
    "F10": ("bollinger_upper",     "布林上轨卖出",        ["closes"]),
    "F11": ("kdj_oversold",        "KDJ超卖反弹",         ["highs","lows","closes"]),
    # ── 波幅类 ─────────────────────
    "F12": ("atr_expand",          "ATR放大确认",         ["highs","lows","closes"]),
    "F13": ("atr_contract",        "ATR收缩预警",         ["highs","lows","closes"]),
    "F14": ("ultraspline",         "波幅收缩爆发",         ["highs","lows","closes"]),
    # ── 时序类 ─────────────────────
    "F15": ("roc",                 "ROC定价过高",          ["closes"]),
    "F16": ("consecutive_up",      "连涨3日",              ["closes"]),
    # ── 新增趋势类（F17-F25）───────
    "F17": ("ichimoku_cloud",      "Ichimoku云图",        ["highs","lows","closes"]),
    "F18": ("ichimoku_signal",     "Ichimoku金叉",        ["highs","lows","closes"]),
    "F19": ("parabolic_sar",       "Parabolic SAR",       ["highs","lows","closes"]),
    "F20": ("kst",                 "KST多周期动量",        ["closes"]),
    "F21": ("trix",                "TRIX三重指数",         ["closes"]),
    "F22": ("donchian_breakout",   "Donchian突破",        ["highs","lows","closes"]),
    "F23": ("aroon_signal",        "Aroon交叉",           ["highs","lows","closes"]),
    "F24": ("ppof",                "PPO信号",             ["closes"]),
    "F25": ("supertrend",          "Supertrend",          ["highs","lows","closes"]),
    # ── 新增均值回归类（F26-F32）───
    "F26": ("mfi_signal",          "MFI资金流",           ["highs","lows","closes","volumes"]),
    "F27": ("rvi_signal",          "RVI相对活力",         ["highs","lows","closes"]),
    "F28": ("momentum_matrix",     "多周期动量矩阵",      ["closes"]),
    "F29": ("multi_roc_signal",    "ROC多周期一致",       ["closes"]),
    "F30": ("obos_signal",         "OBOS综合超买超卖",    ["closes","volumes"]),
    "F31": ("kdwave",              "KDJ波动波形",          ["highs","lows","closes"]),
    "F32": ("volume_price_trend",  "VPT量价趋势",         ["closes","volumes"]),
    # ── 新增成交量类（F33-F38）─────
    "F33": ("force_index",         "Force Index力",       ["closes","volumes"]),
    "F34": ("elder_ray",           "Elder Ray透视",       ["closes","highs","lows"]),
    "F35": ("elder_ray_signal",    "Elder Ray信号",       ["closes","highs","lows"]),
    "F36": ("chaikin_signal",      "Chaikin振荡器",       ["highs","lows","closes","volumes"]),
    "F37": ("accdist",             "A/D累积派发",         ["highs","lows","closes","volumes"]),
    "F38": ("accdist_signal",      "A/D背离信号",         ["highs","lows","closes","volumes"]),
    # ── 新增波幅/工具类（F39-F45）──
    "F39": ("ultraband_signal",    "Ultra-Band突破",      ["closes","highs","lows"]),
    "F40": ("signal_horizon",      "Signal Horizon",      ["highs","lows","closes","volumes"]),
    "F41": ("mass_index",          "Mass Index梅斯",      ["highs","lows","closes"]),
    "F42": ("ergodic",             "Ergodic遍历摆动",     ["closes","highs","lows"]),
    "F43": ("cci_signal",         "CCI顺势指标",          ["highs","lows","closes"]),
    "F44": ("williams_r",          "Williams %R",         ["highs","lows","closes"]),
    "F45": ("volume_ratio",        "成交量比率VR",         ["volumes"]),
    # ── 缠论类（F46-F48）───────────
    "F46": ("chanlun_bi",         "缠论笔",               ["closes"]),
    "F47": ("chanlun_tao",        "缠论套",               ["closes"]),
    # ── 复合类（F49-F55）───────────
    "F48": ("macd_divergence",     "MACD背离",            ["closes","highs","lows"]),
    "F49": ("rsi_divergence",      "RSI背离",             ["closes"]),
    "F50": ("stoch_divergence",    "KD随机背离",          ["highs","lows","closes"]),
    "F51": ("trendline_break",     "趋势线突破",          ["closes"]),
    "F52": ("pivot_reversal",      "Pivot反转",           ["highs","lows","closes"]),
    "F53": ("wave_impulse",        "波浪脉冲",             ["closes"]),
    "F54": ("momentum_divergence", "动量背离",            ["closes"]),
    "F55": ("adx_filter",          "ADX趋势过滤",         ["highs","lows","closes"]),
}


# ───────────────────────────────────────────────────────────────────
#  因子信号生成器（接收OHLCV，输出信号序列）
# ───────────────────────────────────────────────────────────────────

def generate_signal(factor_id: str, closes: list,
                    highs: list = None, lows: list = None,
                    volumes: list = None) -> List[int]:
    """
    统一入口：根据因子ID生成交易信号
    returns: [1=多/-1=空/0=中性]
    """
    highs  = highs  or closes
    lows   = lows   or closes
    vols   = volumes or [1.0] * len(closes)

    mapping: dict = {
        # 趋势
        "ichimoku_signal":   lambda: ichimoku_signal(closes, highs, lows),
        "parabolic_sar":     lambda: [1 if closes[i] > (parabolic_sar(highs,lows,closes)[i] or 0) else -1 for i in range(len(closes))],
        "kst":               lambda: kst_signal(closes),
        "trix":              lambda: trix_signal(closes),
        "donchian_breakout": lambda: donchian_breakout(closes, highs, lows),
        "aroon_signal":      lambda: aroon_signal(closes, highs, lows),
        "ppof":              lambda: ppo_signal(closes),
        "supertrend":        lambda: supertrend(highs, lows, closes)[0],
        # 均值回归
        "mfi_signal":        lambda: mfi_signal(closes, highs, lows, vols),
        "rvi_signal":        lambda: [1 if (rvi(highs,lows,closes)[i] if not math.isnan(rvi(highs,lows,closes)[i]) else 50) < 30 else -1 for i in range(len(closes))],
        "multi_roc_signal":  lambda: multi_roc_signal(closes),
        "obos_signal":       lambda: obos_composite(closes, vols)[1],
        "kdwave":            lambda: kdwave(highs, lows, closes)[2],
        "volume_price_trend": lambda: [1 if vpt > 0 else -1 for vpt in volume_price_trend(closes, vols)],
        # 成交量
        "force_index":       lambda: [1 if fi > 0 else -1 for fi in force_index(closes, vols)],
        "elder_ray_signal":  lambda: elder_ray_signal(closes, highs, lows),
        "chaikin_signal":    lambda: chaikin_signal(highs, lows, closes, vols),
        "accdist_signal":    lambda: accumulation_distribution_signal(closes, highs, lows, vols),
        # 波幅
        "ultraband_signal":  lambda: ultraband_signal(closes, highs, lows),
        # 工具
        "mass_index":        lambda: [1 if mass > 27 else -1 for mass in mass_index(highs, lows)],
        "ergodic":           lambda: ergodic_signal(closes, highs, lows),
    }

    fn = mapping.get(factor_id)
    if fn:
        try:
            return fn()
        except Exception:
            return [0] * len(closes)
    return [0] * len(closes)


def kst_signal(closes):
    k, s = kst(closes)
    return [1 if k[i] > s[i] and not math.isnan(k[i]) else -1 if k[i] < s[i] and not math.isnan(k[i]) else 0 for i in range(len(closes))]


def trix_signal(closes):
    t, sig = trix(closes)
    return [1 if t[i] > sig[i] and not math.isnan(t[i]) else -1 if t[i] < sig[i] and not math.isnan(t[i]) else 0 for i in range(len(closes))]


def ppo_signal(closes):
    p, s = ppo(closes)
    return [1 if p[i] > s[i] and not math.isnan(p[i]) else -1 if p[i] < s[i] and not math.isnan(p[i]) else 0 for i in range(len(closes))]


def ergodic_signal(closes, highs, lows):
    e, s = ergodic_oscillator(closes, highs, lows)
    return [1 if s[i] > 0 and not math.isnan(s[i]) else -1 for i in range(len(closes))]

