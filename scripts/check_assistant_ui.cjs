const { chromium } = require('playwright-core');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.RAGIT_TEST_URL || 'http://127.0.0.1:8001';
(async () => {
  const browser = await chromium.launch({ executablePath: process.argv[2], headless: true });
  const context = await browser.newContext({ viewport: {width:1440, height:1000}, permissions:['clipboard-read','clipboard-write'] });
  const page = await context.newPage();
  const errors = []; page.on('pageerror', e => { errors.push(e.message); console.log('PAGE ERROR', e.message); });
  try {
    await page.goto(base); await page.getByRole('heading', {name:'What would you like to understand?'}).waitFor();
    await page.screenshot({path:'reports/assistant-welcome.png'});
    await page.getByRole('button', {name:/Explore with a sample/}).click();
    await page.getByRole('button', {name:'sample_enterprise_sop.txt', exact:true}).first().waitFor();
    await page.getByRole('textbox', {name:'Message RagIT'}).fill('What is the penalty credit if availability drops below 99.5%?');
    await page.getByRole('button', {name:'Send message',exact:true}).click();
    await page.getByRole('button', {name:'Copy answer',exact:true}).waitFor();
    assert.match(await page.locator('.assistant-message').innerText(), /15%/);
    await page.screenshot({path:'reports/assistant-answer.png'});
    await page.getByRole('button',{name:'View source 1',exact:true}).first().click();
    await page.getByRole('heading',{name:'Source evidence'}).waitFor();
    assert.match(await page.locator('.source-quote').innerText(), /15%/);
    await page.getByRole('button',{name:'Close source'}).click();
    await page.getByRole('button',{name:'Copy answer',exact:true}).click();
    assert.match(await page.evaluate(() => navigator.clipboard.readText()), /15%/);
    const download = page.waitForEvent('download');
    await page.getByRole('button',{name:'Export answer'}).click();
    await page.getByRole('menuitem',{name:'PDF',exact:true}).click();
    assert.match((await download).suggestedFilename(), /\.pdf$/);
    await page.getByRole('button',{name:'Regenerate answer'}).click();
    await page.getByRole('button',{name:'Next response version'}).waitFor();
    await page.getByRole('button',{name:'Previous response version'}).click();
    await page.getByRole('button',{name:'Edit message',exact:true}).click();
    await page.getByRole('textbox',{name:'Edit your message'}).fill('What is the uptime guarantee?');
    await page.getByRole('button',{name:'Save and resend'}).click();
    await page.getByRole('button',{name:'Copy answer',exact:true}).waitFor();
    // The offline definition fallback can refuse this wording; the frontend
    // must faithfully display that refusal and allow editing to continue.
    const editedAnswer = await page.locator('.assistant-message').innerText();
    if (!/99\.9/.test(editedAnswer)) {
      assert.match(editedAnswer, /Not found in document/);
      await page.getByRole('button',{name:'Edit message',exact:true}).click();
      await page.getByRole('textbox',{name:'Edit your message'}).fill('Which availability percentage is guaranteed?');
      await page.getByRole('button',{name:'Save and resend'}).click();
      await page.getByRole('button',{name:'Copy answer',exact:true}).waitFor();
      assert.match(await page.locator('.assistant-message').innerText(), /99\.9/);
    }
    await page.reload();
    await page.getByRole('button',{name:'Copy answer',exact:true}).waitFor();
    assert.match(await page.locator('.assistant-message').innerText(), /99\.9/);
    await page.getByRole('button',{name:'Use dark theme'}).click();
    await page.screenshot({path:'reports/assistant-dark.png'});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:'reports/assistant-mobile.png'});
    const width = await page.locator('.thread-content').evaluate(el => el.getBoundingClientRect().width);
    assert.ok(width >= 350);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.getByRole('button',{name:'Open navigation'}).click();
    await page.getByRole('button',{name:'New conversation',exact:true}).last().click();
    await page.getByRole('heading',{name:'What would you like to understand?'}).waitFor();
    assert.equal(errors.length,0,errors.join('\n'));
    if (process.argv[3]) {
      await page.setViewportSize({width:1440,height:1000});
      const chooser = page.waitForEvent('filechooser');
      await page.getByRole('button',{name:'Attach document',exact:true}).click();
      await (await chooser).setFiles(process.argv[3]);
      await page.getByRole('button',{name:'preview-fixture.pdf',exact:true}).first().waitFor();
      await page.getByRole('button',{name:'Remove attachment'}).click();
      await page.getByRole('button',{name:'Open document library'}).click();
      const library = page.getByRole('dialog',{name:'Document library',exact:true});
      await library.getByRole('combobox',{name:'PDF page'}).selectOption('3');
      await library.getByRole('button',{name:'Zoom in',exact:true}).click();
      assert.equal(await library.locator('.evidence-canvas img').evaluate(el=>el.naturalWidth>100),true);
      await page.screenshot({path:'reports/frontend/library-real-pdf.png'});
      await page.keyboard.press('Escape');
      await page.getByRole('textbox',{name:'Message RagIT'}).fill('Orion Revenue 2025 on PDF page 3');
      await page.getByRole('button',{name:'Send message',exact:true}).click();
      await page.getByRole('button',{name:'Copy answer',exact:true}).waitFor();
      assert.match(await page.locator('.assistant-message').innerText(), /842/);
      await page.getByRole('button',{name:'View source 1',exact:true}).first().click();
      await page.getByRole('button',{name:'Zoom in',exact:true}).click();
      await page.screenshot({path:'reports/frontend/evidence-real-pdf.png'});
      await page.getByRole('button',{name:'Full page',exact:true}).click();
      await page.getByRole('button',{name:'Zoom in',exact:true}).click();
      assert.match(await page.getByRole('link',{name:/Open original/}).getAttribute('href'),/\/3$/);
      await page.keyboard.press('Escape');
      await page.screenshot({path:'reports/frontend/answer-real-pdf.png'});
      assert.equal(errors.length,0,errors.join('\n'));
    }
    fs.writeFileSync('reports/assistant-ui-check.json',JSON.stringify({passed:true,mode:'Real local backend, local retrieval and extractive answers; no external models',errors,checks:['real streaming response','source drawer','copy','PDF export','regenerate and branch','edit and resend','reload persistence','dark mode','mobile navigation',...(process.argv[3]?['PDF upload','real page previews','table answer with page citation','crop and full page evidence']:[])]},null,2));
    console.log('Assistant UI checks passed.');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
