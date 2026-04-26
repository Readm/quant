# 变更计划 — gen_architecture 边排序稳定

## 需求
修 gen_architecture.py 每次运行时边顺序不固定，导致 deps.json 产生噪音 diff。

## 影响范围
- 文件: `scripts/gen_architecture.py`
- 风险: isolated（单文件、不改数据、不改逻辑）
- 涉及角色: DevOps（改脚本）→ 代码质量工程师（审）→ DevOps（自提）

## 修改内容
在 gen_architecture.py 的边序列化处加 `sorted()`，按 (source, target) 排序。

当前代码（约 line 120-130）:
```python
edges = []
for src, tgts in deps.items():
    for tgt in tgts:
        edges.append({"source": src, "target": tgt})
```

改为:
```python
edges = sorted(
    [{"source": src, "target": tgt}
     for src, tgts in deps.items()
     for tgt in tgts],
    key=lambda e: (e["source"], e["target"])
)
```

## 验证方式
1. 跑两次 gen_architecture.py，确认 deps.json 的边顺序一致
2. smoke_test.py
3. 确认 deps.json diff 干净

## 分派
- DevOps: 改代码
- 代码质量工程师: 审查改动
- DevOps: 自提

## 依赖
无（单文件，无人依赖）
