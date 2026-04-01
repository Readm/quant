# 因子数据需求待处理: 订单流不平衡 (`order_flow_imbalance`)
**来源**: http://arxiv.org/abs/2602.00776v1
**描述**: 衡量买方主导与卖方主导的订单压力，通过订单簿主动成交量的净差值计算，反映短期价格走势的微观驱动力。
**公式**: OFI = Σ(主动买入量 * sign(Δprice)) - Σ(主动卖出量 * sign(Δprice))，或简化为：OFI = Δbid_volume - Δask_volume

## 需要的额外数据
### `bid_volume`
主动买成交量（按价格方向标记）
### `ask_volume`
主动卖成交量（按价格方向标记）

## 自动获取失败原因
```
akshare 未安装 (pip install akshare)
```

## 处理方式
1. 确认数据来源（akshare/tushare/Wind/第三方API）
2. 在 `experts/factor_library/adapters/` 中实现获取函数
3. 删除此文件后重新运行 ResearchExpert
