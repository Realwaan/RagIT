const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

test('legacy glassmorphism UI files are retired and absent', () => {
    assert.equal(fs.existsSync('app/static/app.js'), false, 'Legacy app.js must not exist');
    assert.equal(fs.existsSync('app/static/index.html'), false, 'Legacy index.html must not exist');
    assert.equal(fs.existsSync('app/static/marked.min.js'), false, 'Legacy marked.min.js must not exist');
});

test('modern assistant app shell is present and configured for React mounting', () => {
    const assistantHtmlPath = path.resolve('app/static/assistant/index.html');
    assert.equal(fs.existsSync(assistantHtmlPath), true, 'Modern assistant index.html must exist');

    const html = fs.readFileSync(assistantHtmlPath, 'utf8');
    const dom = new JSDOM(html);
    const { document } = dom.window;

    const root = document.getElementById('root');
    assert.ok(root, 'Assistant app must have a #root mount point');

    const scripts = Array.from(document.querySelectorAll('script')).map(s => s.getAttribute('src') || '');
    assert.ok(scripts.some(src => src.includes('/static/assistant/assets/')), 'Assistant must bundle static assets');
    assert.equal(scripts.some(src => src.includes('marked.min.js')), false, 'Marked.js must not be loaded');
    assert.equal(scripts.some(src => src.includes('app.js')), false, 'Legacy app.js must not be loaded');

    assert.equal(document.title.includes('RagIT'), true, 'Document title must reflect RagIT');
    dom.window.close();
});
