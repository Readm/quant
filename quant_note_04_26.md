# Quant System — Session Notes 04-26

## 架构变更

### FactorComboExpert (合并 TrendExpert + MeanReversionExpert)
- **26 → 38 模板**: 新增 force_index, ppo, accdist, VPT, mass_index, ergodic_oscillator, signal_horizon, ultraspline, ultraband_signal, chanlun_bi, chanlun_tao
- 候选生成策略: 30% 单因子 / 40% 双因子 AND / 20% 双因子 OR / 10% 三因子加权
- 统一 `strategy_type: "combo"`，不再区分趋势/均值回归

### 因子层
- `_SCORE_REGISTRY` 补全 12 个缺失因子的评分函数（`_make_signal_score` 工厂）
- `_SCORE_REGISTRY` 共 38 个入口
- 注册表定义必须在 `_make_signal_score` 之后（Python 定义顺序问题）

### LLM API: MiniMax → DeepSeek
- **模型**: `deepseek-chat` (DeepSeek v4 Pro 不可用, `deepseek-v4-pro` 超时)
- **接口**: `https://api.deepseek.com/v1/chat/completions` (OpenAI 兼容)
- **Key**: `sk-5749a1d537684455acb77322f6600302`
- **规则**: 所有 API 失败直接 raise, 禁止任何降级返回默认值
- 网络层重试: URLError/OSError 自动重试 3 次, API 错误不重试

### 评估体系迭代 (9 轮优化)
```
Iter   改动              夏普      Alpha     Top 策略
───    ───              ────      ─────     ────────
基线   v5 初始          1.463     0.24%     RSI
1      +12 因子         1.452     —         RSI
2      +Alpha 权重      1.470     12.14%    RSI+OBOS
3      Alpha×2          1.500     13.0%     RSI+MFI
4      Alpha×5 缩放     1.513     13.6%     RSI
5      多样性奖励       1.504     13.8%     ICHIMOKU #1 🏆
6      放宽门槛         1.462     —         4 种因子共存
7      vol_inverse 权重  1.449    16.3%     RVI #1 (零RSI) 🏆
8      交易质量奖励     1.823     25.0%     RSI 回归
9      混搭标的+加密    1.835     26.9%     RSI 通杀
```
**最终**: 夏普 1.835, 年化 26.9%, Alpha 16.3%, 架构评级 A

### 评估权重 (v5.3)
- W_SORTINO = 0.22, W_CALMAR = 0.18, W_IR = 0.18, W_DRAWDOWN = 0.18, W_ALPHA = 0.24
- Alpha 缩放: `alpha_scaled = max(0, min(100, alpha * 5))`
- 多样性奖励: 久未出现的模板最多 +8 分
- 交易质量奖励: ≥15 笔 +3, ≤2 笔 -2
- PBO 硬拒: 0.50, 软折: 0.30
- MIN_TRADES: 1 (放宽), MAX_DRAWDOWN: 25% (收紧)

### 组合回测
- 默认权重: `vol_inverse` (低波动权重高)
- 默认调仓: 10 天
- 权重探索偏向: vol_inverse 40% / score_weighted 40% / equal 20%

## 数据源
- **主**: 腾讯行情 API (`web.ifzq.gtimg.cn`), SPY→sh000300 映射, BTCUSDT/ETHUSDT
- **备用**: 本地缓存 `data/raw/*.json` (Stooq/akshare)
- **基准**: Tushare `data/tushare/index_daily/000300.SH.csv` (沪深300)
- **tushare 数据**: 从 ~/quant 迁移 4.1G, 含 index_daily/daily/moneyflow/daily_basic/adj_factor/stk_limit/fina_basic/metadata

## Dashboard

### ExpertView (专家流程图)
- 移除彩色 Handle 点, 简化 10→8 节点
- Hover 显示输入/输出/Prompt 详情
- ReactFlow 实现

### ArchitectureView (系统架构)
- 模块依赖图: 自动从 gen_architecture.py 读取 deps.json, ReactFlow 分层布局
- 模块说明卡: 每层一句话
- 数据来源表
- 因子覆盖矩阵 (47 因子 × 评分 × 模板)

### IterationView
- 新增 Alpha 列 (琥珀色, 可排序)
- 12 个 Thread (9 轮优化结果)
- 修复 colSpan 9→10
- 修复 meta_evaluation 硬编码 False (改为 null)

### 页面加载问题
- **根因**: index.json 格式不符 — 需要 ThreadMeta[] 对象, 不是字符串数组
- `id` 必须匹配文件名 (不含路径/.json)
- **修复**: 删除 59MB 旧数据, 保留 80KB 有效数据

## 验证体系

### CHECKLIST.md
- 审计日志: 每次 commit 必须更新
- pre-commit hook 强制检查: 暂存区 √ / 全部 [x] √ / **时间戳不同 √** (防复用)

### scripts/smoke_test.py
- 6 层静态验证: 导入/JSON/Dashboard/TS/规则
- 秒级, 不触发 LLM 调用

### scripts/gen_architecture.py
- 自动扫描 .py 文件, 分析 import 关系
- 输出 Mermaid 图 + JSON 供 Dashboard 使用

### scripts/pre-commit (git hook)
- 安装: `cp scripts/pre-commit .git/hooks/pre-commit`
- 验证时间戳 != 上次 commit 的 CHECKLIST.md 时间戳
- 阻止时间戳相同或未更新的提交

### scripts/validate_dashboard.py
- 验证 Dashboard 迭代数据完整性
- 检查 alpha 字段存在性

## 遗留问题
- ~/quant 目录待删除 (已迁移 4.1G tushare 数据)
- Dashboard 端口 9000 要用 `fuser -k 9000/tcp` 重置
- DeepSeek v4-pro 模型可用但超时, 暂用 deepseek-chat
- 浏览器工具连接 localhost 受代理限制 (http_proxy=192.168.1.3:7890)
