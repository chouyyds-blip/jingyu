/* 可选开发验证：需要 Playwright 和 Edge，业务运行不依赖它们。使用独立验收库。 */
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async()=>{
  const out=path.resolve(__dirname,'../output/acceptance');fs.mkdirSync(out,{recursive:true});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({baseURL:process.env.BASE_URL||'http://127.0.0.1:8010',viewport:{width:1440,height:1000},timezoneId:'Asia/Shanghai'});
  const errors=[], checks=[];page.on('pageerror',err=>errors.push(err.message));
  async function close(){if(await page.locator('dialog').isVisible())await page.getByRole('button',{name:'关闭',exact:true}).click();}
  async function login(user){
    await close();
    if(await page.locator('#account').getByRole('button',{name:'退出'}).count())await page.locator('#account').getByRole('button',{name:'退出'}).click();
    await page.locator('#account').getByRole('button',{name:'登录',exact:true}).click();
    await page.locator(`[data-action="account-fill"][data-user="${user}"]`).click();
    await page.locator('#auth-form').getByRole('button',{name:'登录',exact:true}).click();
    await page.locator('dialog').waitFor({state:'hidden'});
    await page.waitForFunction(user=>document.querySelector('#account').innerText.includes(user),user);
    assert.match(await page.locator('#account').innerText(),new RegExp(user));
  }
  async function nav(name){await close();const key={'发现竞赛':'competitions','队伍与招募':'teams','报名记录':'registrations','个人资料':'profile'}[name];await page.locator(`[data-page="${key}"]`).click();await page.locator(`[data-page="${key}"][aria-current="page"]`).waitFor();}
  async function openTeam(name){await nav('队伍与招募');await page.locator('article.card').filter({has:page.getByRole('heading',{name,exact:true})}).getByRole('button',{name:'队伍详情 ↗'}).click();}
  async function apply(){await page.getByRole('button',{name:'申请加入',exact:true}).click();await page.locator('#apply-form textarea').fill('浏览器实际验证申请');await page.getByRole('button',{name:'发送申请'}).click();await page.locator('dialog').waitFor({state:'hidden'});}
  try{
    await page.goto(process.env.BASE_URL||'http://127.0.0.1:8010');
    await page.getByRole('heading',{name:'发现竞赛',exact:true}).waitFor();
    const forbidden=/演示|虚构|待补充/;
    assert.doesNotMatch(await page.locator('body').innerText(),forbidden);
    for(const title of await page.locator('article.card h3').allTextContents())assert.doesNotMatch(title,/待审核|已通过|待补充|演示/);
    checks.push('初始化竞赛标题自然且页面无测试文案');
    await page.getByLabel('按竞赛名称搜索').fill('不存在的关键词');
    await page.getByText('暂无符合条件的竞赛').waitFor();
    await page.getByLabel('按竞赛名称搜索').fill('');checks.push('访客搜索和空状态');
    await login('admin');
    await page.getByRole('button',{name:'发布竞赛',exact:false}).click();
    const suffix=Date.now(),title=`浏览器验收赛 ${suffix}`,team=`浏览器验证队 ${suffix}`;
    await page.getByLabel('竞赛名称',{exact:true}).fill(title);
    await page.locator('dialog').getByLabel('竞赛分类',{exact:true}).fill('软件开发');
    await page.getByLabel('竞赛简介',{exact:true}).fill('来自真实浏览器操作的虚构竞赛');
    await page.getByLabel('报名截止时间',{exact:true}).fill('2099-12-31T23:59');
    await page.getByLabel('最少人数',{exact:true}).fill('3');
    await page.getByLabel('最多人数',{exact:true}).fill('3');
    await page.getByRole('button',{name:'保存竞赛'}).click();await page.locator('dialog').waitFor({state:'hidden'});
    const created=(await (await page.request.get('/api/competitions')).json()).competitions.find(c=>c.title===title);
    for(const [raw,expected] of [['2099-12-31T10:00:23+00:00','2099-12-31T18:00'],['2099-12-31','2099-12-31T23:59']]){
      assert.ok((await page.request.put(`/api/competitions/${created.id}`,{data:{deadline:raw}})).ok());await nav('发现竞赛');
      await page.locator('article.card').filter({has:page.getByRole('heading',{name:title,exact:true})}).getByRole('button',{name:'编辑',exact:true}).click();
      assert.equal(await page.locator('#competition-form [name="deadline"]').inputValue(),expected);
      await page.getByLabel('竞赛简介',{exact:true}).fill('仅修改简介不改变原始截止时间');await page.getByRole('button',{name:'保存竞赛'}).click();await page.locator('dialog').waitFor({state:'hidden'});
      assert.equal((await (await page.request.get(`/api/competitions/${created.id}`)).json()).competition.deadline,raw);
    }
    checks.push('带时区和日期型截止正确显示且未修改时原值保留');
    await login('zhou');await nav('发现竞赛');
    await page.locator('article.card').filter({has:page.getByRole('heading',{name:title,exact:true})}).getByRole('button',{name:'查看详情 ↗'}).click();
    await page.getByRole('button',{name:'为此竞赛创建队伍'}).click();
    await page.getByLabel('队伍名称',{exact:true}).fill(team);
    await page.getByLabel('队伍介绍',{exact:true}).fill('用户竞赛、队伍招募、报名审核三个分工');
    await page.locator('#team-form').getByRole('button',{name:'创建队伍',exact:true}).click();await page.locator('dialog').waitFor({state:'hidden'});
    await login('wang');await openTeam(team);await apply();
    await openTeam(team);await page.getByRole('button',{name:'撤回入队申请'}).click();await page.getByRole('button',{name:'确认撤回申请'}).click();await page.locator('dialog').waitFor({state:'hidden'});
    await openTeam(team);await apply();checks.push('王申请与撤回后重申');
    await login('zhou');await openTeam(team);await page.getByRole('button',{name:'同意',exact:true}).click();
    await page.getByRole('button',{name:'移除成员 王',exact:true}).click();await page.getByRole('button',{name:'确认移除成员'}).click();await page.getByText('成员已移除',{exact:true}).waitFor();
    await login('wang');await openTeam(team);await apply();
    await login('zhou');await openTeam(team);await page.getByRole('button',{name:'同意',exact:true}).click();await page.getByText('申请已处理',{exact:true}).waitFor();
    await login('wang');await openTeam(team);await page.getByRole('button',{name:'退出队伍',exact:true}).click();await page.getByRole('button',{name:'确认退出队伍'}).click();await page.locator('dialog').waitFor({state:'hidden'});
    await openTeam(team);await apply();
    await login('chen');await openTeam(team);await apply();
    await login('zhou');await openTeam(team);
    while(await page.getByRole('button',{name:'同意',exact:true}).count()){await page.getByRole('button',{name:'同意',exact:true}).first().click();await page.waitForFunction(()=>!document.querySelector('[data-action="application-review"][disabled]'));}
    await page.screenshot({path:path.join(out,'队伍与成员.png'),fullPage:true});
    await page.getByRole('button',{name:'提交报名',exact:true}).click();
    await page.getByLabel('联系电话',{exact:true}).fill('13800000000');
    await page.getByLabel('参赛说明',{exact:true}).fill('浏览器完整流程第一版');
    await page.getByRole('button',{name:'确认提交'}).click();await page.locator('dialog').waitFor({state:'hidden'});
    checks.push('退出与移除、重新入队、三人组队报名');
    await login('admin');await nav('报名记录');
    let card=page.locator('article.card').filter({has:page.getByRole('heading',{name:team,exact:true})});
    for(const text of ['报名待审核','需要修改报名','报名已通过'])assert.match(await page.locator('.status-guide').innerText(),new RegExp(text));
    assert.match(await card.locator('.registration-status').innerText(),/报名待审核[\s\S]*等待管理员处理/);
    assert.equal(await card.locator('h3').innerText(),team);
    checks.push('报名状态和含义独立显示，队伍标题不随状态变化');
    await card.getByRole('button',{name:'要求修改',exact:true}).click();
    await page.getByLabel('修改原因（必填）',{exact:true}).fill('请补充作品范围');await page.getByRole('button',{name:'确认要求修改'}).click();await page.locator('dialog').waitFor({state:'hidden'});
    await login('zhou');await nav('报名记录');
    card=page.locator('article.card').filter({has:page.getByRole('heading',{name:team,exact:true})});
    assert.match(await card.locator('.registration-status').innerText(),/需要修改报名/);
    assert.match(await card.innerText(),/修改原因：请补充作品范围/);
    await card.getByRole('button',{name:'修改并重新提交'}).click();
    assert.match(await page.locator('#modal-body').innerText(),/修改原因：请补充作品范围/);
    checks.push('要求修改后显示原因及重提说明');
    await page.getByLabel('参赛说明',{exact:true}).fill('补充作品范围：六个业务模块');await page.getByRole('button',{name:'确认提交'}).click();await page.locator('dialog').waitFor({state:'hidden'});
    await login('admin');await nav('报名记录');
    card=page.locator('article.card').filter({has:page.getByRole('heading',{name:team,exact:true})});await card.getByRole('button',{name:'通过',exact:true}).click();await page.getByRole('button',{name:'确认通过'}).click();await page.locator('dialog').waitFor({state:'hidden'});
    await card.locator('summary').first().click();assert.match(await card.innerText(),/提交和审核历史（4 条）/);
    await page.screenshot({path:path.join(out,'报名审核历史.png'),fullPage:true});checks.push('驳回重提通过与四条历史');
    const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'导出可见报名 CSV'}).click();const download=await downloadPromise;await download.saveAs(path.join(out,'ui-export.csv'));assert.ok(fs.readFileSync(path.join(out,'ui-export.csv'),'utf8').includes(team));checks.push('授权CSV下载');
    await nav('发现竞赛');
    await page.locator('article.card').filter({has:page.getByRole('heading',{name:title,exact:true})}).getByRole('button',{name:'编辑',exact:true}).click();
    for(const name of ['deadline','min_members','max_members'])assert.equal(await page.locator(`#competition-form [name="${name}"]`).isDisabled(),true);
    await page.getByLabel('竞赛简介',{exact:true}).fill('已有报名后仍可修改简介，资格规则保持锁定');await page.getByRole('button',{name:'保存竞赛'}).click();await page.locator('dialog').waitFor({state:'hidden'});checks.push('已有报名冻结资格字段且简介可保存');
    const closedTitle=`下架撤回测试 ${suffix}`,closedTeam=`下架待审队 ${suffix}`;
    const closedCompetition=await (await page.request.post('/api/competitions',{data:{title:closedTitle,category:'软件开发',description:'验证下架待审入口',deadline:'2099-12-31',min_members:1,max_members:3}})).json();
    await login('zhou');await page.request.post('/api/teams',{data:{competition_id:closedCompetition.competition.id,name:closedTeam}});
    await login('wang');await openTeam(closedTeam);await apply();
    await login('admin');assert.ok((await page.request.put(`/api/competitions/${closedCompetition.competition.id}`,{data:{active:0}})).ok());
    await login('wang');await openTeam(closedTeam);await page.getByRole('button',{name:'撤回入队申请'}).click();await page.getByRole('button',{name:'确认撤回申请'}).click();await page.locator('dialog').waitFor({state:'hidden'});await nav('队伍与招募');assert.equal(await page.getByRole('heading',{name:closedTeam,exact:true}).count(),0);checks.push('下架待审队伍保留撤回入口且撤回后隐藏');
    await login('chen');await nav('报名记录');card=page.locator('article.card').filter({has:page.getByRole('heading',{name:team,exact:true})});assert.match(await card.innerText(),/已通过/);assert.equal(await card.getByRole('button',{name:'通过',exact:true}).count(),0);checks.push('队员查看结果无审核入口');
    await nav('个人资料');await page.getByRole('button',{name:'修改密码',exact:true}).click();await page.getByLabel('当前密码',{exact:true}).fill('wrong-password');await page.getByLabel('新密码',{exact:true}).fill('Unchanged123');await page.getByRole('button',{name:'保存新密码'}).click();await page.locator('#password-form .error').filter({hasText:'原密码不正确'}).waitFor();await close();checks.push('改密错误在表单内提示');
    await nav('发现竞赛');await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'手机竞赛列表.png'),fullPage:true});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);checks.push('390像素页面无横向滚动');
    await page.keyboard.press('Control+Home');await page.keyboard.press('Tab');assert.ok(await page.locator(':focus').count());checks.push('键盘焦点可达');
    await page.emulateMedia({forcedColors:'active',reducedMotion:'reduce'});await page.screenshot({path:path.join(out,'高对比度页面.png')});checks.push('系统高对比度及减少动画模式可渲染');
    assert.deepEqual(errors,[]);checks.push('无JavaScript未捕获错误');
    fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({executed_at:new Date().toISOString(),browser:await browser.version(),successful:true,checks},null,2));
    console.log(JSON.stringify({successful:true,checks},null,2));
  }catch(error){await page.screenshot({path:path.join(out,'browser-failure.png'),fullPage:true});fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({successful:false,checks,errors,error:String(error)},null,2));throw error;}
  finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
