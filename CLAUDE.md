# 编码规范 — 量化系统

## ⛔ LLM API 调用规范（硬性规则）

**任何 LLM API 调用失败必须直接抛出异常，禁止降级、禁止静默返回**。

```python
# ❌ 绝对禁止
result = llm_analyze(...)
if "error" in result:
    return defaults  # 禁止降级返回默认值

try:
    result = llm_analyze(...)
except Exception:
    return fallback  # 禁止捕获后降级

# ✅ 正确做法
result = llm_analyze(...)  # 失败自己 raise，传播到顶层
```

**理由**：降级掩盖 API 配置错误（Key 错误、额度耗尽、模型名错误），导致系统在静默退化状态下运行，产生不可信的结果。API 调用是最核心的基础设施 — 它必须可用，否则整个系统不可信。

### API 配置

- 供应商：DeepSeek
- 接口：`https://api.deepseek.com/v1/chat/completions` (OpenAI 兼容)
- 模型：`deepseek-chat`
- Key：配置在 `.env` 的 `DEEPSEEK_API_KEY`

### 重试策略

- `llm_analyze` 本身不做重试
- `llm_evaluate_round` 最多重试 3 次，3 次全部失败则 raise
- 其他调用方不做重试，失败即 raise

---

## 禁止静默捕获异常

**严禁**以下任何形式的异常吞没：

```python
# ❌ 全部禁止
try:
    ...
except:
    pass

try:
    ...
except Exception:
    pass

try:
    ...
except Exception:
    return {}

try:
    ...
except Exception:
    return [0] * n

try:
    ...
except Exception as e:
    print(e)   # 只打印不处理
    return default_value
```

**理由**：静默捕获掩盖真实 bug，导致系统在错误状态下继续运行，产生错误结果但无任何报警。
每一个被吞掉的异常都是一个未被修复的 bug。

### 允许的做法

```python
# ✅ 让异常传播，调用层决定如何处理
result = risky_operation()

# ✅ 只捕获具体、已知的异常，并做真实处理
try:
    value = int(raw_str)
except ValueError:
    raise ValueError(f"无效输入: {raw_str!r}，期望整数")

# ✅ 外层边界（main / HTTP handler）统一捕获并记录
# ✅ LLM / 网络调用失败：向上抛出，让 orchestrator 决定重试或跳过
```

### 具体场景规则

- **LLM 调用失败**：不捕获，不降级，让异常传播
- **因子计算失败**：不返回 `[0]*n`，让异常传播，修复计算本身
- **数据加载失败**：不返回空 dict，让异常传播，确保调用层得到明确的失败信号
- **导入失败**：不用 try/except 包裹 import，修复缺失的依赖

---

## 其他规范

- 不添加未被要求的功能、重构、注释
- 不为假设的未来需求设计抽象
- 不添加"兼容性"填充代码（如 `# removed`、未使用的 `_var`）
- 修 bug 时只改 bug，不顺手清理周边代码
