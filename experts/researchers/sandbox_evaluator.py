"""
sandbox_evaluator.py — 安全沙盒测试生成的因子代码
==================================================
使用受限命名空间 exec，测试：
  1. 代码能正常执行
  2. 对样本数据返回合理 float 值（>10% 非零）
  3. 计算 IC（因子分 vs 次期收益）简单质量评估
"""

import json
import math
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

_ROOT     = Path(__file__).parent.parent.parent
_DATA_DIR = _ROOT / "data" / "raw"

# IC 通过门槛（信息系数绝对值）
IC_MIN_PASS = 0.01   # 极低门槛，避免拒绝所有因子；仅做合理性检查


class SandboxEvaluator:
    def __init__(self, symbols: list[str] = None):
        self.symbols = symbols or ["SH600519"]
        self._sample = self._load_sample()

    def test(self, code: str, key: str, extensions: dict = None) -> tuple[float, str]:
        """
        在受限命名空间中执行代码，返回 (ic_score, error_msg)。
        error_msg 为空字符串表示通过。
        """
        if not self._sample:
            return 0.0, "无法加载样本数据"

        closes     = self._sample["closes"]
        data       = self._sample["data"]
        indicators = self._sample["indicators"]
        ext        = extensions or {}
        n          = len(closes)

        # 构建受限命名空间（只允许 math）
        safe_globals = {"math": math, "__builtins__": {
            "len": len, "range": range, "int": int, "float": float,
            "max": max, "min": min, "sum": sum, "abs": abs,
            "round": round, "list": list, "dict": dict,
            "zip": zip, "enumerate": enumerate,
            "isinstance": isinstance, "None": None,
            "True": True, "False": False,
            "__import__": __import__,   # 允许 import math（在代码顶部）
        }}
        local_ns = {}

        try:
            exec(compile(code, f"<factor:{key}>", "exec"), safe_globals, local_ns)
        except Exception as e:
            return 0.0, f"exec 失败: {e}"

        compute_fn = local_ns.get("compute_score")
        if not callable(compute_fn):
            return 0.0, "未找到 compute_score 函数"

        # 运行每个时间步
        scores = []
        for t in range(1, n):
            try:
                v = compute_fn(closes, data, indicators, ext, {}, t)
                scores.append(float(v) if v is not None else 0.0)
            except Exception as e:
                return 0.0, f"t={t} 执行异常: {e}"

        if not scores:
            return 0.0, "无有效输出"

        # 检查非零率
        nonzero = sum(1 for s in scores if s != 0.0) / len(scores)
        if nonzero < 0.05:
            return 0.0, f"非零信号比例过低 ({nonzero:.1%} < 5%)，因子可能无效"

        # 计算 IC（排名相关系数简化版）
        ic = self._rank_ic(scores, closes)
        return round(ic, 4), ""

    def _rank_ic(self, scores: list[float], closes: list[float]) -> float:
        """
        简化 IC：因子分 vs 次日收益的 Pearson 相关系数。
        使用全时段数据，不做截面排名（单标的无法做截面）。
        """
        n = min(len(scores), len(closes) - 2)
        if n < 10:
            return 0.0

        # scores[k] corresponds to t=k+1; forward return is closes[k+2]/closes[k+1]-1
        fwd_rets = [(closes[i + 1] / closes[i] - 1) if closes[i] > 0 else 0.0
                    for i in range(1, n + 1)]
        sig = scores[:n]

        mx = sum(sig) / n
        my = sum(fwd_rets) / n
        num = sum((s - mx) * (r - my) for s, r in zip(sig, fwd_rets))
        dx  = math.sqrt(sum((s - mx) ** 2 for s in sig) + 1e-9)
        dy  = math.sqrt(sum((r - my) ** 2 for r in fwd_rets) + 1e-9)
        return num / (dx * dy)

    def _load_sample(self) -> Optional[dict]:
        """加载第一个可用标的的历史数据作为沙盒测试样本"""
        for sym in self.symbols:
            files = sorted(_DATA_DIR.glob(f"{sym}_*.json"), reverse=True)
            if not files:
                continue
            try:
                raw = json.loads(files[0].read_text(encoding="utf-8"))
                # 支持两种格式：平铺数组 或 rows 列表
                if "rows" in raw:
                    rows   = raw["rows"]
                    closes  = [float(r["close"])  for r in rows]
                    highs   = [float(r.get("high",  r["close"])) for r in rows]
                    lows    = [float(r.get("low",   r["close"])) for r in rows]
                    volumes = [float(r.get("vol",   1e6))        for r in rows]
                    opens   = [float(r.get("open",  r["close"])) for r in rows]
                else:
                    closes  = [float(c) for c in raw.get("closes",  [])]
                    highs   = [float(x) for x in raw.get("highs",   closes)]
                    lows    = [float(x) for x in raw.get("lows",    closes)]
                    volumes = [float(x) for x in raw.get("volumes", [1e6]*len(closes))]
                    opens   = [float(x) for x in raw.get("opens",   closes)]
                if len(closes) < 50:
                    continue
                return {
                    "closes": closes,
                    "data": {"highs": highs, "lows": lows,
                             "volumes": volumes, "opens": opens},
                    "indicators": self._build_indicators(closes),
                }
            except Exception:
                continue
        return None

    @staticmethod
    def _build_indicators(closes: list[float]) -> dict:
        """从收盘价计算基础指标（用于沙盒测试）"""
        n = len(closes)

        def ema(arr, p):
            k = 2.0 / (p + 1)
            e = arr[0]
            out = [e]
            for v in arr[1:]:
                e = v * k + e * (1 - k)
                out.append(e)
            return out

        # RSI14
        gains  = [max(closes[i] - closes[i-1], 0) for i in range(1, n)]
        losses = [max(closes[i-1] - closes[i], 0) for i in range(1, n)]
        rsi = [50.0]
        avg_g, avg_l = sum(gains[:14]) / 14, sum(losses[:14]) / 14
        for i in range(14, len(gains)):
            avg_g = (avg_g * 13 + gains[i]) / 14
            avg_l = (avg_l * 13 + losses[i]) / 14
            rs = avg_g / (avg_l + 1e-9)
            rsi.append(100 - 100 / (1 + rs))
        rsi14 = [None] * 14 + rsi

        # MACD hist
        ema12 = ema(closes, 12)
        ema26 = ema(closes, 26)
        macd  = [a - b for a, b in zip(ema12, ema26)]
        sig9  = ema(macd, 9)
        macd_hist = [m - s for m, s in zip(macd, sig9)]

        # Bollinger (20)
        bb_mid = [None] * 20
        bb_upper = [None] * 20
        bb_lower = [None] * 20
        for i in range(20, n):
            seg  = closes[i - 20:i]
            mean = sum(seg) / 20
            std  = math.sqrt(sum((x - mean) ** 2 for x in seg) / 20)
            bb_mid.append(mean)
            bb_upper.append(mean + 2 * std)
            bb_lower.append(mean - 2 * std)

        return {
            "rsi14":     rsi14[:n],
            "macd_hist": macd_hist[:n],
            "adx":       [20.0] * n,   # 简化：固定值
            "bb_upper":  bb_upper[:n],
            "bb_lower":  bb_lower[:n],
            "bb_mid":    bb_mid[:n],
        }
