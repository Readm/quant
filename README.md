# Quant Multi-Expert Trading System v4.2

## 运行
```bash
cd /workspace/quant
python3 scripts/run_pipeline.py
```

## 架构
- `orchestrator.py` — 3轮迭代，编排全流程
- `experts/specialists/expert1a_trend.py` — 趋势专家
- `experts/specialists/expert1b_mean_reversion.py` — 均值回归专家
- `experts/specialists/bull_researcher.py` — 牛市研究员
- `experts/specialists/bear_researcher.py` — 熊市研究员
- `experts/debate_manager.py` — 4-Agent辩论
- `experts/evaluator.py` — 量化评分
- `experts/modules/llm_proxy.py` — LLM调用
- `experts/modules/factor_library.py` — 28因子库
- `backtest/runner.py` — NumPy回测引擎
- `backtest/vectorbt_engine.py` — vectorbt向量化引擎
- `backtest/local_data.py` — 数据加载

## 依赖（pip已安装）
- vectorbt 0.28.4
- pandas 2.3.3
- scipy 1.17.1
- numpy 1.24.2

## 关键功能
- ✅ 交易成本模型（佣金0.08% / 印花税0.18%）
- ✅ 4-Agent辩论（Trend + MR + Bull + Bear）
- ✅ 28因子纯NumPy因子库
- ✅ vectorbt参数网格扫描
- ✅ LLM策略生成（MaxClaw）
- ✅ A股腾讯日K采集

## 数据
- SPY 300天 / BTCUSDT 300天 / A股9标的本地缓存
- 结果输出：results/multi_expert_v4_*.json
- Dashboard：https://t50d9la8qomk.space.minimaxi.com
