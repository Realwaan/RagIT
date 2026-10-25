// Reproduce the reported refusal against the actual PDF and running backend.
const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.RAGIT_TEST_URL || 'http://127.0.0.1:8012';
const executablePath = process.env.CHROME_PATH || [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].find(file => fs.existsSync(file));

(async () => {
  assert.ok(process.argv[2], 'Pass the local Data Abstraction PDF path.');
  const browser = await chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(30000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(base);
    const chooser = page.waitForEvent('filechooser');
    await page.getByRole('button', { name: 'Attach document', exact: true }).click();
    await (await chooser).setFiles({ name: '01_Data_Abstraction_and_Array_Review.pdf', mimeType: 'application/pdf', buffer: fs.readFileSync(process.argv[2]) });
    await page.getByRole('button', { name: '01_Data_Abstraction_and_Array_Review.pdf', exact: true }).first().waitFor();
    await page.getByRole('textbox', { name: 'Message RagIT' }).fill('What are the Abstract Data Types');
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    const answer = page.locator('.assistant-message').last();
    await answer.getByRole('button', { name: 'Copy answer', exact: true }).waitFor();
    assert.match(await answer.innerText(), /a set of objects together with a set of operations/);
    assert.match(await answer.innerText(), /mathematical abstractions/);
    await page.screenshot({ path: 'reports/data-abstraction-answer.png' });
    await answer.getByRole('button', { name: 'View source 1', exact: true }).first().click();
    await page.getByRole('heading', { name: 'Source evidence' }).waitFor();
    assert.match(await page.locator('.source-drawer').innerText(), /Page 4/);
    assert.match(await page.locator('.source-quote').innerText(), /abstract data type/);
    await page.screenshot({ path: 'reports/data-abstraction-source.png' });
    await page.keyboard.press('Escape');
    await page.getByRole('textbox', { name: 'Message RagIT' }).fill('What is quantum chromodynamics?');
    await page.getByRole('button', { name: 'Send message', exact: true }).click();
    await page.locator('.assistant-message').last().getByText('Answer not verified', { exact: true }).waitFor();
    assert.deepEqual(errors, []);
    console.log('PASS: actual PDF upload, reported question answered, page 4 citation, and unsupported question refused. No browser errors.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
