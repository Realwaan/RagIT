const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require('jsdom');

function setup() {
    const dom = new JSDOM('<main id="answer"></main>', { runScripts: 'outside-only' });
    const { window } = dom;
    // Exercise the real renderer independently from application startup/network.
    window.document.addEventListener = () => {};
    window.eval(fs.readFileSync('app/static/marked.min.js', 'utf8'));
    window.eval(fs.readFileSync('app/static/app.js', 'utf8'));
    return { window, el: window.document.getElementById('answer') };
}

test('short answers render semantic headings, lists and citation buttons without disclosure', () => {
    const { window, el } = setup();
    window.renderAuditAnswerInto(el, '**A 15% credit applies.** [1]\n\n### Conditions\n\n- File within 30 days. [1]\n- Excludes maintenance. [2]');
    assert.equal(el.querySelector('strong').textContent, 'A 15% credit applies.');
    assert.equal(el.querySelector('h3').textContent, 'Conditions');
    assert.equal(el.querySelectorAll('li').length, 2);
    assert.equal(el.querySelectorAll('button.citation-anchor').length, 3);
    assert.equal(el.querySelector('details'), null);
    window.close();
});

test('full source excerpts are collapsed but retain every condition and clickable citation', () => {
    const { window, el } = setup();
    window.renderAuditAnswerInto(el, 'A 15% credit applies. [1]\n\n### Source excerpts\n\n#### Source [1]\n\nFile within 30 days. Maintenance is excluded.');
    const details = el.querySelector('details');
    assert.equal(details.open, false);
    assert.equal(details.querySelector('summary').textContent, 'Source excerpts');
    assert.match(details.textContent, /Maintenance is excluded/);
    assert.equal(details.querySelector('button').value, '1');
    details.open = true;
    assert.equal(details.open, true);
    window.close();
});

test('long answers retain all blocks and keep headings with their following details', () => {
    const { window, el } = setup();
    const body = 'Detailed fact. '.repeat(85);
    window.renderAuditAnswerInto(el, 'Summary. [1]\n\n' + body + '\n\n### Exceptions\n\nA final exception. [2]');
    const details = el.querySelector('details');
    assert.equal(details.open, false);
    assert.match(el.textContent, /Summary/);
    assert.match(details.textContent, /Exceptions.*A final exception/s);
    assert.equal(el.textContent.match(/Detailed fact\./g).length, 85);
    window.close();
});

test('citations do not corrupt code or link attributes, and raw scripts stay inert', () => {
    const { window, el } = setup();
    window.renderAuditAnswerInto(el, '`array[1]` and [reference](https://example.com/items[2]) [3]\n\n<script>bad()</script>');
    assert.equal(el.querySelector('code').textContent, 'array[1]');
    assert.equal(decodeURI(el.querySelector('a').getAttribute('href')), 'https://example.com/items[2]');
    assert.equal(el.querySelectorAll('button').length, 1);
    assert.equal(el.querySelector('button').value, '3');
    assert.equal(el.querySelector('script'), null);
    window.close();
});

test('comparison tables preserve headers in a focusable scroll region', () => {
    const { window, el } = setup();
    window.renderAuditAnswerInto(el, '| Metric | Target | Actual |\n| --- | --- | --- |\n| Uptime | 99.9% [1] | 98.2% [2] |');
    assert.equal(el.querySelectorAll('th').length, 3);
    assert.equal(el.querySelectorAll('td').length, 3);
    assert.equal(el.querySelector('.table-wrapper').getAttribute('tabindex'), '0');
    assert.equal(el.querySelectorAll('button').length, 2);
    window.close();
});

test('legacy wall-of-text paragraphs gain spacing without losing inline formatting or citations', () => {
    const { window, el } = setup();
    const sentence = 'A **documented requirement** applies to every account and must be checked before approval. [1] ';
    window.renderAuditAnswerInto(el, sentence.repeat(16));
    assert.ok(el.querySelectorAll('p').length > 2);
    assert.equal(el.querySelectorAll('strong').length, 16);
    assert.equal(el.querySelectorAll('button').length, 16);
    assert.equal(el.textContent.match(/before approval/g).length, 16);
    assert.ok(el.querySelector('details'));
    window.close();
});
