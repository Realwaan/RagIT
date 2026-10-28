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
const doc = { doc_id: 'sample', filename: 'sample_enterprise_sop.pdf', pages: 2, visual_analysis: { status: 'ready', completed: 3, failed: 0, total: 3 } };
const pdfDoc = { doc_id: 'manual', filename: 'Operations manual.pdf', pages: 3, classification: { label: 'Technical Documentation' } };
const source = { citation_id: 1, filename: doc.filename, page: 1, parent_text: 'A 15% credit applies below 99.5% availability. The uptime guarantee is 99.9%.', evidence_origin: 'ai_interpretation', verification_status: 'model_checked', caption: 'Figure 1: Service availability' };
source.image_url = '/api/crop/sample/figure1';
source.linked_visuals = [{ id: 'figure1', title: 'Figure 1: Service availability', page: 2, image_url: source.image_url }];
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
    let pdfLoaded = false;
    let uploadFails = true;
    let exportFails = false;
    let incompleteStream = true;
    const stoppedGate = deferred();
    const uploadGate = deferred();
    const vaultGate = deferred();
    const sampleGate = deferred();
    await page.route('**/vault', async route => {
      vaultCalls++;
      if (vaultCalls === 1) {
        await vaultGate.promise;
        return route.fulfill({ status: 503, json: { detail: 'Documents are temporarily unavailable.' } });
      }
      return route.fulfill({ json: { vault: [...(loaded ? [doc] : []), ...(pdfLoaded ? [pdfDoc] : [])] } });
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
      assert.ok([doc.doc_id, pdfDoc.doc_id].includes(doc_id));
      if (query === 'Stop this response') { await stoppedGate.promise; return route.fulfill({ contentType: 'text/event-stream', body: '' }).catch(() => {}); }
      if (query === 'Recover interrupted response' && incompleteStream) {
        incompleteStream = false;
        return route.fulfill({ contentType: 'text/event-stream', body: 'data: {"type":"delta","text":"Partial response"}\n\n' });
      }
      const answer = query.includes('uptime') ? 'The uptime guarantee is **99.9%**. [1]' : 'A **15% credit** applies. [1]';
      const events = [
        { type: 'activity', label: 'Finding relevant passages' },
        { type: 'delta', text: answer },
        { type: 'done', status: 'SUCCESS', query, answer, sources: [source], evaluation: { claim_support: 'needs_review', claims: [{text: 'A 15% credit applies.', status: 'uncertain', reason: 'Support requires review.'}] } },
      ];
      await route.fulfill({ contentType: 'text/event-stream', body: events.map(event => `data: ${JSON.stringify(event)}\r\n\r\n`).join('') });
    });
    await page.route('**/export-report', route => exportFails ? route.fulfill({ status: 503, json: { detail: 'Export is temporarily unavailable.' } }) : route.fulfill({ contentType: 'application/pdf', body: '%PDF-1.4\nFixture export' }));
    await page.route('**/upload', async route => {
      if (route.request().postDataBuffer().includes(Buffer.from('cancel.pdf'))) {
        await uploadGate.promise;
        return route.fulfill({ json: { ...pdfDoc, pages_processed: 3 } }).catch(() => {});
      }
      if (uploadFails) { uploadFails = false; return route.fulfill({ status: 503, json: { detail: 'Upload unavailable. Please retry.' } }); }
      pdfLoaded = true;
      return route.fulfill({ json: { ...pdfDoc, pages_processed: 3 } });
    });
    let cropCalls = 0;
    const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==', 'base64');
    await page.route('**/api/crop/sample/figure1*', route => {
      cropCalls++;
      return cropCalls === 1 ? route.fulfill({ status: 503, body: '' })
        : route.fulfill({ contentType: 'image/png', body: png });
    });
    await page.route('**/api/preview/sample/2', route => route.fulfill({ contentType: 'image/png', body: png }));
    await page.route('**/api/preview/manual/*', route => route.fulfill({ contentType: 'image/png', body: png }));

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
    await page.locator('.assistant-message .markdown').first().waitFor();
    assert.match(await page.locator('.assistant-message').innerText(), /15%/);
    await page.getByText('Some claims need source review', { exact: true }).click();
    await page.getByText('Support uncertain:', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'View source 1', exact: true }).click();
    await page.getByRole('heading', { name: 'Source evidence' }).waitFor();
    assert.match(await page.locator('.source-quote').innerText(), /15%/);
    await page.getByText('AI interpretation of the image / Checked against the original image', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Retry image', exact: true }).click();
    const zoomIn = page.getByRole('button', { name: 'Zoom in', exact: true });
    await zoomIn.click();
    assert.equal(await page.locator('.evidence-toolbar [aria-live]').innerText(), '125%');
    assert.equal(await page.locator('.evidence-canvas').evaluate(el => el.scrollWidth > el.clientWidth), true);
    await page.getByRole('button', { name: 'Fit', exact: true }).click();
    assert.equal(await page.locator('.evidence-toolbar [aria-live]').innerText(), '100%');
    await page.getByRole('button', { name: 'Full page', exact: true }).click();
    assert.equal(await page.getByRole('link', { name: /Open original/ }).getAttribute('href'), '/api/preview/sample/2');
    await zoomIn.click();
    assert.equal(cropCalls, 2);
    await page.getByText('Figure 1: Service availability', { exact: true }).waitFor();
    await page.getByText('3 visuals searchable', { exact: true }).waitFor();
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
    await page.locator('.assistant-message .markdown').first().waitFor();
    assert.match(await page.locator('.assistant-message').innerText(), /99\.9/);
    await page.reload();
    await page.getByRole('button', { name: 'Copy answer', exact: true }).waitFor();
    await page.locator('.assistant-message .markdown').first().waitFor();
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
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole('textbox', { name: 'Message RagIT' }).fill('Draft without a document');
    await page.getByRole('textbox', { name: 'Message RagIT' }).press('Enter');
    assert.equal(await page.locator('.user-message').count(), 0);
    await page.getByRole('textbox', { name: 'Message RagIT' }).fill('');

    const attach = async (name, content = '%PDF-fixture') => {
      const chooser = page.waitForEvent('filechooser');
      await page.getByRole('button', { name: 'Attach document', exact: true }).click();
      await (await chooser).setFiles({ name, mimeType: 'application/pdf', buffer: Buffer.from(content) });
    };
    await attach('empty.pdf', '');
    await page.getByRole('alert').filter({ hasText: 'This file is empty' }).waitFor();
    await page.getByRole('button', { name: 'Remove attachment' }).click();
    await attach('manual.pdf');
    await page.getByRole('alert').filter({ hasText: 'Upload unavailable' }).waitFor();
    await page.getByRole('button', { name: 'Remove attachment' }).click();
    await attach('cancel.pdf');
    await page.getByRole('status').filter({ hasText: 'Processing document' }).waitFor();
    await page.getByRole('button', { name: 'Remove attachment' }).click();
    uploadGate.resolve();
    await attach('manual.pdf');
    await page.getByRole('button', { name: pdfDoc.filename, exact: true }).first().waitFor();
    await page.getByRole('button', { name: 'Remove attachment' }).click();

    await page.getByRole('button', { name: 'Open document library', exact: true }).click();
    const library = page.getByRole('dialog', { name: 'Document library', exact: true });
    await library.getByRole('textbox', { name: 'Search documents' }).fill('does-not-exist');
    await library.getByRole('button', { name: 'Clear search' }).click();
    await library.getByRole('button', { name: /Operations manual.pdf/ }).click();
    await library.getByRole('button', { name: 'Next PDF page' }).click();
    assert.equal(await library.getByRole('combobox', { name: 'PDF page' }).inputValue(), '2');
    await library.getByRole('combobox', { name: 'PDF page' }).selectOption('3');
    assert.equal(await library.getByRole('button', { name: 'Next PDF page' }).isDisabled(), true);
    await library.getByRole('button', { name: 'Zoom in', exact: true }).click();
    assert.equal(await library.locator('.evidence-canvas').evaluate(el => el.scrollWidth > el.clientWidth), true);
    fs.mkdirSync('reports/frontend', { recursive: true });
    await page.screenshot({ path: 'reports/frontend/library-desktop.png' });
    await page.keyboard.press('Escape');
    assert.equal(await page.getByRole('button', { name: 'Open document library' }).evaluate(el => el === document.activeElement), true);

    await page.getByRole('textbox', { name: 'Message RagIT' }).fill('What credit applies?');
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    await page.getByRole('button', { name: 'Copy answer', exact: true }).waitFor();
    await page.getByRole('button', { name: /^Rename / }).first().click();
    await page.getByRole('textbox', { name: 'Conversation name' }).fill('Operations review');
    await page.getByRole('button', { name: 'Save name' }).click();
    await page.getByRole('button', { name: 'Regenerate answer' }).click();
    await page.getByRole('button', { name: 'Copy answer', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Operations review', exact: true }).waitFor();
    await page.getByRole('textbox', { name: 'Message RagIT' }).fill('Keep this unsent draft');
    await page.getByRole('button', { name: 'New conversation', exact: true }).click();
    await page.getByRole('button', { name: 'Operations review', exact: true }).click();
    assert.equal(await page.getByRole('textbox', { name: 'Message RagIT' }).inputValue(), 'Keep this unsent draft');
    await page.reload();
    await page.getByRole('button', { name: 'Copy answer', exact: true }).waitFor();
    assert.equal(await page.getByRole('textbox', { name: 'Message RagIT' }).inputValue(), 'Keep this unsent draft');
    assert.equal(await page.getByRole('button', { name: 'Operations review', exact: true }).getAttribute('aria-current'), 'page');
    exportFails = true;
    await page.getByRole('button', { name: 'Export answer' }).click();
    await page.getByRole('menuitem', { name: 'PDF', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Export is temporarily unavailable' }).waitFor();
    exportFails = false;
    const retryDownload = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export answer' }).click();
    await page.getByRole('menuitem', { name: 'PDF', exact: true }).click();
    await retryDownload;
    await page.getByRole('textbox', { name: 'Message RagIT' }).fill('Stop this response');
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    await page.getByRole('button', { name: 'Stop response', exact: true }).click();
    stoppedGate.resolve();
    await page.getByText('Response stopped. You can retry below.', { exact: true }).waitFor();
    await page.getByRole('textbox', { name: 'Message RagIT' }).fill('Recover interrupted response');
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    await page.getByText('The connection ended before the answer finished. Retry to continue.', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Regenerate answer' }).last().click();
    await page.locator('.assistant-message').last().getByRole('button', { name: 'Copy answer', exact: true }).waitFor();
    await page.locator('.assistant-message').last().locator('.markdown').first().waitFor();
    assert.match(await page.locator('.assistant-message').last().innerText(), /15%/);
    await page.screenshot({ path: 'reports/frontend/conversation-desktop.png' });
    await page.getByRole('button', { name: doc.filename, exact: true }).click();
    await page.getByRole('heading', { name: 'What would you like to understand?' }).waitFor();
    assert.equal(await page.locator('.assistant-message').count(), 0);
    await page.getByRole('button', { name: 'Operations review', exact: true }).click();
    assert.ok(await page.locator('.assistant-message').count() > 0);
    for (const width of [320, 390, 768]) {
      await page.setViewportSize({ width, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.getByRole('button', { name: 'Open document library', exact: true }).click();
      assert.equal(await library.evaluate(el => el.scrollWidth <= el.clientWidth), true);
      if (width === 390) await page.screenshot({ path: 'reports/frontend/library-mobile.png' });
      await page.keyboard.press('Escape');
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: 'Use light theme' }).click();
    await page.screenshot({ path: 'reports/frontend/conversation-mobile.png' });
    pdfLoaded = false;
    await page.reload();
    await page.getByRole('status').filter({ hasText: 'document is no longer loaded' }).waitFor();
    await page.getByRole('textbox', { name: 'Message RagIT' }).fill('Must not send to a missing document');
    assert.equal(await page.getByRole('button', { name: 'Send message', exact: true }).isDisabled(), true);
    assert.deepEqual(errors, []);
    fs.writeFileSync('reports/frontend/verification.json', JSON.stringify({ passed: true, mode: 'Production build in Chromium with deterministic API fixtures', errors, checks: ['uncertain claims are visible and reviewable', 'sample and document retry', 'streaming and CRLF events', 'sources and image retry', 'real image zoom', 'copy and export retry', 'response branches and editing', 'upload validation, retry and cancellation', 'document library search and PDF pagination', 'rename persistence', 'draft and active conversation restoration', 'stop and interrupted stream recovery', 'document context separation', 'missing document recovery', 'desktop and 320/390/768px layouts', 'light and dark themes', 'dialog keyboard dismissal and focus restoration'] }, null, 2));
    console.log('Frontend completion checks passed. API responses were fixtures. Screenshots and verification report: reports/frontend.');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
