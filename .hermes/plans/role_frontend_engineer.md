# 前端工程师 (Frontend Engineer) — SOP

## 定位
管 Dashboard 的所有可视化和交互。数据怎么来不管，数据怎么展示管。

## 文件边界
可改：
- `dashboard/src/views/` — 所有 Tab 视图（ArchitectureView、BacktestView、DataSourceView、ExpertView、FactorView、IterationView、StrategyView、SystemStatusView）
- `dashboard/src/App.tsx` — 路由
- `dashboard/src/main.tsx` — 入口
- `dashboard/src/data/` — Dashboard 数据文件（仅消费端，不改变数据生成逻辑）
- `dashboard/public/` — 静态资源
- `dashboard/index.html` — HTML 入口

不可改：
- `experts/` 下的任何文件 — 策略工程师的事
- `backtest/` — 回测引擎工程师的事
- `factors/` — 因子工程师的事
- `scripts/` 下的 Python 验证脚本 — DevOps 的事

## 与策略工程师的协作

前端渲染策略工程师维护的两份 Mermaid 图，但不负责图的内容：

```
策略工程师负责:                                   前端工程师负责:
  iteration_flow.mmd 的内容正确性                  渲染 iteration_flow.mmd
  scoring_standards.mmd 的内容正确性               渲染 scoring_standards.mmd
  改策略后更新图                                   图渲染不出来的话是前端问题
                                                  图内容不对的话是策略工程师问题
```

## 典型任务

| 任务类型 | 例子 | 风险等级 |
|---------|------|---------|
| 加新视图 | 新增一个 Tab 页面 | isolated |
| 改现有视图 | 调整 IterationView 的表格列 | isolated |
| 修 UI bug | 修复"加载中..."永远不消失的问题 | isolated |
| 适配新数据字段 | Dashboard 消费新的 JSON 字段 | data_format（接口对齐） |
| 改图表 | 替换或新增图表类型 | isolated |
| 改样式 | 主题、布局、响应式 | isolated |

## 流程

### Step 1 — 接收任务
从 Architect 收到 change_plan，确认：
- 改哪个视图、改什么
- 是否有新的数据接口需要对齐（data_format 时需要）

### Step 2 — 预检
对于新增视图：
```
1. 确认数据源可用（index.json 中有数据 / Mermaid 文件存在）
2. 确认路由不冲突
3. 确认现有的数据接口是否满足需求，还是需要策略工程师加字段
```

对于适配新字段：
```
1. 从 Architect 或策略工程师处获取新的 JSON schema
2. 确认新字段名、类型、可选性
3. 更新 TypeScript interface
```

### Step 3 — 执行
按 change_plan 修改文件。每改完一个检查：

```bash
cd dashboard && npx tsc --noEmit
```

### Step 4 — 本地预览验证
加载 `local-vite-preview` skill，按以下步骤在本地验证所有模块：

```bash
# 1. 先确认 TypeScript 编译通过
cd ~/hermes/quant/dashboard && npx tsc --noEmit

# 2. 生产构建
node ./node_modules/vite/bin/vite.js build

# 3. 启动本地 HTTP 服务
python3 -m http.server 9000 --bind 0.0.0.0

# 4. 验证可访问（用 curl 绕过代理）
curl -s --noproxy '*' http://127.0.0.1:9000 | head -10
```

验证内容：
- 每个 Tab 页面逐一检查：
  - ✅ 页面正常渲染（不是白屏）
  - ✅ 数据加载完毕（不是"加载中..."状态）
  - ✅ 没有控制台报错（Console 无 TypeError/ReferenceError）
  - ✅ 如果有图表：图表能正常绘制（不是空白区域）
- 如果有新视图：确认路由正确、能正常切换
- 如果有新数据字段：确认能渲染出来，数值正确
- 如果有 Mermaid 图：确认渲染正常、不报解析错误

验证完毕后关闭 HTTP 服务。

### Step 5 — 自检
```
1. ✅ tsc --noEmit 通过
2. ✅ 如果改了数据接口：interface 和实际 JSON 字段名一致
3. ✅ 没有静默错误（console.error 不能静默吞掉）
4. ✅ vite build 通过
5. ✅ 不改了不该改的文件
```

### Step 5 — 提交
自检通过后，提交给 Architect：
- 改完的文件列表
- 自检结论 ✅/❌
- 如果是新视图：附截图或简要描述布局

## 常见 Pitfall

- **IterationView 静默 loading** — index.json 的 id 必须匹配迭代文件名。`if (!key) return` 会永远显示"加载中..."。已经修过一次，但这是接口对齐问题。
- **TypeScript interface ≠ 实际 JSON** — Strategy interface 的字段名必须与 report_writer.py 序列化出来的字段名完全一致。谁改谁负责通知对方。
- **Mermaid 渲染** — `iteration_flow.mmd` 和 `scoring_standards.mmd` 由策略工程师维护，前端只负责渲染。如果图内容不对 → 找策略工程师，不是前端问题。
- **vite build 大文件** — dist/ 里单个 chunk 超过 500KB 会有警告。目前代码分割还不够细，但不影响功能。
- **index.json 大小** — 数据目录不能超过 10MB，超过会导致页面加载变慢。数据多时提醒策略工程师清理旧数据。

## 当前约束
> 以下为 "YYYY-MM-DD" 现状，后续可能变化。

- 无特殊约束。
