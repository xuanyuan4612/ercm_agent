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

  // Collect console errors
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', err => errors.push(err.message));

  // ═══ Step 1: Login ═══
  console.log('[1] Logging in...');
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' });
  await page.fill('input[type="text"], input[placeholder*="用户"], input:first-of-type', 'admin', { timeout: 3000 })
    .catch(() => console.log('  Tried generic selector for username'));

  // Try to find the username and password fields explicitly
  const inputs = await page.$$('input');
  console.log(`  Found ${inputs.length} input fields`);
  for (const inp of inputs) {
    const placeholder = await inp.getAttribute('placeholder');
    const type = await inp.getAttribute('type');
    console.log(`  Input: type=${type}, placeholder="${placeholder}"`);
  }

  // Fill username
  const usernameInput = page.locator('input').first();
  await usernameInput.fill('admin');

  // Fill password
  const passwordInput = page.locator('input[type="password"]');
  await passwordInput.fill('admin');

  // Click login button
  await page.click('button');
  await page.waitForTimeout(2000);

  const afterLoginUrl = page.url();
  console.log(`  After login URL: ${afterLoginUrl}`);

  if (afterLoginUrl.includes('/login')) {
    console.log('  ⚠️ Still on login page — login may have failed');
    console.log('  Page errors:', errors.slice(-5));
    await page.screenshot({ path: `${SCREENSHOTS}/01-login-failed.png`, fullPage: true });
  } else {
    console.log('  ✅ Login successful');
    const pageContent = await page.textContent('body');
    console.log('  Page title snippet:', pageContent.substring(0, 200));
  }

  // ═══ Step 2: Navigate risk monitoring pages ═══
  const pages = [
    { name: 'Risk Rules', url: '/risk-monitor/rules' },
    { name: 'Create Rule', url: '/risk-monitor/rules/create' },
    { name: 'Scan Dashboard', url: '/risk-monitor/scans' },
    { name: 'Alert List', url: '/risk-monitor/alerts' },
    { name: 'Cases', url: '/cases' },
  ];

  for (const p of pages) {
    console.log(`\n[Navigating to ${p.name}] ${BASE}${p.url}`);
    const beforeErrors = errors.length;
    await page.goto(`${BASE}${p.url}`, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);

    const newErrors = errors.slice(beforeErrors);
    if (newErrors.length > 0) {
      console.log(`  ⚠️ New console errors:`, newErrors);
    }

    // Check page content
    const bodyText = await page.textContent('body').catch(() => '(error reading body)');
    const snippet = bodyText.substring(0, 300).replace(/\s+/g, ' ');
    console.log(`  Page content: ${snippet}...`);

    // Screenshot
    const filename = p.name.toLowerCase().replace(/\s+/g, '-');
    await page.screenshot({ path: `${SCREENSHOTS}/02-${filename}.png`, fullPage: true });
    console.log(`  Screenshot saved: 02-${filename}.png`);
  }

  // ═══ Step 3: Check sidebar menu ═══
  console.log('\n[3] Checking sidebar...');
  await page.goto(`${BASE}/cases`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  // Look for menu items
  const menuItems = await page.$$eval('.el-menu-item, .el-sub-menu__title, [class*="menu"]', els =>
    els.map(e => ({ text: e.textContent?.trim().substring(0, 50), class: e.className.substring(0, 80) }))
  );
  console.log('  Menu items found:', menuItems.length);
  menuItems.slice(0, 20).forEach(m => console.log(`    - "${m.text}" [${m.class}]`));

  await page.screenshot({ path: `${SCREENSHOTS}/03-sidebar.png`, fullPage: true });

  // ═══ Step 4: Case detail & approval ═══
  console.log('\n[4] Checking case detail & approval...');
  // First get case list from API to find a case ID
  const token = await page.evaluate(() => localStorage.getItem('access_token'));
  console.log(`  Token available: ${token ? 'yes' : 'no'}`);

  if (token) {
    // Use the API to get case list
    const response = await page.evaluate(async (t) => {
      const res = await fetch('/api/v1/cases?page=1&page_size=5', {
        headers: { 'Authorization': `Bearer ${t}` }
      });
      return res.json();
    }, token);

    console.log(`  Cases API response code: ${response?.code}`);
    if (response?.data?.items?.length > 0) {
      const firstCase = response.data.items[0];
      console.log(`  First case: id=${firstCase.id}, title="${firstCase.title}"`);

      // Navigate to case detail
      await page.goto(`${BASE}/cases/${firstCase.id}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(1000);
      await page.screenshot({ path: `${SCREENSHOTS}/04-case-detail.png`, fullPage: true });
      console.log('  Case detail screenshot saved');

      // Navigate to approval page
      await page.goto(`${BASE}/cases/${firstCase.id}/approval`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(1000);
      await page.screenshot({ path: `${SCREENSHOTS}/05-approval.png`, fullPage: true });
      console.log('  Approval page screenshot saved');

      const approvalBody = await page.textContent('body').catch(() => '');
      if (approvalBody.includes('划词调整') || approvalBody.includes('重新生成')) {
        console.log('  ✅ "划词调整" or "重新生成" found on approval page');
      } else {
        console.log('  ⚠️ "划词调整" NOT found on approval page');
      }
    } else {
      console.log('  ⚠️ No cases found, skipping case detail checks');
    }
  }

  // ═══ Step 5: Check for risk monitor rule approval ═══
  console.log('\n[5] Checking risk rule approval...');
  if (token) {
    const rulesResponse = await page.evaluate(async (t) => {
      const res = await fetch('/api/v1/risk-monitor/rules?page=1&page_size=5', {
        headers: { 'Authorization': `Bearer ${t}` }
      });
      return res.json();
    }, token);

    console.log(`  Rules API response code: ${rulesResponse?.code}`);
    if (rulesResponse?.data?.items?.length > 0) {
      const firstRule = rulesResponse.data.items[0];
      console.log(`  First rule: id=${firstRule.id}, name="${firstRule.name}"`);

      // Check rule approval page
      await page.goto(`${BASE}/risk-monitor/rules/${firstRule.id}/approval`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(1000);
      await page.screenshot({ path: `${SCREENSHOTS}/06-rule-approval.png`, fullPage: true });
      console.log('  Rule approval screenshot saved');
    } else {
      console.log('  No rules found');
    }
  }

  // ═══ Summary ═══
  console.log('\n═══════════════════════════════════');
  console.log('Summary:');
  console.log(`  Total console errors: ${errors.length}`);
  if (errors.length > 0) {
    console.log('  Errors:');
    errors.forEach((e, i) => console.log(`    [${i+1}] ${e}`));
  }
  console.log(`  Screenshots saved to: ${SCREENSHOTS}/`);
  console.log('═══════════════════════════════════');

  await browser.close();
}

main().catch(err => {
  console.error('Script failed:', err);
  process.exit(1);
});
