// Run against a local RagIT server: node scripts/check_answer_ui.cjs <browser executable>
const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
    const browser = await chromium.launch({ executablePath: process.argv[2], headless: true });
    try {
        const page = await browser.newPage({ viewport: { width: 1365, height: 1000 } });
        const errors = [];
        page.on('pageerror', e => errors.push(e.message));
        await page.goto('http://127.0.0.1:8000');
        const loaded = await page.request.post('http://127.0.0.1:8000/load-sample');
        assert.equal(loaded.ok(), true, await loaded.text());
        await page.locator('#query-input').fill('What is the penalty credit if availability drops below 99.5%?');
        const answerResponse = page.waitForResponse(r => r.url().endsWith('/ask') && r.request().method() === 'POST');
        await page.locator('#btn-submit').click();
        const response = await answerResponse;
        assert.equal(response.ok(), true);
        const result = await response.json();
        assert.notEqual(result.status, 'REFUSE');
        await page.locator('#answer-container .citation-anchor').first().waitFor();
        const details = page.locator('#answer-container details');
        assert.equal(await details.count(), 1);
        assert.equal(await details.getAttribute('open'), null);
        await page.screenshot({ path: 'reports/answer-desktop.png', fullPage: true });
        await details.locator('summary').focus();
        await page.keyboard.press('Enter');
        assert.notEqual(await details.getAttribute('open'), null);
        assert.match(await details.innerText(), /15%/);
        await details.locator('summary').click();
        await page.locator('#answer-container .citation-anchor').first().click();
        await page.waitForFunction(() => document.getElementById('proof-drawer').getBoundingClientRect().right <= innerWidth + 1);
        await page.screenshot({ path: 'reports/answer-source.png', fullPage: true });
        await page.keyboard.press('Escape');
        await page.waitForFunction(() => document.getElementById('proof-drawer').getBoundingClientRect().left >= innerWidth);

        // Exercise rich formatting through the same renderer used for live and restored answers.
        await page.evaluate(() => {
            renderAuditAnswerInto(document.getElementById('answer-container'),
                '**Availability fell below the target.** [1]\n\n### What this means\n\n' +
                '- A 15% billing credit applies below 99.5% availability. [1]\n' +
                '- Submit the claim within 30 days. [2]\n\n### Comparison\n\n' +
                '| Metric | Target | Actual |\n| --- | --- | --- |\n| Availability | 99.9% [1] | 98.2% [2] |\n\n' +
                '### Source excerpts\n\nFull supporting terms remain available here. [2]');
        });
        await page.screenshot({ path: 'reports/answer-structured-desktop.png', fullPage: true });
        await page.setViewportSize({ width: 390, height: 844 });
        await page.screenshot({ path: 'reports/answer-mobile.png', fullPage: true });
        const layout = await page.evaluate(() => {
            const answer = document.getElementById('answer-container');
            const wrapper = answer.querySelector('.table-wrapper');
            return {
                viewport: innerWidth, bodyWidth: document.documentElement.scrollWidth,
                answerWidth: answer.getBoundingClientRect().width,
                tableWidth: wrapper.getBoundingClientRect().width,
                headers: [...answer.querySelectorAll('th')].map(e => getComputedStyle(e).display),
                fontSize: getComputedStyle(answer).fontSize,
            };
        });
        assert.ok(layout.bodyWidth <= layout.viewport, JSON.stringify(layout));
        assert.ok(layout.answerWidth >= 280, JSON.stringify(layout));
        assert.ok(layout.tableWidth <= layout.answerWidth, JSON.stringify(layout));
        assert.ok(layout.headers.every(display => display === 'table-cell'));
        // The mobile sidebar overlays the page when requested, never squeezes it.
        await page.locator('#sidebar-toggle-btn').click();
        assert.equal(await page.locator('#left-sidebar').isVisible(), true);
        await page.locator('#sidebar-toggle-btn').click();
        assert.equal(await page.locator('#left-sidebar').isVisible(), false);

        await page.setViewportSize({ width: 1365, height: 1000 });
        await page.locator('#theme-btn-dark').click();
        await page.screenshot({ path: 'reports/answer-dark.png', fullPage: true });
        await page.locator('#query-input').fill('What is the uptime guarantee?');
        const secondResponse = page.waitForResponse(r => r.url().endsWith('/ask') && r.request().method() === 'POST');
        await page.locator('#btn-submit').click();
        assert.equal((await secondResponse).ok(), true);
        const history = page.locator('#session-history-list > details').first();
        await history.waitFor();
        assert.equal(await history.getAttribute('open'), null);
        await history.locator(':scope > summary').click();
        assert.notEqual(await history.getAttribute('open'), null);
        assert.equal(await history.locator('.prose-audit .citation-anchor').first().isVisible(), true);
        await history.locator('.prose-audit .citation-anchor').first().click();
        await page.waitForFunction(() => document.getElementById('proof-drawer').getBoundingClientRect().right <= innerWidth + 1);
        assert.match(await page.locator('#proof-drawer').innerText(), /15%/);
        assert.equal(errors.length, 0, errors.join('\n'));
        fs.writeFileSync('reports/answer-ui-check.json', JSON.stringify({ passed: true, layout, errors }, null, 2));
        console.log('Answer UI passed: real response, disclosure keyboard control, citations, desktop/mobile layout.');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
