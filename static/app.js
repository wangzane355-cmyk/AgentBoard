let state = {projects:[],tasks:[],runs:[],agents:{}};
let activeProject = null;
let activeTask = null;
let editingTask = null;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cols = [
  ['ready','待处理', t => ['ready','queued'].includes(t.status)],
  ['running','进行中', t => t.status === 'running'],
  ['decision','决策收件箱', t => t.status === 'decision'],
  ['review','待你查收', t => t.status === 'review'],
  ['done','已完成', t => t.status === 'done'],
  ['blocked','已阻塞', t => t.status === 'blocked']
];
const statusText = {ready:'待处理',queued:'已排队',running:'进行中',decision:'需要你决定',review:'待你查收',done:'已完成',blocked:'已阻塞'};

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || '操作失败');
  return data;
}
function toast(message) {
  const el = $('#toast'); el.textContent = AgentBoardI18n.translate(message); el.classList.remove('hidden');
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.classList.add('hidden'), 4200);
}
function elapsed(iso) {
  if (!iso) return '准备中';
  const sec = Math.max(0, Math.floor((Date.now()-Date.parse(iso))/1000));
  return `${String(Math.floor(sec/60)).padStart(2,'0')}:${String(sec%60).padStart(2,'0')}`;
}
function latestRun(task) {return state.runs.find(r => r.id === task.run_ids.at(-1));}
function render() {
  if (!activeProject && state.projects.length) activeProject = state.projects[0].id;
  if (activeProject && !state.projects.some(p=>p.id===activeProject)) activeProject = state.projects[0]?.id || null;
  const project = state.projects.find(p=>p.id===activeProject);
  $('#project-nav').innerHTML = state.projects.map(p=>`<button class="project-link ${p.id===activeProject?'active':''}" data-project="${esc(p.id)}">${esc(p.name)}</button>`).join('') || '<div class="tiny">暂无项目</div>';
  $('#project-title').textContent = project?.name || AgentBoardI18n.translate('任务看板');
  $('#project-subtitle').textContent = project ? '用任务卡调度 Codex 和 DeepSeek；Python 负责监督。' : '先添加一个本地项目。';
  $('#agent-status').innerHTML = `<span class="mini-badge ${state.agents.codex?'ok':''}">Codex ${state.agents.codex?'可用':'未找到'}</span><span class="mini-badge ${state.agents.deepseek?'ok':''}">DeepSeek ${state.agents.deepseek?'可用':'未找到'}</span>`;
  const budget=state.budget||{}, age=budget.observed_at?Date.now()-Date.parse(budget.observed_at):Infinity;
  $('#budget-button').textContent=budget.probe_error?'Codex 5h：读取失败 · 点击重试':budget.codex_5h_remaining==null?'Codex 5h：读取中':`Codex 5h：剩余 ${budget.codex_5h_remaining}%${age>30*60*1000?' · 已过期':''}`;
  $('#budget-button').title=budget.probe_error||'通过本机 Codex app-server 自动读取；点击立即刷新';
  if(state.demo){$('#project-subtitle').textContent='演示工作区 · 示例数据 · 不调用真实Agent';$('#budget-button').textContent='只读演示';$('#agent-status').innerHTML='<span class="mini-badge">DEMO · SAMPLE DATA</span>';}
  const tasks = state.tasks.filter(t=>t.project_id===activeProject);
  $('#metric-running').textContent = tasks.filter(t=>t.status==='running').length;
  $('#metric-review').textContent = tasks.filter(t=>['review','blocked','decision'].includes(t.status)).length;
  $('#metric-done').textContent = tasks.filter(t=>t.status==='done').length;
  $('#board').innerHTML = cols.map(([key,label,filter])=>{
    const items = tasks.filter(filter);
    return `<div class="column" data-column="${key}"><div class="column-head"><span class="dot"></span>${label}<span class="count">${items.length}</span></div><div class="cards">${items.map(card).join('') || '<div class="empty">目前没有任务</div>'}</div></div>`;
  }).join('');
  document.querySelectorAll('[data-project]').forEach(b=>b.onclick=()=>{activeProject=b.dataset.project;activeTask=null;closeDrawer();render();});
  document.querySelectorAll('[data-task]').forEach(b=>b.onclick=()=>openDrawer(b.dataset.task));
  if (activeTask) drawDrawer();
  if(typeof renderAgents==='function')renderAgents();
}
function card(t) {
  const run = latestRun(t);
  const bottom = t.status==='running' ? `${elapsed(run?.started_at)} / ${t.limit_minutes}:00` : t.mode==='explore'?'先调查':'开发任务';
  const agent=run?.agent||t.agent;
  return `<button class="card" data-task="${esc(t.id)}"><div class="card-top"><span>${esc(t.id.toUpperCase())}</span><span class="agent-chip ${agent}">${esc(profileName(agent))}${(run?.simulation||(!run&&profiles().find(p=>p.id===agent)?.simulation))?' [SIMULATION]':''}</span></div><div class="card-title">${esc(t.title)}</div><div class="card-description">${esc(t.description)}</div>${run?.error?`<div class="card-error">${esc(run.error)}</div>`:''}<div class="card-bottom"><span>${esc(statusText[t.status])}</span><span>${esc(bottom)}</span></div></button>`;
}
function openDrawer(id) {activeTask=id;$('#shade').classList.remove('hidden');$('#drawer').classList.remove('hidden');drawDrawer();}
function closeDrawer() {activeTask=null;$('#shade').classList.add('hidden');$('#drawer').classList.add('hidden');}
async function loadResult(runId) {
  try {
    const data = await api(`/api/runs/${runId}/result`);
    const box = $('#result-box');
    if (box) box.textContent = data.result || '(还没有结果)';
    const capsule = $('#capsule-box');
    if (capsule) capsule.textContent = data.capsule || '(任务胶囊正在生成)';
    const log = $('#log-box');
    if (log) log.textContent = data.diagnostics_tail || '(暂无诊断日志)';
  } catch (e) {toast(e.message);}
}
function drawDrawer() {
  const t = state.tasks.find(t=>t.id===activeTask); if (!t) return closeDrawer();
  const run = latestRun(t), deps=t.depends_on.map(id=>state.tasks.find(x=>x.id===id)?.title||id);
  const children=state.tasks.filter(x=>x.depends_on.includes(t.id));
  let actions='';
  actions += '<button class="ghost" data-action="discuss">讨论这张任务</button>';
  if (['ready','blocked','done'].includes(t.status)) actions += `<button class="primary" data-action="start">${t.status==='blocked'?'重新运行':'启动任务'}</button>`;
  if (!['running','queued'].includes(t.status)) actions += '<button class="ghost" data-action="edit">编辑任务</button>';
  if (t.status==='queued') actions += '<button class="ghost" data-action="stop">取消排队</button>';
  if (t.status==='running') actions += '<button class="danger" data-action="stop">停止运行</button>';
  if (t.status==='review') actions += `<button class="soft" data-action="accept">${t.mode==='explore'?'标记已了解':'接入原项目'}</button>`;
  if (t.status==='done' && t.mode==='implement' && run?.promotion && Object.keys(run.promotion).length) actions += '<button class="danger" data-action="rollback">撤回本次接入</button>';
  const checkRows = run ? (run.evidence||[]).map(item=>`<div class="check ${item.status==='pass'?'ok':item.status==='fail'?'bad':''}">${item.status==='pass'?'✓':item.status==='fail'?'✕':'○'} <strong>${esc(item.label)}</strong> · ${esc(item.detail)}</div>`).join('') || `<div class="check">${esc(run.error || 'Python 正在检查')}</div>` : '<div class="check">尚未运行</div>';
  $('#drawer-body').innerHTML = `<h2>${esc(t.title)}</h2><div class="detail-desc">${esc(t.description)}</div>
    <div class="detail-section"><div class="detail-row"><span>状态</span><strong>${esc(statusText[t.status])}</strong></div><div class="detail-row"><span>指定执行者</span><strong>${esc(profileName(t.agent))}</strong></div>${run?`<div class="detail-row"><span>实际执行者</span><strong>${esc(profileName(run.agent))}</strong></div>`:''}<div class="detail-row"><span>方式</span><strong>${t.mode==='explore'?'只读调查':'开发修改'}</strong></div><div class="detail-row"><span>时限</span><strong>${t.limit_minutes} 分钟</strong></div><div class="detail-row"><span>任务 ID</span><strong>${esc(t.id)}</strong></div>${run?.started_at?`<div class="detail-row"><span>开始</span><strong>${esc(new Date(run.started_at).toLocaleString())}</strong></div>`:''}</div>
    ${run?.budget_note?`<div class="warning">${esc(run.budget_note)}</div>`:''}
    <div class="detail-section"><h3>允许改动</h3><div class="tag-list">${t.allowed_paths.map(x=>`<span class="tag">${esc(x)}</span>`).join('')||'<span class="tag">无 · 只读</span>'}</div></div>
    <div class="detail-section"><h3>关联资料</h3><div class="tag-list">${[...(state.projects.find(p=>p.id===t.project_id)?.context_files||[]),...(state.projects.find(p=>p.id===t.project_id)?.context_urls||[]),...(t.context_files||[]),...(t.context_urls||[])].map(x=>`<span class="tag">${esc(x)}</span>`).join('')||'<span class="hint">未配置；可在项目资料中选择</span>'}</div>${t.discussion_id?'<p class="hint">已关联讨论与共识，执行时会自动带入。</p>':''}</div>
    ${deps.length?`<div class="detail-section"><h3>前置任务</h3><div class="tag-list">${deps.map(x=>`<span class="tag">${esc(x)}</span>`).join('')}</div></div>`:''}
    ${children.length?`<div class="detail-section"><h3>接下来依赖这张卡</h3><div class="tag-list">${children.map(x=>`<span class="tag">${esc(x.title)} · ${esc(statusText[x.status])}</span>`).join('')}</div></div>`:''}
    ${t.assertions?.length?`<div class="detail-section"><h3>机器验收规则</h3><div class="tag-list">${t.assertions.map(x=>`<span class="tag">${esc(x)}</span>`).join('')}</div></div>`:''}
    <div class="detail-section"><h3>Python 验收证据</h3><div class="checks">${checkRows}</div></div>
    ${t.status==='decision' && run?.decision?`<div class="decision-panel"><h3>只需要你决定这一点</h3><p>${esc(run.decision.question)}</p><div class="decision-options">${(run.decision.options||[]).map(x=>`<button class="ghost" data-answer="${esc(x)}">${esc(x)}</button>`).join('')}</div><textarea id="decision-answer" rows="3" placeholder="也可以写自己的决定"></textarea><button class="primary" data-action="answer">提交决定并继续</button></div>`:''}
    ${t.status==='review' && t.mode==='implement' && !run?.automated_check_passed?'<div class="warning">这张卡还没有自动编译通过的证据；接入前请查看结果或先配置项目检查。</div>':''}
    ${t.status==='review' && t.mode==='implement' && run?.automated_check_passed?'<div class="warning">自动编译已过，但画面、手感和玩法仍需要你查看；Python 无法判断这些体验。</div>':''}
    <div class="detail-actions">${actions}</div>
    ${run?`<div class="detail-section"><h3>跨模型任务胶囊</h3><div id="capsule-box" class="result-box">读取中…</div></div><div class="detail-section"><h3>交付结果</h3><div id="result-box" class="result-box">读取中…</div></div><details class="detail-section"><summary>技术诊断日志（本地私有）</summary><div id="log-box" class="result-box">展开后读取</div></details>
    ${run.image_paths?.length?`<div class="detail-section"><h3>本次生成的画面</h3><div class="image-grid">${run.image_paths.map(p=>`<figure><img src="/api/runs/${encodeURIComponent(run.id)}/image?path=${encodeURIComponent(p)}" alt="${esc(p)}"><figcaption>${esc(p)}</figcaption></figure>`).join('')}</div></div>`:''}
    <div class="detail-section"><h3>改动文件</h3><div class="change-list">${(run.changes||[]).map(c=>`<button class="tag change-button" data-diff="${esc(c.path)}">${esc(c.change)} · ${esc(c.path)} · 查看差异</button>`).join('')||'<span class="tag">暂无</span>'}</div><pre id="diff-box" class="result-box hidden"></pre></div>`:''}`;
  document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>act(t.id,b.dataset.action));
  document.querySelectorAll('[data-answer]').forEach(b=>b.onclick=()=>{$('#decision-answer').value=b.dataset.answer;});
  document.querySelectorAll('[data-diff]').forEach(b=>b.onclick=async()=>{try{const data=await api(`/api/runs/${run.id}/diff?path=${encodeURIComponent(b.dataset.diff)}`);$('#diff-box').textContent=data.diff;$('#diff-box').classList.remove('hidden');}catch(e){toast(e.message);}});
  if (run) loadResult(run.id);
}
async function act(id,action) {
  const t=state.tasks.find(x=>x.id===id);
  if (action==='edit') {openTaskForm(t);return;}
  if (action==='discuss') {closeDrawer();showChat(t.id);return;}
  if (action==='accept' && t?.mode==='implement' && !confirm(AgentBoardI18n.translate('接入原项目会复制本次改动。请先查看结果；确认接入吗？'))) return;
  if (action==='rollback' && !confirm(AgentBoardI18n.translate('确认撤回本次接入的文件改动？若文件已被再次修改，系统会拒绝撤回。'))) return;
  const body=action==='answer'?{answer:$('#decision-answer')?.value||''}:{};
  try {await api(`/api/tasks/${id}/${action}`,body);toast(action==='start'?'任务已启动':action==='stop'?'已请求停止':action==='rollback'?'已撤回改动':action==='answer'?'决定已提交，任务继续':'任务已完成');await refresh();} catch(e){toast(e.message);}
}
async function refresh(){try{state=await api('/api/state');render();}catch(e){toast(e.message);}}
function dialog(id){$(id).showModal();}
function lines(s){return s.split(/[\n,]/).map(x=>x.trim()).filter(Boolean);}
function openTaskForm(task=null){
  if(!state.projects.length)return toast('请先添加项目');
  editingTask=task?.id||null;
  const form=$('#task-form');form.reset();
  $('#task-dialog-title').textContent=task?'编辑任务卡':'创建任务卡';
  $('#task-submit').textContent=task?'保存修改':'创建任务';
  $('#task-project').innerHTML=state.projects.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  form.elements.project_id.value=task?.project_id||activeProject;
  if(task){for(const key of ['title','description','agent','mode','limit_minutes'])form.elements[key].value=task[key];form.elements.allowed_paths.value=task.allowed_paths.join('\n');form.elements.assertions.value=(task.assertions||[]).join('\n');form.elements.depends_on.value=task.depends_on.join(', ');form.elements.auto_start.checked=task.auto_start;}
  form.elements.fallback_to_deepseek.checked=task?.fallback_to_deepseek??true;
  form.elements.context_files.value=(task?.context_files||[]).join('\n');
  form.elements.context_urls.value=(task?.context_urls||[]).join('\n');
  form.elements.discussion_id.value=task?.discussion_id||'';
  dialog('#task-dialog');
}
$('#new-task').onclick=()=>openTaskForm();
$('#add-project').onclick=()=>dialog('#project-dialog');
$('#refresh').onclick=refresh;
$('#budget-button').onclick=async()=>{try{const r=await api('/api/budget/refresh',{});toast(r.data.probe_error?`读取失败：${r.data.probe_error}`:'Codex 用量已自动刷新');await refresh();}catch(e){toast(e.message);}};
$('#close-drawer').onclick=closeDrawer;
$('#shade').onclick=closeDrawer;
document.querySelectorAll('.close-dialog').forEach(x=>x.onclick=()=>x.closest('dialog').close());
$('#task-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target);const body={title:f.get('title'),description:f.get('description'),project_id:f.get('project_id'),agent:f.get('agent'),mode:f.get('mode'),limit_minutes:Number(f.get('limit_minutes')),allowed_paths:lines(f.get('allowed_paths')),assertions:String(f.get('assertions')||'').split('\n').map(x=>x.trim()).filter(Boolean),depends_on:lines(f.get('depends_on')),auto_start:f.has('auto_start'),fallback_to_deepseek:f.has('fallback_to_deepseek'),context_files:String(f.get('context_files')||'').split('\n').map(x=>x.trim()).filter(Boolean),context_urls:String(f.get('context_urls')||'').split('\n').map(x=>x.trim()).filter(Boolean),discussion_id:f.get('discussion_id')||''};try{await api(editingTask?`/api/tasks/${editingTask}/update`:'/api/tasks',body);$('#task-dialog').close();toast(editingTask?'任务卡已修改':'任务卡已创建');await refresh();}catch(err){toast(err.message);}};
$('#project-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target);try{const result=await api('/api/projects',{name:f.get('name'),path:f.get('path'),protected_paths:lines(f.get('protected_paths')),check:f.get('check'),context_files:String(f.get('context_files')||'').split('\n').map(x=>x.trim()).filter(Boolean),context_urls:String(f.get('context_urls')||'').split('\n').map(x=>x.trim()).filter(Boolean)});activeProject=result.data.id;$('#project-dialog').close();toast('项目已添加');await refresh();}catch(err){toast(err.message);}};
refresh();setInterval(refresh,3000);
