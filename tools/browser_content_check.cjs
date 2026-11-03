/* 只读取现用库页面，不提交报名或审核。完整写入流程另在browser_check.cjs的独立库验证。 */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

(async()=>{
  const out=path.resolve(__dirname,'../output/acceptance');
  fs.mkdirSync(out,{recursive:true});
  const baseURL=process.env.BASE_URL||'http://127.0.0.1:8000';
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({baseURL,viewport:{width:1440,height:1000}});
  const errors=[],checks=[];
  page.on('pageerror',e=>errors.push(e.message));
  try{
    await page.goto(baseURL);
    await page.getByRole('heading',{name:'校园软件实践赛',exact:true}).waitFor();
    assert.doesNotMatch(await page.locator('body').innerText(),/演示|虚构|待补充/);
    for(const name of await page.locator('article.card h3').allTextContents())assert.doesNotMatch(name,/待审核|已通过|待补充|演示/);
    await page.screenshot({path:path.join(out,'现有竞赛名称.png'),fullPage:true});
    checks.push('现用验收库的六项竞赛名称及简介已清理');
    await page.locator('#account [data-action="login"]').click();
    assert.doesNotMatch(await page.locator('dialog').innerText(),/演示|虚构/);
    await page.locator('[data-action="account-fill"][data-user="zhou"]').click();
    await page.locator('#auth-form [type="submit"]').click();
    await page.locator('dialog').waitFor({state:'hidden'});
    await page.locator('[data-page="registrations"]').click();
    await page.locator('.registration-status').first().waitFor();
    const expected=[['星火开发队','报名待审核'],['青禾创作队','需要修改报名'],['远航实践队','报名已通过']];
    for(const [name,status] of expected){
      const card=page.locator('article.card').filter({has:page.getByRole('heading',{name,exact:true})});
      assert.equal(await card.locator('h3').innerText(),name);
      assert.match(await card.locator('.registration-status').innerText(),new RegExp(status));
      assert.equal(await card.locator('h3 .status').count(),0);
    }
    assert.doesNotMatch(await page.locator('body').innerText(),/演示|虚构|待补充/);
    const rejected=page.locator('article.card').filter({has:page.getByRole('heading',{name:'青禾创作队',exact:true})});
    assert.match(await rejected.innerText(),/修改原因：请补充作品范围说明/);
    const guide=await page.locator('.status-guide').innerText();
    for(const text of ['等待管理员处理','需要队长按修改原因','报名审核已完成'])assert.ok(guide.includes(text));
    checks.push('现有三支队伍名称稳定，三种报名状态及含义独立展示');
    for(const status of ['pending','rejected','approved']){
      await page.getByRole('combobox',{name:'报名审核状态',exact:true}).selectOption(status);
      assert.equal(await page.locator('article.card').count(),1);
      assert.match(await page.locator('.registration-status .status').innerText(),new RegExp(expected[{pending:0,rejected:1,approved:2}[status]][1]));
    }
    await page.getByRole('combobox',{name:'报名审核状态',exact:true}).selectOption('');
    checks.push('三种状态筛选均返回对应的现有记录');
    for(const summary of await page.locator('details.history > summary').all())await summary.click();
    assert.doesNotMatch(await page.locator('#content').innerText(),/演示|虚构|待补充/);
    assert.equal(await page.locator('details.history > ol > li').count(),7);
    checks.push('七条原有提交审核事件保留，历史固定文案已清理');
    for(const summary of await page.locator('details.history > summary').all())await summary.click();
    await page.waitForFunction(()=>!document.querySelector('#toast').classList.contains('visible'));
    await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
    await page.screenshot({path:path.join(out,'现有报名状态说明.png'),fullPage:true});
    await rejected.getByRole('button',{name:'修改并重新提交'}).click();
    assert.match(await page.locator('dialog').innerText(),/修改原因：请补充作品范围说明/);
    await page.getByRole('button',{name:'关闭',exact:true}).click();
    checks.push('已有需修改报名打开后可见具体原因，未提交任何修改');
    const exported=await (await page.request.get('/api/registrations/export')).json();
    for(const [,label] of expected)assert.ok(exported.content.includes(label));
    assert.doesNotMatch(exported.content,/演示|虚构|待补充/);
    checks.push('当前后端导出的名称和三种状态文案与页面一致');
    await page.setViewportSize({width:390,height:844});
    await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:path.join(out,'手机报名状态说明.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    checks.push('390像素报名说明无横向溢出且无脚本错误');
    const report={executed_at:new Date().toISOString(),successful:true,baseURL,checks};
    fs.writeFileSync(path.join(out,'content-browser-results.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report,null,2));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
