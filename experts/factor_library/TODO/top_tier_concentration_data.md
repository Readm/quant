# 因子数据需求待处理: 顶部集中度质量因子 (`top_tier_concentration`)
**来源**: http://arxiv.org/abs/2601.11958v1
**描述**: 专注于高AI评分股票的集中度因子，通过对前20名股票赋予更高权重实现。文献发现alpha高度集中于顶部层级，向下扩展会快速稀释收益。
**公式**: concentration = W * Rank(ai_score) 其中 W 对 Top20 使用高权重系数

## 需要的额外数据
### `ai_score`
AI模型输出的股票吸引力评分

## 自动获取失败原因
```
akshare 未安装 (pip install akshare)
```

## 处理方式
1. 确认数据来源（akshare/tushare/Wind/第三方API）
2. 在 `experts/factor_library/adapters/` 中实现获取函数
3. 删除此文件后重新运行 ResearchExpert
