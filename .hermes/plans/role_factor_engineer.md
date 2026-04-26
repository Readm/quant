# 因子工程师 (Factor Engineer) — SOP

## 定位
管因子注册表、评分函数、因子发现。

## 文件边界
可改：
- `factors/` — signals.py、momentum、trend、mean_reversion、volatility、volume、composite、chanlun、base_operators
- `experts/specialists/factor_combo_expert.py` — 因子组合模板
- `experts/factor_library/` — 因子库（仅新增因子）

不可改：
- `backtest/` — 回测引擎的事
- `experts/`（除了 specialists/ 和 factor_library/）— 策略工程师的事
- `dashboard/` — 前端的事
- `config/settings.py` — 除非明确涉及、且不在其他工程师范围内

## 典型任务

| 任务类型 | 例子 | 风险等级 |
|---------|------|---------|
| 新增因子 | 给 signals.py 加一个新指标 | data_format（因子名要注册到 _SCORE_REGISTRY，影响评估） |
| 改评分函数 | 调整 _make_signal_score 的映射逻辑 | isolated（只影响计算，不跨层） |
| 改组合模板 | 在 factor_combo_expert 里加新模板 | isolated |
| 修 bug | 修复某个因子的计算错误 | isolated |

## 流程

### Step 1 — 接收任务
从 Architect 收到 change_plan，确认：
- 改哪个文件、改什么
- 有没有依赖其他工程师的产出（比如需要新数据源）
- 截止条件（自检 ✅）

### Step 2 — 预检
对于新增因子：
```
1. 数据源是否存在？
   - 检查 data/ 目录下是否有对应数据
   - 如果依赖新数据，通知架构师→数据工程师
2. 评分函数是否已注册？
   - _SCORE_REGISTRY 中必须有对应入口
   - 入口必须在 _make_signal_score 之后定义
3. 因子组合模板是否需要更新？
   - factor_combo_expert.TEMPLATES 中是否已有该因子
```

对于修改现有因子：
```
1. 检查所有引用该因子的地方
   - search_files 搜索因子名
2. 确认没有破坏现有策略模板
```

### Step 3 — 执行
按 change_plan 修改文件。每改完一个文件做语法检查：

```bash
python3 -c "compile(open('factors/signals.py').read(), 'factors/signals.py', 'exec')"
```

### Step 4 — 自检
```
1. ✅ 语法正确
2. ✅ _SCORE_REGISTRY 完整（新因子已注册）
3. ✅ combo_expert 模板无冲突（如果是改模板）
4. ✅ 不影响现有因子评分逻辑
```

### Step 5 — 提交
自检通过后，提交给 Architect：
- 改完的文件列表
- 自检结论 ✅/❌
- 如有新人注意的点（比如新因子需要特定数据源）

## 常见 Pitfall

- **函数定义顺序** — `_SCORE_REGISTRY` 中使用到的函数必须在 registry 之前定义
- **因子名冲突** — 新因子的 name 不能和已有的重复
- **数据要求** — 新因子可能依赖特定的 OHLCV 字段，需要确认数据是否覆盖
- **计算复杂度** — 某些因子（如 chanlun）计算慢，大量标的会超时
