# 因子数据需求待处理: AI预测排名动量因子 (`ai_nowcast_momentum`)
**来源**: http://arxiv.org/abs/2601.11958v1
**描述**: 基于AI量化评分对股票吸引力进行排名，取排名前20的股票做多做多。文献显示该策略具有每日18.4bp的alpha和2.43的夏普比率，但仅在顶部排名有效。
**公式**: rank_momentum = Rank(ai_score) 选择 Top20 股票做多

## 需要的额外数据
### `ai_score`
AI模型输出的股票吸引力评分(0-100)

## 自动获取失败原因
```
akshare 未安装 (pip install akshare)
```

## 处理方式
1. 确认数据来源（akshare/tushare/Wind/第三方API）
2. 在 `experts/factor_library/adapters/` 中实现获取函数
3. 删除此文件后重新运行 ResearchExpert
