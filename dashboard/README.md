# Quant System Dashboard v3.0

多专家量化系统可视化平台，支持 GitHub Pages 自动部署。

## 技术栈

- **React 18** + **TypeScript 5.6**
- **Vite 5** (构建工具)
- **Tailwind CSS v3** (样式)
- **Recharts** (图表)
- **Lucide React** (图标)

## 本地开发

```bash
cd dashboard/
npm install
npm run dev        # 开发服务器 http://localhost:5173
npm run build      # 生产构建
npm run preview    # 预览构建结果 http://localhost:3000
```

## 部署到 GitHub Pages

1. 将 `dashboard/` 目录内容推送到 GitHub 仓库的 `web/quant-system/` 路径
2. GitHub Actions 自动触发 CI/CD：
   - 类型检查 (TypeScript)
   - ESLint 检查
   - 生产构建
   - 部署到 GitHub Pages

或手动触发：
```bash
npm run build
# 将 dist/ 目录内容推送到 gh-pages 分支
```

## 页面说明

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | 首页 Dashboard | 系统概览、KPI 指标 |
| `/experts` | 专家辩论 | 多专家辩论引擎可视化 |
| `/backtest` | 融合回测 | quant → Qlib 融合回测结果 |
| `/factors` | 因子库 | Alpha158 vs quant 因子对比 |
| `/data` | 数据源 | Qlib 数据状态监控 |
| `/strategy` | 策略池 | 专家生成的候选策略 |

## 环境要求

- Node.js 18+ (推荐 20 LTS)
- npm 9+
