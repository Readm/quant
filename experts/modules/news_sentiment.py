"""
news_sentiment.py — 新闻 & 市场情绪分析模块

功能：
  1. 通过 web search 抓取相关市场新闻
  2. 计算净情绪分（-1 ~ +1）
  3. 输出每轮情绪报告（可解释）

接口：
  NewsSentimentAnalyzer.analyze(symbols: list[str]) -> dict
  返回：{
    "sentiment_score"   : float,      # -1 ~ +1
    "sentiment_label"   : str,        # NEGATIVE / NEUTRAL / POSITIVE
    "confidence"        : float,       # 0 ~ 1
    "top_stories"       : list[dict], # [{title, source, date, summary}]
    "market_tips"       : list[str],  # 策略适配建议
    "explanation"       : str,        # 可解释性说明
  }
"""

import sys, re, math
from typing import List
from dataclasses import dataclass

# 正面/负面关键词（简化词典，无外部依赖）
POSITIVE_WORDS = {
    "大涨", "暴涨", "突破", "创新高", "超预期", "大增", "强劲",
    "牛", "买入", "推荐", "看好", "增长", "回升", "反弹",
    "surge", "rally", "bullish", "beat", "upgrade", "growth",
    "surge", "jump", "gain", "rise", "high", "strong", "buy"
}
NEGATIVE_WORDS = {
    "大跌", "暴跌", "破发", "预警", "风险", "减持", "亏损",
    "熊", "卖出", "看空", "下降", "回落", "裁员", "危机",
    "crash", "plunge", "bearish", "miss", "downgrade", "risk",
    "drop", "fall", "loss", "low", "weak", "sell", "warning"
}

# 全局缓存（避免同一轮重复搜索）
_SEARCH_CACHE = {}


@dataclass
class NewsArticle:
    title   : str
    snippet : str
    source  : str
    date    : str
    url     : str


