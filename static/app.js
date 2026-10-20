'use strict';
const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {user:null,page:'competitions',competitions:[],teams:[],registrations:[],query:'',category:'',teamFilter:''};
const labels = {pending:'待审核',approved:'已通过',rejected:'已驳回'};
const badge = status => `<span class="status ${esc(status)}">${esc(labels[status] || status)}</span>`;
const admin = () => state.user?.role === 'admin';
let toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3500);}
async function api(path,method='GET',body){
  const res=await fetch('/api'+path,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
  const result=await res.json();if(!res.ok)throw new Error(result.error || '请求失败');return result;
}
function showModal(title,html){$('#modal-title').textContent=title;$('#modal-body').innerHTML=html;if(!$('#modal').open)$('#modal').showModal();}
$('#close-modal').onclick=()=>$('#modal').close();
$('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const r=$('#modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('#modal').close();}});
const field=(name,label,value='',type='text',extra='')=>`<label class="field">${esc(label)}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;
const area=(name,label,value='',extra='')=>`<label class="field">${esc(label)}<textarea name="${name}" ${extra}>${esc(value)}</textarea></label>`;
const formEnd=(text='保存')=>`<div class="error" role="alert"></div><div class="form-actions"><button type="button" class="btn" data-action="close">取消</button><button class="btn primary" type="submit">${text}</button></div></form>`;
function bindForm(id,callback){
  $(id).onsubmit=async e=>{e.preventDefault();const form=e.target;const btn=form.querySelector('[type=submit]');btn.disabled=true;form.querySelector('.error').textContent='';try{await callback(Object.fromEntries(new FormData(form)));}catch(err){form.querySelector('.error').textContent=err.message;}finally{btn.disabled=false;}};
}
function account(){
 $('#account').innerHTML=state.user?`<span class="avatar">${esc(state.user.name.slice(0,1))}</span><div><strong>${esc(state.user.name)}</strong><small>${admin()?'管理员':'学生'} · ${esc(state.user.username)}</small></div><button class="link" data-action="logout">退出</button>`:`<span class="avatar">访</span><div><strong>访客</strong><small>登录后组队报名</small></div><button class="link" data-action="login">登录</button>`;
}
function requireLogin(){if(state.user)return true;login();return false;}
function heading(title,subtitle,button=''){$('#page-heading').innerHTML=`<div><h2>${title}</h2><p>${subtitle}</p></div>${button}`;}
function empty(title,description){return `<div class="empty"><strong>${title}</strong>${description}</div>`;}
function render(){
 document.querySelectorAll('[data-page]').forEach(el=>el.classList.toggle('active',el.dataset.page===state.page));account();
 if(state.page==='competitions')renderCompetitions();
 if(state.page==='teams')renderTeams();
 if(state.page==='registrations')renderRegistrations();
 if(state.page==='profile')renderProfile();
}
async function refresh(){
 const [c,t]=await Promise.all([api('/competitions'),api('/teams')]);state.competitions=c.competitions;state.teams=t.teams;
 state.registrations=state.user?(await api('/registrations')).registrations:[];render();
}
function renderCompetitions(){
 heading('发现竞赛','找到感兴趣的方向，开启你的下一次挑战。',admin()?'<button class="btn primary" data-action="competition-new">＋ 发布竞赛</button>':'');
 const categories=[...new Set(state.competitions.map(c=>c.category))];
 const list=state.competitions.filter(c=>(!state.query||c.title.toLowerCase().includes(state.query.toLowerCase()))&&(!state.category||c.category===state.category));
 $('#content').innerHTML=`<div class="toolbar"><input id="search" aria-label="按竞赛名称搜索" placeholder="搜索竞赛名称…" value="${esc(state.query)}"><select id="category" aria-label="竞赛分类"><option value="">全部分类</option>${categories.map(c=>`<option ${state.category===c?'selected':''}>${esc(c)}</option>`).join('')}</select><span class="form-note">共 ${list.length} 项竞赛</span></div>`+(list.length?`<div class="grid">${list.map(c=>`<article class="card"><div class="card-top"><span class="tag">${esc(c.category)}</span>${!c.active?'<span class="status inactive">已下架</span>':'<span class="form-note">课程演示</span>'}</div><h3>${esc(c.title)}</h3><p class="description">${esc(c.description.slice(0,85))}</p><div class="meta"><span>◷ 截止 ${esc(c.deadline.replace('T',' '))}</span><span>♧ ${c.min_members}–${c.max_members} 人 / 队</span></div><div class="card-bottom"><span>${state.teams.filter(t=>t.competition_id===c.id).length} 支队伍正在集结</span><div class="actions">${admin()?`<button class="link" data-action="competition-edit" data-id="${c.id}">编辑</button>`:''}<button class="btn small" data-action="competition-detail" data-id="${c.id}">查看详情 ↗</button></div></div></article>`).join('')}</div>`:empty('暂无符合条件的竞赛','试试其他关键词或分类。'));
 $('#search').oninput=e=>{const start=e.target.selectionStart;state.query=e.target.value;renderCompetitions();$('#search').focus();$('#search').setSelectionRange(start,start);};$('#category').onchange=e=>{state.category=e.target.value;renderCompetitions();};
}
function competitionDetail(id){const c=state.competitions.find(x=>x.id===id);showModal(c.title,`<span class="tag">${esc(c.category)}</span><p class="detail-text">${esc(c.description)}</p><div class="meta"><span>截止：${esc(c.deadline.replace('T',' '))}</span><span>人数：${c.min_members}–${c.max_members} 人</span></div>${c.official_url?`<p><a href="${esc(c.official_url)}" target="_blank" rel="noopener noreferrer">访问竞赛官网 ↗</a></p>`:''}<div class="hint">本系统仅提供内部组队与报名登记，实际参赛要求以主办方通知为准。</div><div class="actions"><button class="btn" data-action="find-team" data-id="${id}">查看相关队伍</button>${c.active?`<button class="btn primary" data-action="team-new" data-id="${id}">为此竞赛创建队伍</button>`:''}</div>`);}
function competitionForm(id){
 const c=state.competitions.find(x=>x.id===id)||{min_members:1,max_members:3,active:1};
 showModal(id?'编辑竞赛':'发布竞赛',`<form id="competition-form">${field('title','竞赛名称',c.title,'text','required maxlength="100"')}${field('category','竞赛分类',c.category,'text','required maxlength="30"')}${area('description','竞赛简介',c.description,'required maxlength="3000"')}${field('deadline','报名截止时间',c.deadline?.slice(0,16),'datetime-local','required')}<div class="form-grid">${field('min_members','最少人数',c.min_members,'number','required min="1" max="20"')}${field('max_members','最多人数',c.max_members,'number','required min="1" max="20"')}</div>${field('official_url','官网链接（选填）',c.official_url,'url')}<label class="field">发布状态<select name="active"><option value="1" ${c.active?'selected':''}>上架</option><option value="0" ${!c.active?'selected':''}>下架</option></select></label>${formEnd('保存竞赛')}`);
 bindForm('#competition-form',async data=>{data.min_members=Number(data.min_members);data.max_members=Number(data.max_members);data.active=Number(data.active);await api('/competitions'+(id?'/'+id:''),id?'PUT':'POST',data);$('#modal').close();await refresh();toast('竞赛信息已保存');});
}
function login(register=false){
 showModal(register?'创建学生账号':'欢迎回到竞遇',`<form id="auth-form">${field('username','用户名','','text','required minlength="3" maxlength="30" autocomplete="username"')}${register?field('name','姓名','','text','required maxlength="30"'):''}${field('password','密码','','password',`required minlength="8" maxlength="128" autocomplete="${register?'new-password':'current-password'}"`)}<div class="form-note">${register?'用户名使用字母、数字或下划线；密码至少 8 位。':'使用演示账号体验完整业务流程。'}</div><div class="error" role="alert"></div><div class="form-actions"><button type="button" class="btn" data-action="${register?'login':'register'}">${register?'已有账号':'注册账号'}</button><button class="btn primary" type="submit">${register?'注册并登录':'登录'}</button></div></form>${register?'':`<div class="demo-accounts">演示密码均为 <strong>Demo123456</strong><br>${['zhou','wang','chen','admin'].map(u=>`<button class="btn small" data-action="demo-fill" data-user="${u}">${({zhou:'周',wang:'王',chen:'陈',admin:'管理员'})[u]}</button>`).join('')}<p class="form-note">点击填入账号，然后登录；这些账号只用于本地演示。</p></div>`}`);
 bindForm('#auth-form',async data=>{const result=await api(register?'/register':'/login','POST',data);state.user=result.user|| (await api('/me')).user;$('#modal').close();await refresh();toast(register?'注册成功':'登录成功');});
}
function renderTeams(){
 heading('队伍与招募','找到志同道合的伙伴，让参赛从一个人变成一群人。','<button class="btn primary" data-action="team-new">＋ 创建队伍</button>');
 const list=state.teams.filter(t=>!state.teamFilter||String(t.competition_id)===state.teamFilter);
 $('#content').innerHTML=`<div class="hint">每人每项竞赛最多加入一支队伍。报名提交后成员锁定；所有申请由队长处理。</div><div class="toolbar"><select id="team-filter" aria-label="按竞赛筛选队伍"><option value="">全部竞赛</option>${state.competitions.map(c=>`<option value="${c.id}" ${String(c.id)===state.teamFilter?'selected':''}>${esc(c.title)}</option>`).join('')}</select><span class="form-note">共 ${list.length} 支队伍</span></div>`+(list.length?`<div class="grid">${list.map(t=>`<article class="card"><div class="card-top"><span class="tag">${esc(t.competition_title)}</span>${t.captain_id===state.user?.id?'<span class="badge">我是队长</span>':t.is_member?'<span class="badge">我已加入</span>':''}</div><h3>${esc(t.name)}</h3><p>${esc(t.intro||'一起把想法变成作品。')}</p><p>招募：${esc(t.requirements||'欢迎感兴趣的同学加入')}</p><div class="meta"><span>队长 ${esc(t.captain_name)}</span><span>${t.member_count} / ${t.max_members} 人</span>${t.registration_status?badge(t.registration_status):''}</div>${t.my_application&&!t.is_member?`<p>我的入队申请：${badge(t.my_application.status)}</p>`:''}<div class="card-bottom"><span>${(t.members||[]).map(m=>esc(m.name)).join(' · ')}</span><button class="btn small" data-action="team-detail" data-id="${t.id}">队伍详情 ↗</button></div></article>`).join('')}</div>`:empty('暂无符合条件的队伍','切换竞赛，或点击“创建队伍”发起协作。'));
 $('#team-filter').onchange=e=>{state.teamFilter=e.target.value;renderTeams();};
}
function teamForm(competitionId,id){
 if(!requireLogin())return;const t=state.teams.find(x=>x.id===id)||{};const cs=state.competitions.filter(c=>c.active);
 if(!id&&!cs.length){toast('暂无可创建队伍的竞赛');return;}
 showModal(id?'编辑队伍':'创建一支新队伍',`<form id="team-form">${id?'':`<label class="field">选择竞赛<select name="competition_id" required>${cs.map(c=>`<option value="${c.id}" ${competitionId===c.id?'selected':''}>${esc(c.title)}</option>`).join('')}</select></label>`}${field('name','队伍名称',t.name,'text','required maxlength="50"')}${area('intro','队伍介绍',t.intro,'maxlength="1000"')}${area('requirements','招募要求',t.requirements,'maxlength="500"')}${formEnd(id?'保存修改':'创建队伍')}`);
 bindForm('#team-form',async data=>{if(data.competition_id)data.competition_id=Number(data.competition_id);await api('/teams'+(id?'/'+id:''),id?'PUT':'POST',data);$('#modal').close();state.page='teams';await refresh();toast('队伍已保存');});
}
function teamDetail(id){
 const t=state.teams.find(x=>x.id===id);const captain=t.captain_id===state.user?.id;
 showModal(t.name,`<span class="tag">${esc(t.competition_title)}</span><p class="detail-text">${esc(t.intro)}</p><h3 class="section-title">招募要求</h3><p class="detail-text">${esc(t.requirements||'欢迎感兴趣的同学加入')}</p><h3 class="section-title">队伍成员</h3><div class="members">${(t.members||[]).map(m=>`<span class="member">${esc(m.name)}${m.id===t.captain_id?' · 队长':''}</span>`).join('')}</div>${captain?`<h3 class="section-title">入队申请</h3>${(t.applications||[]).length?(t.applications||[]).map(a=>`<div class="row"><div><strong>${esc(a.name||a.user_name)}</strong><p>${esc(a.message||'希望加入队伍')}</p>${badge(a.status)}</div>${a.status==='pending'?`<div class="actions"><button class="btn small primary" data-action="application-review" data-id="${a.id}" data-status="approved" data-team="${id}">同意</button><button class="btn small" data-action="application-review" data-id="${a.id}" data-status="rejected" data-team="${id}">拒绝</button></div>`:''}</div>`).join(''):'<p class="form-note">暂无申请</p>'}`:''}<div class="form-actions">${captain?`${!t.registration_status?`<button class="btn danger" data-action="team-delete" data-id="${id}">解散队伍</button><button class="btn" data-action="team-edit" data-id="${id}">编辑</button>`:''}<button class="btn primary" data-action="registration-new" data-id="${id}">${t.registration_status?'查看报名':'提交报名'}</button>`:!t.is_member?`<button class="btn primary" data-action="apply" data-id="${id}" ${t.registration_status?'disabled':''}>申请加入</button>`:'<span class="form-note">你已是队伍成员，由队长统一提交报名。</span>'}</div>`);
}
function applyForm(id){if(!requireLogin())return;showModal('申请加入队伍',`<form id="apply-form">${area('message','向队长介绍一下自己','','required maxlength="500"')}<p class="form-note">可以介绍你的专业、技能和希望承担的工作。</p>${formEnd('发送申请')}`);bindForm('#apply-form',async data=>{await api(`/teams/${id}/apply`,'POST',data);$('#modal').close();await refresh();toast('申请已发送，等待队长处理');});}
function renderRegistrations(){
 heading(admin()?'报名审核':'报名记录',admin()?'核对参赛信息，处理队伍报名。':'查看所在队伍的报名信息和处理结果。');
 if(!state.user){$('#content').innerHTML=empty('登录后查看报名记录','<button class="btn primary" data-action="login">立即登录</button>');return;}
 $('#content').innerHTML=`<div class="hint">${admin()?'驳回时请填写原因，队长可在截止前修改后重新提交。':'由队长统一提交报名，队员共享审核结果。报名为系统内登记。'}</div>`+(state.registrations.length?`<div class="grid">${state.registrations.map(r=>`<article class="card"><div class="card-top"><span class="tag">${esc(r.competition_title)}</span>${badge(r.status)}</div><h3>${esc(r.team_name)}</h3><p>联系人：${esc(r.contact_name)} · ${esc(r.contact_phone)}</p><p>队员：${(r.members||[]).map(m=>esc(m.name)).join('、')}</p><p class="detail-text">参赛说明：${esc(r.statement||'无')}</p>${r.review_note?`<div class="hint">审核意见：${esc(r.review_note)}</div>`:''}<div class="card-bottom"><span>报名编号 #${r.id}</span><div class="actions">${admin()&&r.status==='pending'?`<button class="btn small" data-action="registration-review" data-id="${r.id}" data-status="rejected">驳回</button><button class="btn small primary" data-action="registration-review" data-id="${r.id}" data-status="approved">通过</button>`:r.captain_id===state.user.id&&r.status==='rejected'?`<button class="btn small primary" data-action="registration-new" data-id="${r.team_id}">修改并重新提交</button>`:''}</div></div></article>`).join('')}</div>`:empty('暂无报名记录',admin()?'队长提交报名后，会显示在这里。':'先创建或加入队伍，再由队长在队伍详情提交报名。'));
}
function registrationForm(teamId){
 if(!requireLogin())return;const r=state.registrations.find(x=>x.team_id===teamId);if(r&&r.status!=='rejected'){$('#modal').close();state.page='registrations';render();return;}
 const t=state.teams.find(x=>x.id===teamId);showModal(r?'修改报名信息':'提交队伍报名',`<div class="hint">${esc(t?.name)} · ${(t?.members||[]).map(m=>esc(m.name)).join('、')}<br>提交后队伍成员将锁定，请核对名单。</div><form id="registration-form">${field('contact_name','联系人',r?.contact_name||state.user.name,'text','required maxlength="30"')}${field('contact_phone','联系电话',r?.contact_phone,'tel','required maxlength="30"')}${area('statement','参赛说明',r?.statement,'required maxlength="2000"')}<p class="form-note">本阶段使用文字表单，不上传附件。</p>${formEnd('确认提交')}`);
 bindForm('#registration-form',async data=>{await api('/registrations','POST',{...data,team_id:teamId});$('#modal').close();state.page='registrations';await refresh();toast('报名已提交，等待管理员审核');});
}
function reviewForm(id,status){showModal(status==='approved'?'通过报名':'驳回报名',`<form id="review-form">${area('review_note',status==='rejected'?'驳回原因（必填）':'审核意见（选填）','',`${status==='rejected'?'required':''} maxlength="1000"`)}${formEnd('确认'+(status==='approved'?'通过':'驳回'))}`);bindForm('#review-form',async data=>{await api(`/registrations/${id}/review`,'POST',{...data,status});$('#modal').close();await refresh();toast('审核结果已保存');});}
function renderProfile(){heading('个人资料','让队友更了解你，从一份简单的自我介绍开始。');if(!state.user){$('#content').innerHTML=empty('请先登录','<button class="btn primary" data-action="login">立即登录</button>');return;}
 const u=state.user;$('#content').innerHTML=`<div class="panel profile"><form id="profile-form">${field('name','姓名',u.name,'text','required maxlength="30"')}<div class="form-grid">${field('major','专业',u.major,'text','maxlength="60"')}${field('grade','年级',u.grade,'text','maxlength="30"')}</div>${area('skills','技能与个人简介',u.skills,'maxlength="500"')}<div class="error" role="alert"></div><button class="btn primary" type="submit">保存资料</button></form></div>`;bindForm('#profile-form',async data=>{await api('/profile','PUT',data);state.user=(await api('/me')).user;await refresh();toast('个人资料已更新');});
}
document.addEventListener('click',async e=>{
 const nav=e.target.closest('[data-page]');if(nav){state.page=nav.dataset.page;try{await refresh();}catch(err){toast(err.message);}return;}
 const el=e.target.closest('[data-action]');if(!el)return;const a=el.dataset.action,id=Number(el.dataset.id);
 try{
 if(a==='close')$('#modal').close();
 if(a==='login')login();if(a==='register')login(true);
 if(a==='demo-fill'){$('#auth-form [name=username]').value=el.dataset.user;$('#auth-form [name=password]').value='Demo123456';}
 if(a==='logout'){await api('/logout','POST',{});state.user=null;await refresh();toast('已退出登录');}
 if(a==='competition-detail')competitionDetail(id);
 if(a==='competition-new')competitionForm();if(a==='competition-edit')competitionForm(id);
 if(a==='find-team'){$('#modal').close();state.teamFilter=String(id);state.page='teams';render();}
 if(a==='team-new')teamForm(id);if(a==='team-edit')teamForm(null,id);
 if(a==='team-detail')teamDetail(id);if(a==='apply')applyForm(id);
 if(a==='application-review'){el.disabled=true;await api(`/applications/${id}/review`,'POST',{status:el.dataset.status});await refresh();teamDetail(Number(el.dataset.team));toast('申请已处理');}
 if(a==='team-delete'){showModal('确认解散队伍',`<p>解散后队伍及其入队申请将被删除。是否继续？</p><div class="form-actions"><button class="btn" data-action="close">取消</button><button class="btn danger" data-action="team-delete-confirm" data-id="${id}">确认解散</button></div>`);}
 if(a==='team-delete-confirm'){await api(`/teams/${id}`,'DELETE');$('#modal').close();await refresh();toast('队伍已解散');}
 if(a==='registration-new')registrationForm(id);
 if(a==='registration-review')reviewForm(id,el.dataset.status);
 }catch(err){toast(err.message);}finally{el.disabled=false;}
});
(async()=>{try{state.user=(await api('/me')).user;await refresh();}catch(err){$('#content').innerHTML=empty('暂时无法连接服务',esc(err.message)+'，请确认服务器已启动，然后刷新页面。');}})();
