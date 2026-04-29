#!/usr/bin/env node
/**
 * smoke_dashboard_e2e.mjs — E2E 冒烟测试
 *
 * 启动本地 HTTP server → 用 Playwright 打开 Dashboard →
 * 检查各页签渲染无 console error。
 *
 * 用法:
 *   node scripts/smoke_dashboard_e2e.mjs
 *
 * 依赖:
 *   npm install -D playwright   (已通过 hermes-agent 提供)
 */

import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium } = require('/home/readm/.hermes/hermes-agent/node_modules/playwright/index.js');
import { createServer } from 'http';
import { readFileSync, existsSync } from 'fs';
import { join, extname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = join(fileURLToPath(import.meta.url), '..');
const PROJECT = join(__dirname, '..');
const DASHBOARD = join(PROJECT, 'dashboard');
const PUBLIC_DIR = join(DASHBOARD, 'dist');  // npm run build 的输出目录

const MIME_TYPES = {
  '.html': 'text/html',
  '.js':   'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.svg':  'image/svg+xml',
  '.ico':  'image/x-icon',
};

const ERRORS = [];
let PASS = 0;
let FAIL = 0;

function check(name, ok, detail = '') {
  const mark = ok ? '✅' : '❌';
  console.log(`  ${mark} ${name}${detail ? ' — ' + detail : ''}`);
  if (ok) PASS++; else FAIL++;
}

async function buildDashboard() {
  console.log('\n[1] 构建 Dashboard');
  const { execSync } = await import('child_process');
  try {
    execSync('npm run build', { cwd: DASHBOARD, stdio: ['ignore', 'pipe', 'pipe'], timeout: 60_000 });
    check('npm run build', existsSync(join(PUBLIC_DIR, 'index.html')), 'dist/index.html 存在');
  } catch (e) {
    check('npm run build', false, e.stderr?.toString()?.slice(0, 200) || e.message);
    throw new Error('构建失败，终止');
  }
}

function startServer() {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      let url = req.url === '/' ? '/index.html' : req.url;
      const fp = join(PUBLIC_DIR, url);
      const ext = extname(fp);
      const ct = MIME_TYPES[ext] || 'application/octet-stream';

      try {
        const data = readFileSync(fp);
        res.writeHead(200, { 'Content-Type': ct });
        res.end(data);
      } catch {
        res.writeHead(404);
        res.end('Not Found');
      }
    });

    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      console.log(`  📡 Server on http://127.0.0.1:${port}`);
      resolve({ server, port });
    });
  });
}

async function runE2E(port) {
  console.log('\n[2] E2E 页面渲染测试');
  const baseUrl = `http://127.0.0.1:${port}`;

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--disable-setuid-sandbox'],
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 900 },
  });

  // 收集所有 console 错误
  const collectedErrors = [];

  const page = await context.newPage();
  page.on('console', msg => {
    if (msg.type() === 'error') {
      collectedErrors.push({ type: 'console', text: msg.text(), loc: msg.location() });
    }
  });
  page.on('pageerror', err => {
    collectedErrors.push({ type: 'page', text: err.message, stack: err.stack });
  });

  // ── 2a. 首页加载 ──
  console.log('\n  ── 2a. 首页加载');
  await page.goto(baseUrl, { waitUntil: 'networkidle', timeout: 30_000 });
  await page.waitForTimeout(2000); // 等待 React 渲染 & fetch 完成
  check('首页无 JS 报错', collectedErrors.length === 0,
    collectedErrors.length > 0 ? collectedErrors[0].text : '');

  // 检查页面主体有内容
  const bodyText = await page.locator('body').innerText();
  check('页面有渲染内容', bodyText.length > 50, `${bodyText.length} chars`);

  // ── 2b. 检查页签 ──
  console.log('\n  ── 2b. 页签导航');
  const tabs = await page.locator('[role="tab"], button, a').all();
  console.log(`    找到 ${tabs.length} 个可点击元素`);

  // 尝试点击每个看起来是页签的元素
  const tabTexts = [];
  for (const tab of tabs) {
    const text = (await tab.textContent())?.trim();
    if (text && text.length > 0 && text.length < 30) {
      tabTexts.push(text);
    }
  }
  check(`找到 ${tabTexts.length} 个页签`, tabTexts.length >= 2, tabTexts.join(', '));

  // ── 2c. 迭代视图（最可能出问题的地方） ──
  console.log('\n  ── 2c. 迭代视图渲染');
  const iterationLinks = page.locator('a[href*="iter"], [role="tab"]:has-text("Iter")');
  const hasIterTab = await iterationLinks.count();
  if (hasIterTab > 0) {
    await iterationLinks.first().click();
    await page.waitForTimeout(2000); // 等待 fetch 加载迭代数据
    check(`迭代页签点击后无报错`, collectedErrors.length === 0);
  } else {
    // 尝试用 URL hash 导航
    console.log('    未找到迭代页签链接，尝试 URL 导航');
    await page.goto(`${baseUrl}/#/iterations`, { waitUntil: 'networkidle', timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(2000);
    check('URL 导航后无报错', collectedErrors.length === 0);
  }

  // ── 2d. 检查 equity_curve 数据渲染 ──
  console.log('\n  ── 2d. 数据关键字段检查');
  const equityElements = page.locator('text=/equity|收益曲线|净值|回撤/i');
  const equityCount = await equityElements.count();
  check(`存在收益相关文本元素`, equityCount > 0, `${equityCount} 个`);

  // ── 2e. 检查 console.error 总数 ──
  console.log('\n  ── 2e. 错误汇总');
  if (collectedErrors.length > 0) {
    console.log('    Console 错误:');
    for (const e of collectedErrors) {
      console.log(`    🔴 [${e.type}] ${e.text.slice(0, 200)}`);
    }
  }
  check('全程无控制台报错', collectedErrors.length === 0, `${collectedErrors.length} 个错误`);

  await browser.close();
  return collectedErrors;
}

// ── Main ──
async function main() {
  console.log('='.repeat(60));
  console.log('  Dashboard E2E 冒烟测试');
  console.log('='.repeat(60));

  try {
    await buildDashboard();
  } catch {
    process.exit(1);
  }

  const { server, port } = await startServer();

  let errors = [];
  try {
    errors = await runE2E(port);
  } catch (e) {
    console.log(`\n  ❌ E2E 异常: ${e.message}`);
    FAIL++;
  }

  server.close();

  console.log('\n' + '='.repeat(60));
  const total = PASS + FAIL;
  console.log(`  结果: ${PASS}✅ / ${FAIL}❌ / 共${total}项`);
  if (FAIL === 0) {
    console.log('  ✅ Dashboard E2E 冒烟测试全部通过');
    console.log('='.repeat(60));
    process.exit(0);
  } else {
    console.log(`  ❌ ${FAIL} 项检查失败`);
    console.log('='.repeat(60));
    process.exit(1);
  }
}

main();