class NewsSentimentAnalyzer:
    """
    新闻情绪分析器。
    使用 batch_web_search 搜索，每轮最多搜索 3 个标的，
    复用已搜索结果避免重复调用。
    """

    def __init__(self, cache: dict = None):
        self.cache = cache or _SEARCH_CACHE
        self._batch_web_search = None  # 延迟初始化

    # ── 对外接口 ─────────────────────────────────

    def analyze(self, symbols: List[str]) -> dict:
        """
        主入口：对多个标的分析新闻情绪。
        先检查缓存，再搜索，最后综合。
        """
        articles = []
        searched = []

        for sym in symbols:
            if sym not in self.cache:
                results = self._search_news(sym)
                self.cache[sym] = results
            articles.extend(self.cache[sym])
            if sym not in searched:
                searched.append(sym)

        if not articles:
            return self._neutral_result(
                "未找到相关新闻数据，使用中性情绪基准"
            )

        sentiment, confidence = self._score_articles(articles)
        label = self._label(sentiment)
        tips  = self._adapt_tips(sentiment, confidence)
        explanation = self._explain(sentiment, confidence, articles, tips)

        return {
            "sentiment_score"  : round(sentiment, 3),
            "sentiment_label"  : label,
            "confidence"       : round(confidence, 3),
            "top_stories"      : [a.__dict__ for a in articles[:5]],
            "market_tips"      : tips,
            "explanation"      : explanation,
            "symbols_searched" : searched,
            "articles_found"   : len(articles),
        }

    # ── 搜索层 ──────────────────────────────────

    def _search_news(self, symbol: str) -> List[NewsArticle]:
        """用 batch_web_search 搜索新闻（延迟导入避免启动报错）"""
        try:
            from importlib import import_module
            mcp = import_module("MCP_DONE")  # 触发MCP工具注入
            # 实际使用 batch_web_search
            return self._do_search(symbol)
        except Exception:
            # 无网络环境，返回空
            return []

    def _do_search(self, symbol: str) -> List[NewsArticle]:
        """实际执行搜索的内部方法"""
        try:
            # 动态获取 batch_web_search
            import __main__
            if hasattr(__main__, 'batch_web_search'):
                return self._search_via_mcp(symbol, __main__.batch_web_search)
        except Exception:
            pass

        # 兜底：返回空（不崩溃）
        return []

    def _search_via_mcp(self, symbol: str, search_fn) -> List[NewsArticle]:
        """通过 MCP search 函数执行搜索"""
        try:
            # 判断市场类型
            s = symbol.upper()
            if "BTC" in s or "ETH" in s or "USDT" in s:
                query_en = f"{symbol} crypto market news 2026"
                query_cn = f"{symbol} 加密货币 市场 2026"
            else:
                query_en = f"{symbol} stock market news 2026"
                query_cn = f"{symbol} 股票 市场 2026"

            results = search_fn(queries=[
                {"query": query_en, "num_results": 5, "data_range": "m"},
                {"query": query_cn, "num_results": 5, "data_range": "m"},
            ])
            return self._parse_search_results(results)
        except Exception:
            return []

    def _parse_search_results(self, raw_results) -> List[NewsArticle]:
        """解析搜索结果为 NewsArticle 列表"""
        articles = []
        try:
            for query_result in raw_results:
                for item in query_result.get("organic_results", []):
                    title   = item.get("title", "")
                    snippet = item.get("snippet", "")
                    source  = item.get("source", "")
                    date    = item.get("date", "")
                    url     = item.get("link", "")
                    if title:
                        articles.append(NewsArticle(
                            title=title, snippet=snippet,
                            source=source, date=date, url=url
                        ))
        except Exception:
            # 兜底：直接遍历（格式兼容）
            try:
                for item in raw_results:
                    if isinstance(item, dict):
                        for r in item.get("data", []):
                            articles.append(NewsArticle(
                                title  = r.get("title", ""),
                                snippet= r.get("snippet", ""),
                                source = r.get("source", ""),
                                date   = r.get("date", ""),
                                url    = r.get("link", ""),
                            ))
            except Exception:
                pass
        return articles

    # ── 情绪打分 ───────────────────────────────

    def _score_articles(self, articles: List[NewsArticle]) -> tuple:
        """
        计算综合情绪分。
        返回：(sentiment: float, confidence: float)
        sentiment ∈ [-1, +1]
        confidence ∈ [0, 1]：基于文章数量和质量
        """
        if not articles:
            return 0.0, 0.0

        scores = []
        for a in articles:
            text = (a.title + " " + a.snippet).lower()
            pos = sum(1 for w in POSITIVE_WORDS if w.lower() in text)
            neg = sum(1 for w in NEGATIVE_WORDS if w.lower() in text)
            if pos + neg == 0:
                scores.append(0.0)
            else:
                scores.append((pos - neg) / (pos + neg + 1))
            # 时间加权
            if a.date and "2026" in str(a.date):
                scores[-1] *= 1.2   # 今年新闻权重略高

        sentiment = sum(scores) / len(scores)
        # confidence：文章越多越稳定
        confidence = min(1.0, len(articles) / 5.0)
        return sentiment, confidence

    def _label(self, sentiment: float) -> str:
        if sentiment >= 0.2:  return "POSITIVE"
        if sentiment <= -0.2: return "NEGATIVE"
        return "NEUTRAL"

    # ── 策略适配建议 ───────────────────────────

    def _adapt_tips(self, sentiment: float, confidence: float) -> List[str]:
        """
        根据情绪给出策略适配建议。
        可解释性：每条建议都附带原因。
        """
        tips = []
        if abs(sentiment) < 0.15:
            tips.append("市场情绪中性，建议降低总体仓位，减少交易频率")
            tips.append("此时均值回归策略可能优于趋势策略")
        elif sentiment >= 0.3 and confidence >= 0.5:
            tips.append("情绪积极看多，趋势策略权重可上调至60-70%")
            tips.append("MACD/均线多头排列，动量信号可信度较高")
        elif sentiment <= -0.3 and confidence >= 0.5:
            tips.append("情绪负面，优先配置均值回归/防御型策略")
            tips.append("RSI超卖信号可信，建议关注反弹机会")
            tips.append("减少趋势跟踪策略敞口")
        elif sentiment >= 0.2:
            tips.append("情绪偏多，可适度增配趋势跟踪策略")
        elif sentiment <= -0.2:
            tips.append("情绪偏空，建议谨慎，增加防御型仓位")
        else:
            tips.append("情绪平稳，维持均衡配置")
        return tips

    # ── 可解释报告 ─────────────────────────────

    def _explain(self, sentiment: float, confidence: float,
                 articles: List[NewsArticle], tips: List[str]) -> str:
        """生成人类可读的情绪分析报告"""
        label  = self._label(sentiment)
        direc  = {
            "POSITIVE": "正面",
            "NEGATIVE": "负面",
            "NEUTRAL" : "中性",
        }[label]

        # 提取关键词
        all_text = " ".join(a.title + a.snippet for a in articles)
        pos_hits = [w for w in POSITIVE_WORDS if w.lower() in all_text.lower()]
        neg_hits = [w for w in NEGATIVE_WORDS if w.lower() in all_text.lower()]

        # 核心驱动事件
        top_titles = [a.title for a in articles[:3]]

        lines = [
            f"本轮情绪基调：{direc}（情绪分={sentiment:+.2f}，置信度={confidence:.0%}）",
            f"数据来源：{len(articles)} 篇新闻/资讯",
            "",
            f"正面词汇出现：{', '.join(pos_hits[:5]) if pos_hits else '无'}",
            f"负面词汇出现：{', '.join(neg_hits[:5]) if neg_hits else '无'}",
            "",
            "主要新闻标题：",
        ]
        for t in top_titles:
            lines.append(f"  · {t}")

        lines.extend(["", "策略建议："])
        for tip in tips:
            lines.append(f"  → {tip}")

        return "\n".join(lines)

    def _neutral_result(self, reason: str) -> dict:
        return {
            "sentiment_score"  : 0.0,
            "sentiment_label"  : "NEUTRAL",
            "confidence"       : 0.0,
            "top_stories"      : [],
            "market_tips"      : ["市场情绪不明，保持均衡配置，等待明确信号"],
            "explanation"      : reason,
            "symbols_searched" : [],
            "articles_found"   : 0,
        }


# ── 独立测试入口 ────────────────────────────────────

if __name__ == "__main__":
    analyzer = NewsSentimentAnalyzer()
    result = analyzer.analyze(["BTCUSDT", "ETHUSDT"])
    print(result["explanation"])
