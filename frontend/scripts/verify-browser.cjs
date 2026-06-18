// Playwright script to verify the frontend in a browser
const { chromium } = require('playwright');

const BASE = 'http://localhost:5173';
const SCREENSHOTS = 'scripts/screenshots';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    locale: 'zh-CN',
  });
  const page = await context.newPage();

  // Collect console errors and network failures
  const errors = [];
  const networkFails = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', err => errors.push(err.message));
  page.on('response', resp => {
    if (resp.status() >= 400) {
      networkFails.push(`${resp.status()} ${resp.request().method()} ${resp.url()}`);
    }
  });

  // ═══ Step 1: Login ═══
  console.log('[1] Logging in...');
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(500);

  const usernameInput = page.locator('input').first();
  await usernameInput.fill('admin');
  const passwordInput = page.locator('input[type="password"]');
  await passwordInput.fill('admin');
  await page.click('button');
  await page.waitForTimeout(2000);

  if (page.url().includes('/login')) {
    console.log('  ⚠️ FAIL: Still on login page!');
    await page.screenshot({ path: `${SCREENSHOTS}/01-login-failed.png`, fullPage: true });
    await browser.close();
    process.exit(1);
  }
  console.log('  ✅ Login successful');
  await page.screenshot({ path: `${SCREENSHOTS}/01-layout.png`, fullPage: true });

  // ═══ Step 2: Risk Monitoring pages ═══
  const checkPages = [
    { name: 'Rules', url: '/risk-monitor/rules', key: '规则管理', desc: '规则列表页' },
    { name: 'CreateRule', url: '/risk-monitor/rules/create', key: '创建规则', desc: '创建规则表单页' },
    { name: 'Scans', url: '/risk-monitor/scans', key: '扫描任务', desc: '扫描任务仪表板' },
    { name: 'Alerts', url: '/risk-monitor/alerts', key: '预警列表', desc: '预警列表页' },
  ];

  for (const p of checkPages) {
    console.log(`\n[2.${checkPages.indexOf(p)+1}] ${p.desc}: ${BASE}${p.url}`);
    const beforeErrors = errors.length;
    const beforeFails = networkFails.length;

    await page.goto(`${BASE}${p.url}`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(800);

    const newErrors = errors.slice(beforeErrors);
    const newFails = networkFails.slice(beforeFails);

    // Check page content
    const bodyText = await page.textContent('body').catch(() => '(error)');
    const hasContent = bodyText.includes(p.key);
    const hasErrorMsg = bodyText.includes('失败') || bodyText.includes('错误') || bodyText.includes('Error');

    console.log(`  Key "${p.key}": ${hasContent ? '✅ found' : '⚠️ NOT found'}`);
    if (hasErrorMsg) {
      const errIdx = Math.max(
        bodyText.indexOf('失败'),
        bodyText.indexOf('错误'),
      );
      const ctx = bodyText.substring(Math.max(0, errIdx - 50), errIdx + 30);
      console.log(`  ⚠️ Error message on page: "...${ctx}..."`);
    }
    if (newErrors.length > 0) console.log(`  ⚠️ Console errors:`, newErrors.slice(0, 5));
    if (newFails.length > 0) console.log(`  ⚠️ Network fails:`, newFails.slice(0, 5));

    const filename = p.name.toLowerCase();
    await page.screenshot({ path: `${SCREENSHOTS}/02-${filename}.png`, fullPage: true });
  }

  // ═══ Step 3: Sidebar navigation ═══
  console.log('\n[3] Testing sidebar navigation...');
  await page.goto(`${BASE}/cases`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);

  // Find and click risk monitor submenu
  const riskMenu = page.locator('.el-sub-menu__title').filter({ hasText: '风险监控' });
  const riskMenuExists = (await riskMenu.count()) > 0;
  console.log(`  Risk monitor submenu: ${riskMenuExists ? '✅ found' : '⚠️ NOT found'}`);

  if (riskMenuExists) {
    await riskMenu.click();
    await page.waitForTimeout(500);

    // Check submenu items
    for (const item of ['规则管理', '扫描任务', '预警列表']) {
      const menuItem = page.locator('.el-menu-item').filter({ hasText: item });
      const count = await menuItem.count();
      console.log(`  Submenu "${item}": ${count > 0 ? '✅ visible' : '⚠️ NOT visible'}`);

      // Click and verify navigation
      if (count > 0) {
        await menuItem.click();
        await page.waitForTimeout(1000);
        const url = page.url();
        console.log(`    Navigated to: ${url}`);
        await page.screenshot({ path: `${SCREENSHOTS}/03-nav-${item}.png`, fullPage: true });
      }
    }
  }

  // ═══ Step 4: Case detail & approval ═══
  console.log('\n[4] Testing case detail & approval...');
  const token = await page.evaluate(() => localStorage.getItem('access_token'));

  if (token) {
    const response = await page.evaluate(async (t) => {
      const res = await fetch('/api/v1/cases?page=1&page_size=5', {
        headers: { 'Authorization': `Bearer ${t}` }
      });
      return res.json();
    }, token);

    if (response?.data?.items?.length > 0) {
      const firstCase = response.data.items[0];
      console.log(`  Case: id=${firstCase.id}`);

      // Case detail
      await page.goto(`${BASE}/cases/${firstCase.id}`, { waitUntil: 'networkidle', timeout: 15000 });
      await page.waitForTimeout(1000);
      const detailBody = await page.textContent('body').catch(() => '');
      const hasTimeline = detailBody.includes('阶段') || detailBody.includes('进度') || detailBody.includes('时间线');
      console.log(`  Case detail timeline: ${hasTimeline ? '✅ found' : '⚠️ may be missing'}`);
      // Check for "修改通过" status
      if (detailBody.includes('修改通过')) console.log(`  ✅ "修改通过" status visible in timeline`);
      await page.screenshot({ path: `${SCREENSHOTS}/04-case-detail.png`, fullPage: true });

      // Approval page
      await page.goto(`${BASE}/cases/${firstCase.id}/approval`, { waitUntil: 'networkidle', timeout: 15000 });
      await page.waitForTimeout(1000);
      const approvalBody = await page.textContent('body').catch(() => '');
      console.log(`  "划词调整": ${approvalBody.includes('划词调整') ? '✅ found' : '⚠️ NOT found'}`);
      console.log(`  "重新生成": ${approvalBody.includes('重新生成') ? '✅ found' : '⚠️ NOT found'}`);
      console.log(`  "选中原文": ${approvalBody.includes('选中原文') ? '✅ found' : '⚠️ NOT found'}`);
      console.log(`  "修改指令": ${approvalBody.includes('修改指令') ? '✅ found' : '⚠️ NOT found'}`);
      await page.screenshot({ path: `${SCREENSHOTS}/05-approval.png`, fullPage: true });
    } else {
      console.log('  ⚠️ No cases found');
    }
  }

  // ═══ Step 5: Check for create rule form ═══
  console.log('\n[5] Testing Create Rule form...');
  await page.goto(`${BASE}/risk-monitor/rules/create`, { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(1000);

  // Check key form elements
  const formBody = await page.textContent('body').catch(() => '');
  const formElements = ['SQL 语句', '风险等级', '事业部', '业务循环', '监控频率'];
  for (const el of formElements) {
    console.log(`  "${el}": ${formBody.includes(el) ? '✅ present' : '⚠️ missing'}`);
  }

  // ═══ Summary ═══
  console.log('\n' + '═'.repeat(60));
  console.log('VERIFICATION SUMMARY');
  console.log('═'.repeat(60));
  console.log(`Console errors: ${errors.length}`);
  if (errors.length > 0) {
    // Deduplicate errors
    const unique = [...new Set(errors)];
    console.log('Unique errors:');
    unique.slice(0, 10).forEach((e, i) => console.log(`  [${i+1}] ${e.substring(0, 120)}`));
  }
  console.log(`Network fails (4xx/5xx): ${networkFails.length}`);
  const uniqueFails = [...new Set(networkFails)];
  uniqueFails.slice(0, 10).forEach((f, i) => console.log(`  [${i+1}] ${f}`));
  console.log(`\nScreenshots: ${SCREENSHOTS}/`);
  console.log('═'.repeat(60));

  await browser.close();
}

main().catch(err => {
  console.error('Script failed:', err);
  process.exit(1);
});
