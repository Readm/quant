# 编码规范 — 量化系统

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

- **LLM 调用失败**：不捕获，让错误传播到 orchestrator 层处理重试逻辑
- **因子计算失败**：不返回 `[0]*n`，让异常传播，修复计算本身
- **数据加载失败**：不返回空 dict，让异常传播，确保调用层得到明确的失败信号
- **导入失败**：不用 try/except 包裹 import，修复缺失的依赖

---

## 其他规范

- 不添加未被要求的功能、重构、注释
- 不为假设的未来需求设计抽象
- 不添加"兼容性"填充代码（如 `# removed`、未使用的 `_var`）
- 修 bug 时只改 bug，不顺手清理周边代码
