// Exercise the production UI with deterministic API fixtures; no model API is needed.
const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');

const root = path.resolve(__dirname, '../app/static/assistant');
const executablePath = process.argv[2] || process.env.CHROME_PATH || [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/chromium', '/usr/bin/google-chrome',
].find(file => fs.existsSync(file));
const doc = { doc_id: 'sample', filename: 'sample_enterprise_sop.txt', pages: 2 };
const source = { citation_id: 1, filename: doc.filename, page: 1, parent_text: 'A 15% credit applies below 99.5% availability. The uptime guarantee is 99.9%.' };
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };

(async () => {
  assert.ok(executablePath, 'Pass a Chromium executable path or set CHROME_PATH.');
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    const relative = url.pathname === '/' ? 'index.html' : url.pathname.replace(/^\/static\/assistant\//, '');
    const file = path.resolve(root, relative);
    if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404).end(); return;
    }
    const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2' };
    res.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream');
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ executablePath, headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, permissions: ['clipboard-read', 'clipboard-write'] });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let vaultCalls = 0;
    let sampleCalls = 0;
    let loaded = false;
    const vaultGate = deferred();
    const sampleGate = deferred();
    await page.route('**/vault', async route => {
      vaultCalls++;
      if (vaultCalls === 1) {
        await vaultGate.promise;
        return route.fulfill({ status: 503, json: { detail: 'Documents are temporarily unavailable.' } });
      }
      return route.fulfill({ json: { vault: loaded ? [doc] : [] } });
    });
    await page.route('**/load-sample', async route => {
      sampleCalls++;
      if (sampleCalls === 1) {
        await sampleGate.promise;
        return route.fulfill({ status: 503, json: { detail: 'Sample could not load. Please retry.' } });
      }
      loaded = true;
      return route.fulfill({ json: doc });
    });
    await page.route('**/api/chat', async route => {
      const { query, doc_id } = route.request().postDataJSON();
      assert.equal(doc_id, doc.doc_id);
      const answer = query.includes('uptime') ? 'The uptime guarantee is **99.9%**. [1]' : 'A **15% credit** applies. [1]';
      const events = [
        { type: 'activity', label: 'Finding relevant passages' },
        { type: 'delta', text: answer },
        { type: 'done', status: 'SUCCESS', query, answer, sources: [source] },
      ];
      await route.fulfill({ contentType: 'text/event-stream', body: events.map(event => `data: ${JSON.stringify(event)}\n\n`).join('') });
    });
    await page.route('**/export-report', route => route.fulfill({ contentType: 'application/pdf', body: '%PDF-1.4\nFixture export' }));

    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.getByRole('heading', { name: 'What would you like to understand?' }).waitFor();
    await page.getByRole('status').filter({ hasText: 'Loading documents' }).waitFor();
    vaultGate.resolve();
    await page.getByRole('alert').filter({ hasText: 'Documents are temporarily unavailable' }).waitFor();
    await page.locator('.context-picker').click();
    await page.getByRole('menu').getByRole('alert').waitFor();
    await page.getByRole('menuitem', { name: 'Retry documents' }).click();
    await page.getByText('Attach a file using the paperclip.', { exact: true }).waitFor();
    await page.keyboard.press('Escape');
    await page.getByText('Attach a PDF, text, or Markdown file to get started.', { exact: true }).waitFor();

    await page.getByRole('button', { name: 'Explore with a sample document' }).click();
    await page.getByRole('status').filter({ hasText: 'Preparing your sample document' }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Loading sample document' }).isDisabled(), true);
    assert.equal(await page.locator('.new-chat').isDisabled(), true);
    assert.equal(await page.getByRole('textbox', { name: 'Message RagIT' }).isDisabled(), true);
    assert.equal(await page.getByRole('button', { name: 'Attach document' }).isDisabled(), true);
    assert.equal(await page.getByRole('button', { name: 'Find the essentials' }).isDisabled(), true);
    sampleGate.resolve();
    await page.getByRole('alert').filter({ hasText: 'Sample could not load' }).waitFor();
    await page.getByRole('button', { name: 'Explore with a sample document' }).click();
    await page.getByRole('button', { name: doc.filename, exact: true }).first().waitFor();
    assert.equal(sampleCalls, 2);
    await page.locator('.context-picker').click();
    assert.equal(await page.getByRole('menuitemradio', { name: doc.filename }).getAttribute('aria-checked'), 'true');
    await page.keyboard.press('Escape');

    await page.getByRole('textbox', { name: 'Message RagIT' }).fill('What credit applies?');
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    await page.getByRole('button', { name: 'Copy answer', exact: true }).waitFor();
    assert.match(await page.locator('.assistant-message').innerText(), /15%/);
    await page.getByRole('button', { name: 'View source 1', exact: true }).click();
    await page.getByRole('heading', { name: 'Source evidence' }).waitFor();
    assert.match(await page.locator('.source-quote').innerText(), /15%/);
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Copy answer', exact: true }).click();
    assert.match(await page.evaluate(() => navigator.clipboard.readText()), /15%/);
    const download = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export answer' }).click();
    await page.getByRole('menuitem', { name: 'PDF', exact: true }).click();
    assert.equal((await download).suggestedFilename(), 'ragit-answer.pdf');
    await page.getByRole('button', { name: 'Regenerate answer' }).click();
    await page.getByRole('button', { name: 'Previous response version' }).waitFor();
    await page.getByRole('button', { name: 'Previous response version' }).click();
    await page.getByRole('button', { name: 'Edit message', exact: true }).click();
    await page.getByRole('textbox', { name: 'Edit your message' }).fill('What is the uptime guarantee?');
    await page.getByRole('button', { name: 'Save and resend' }).click();
    await page.getByRole('button', { name: 'Copy answer', exact: true }).waitFor();
    assert.match(await page.locator('.assistant-message').innerText(), /99\.9/);
    await page.reload();
    await page.getByRole('button', { name: 'Copy answer', exact: true }).waitFor();
    assert.match(await page.locator('.assistant-message').innerText(), /99\.9/);
    await page.getByRole('button', { name: 'Use dark theme' }).click();
    assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');

    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.getByRole('button', { name: 'Open navigation' }).click();
    const navigation = page.getByRole('dialog', { name: 'Workspace navigation' });
    await navigation.getByRole('button', { name: /^Delete / }).click();
    await page.getByRole('button', { name: 'Keep conversation' }).click();
    await navigation.getByRole('button', { name: /^Delete / }).click();
    await page.getByRole('button', { name: 'Delete', exact: true }).click();
    await page.getByRole('button', { name: 'Close navigation' }).click();
    await page.getByRole('heading', { name: 'What would you like to understand?' }).waitFor();
    assert.equal(await page.locator('.assistant-message').count(), 0);
    assert.deepEqual(errors, []);
    console.log('Assistant components passed: document retry, sample loading/retry, message rendering, source dialog, copy/export, regenerate/branches, edit, persistence, theme, mobile layout, and deletion. API responses were fixtures.');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
