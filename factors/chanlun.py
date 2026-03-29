# factors/chanlun.py
# 缠论简化因子
# 缠论笔（Bi）· 缠论套（Tao）

from typing import List, Tuple

def chanlun_bi(closes: List[float], period: int = 5) -> Tuple[List[int], List[float]]:
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
        window_h = max(closes[max(0, i - period):i])
        window_l = min(closes[max(0, i - period):i])

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
                for j in range(i - period, i):
                    if j >= 0:
                        direction[j] = -1
                        extreme[j]   = local_low
                current_dir = 1
                local_high   = closes[i]

        i += 1

    return direction, extreme


def chanlun_tao(directions: List[int], extremes: List[float]) -> List[int]:
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
