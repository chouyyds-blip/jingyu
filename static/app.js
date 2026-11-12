'use strict';
const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {user:null,page:'competitions',competitions:[],teams:[],registrations:[],query:'',category:'',teamFilter:'',onlyMine:false,registrationStatus:''};
const labels = {pending:'待审核',approved:'已通过',rejected:'已驳回'};
const registrationLabels = {pending:'报名待审核',rejected:'需要修改报名',approved:'报名已通过'};
const registrationDescriptions = {pending:'已提交报名，等待管理员处理。',rejected:'管理员指出了问题，需要队长按修改原因调整报名信息，并在截止前重新提交。',approved:'报名审核已完成。'};
const badge = (status,registration=false) => `<span class="status ${esc(status)}">${esc((registration?registrationLabels:labels)[status] || status)}</span>`;
const admin = () => state.user?.role === 'admin';
function expired(deadline){if(!deadline)return true;const end=new Date(deadline.length===10?deadline+'T23:59:59.999':deadline);return !Number.isFinite(end.getTime())||Date.now()>end.getTime();}
function deadlineInputValue(value){if(!value)return '';if(value.length===10)return value+'T23:59';const date=new Date(value);if(!Number.isFinite(date.getTime()))return '';const pad=n=>String(n).padStart(2,'0');return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;}
const competitionOpen=c=>Boolean(c.active)&&!expired(c.deadline);
const teamOpen=t=>Boolean(t.competition_active)&&!expired(t.deadline)&&!t.registration_status;
const actionLabels={submitted:'首次提交',resubmitted:'修改后重提',approved:'审核通过',rejected:'要求修改报名',migrated:'旧版记录迁入'};
function confirmAction(title,message,action,id,extra=''){showModal(title,`<p>${esc(message)}</p><div class="form-actions"><button class="btn" data-action="close">取消</button><button class="btn danger" data-action="${action}" data-id="${id}" ${extra}>确认${esc(title)}</button></div>`);}

let toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),3500);}
async function api(path,method='GET',body){
  const res=await fetch('/api'+path,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
  const result=await res.json();if(!res.ok)throw new Error(result.error || '请求失败');return result;
}
function showModal(title,html){$('#modal-title').textContent=title;$('#modal-body').innerHTML=html;if(!$('#modal').open)$('#modal').showModal();}
$('#close-modal').onclick=()=>$('#modal').close();
$('#modal').addEventListener('click',e=>{if(e.target===$('#modal')){const r=$('#modal').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('#modal').close();}});
let fieldSequence=0;
const field=(name,label,value='',type='text',extra='')=>{const id='field-'+(++fieldSequence);return `<div class="field"><label for="${id}">${esc(label)}</label><input id="${id}" name="${name}" type="${type}" value="${esc(value)}" ${extra}></div>`;};
const area=(name,label,value='',extra='')=>{const id='field-'+(++fieldSequence);return `<div class="field"><label for="${id}">${esc(label)}</label><textarea id="${id}" name="${name}" ${extra}>${esc(value)}</textarea></div>`;};
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
 document.querySelectorAll('[data-page]').forEach(el=>{el.classList.toggle('active',el.dataset.page===state.page);if(el.dataset.page===state.page)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});account();
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
$('#content').innerHTML=`<div class="toolbar"><input id="search" aria-label="按竞赛名称搜索" placeholder="搜索竞赛名称…" value="${esc(state.query)}"><select id="category" aria-label="竞赛分类"><option value="">全部分类</option>${categories.map(c=>`<option ${state.category===c?'selected':''}>${esc(c)}</option>`).join('')}</select><span class="form-note">共 0 项竞赛</span></div><div id="competition-results"></div>`;
 const search = $('#search');
 function updateQuery() {
  state.query = search.value;
  renderCompetitionResults();
 }
 search.addEventListener('input', event => {
  if (!event.isComposing) updateQuery();
 });
 search.addEventListener('compositionend', updateQuery);
 $('#category').onchange = event => {
  state.category = event.target.value;
  renderCompetitionResults();
 };
 renderCompetitionResults();
}
function renderCompetitionResults(){
 const query = state.query.trim().toLowerCase();
 const list = state.competitions.filter(c =>
  (!query || c.title.toLowerCase().includes(query) || c.category.toLowerCase().includes(query)) &&
  (!state.category || c.category === state.category)
 );
 $('#content .toolbar .form-note').textContent = `共 ${list.length} 项竞赛`;
 $('#competition-results').innerHTML = list.length?`<div class="grid">${list.map(c=>`<article class="card"><div class="card-top"><span class="tag">${esc(c.category)}</span>${!c.active?'<span class="status inactive">已下架</span>':expired(c.deadline)?'<span class="status inactive">已截止</span>':'<span class="status approved">报名开放</span>'}</div><h3>${esc(c.title)}</h3><p class="description">${esc(c.description.slice(0,85))}</p><div class="meta"><span>◷ 截止 ${esc(c.deadline.replace('T',' '))}</span><span>♧ ${c.min_members}–${c.max_members} 人 / 队</span></div><div class="card-bottom"><span>${state.teams.filter(t=>t.competition_id===c.id).length} 支队伍正在集结</span><div class="actions">${admin()?`<button class="link" data-action="competition-edit" data-id="${c.id}">编辑</button>`:''}<button class="btn small" data-action="competition-detail" data-id="${c.id}">查看详情 ↗</button></div></div></article>`).join('')}</div>`:empty('暂无符合条件的竞赛','试试其他关键词或分类。');
}
function competitionDetail(id){const c=state.competitions.find(x=>x.id===id);showModal(c.title,`<span class="tag">${esc(c.category)}</span><p class="detail-text">${esc(c.description)}</p><div class="meta"><span>截止：${esc(c.deadline.replace('T',' '))}</span><span>人数：${c.min_members}–${c.max_members} 人</span></div>${c.official_url?`<p><a href="${esc(c.official_url)}" target="_blank" rel="noopener noreferrer">访问竞赛官网 ↗</a></p>`:''}<div class="hint">本系统仅提供内部组队与报名登记，实际参赛要求以主办方通知为准。</div><div class="actions"><button class="btn" data-action="find-team" data-id="${id}">查看相关队伍</button>${competitionOpen(c)&&!admin()?`<button class="btn primary" data-action="team-new" data-id="${id}">为此竞赛创建队伍</button>`:''}</div>`);}
function competitionForm(id){
 const c=state.competitions.find(x=>x.id===id)||{min_members:1,max_members:3,active:1};
 const frozen=Boolean(id&&state.registrations.some(r=>r.competition_id===id)),initialDeadline=deadlineInputValue(c.deadline);
 showModal(id?'编辑竞赛':'发布竞赛',`${frozen?'<div class="hint">已有队伍报名，人数和截止时间已锁定；可修改名称、简介和发布状态。</div>':''}<form id="competition-form">${field('title','竞赛名称',c.title,'text','required maxlength="100"')}${field('category','竞赛分类',c.category,'text','required maxlength="30"')}${area('description','竞赛简介',c.description,'required maxlength="3000"')}${field('deadline','报名截止时间',initialDeadline,'datetime-local','required')}<div class="form-grid">${field('min_members','最少人数',c.min_members,'number','required min="1" max="20"')}${field('max_members','最多人数',c.max_members,'number','required min="1" max="20"')}</div>${field('official_url','官网链接（选填）',c.official_url,'url')}<label class="field">发布状态<select name="active"><option value="1" ${c.active?'selected':''}>上架</option><option value="0" ${!c.active?'selected':''}>下架</option></select></label>${formEnd('保存竞赛')}`);
 if(frozen)for(const name of ['deadline','min_members','max_members'])$('#competition-form [name='+name+']').disabled=true;
 bindForm('#competition-form',async data=>{if(id&&data.deadline===initialDeadline)delete data.deadline;if(data.min_members!==undefined)data.min_members=Number(data.min_members);if(data.max_members!==undefined)data.max_members=Number(data.max_members);data.active=Number(data.active);await api('/competitions'+(id?'/'+id:''),id?'PUT':'POST',data);$('#modal').close();await refresh();toast('竞赛信息已保存');});
}
function login(register=false){
 showModal(register?'创建学生账号':'欢迎回到竞遇',`<form id="auth-form">${field('username','用户名','','text','required minlength="3" maxlength="30" autocomplete="username"')}${register?field('name','姓名','','text','required maxlength="30"'):''}${field('password','密码','','password',`required minlength="8" maxlength="128" autocomplete="${register?'new-password':'current-password'}"`)}<div class="form-note">${register?'用户名使用字母、数字或下划线；密码至少 8 位。':'输入用户名和密码登录。'}</div><div class="error" role="alert"></div><div class="form-actions"><button type="button" class="btn" data-action="${register?'login':'register'}">${register?'已有账号':'注册账号'}</button><button class="btn primary" type="submit">${register?'注册并登录':'登录'}</button></div></form><p class="form-note">资料用于身份识别和组队展示；姓名、专业、年级和简介会展示给浏览者。联系电话和报名说明仅本队成员与管理员可见。请勿填写身份证等无关敏感信息。</p>${register?'':`<div class="initial-accounts">初始账号密码为 <strong>Demo123456</strong><br>${['zhou','wang','chen','admin'].map(u=>`<button class="btn small" data-action="account-fill" data-user="${u}">${({zhou:'周',wang:'王',chen:'陈',admin:'管理员'})[u]}</button>`).join('')}<p class="form-note">点击填入初始账号；登录后可在个人资料中修改密码。</p></div>`}`);
 bindForm('#auth-form',async data=>{const result=await api(register?'/register':'/login','POST',data);state.user=result.user|| (await api('/me')).user;$('#modal').close();await refresh();toast(register?'注册成功':'登录成功');});
}
function renderTeams(){
 heading('队伍与招募','找到志同道合的伙伴，让参赛从一个人变成一群人。','<button class="btn primary" data-action="team-new">＋ 创建队伍</button>');
 const list=state.teams.filter(t=>(!state.teamFilter||String(t.competition_id)===state.teamFilter)&&(!state.onlyMine||t.is_member));
 $('#content').innerHTML=`<div class="hint">每人每项竞赛最多加入一支队伍。报名提交后成员锁定；所有申请由队长处理。</div><div class="toolbar"><select id="team-filter" aria-label="按竞赛筛选队伍"><option value="">全部竞赛</option>${state.competitions.map(c=>`<option value="${c.id}" ${String(c.id)===state.teamFilter?'selected':''}>${esc(c.title)}</option>`).join('')}</select><label class="check-field"><input type="checkbox" id="only-mine" ${state.onlyMine?'checked':''}>只看我加入的队伍</label><span class="form-note">共 ${list.length} 支队伍</span></div>`+(list.length?`<div class="grid">${list.map(t=>`<article class="card"><div class="card-top"><span class="tag">${esc(t.competition_title)}</span>${t.captain_id===state.user?.id?'<span class="badge">我是队长</span>':t.is_member?'<span class="badge">我已加入</span>':''}</div><h3>${esc(t.name)}</h3><p>${esc(t.intro||'一起把想法变成作品。')}</p><p>招募：${esc(t.requirements||'欢迎感兴趣的同学加入')}</p><div class="meta"><span>队长 ${esc(t.captain_name)}</span><span>${t.member_count} / ${t.max_members} 人</span>${t.registration_status?badge(t.registration_status,true):''}</div>${t.my_application&&!t.is_member?`<p>我的入队申请：${badge(t.my_application.status)}</p>`:''}<div class="card-bottom"><span>${(t.members||[]).map(m=>esc(m.name)).join(' · ')}</span><button class="btn small" data-action="team-detail" data-id="${t.id}">队伍详情 ↗</button></div></article>`).join('')}</div>`:empty('暂无符合条件的队伍','切换竞赛，或点击“创建队伍”发起协作。'));
 $('#team-filter').onchange=e=>{state.teamFilter=e.target.value;renderTeams();};$('#only-mine').onchange=e=>{state.onlyMine=e.target.checked;renderTeams();};
}
function teamForm(competitionId,id){
 if(!requireLogin())return;if(admin()){toast('请使用学生账号创建队伍');return;}const t=state.teams.find(x=>x.id===id)||{};const cs=state.competitions.filter(competitionOpen);
 if(!id&&!cs.length){toast('暂无可创建队伍的竞赛');return;}
 showModal(id?'编辑队伍':'创建一支新队伍',`<form id="team-form">${id?'':`<label class="field">选择竞赛<select name="competition_id" required>${cs.map(c=>`<option value="${c.id}" ${competitionId===c.id?'selected':''}>${esc(c.title)}</option>`).join('')}</select></label>`}${field('name','队伍名称',t.name,'text','required maxlength="50"')}${area('intro','队伍介绍',t.intro,'maxlength="1000"')}${area('requirements','招募要求',t.requirements,'maxlength="500"')}${formEnd(id?'保存修改':'创建队伍')}`);
 bindForm('#team-form',async data=>{if(data.competition_id)data.competition_id=Number(data.competition_id);await api('/teams'+(id?'/'+id:''),id?'PUT':'POST',data);$('#modal').close();state.page='teams';await refresh();toast('队伍已保存');});
}
function teamDetail(id){
 const t=state.teams.find(x=>x.id===id);if(!t){toast('队伍已不存在，请刷新');return;}const captain=t.captain_id===state.user?.id;
 const canApply=teamOpen(t)&&t.member_count<t.max_members&&!admin()&&t.my_application?.status!=='pending';
 showModal(t.name,`<span class="tag">${esc(t.competition_title)}</span><p class="detail-text">${esc(t.intro)}</p><h3 class="section-title">招募要求</h3><p class="detail-text">${esc(t.requirements||'欢迎感兴趣的同学加入')}</p><p>人数 ${t.member_count} / ${t.max_members} · 截止 ${esc(t.deadline.replace('T',' '))}</p><h3 class="section-title">队伍成员</h3><div class="members">${(t.members||[]).map(m=>`<span class="member">${esc(m.name)}${m.id===t.captain_id?' · 队长':''}${captain&&m.id!==t.captain_id&&!t.registration_status?` <button class="link" data-action="member-remove" data-id="${id}" data-user="${m.id}" aria-label="移除成员 ${esc(m.name)}">移除</button>`:''}</span>`).join('')}</div>${t.registration_status?`<div class="hint" role="group" aria-label="报名审核状态">${badge(t.registration_status,true)}<p>${esc(registrationDescriptions[t.registration_status])}</p>队伍信息和成员名单已锁定。</div>`:''}${captain?`<h3 class="section-title">入队申请</h3>${t.applications.length?t.applications.map(a=>`<div class="row"><div><strong>${esc(a.name)}</strong><p>${esc(a.message||'希望加入队伍')}</p>${badge(a.status)}</div>${a.status==='pending'&&!t.registration_status?`<div class="actions"><button class="btn small primary" data-action="application-review" data-id="${a.id}" data-status="approved" data-team="${id}" ${!teamOpen(t)||t.member_count>=t.max_members?'disabled':''}>同意</button><button class="btn small" data-action="application-review" data-id="${a.id}" data-status="rejected" data-team="${id}">拒绝</button></div>`:''}</div>`).join(''):'<p class="form-note">暂无申请</p>'}`:''}<div class="form-actions">${captain?`${!t.registration_status?`<button class="btn danger" data-action="team-delete" data-id="${id}">解散队伍</button><button class="btn" data-action="team-edit" data-id="${id}">编辑</button>`:''}<button class="btn primary" data-action="registration-new" data-id="${id}" ${!t.registration_status&&!teamOpen(t)?'disabled':''}>${t.registration_status?'查看报名':'提交报名'}</button>`:t.is_member?`${!t.registration_status?`<button class="btn danger" data-action="team-leave" data-id="${id}">退出队伍</button>`:''}<span class="form-note">报名由队长统一提交。</span>`:t.my_application?.status==='pending'?`<button class="btn" data-action="application-cancel" data-id="${t.my_application.id}">撤回入队申请</button>`:`<button class="btn primary" data-action="apply" data-id="${id}" ${canApply?'':'disabled'}>${t.registration_status?'报名已锁定':!teamOpen(t)?'招募已结束':t.member_count>=t.max_members?'队伍已满':'申请加入'}</button>`}</div>`);
}
function applyForm(id){if(!requireLogin())return;showModal('申请加入队伍',`<form id="apply-form">${area('message','向队长介绍一下自己','','required maxlength="500"')}<p class="form-note">可以介绍你的专业、技能和希望承担的工作。</p>${formEnd('发送申请')}`);bindForm('#apply-form',async data=>{await api(`/teams/${id}/apply`,'POST',data);$('#modal').close();await refresh();toast('申请已发送，等待队长处理');});}
function renderRegistrations(){
 heading(admin()?'报名审核':'报名记录',admin()?'核对参赛信息，处理队伍报名。':'查看所在队伍的报名信息和处理结果。',state.user?'<button class="btn" data-action="registration-export">导出可见报名 CSV</button>':'');
 if(!state.user){$('#content').innerHTML=empty('登录后查看报名记录','<button class="btn primary" data-action="login">立即登录</button>');return;}
 const records=state.registrations.filter(r=>!state.registrationStatus||r.status===state.registrationStatus);
 $('#content').innerHTML=`<div class="hint">${admin()?'要求修改时请写清原因，队长可在截止前修改后重新提交。':'由队长统一提交报名，队员共享审核结果。报名为系统内登记。'} 成员资料以提交时的快照保存。</div><div class="hint status-guide"><strong>报名审核状态说明</strong><ul>${Object.entries(registrationLabels).map(([key,label])=>`<li><strong>${label}</strong>：${esc(registrationDescriptions[key])}</li>`).join('')}</ul></div><div class="toolbar"><label for="registration-status">报名审核状态</label><select id="registration-status"><option value="">全部状态</option>${Object.entries(registrationLabels).map(([key,label])=>`<option value="${key}" ${state.registrationStatus===key?'selected':''}>${label}</option>`).join('')}</select><span class="form-note">共 ${records.length} 条</span></div>`+(records.length?`<div class="grid">${records.map(r=>`<article class="card"><div class="card-top"><span class="tag">${esc(r.competition_title)}</span></div><h3>${esc(r.team_name)}</h3><div class="registration-status" role="group" aria-label="报名审核状态">${badge(r.status,true)}<p>${esc(registrationDescriptions[r.status])}</p></div><p>联系人：${esc(r.contact_name)} · ${esc(r.contact_phone)}</p><p>队员：${(r.members||[]).map(m=>esc(m.name)).join('、')}</p><p class="detail-text">参赛说明：${esc(r.statement||'无')}</p>${r.review_note?`<div class="hint">${r.status==='rejected'?'修改原因':'审核意见'}：${esc(r.review_note)}</div>`:''}<details class="history"><summary>提交和审核历史（${r.history?.length||0} 条）</summary><ol>${(r.history||[]).map(h=>`<li><strong>${esc(actionLabels[h.action]||h.action)}</strong> · ${esc(h.actor_name||'未记录')}<br><time>${esc(h.occurred_at.replace('T',' '))}</time>${h.review_note?`<p>${esc(h.review_note)}</p>`:''}<details><summary>本次提交快照</summary><p>联系人：${esc(h.contact_name)} · ${esc(h.contact_phone)}</p><p>成员：${(h.members||[]).map(m=>esc(m.name)).join('、')}</p><p class="detail-text">${esc(h.statement)}</p></details></li>`).join('')}</ol></details><div class="card-bottom"><span>报名编号 #${r.id}</span><div class="actions">${admin()&&r.status==='pending'?`<button class="btn small" data-action="registration-review" data-id="${r.id}" data-status="rejected">要求修改</button><button class="btn small primary" data-action="registration-review" data-id="${r.id}" data-status="approved">通过</button>`:r.captain_id===state.user.id&&r.status==='rejected'?`<button class="btn small primary" data-action="registration-new" data-id="${r.team_id}">修改并重新提交</button>`:''}</div></div></article>`).join('')}</div>`:empty('暂无符合条件的报名记录',admin()?'队长提交报名后，会显示在这里。':'先创建或加入队伍，再由队长在队伍详情提交报名。'));
 $('#registration-status').onchange=e=>{state.registrationStatus=e.target.value;renderRegistrations();};
}
function registrationForm(teamId){
 if(!requireLogin())return;const r=state.registrations.find(x=>x.team_id===teamId);if(r&&r.status!=='rejected'){$('#modal').close();state.page='registrations';render();return;}
 const t=state.teams.find(x=>x.id===teamId);showModal(r?'修改报名信息':'提交队伍报名',`<div class="hint">${esc(t?.name)} · ${(t?.members||[]).map(m=>esc(m.name)).join('、')}<br>提交后队伍成员将锁定，请核对名单。</div>${r?.review_note?`<div class="hint">修改原因：${esc(r.review_note)}<br>修改后重新提交，报名将进入“报名待审核”。</div>`:''}<form id="registration-form">${field('contact_name','联系人',r?.contact_name||state.user.name,'text','required maxlength="30"')}${field('contact_phone','联系电话',r?.contact_phone,'tel','required maxlength="30"')}${area('statement','参赛说明',r?.statement,'required maxlength="2000"')}<p class="form-note">联系电话用于报名联系，仅本队成员及管理员可见。请填写可联系到队长的号码。</p>${formEnd('确认提交')}`);
 bindForm('#registration-form',async data=>{await api('/registrations','POST',{...data,team_id:teamId});$('#modal').close();state.page='registrations';await refresh();toast('报名已提交，等待管理员审核');});
}
function reviewForm(id,status){showModal(status==='approved'?'通过报名':'要求修改报名',`<form id="review-form">${area('review_note',status==='rejected'?'修改原因（必填）':'审核意见（选填）','',`${status==='rejected'?'required':''} maxlength="1000"`)}${formEnd('确认'+(status==='approved'?'通过':'要求修改'))}`);bindForm('#review-form',async data=>{await api(`/registrations/${id}/review`,'POST',{...data,status});$('#modal').close();await refresh();toast('审核结果已保存');});}
function renderProfile(){heading('个人资料','让队友更了解你，从一份简单的自我介绍开始。');if(!state.user){$('#content').innerHTML=empty('请先登录','<button class="btn primary" data-action="login">立即登录</button>');return;}
 const u=state.user;$('#content').innerHTML=`<div class="panel profile"><p class="hint">姓名、专业、年级、技能简介会随队伍公开展示，用于组队沟通。报名快照保留提交时资料。</p><form id="profile-form">${field('name','姓名',u.name,'text','required maxlength="30"')}<div class="form-grid">${field('major','专业',u.major,'text','maxlength="60"')}${field('grade','年级',u.grade,'text','maxlength="30"')}</div>${area('skills','技能与个人简介',u.skills,'maxlength="500"')}<div class="error" role="alert"></div><button class="btn primary" type="submit">保存资料</button><button class="btn" type="button" data-action="password-change">修改密码</button></form></div>`;bindForm('#profile-form',async data=>{await api('/profile','PUT',data);state.user=(await api('/me')).user;await refresh();toast('个人资料已更新');});
}
function passwordForm(){showModal('修改密码',`<form id="password-form">${field('old_password','当前密码','','password','required autocomplete="current-password"')}${field('new_password','新密码','','password','required minlength="8" maxlength="128" autocomplete="new-password"')}<p class="form-note">8 至 128 位。修改后其他浏览器中的同账号登录失效，当前登录保留。</p>${formEnd('保存新密码')}`);bindForm('#password-form',async data=>{await api('/password','PUT',data);$('#modal').close();toast('密码已修改，其他登录已失效');});}
async function exportRegistrations(){const result=await api('/registrations/export');const url=URL.createObjectURL(new Blob([result.content],{type:'text/csv;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=result.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('已导出当前账号可见的全部报名记录');}
document.addEventListener('click',async e=>{
 const nav=e.target.closest('[data-page]');if(nav){state.page=nav.dataset.page;try{await refresh();}catch(err){toast(err.message);}return;}
 const el=e.target.closest('[data-action]');if(!el)return;const a=el.dataset.action,id=Number(el.dataset.id);
 try{
 if(a==='close')$('#modal').close();
 if(a==='password-change')passwordForm();
 if(a==='registration-export')await exportRegistrations();
 if(a==='member-remove')confirmAction('移除成员','移除后该成员可重新申请加入。已提交报名的队伍无法移除成员。','member-remove-confirm',id,`data-user="${Number(el.dataset.user)}"`);
 if(a==='member-remove-confirm'){await api(`/teams/${id}/members/${Number(el.dataset.user)}`,'DELETE');await refresh();teamDetail(id);toast('成员已移除');}
 if(a==='team-leave')confirmAction('退出队伍','退出后可重新申请，或加入同一竞赛的其他队伍。','team-leave-confirm',id);
 if(a==='team-leave-confirm'){await api(`/teams/${id}/members/me`,'DELETE');$('#modal').close();await refresh();toast('已退出队伍');}
 if(a==='application-cancel')confirmAction('撤回申请','撤回后可重新提交入队申请。','application-cancel-confirm',id);
 if(a==='application-cancel-confirm'){await api(`/applications/${id}`,'DELETE');$('#modal').close();await refresh();toast('申请已撤回');}

 if(a==='login')login();if(a==='register')login(true);
 if(a==='account-fill'){$('#auth-form [name=username]').value=el.dataset.user;$('#auth-form [name=password]').value='Demo123456';}
 if(a==='logout'){await api('/logout','POST',{});state.user=null;state.onlyMine=false;state.registrationStatus='';await refresh();toast('已退出登录');}
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
