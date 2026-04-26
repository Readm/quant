# Pre-Commit Verification Checklist

> 此文件是审计日志。每次提交前必须更新，pre-commit hook 强制检查。

## Last Verification: 2026-04-27 00:28 UTC

---

### 1. 架构检查
- [x] 无循环导入
- [x] 本次变更范围：backtest/engine.py + experts/orchestrator.py（5 Phase 扩展，data_format风险）

### 2. 数据管线完整性
- [x] Dashboard index.json 已更新，iteration data 已写入
- [x] Vite build 通过（7.74s）

### 3. 冒烟测试
- [x] 20轮全量迭代成功运行（A股~5495只×800天）
- [x] Vite build 通过
- [x] smoke_test.py 全部通过

### 4. 策略空间扩展 v5.0 — Phase 1~5
- [x] Phase 1: _score_composite 复合因子 + 候选生成器
- [x] Phase 2: _apply_gate 6种门控(volume_surge/above_ma/below_ma/adx_filter/low_vol)
- [x] Phase 3: _select_stocks 两阶段筛选(主因子宽池→次因子精选)
- [x] Phase 4: _apply_risk_overlay 止损/止盈/跟踪止盈
- [x] Phase 5: _detect_regime + _score_regime_adaptive 市场状态分支
- [x] 无静默异常捕获/LLM降级

### 5. 20轮迭代结果
| # | 策略 | 得分 | 年化 | 夏普 |
|---|------|:----:|:----:|:----:|
| 1 | Composite(kdwave+ppo)\|LoV | 92.6 | 99.9% | 2.253 |
| 2 | 主力资金流\|2S:obos→mfi_\|SL11% | 87.9 | 110.0% | 2.240 |
| 3 | KDJ波形\|ADX | 87.6 | 176.1% | 2.948 |
| 4 | ROC多周期\|ADX\|SL13% | 86.2 | 139.1% | 3.057 |

### 检查历史
| 时间 | 检查者 | 结果 | 变更描述 |
|------|--------|:----:|---------|
| 2026-04-26 22:40 UTC | Hermes | ✅ PASS | evaluator.py 3项修复(PBO/OOS/反垄断) |
| 2026-04-27 00:28 UTC | Hermes | ✅ PASS | 策略逻辑组合空间扩展 v5.0 (Phase 1-5) |
