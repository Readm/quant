# 因子数据需求待处理: 相对买卖价差 (`relative_spread`)
**来源**: http://arxiv.org/abs/2602.00776v1
**描述**: 买卖价差与中间价的比值，反映市场流动性和交易成本，高价差暗示高不确定性或低流动性。
**公式**: relative_spread = (ask_price - bid_price) / mid_price， 其中 mid_price = (ask_price + bid_price) / 2

## 需要的额外数据
### `best_bid`
最佳买价
### `best_ask`
最佳卖价

## 自动获取失败原因
```
akshare 未安装 (pip install akshare)
```

## 处理方式
1. 确认数据来源（akshare/tushare/Wind/第三方API）
2. 在 `experts/factor_library/adapters/` 中实现获取函数
3. 删除此文件后重新运行 ResearchExpert
