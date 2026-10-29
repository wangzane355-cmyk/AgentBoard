/* Agent settings never contain API key values. */
let agentOptionsSignature = '';
let memberSignature = '';
const say = (zh, en) => AgentBoardI18n.choose(zh, en);
function profiles(){return state.agent_catalog || [{id:'codex',name:'Codex',enabled:true,can_implement:true,kind:'builtin'},{id:'deepseek',name:'DeepSeek',enabled:true,can_implement:true,kind:'builtin'}];}
function profileName(id){return profiles().find(p=>p.id===id)?.name || id;}
function profileOptions(selected, allowAll=false){
  const active=profiles().filter(p=>p.enabled);
  if(selected && selected!=='all' && !active.some(p=>p.id===selected))active.push({id:selected,name:profileName(selected),enabled:false});
  return (allowAll?'<option value="all">'+say('发给全体','Everyone')+'</option>':'')+active.map(p=>`<option data-agent-option value="${esc(p.id)}" ${p.enabled?'':'disabled'}>${esc(p.name)}${p.kind==='mock'?' [SIMULATION]':''}</option>`).join('');
}
function renderAgents(){
  if(typeof renderExecutorManager==='function')renderExecutorManager();
  $('#manage-agents').disabled=!state.agent_catalog;
  $('#manage-agents').textContent=state.agent_catalog?say('⚙ Agent 管理','⚙ Manage agents'):say('⚙ Agent 管理（需重启）','⚙ Manage agents (restart required)');
  if(!state.demo)$('#agent-status').innerHTML=profiles().filter(p=>p.enabled).map(p=>`<span class="mini-badge ${p.configured?'ok':''}">${esc(p.name)}${p.kind==='mock'?' [SIMULATION]':''}</span>`).join('');
  const signature=JSON.stringify(profiles())+AgentBoardI18n.language;
  if(signature===agentOptionsSignature)return;
  agentOptionsSignature=signature;
  for(const select of [document.querySelector('#task-form [name=agent]'),$('#chat-agent')]){
    const value=select.value;select.innerHTML=profileOptions(value,select.id==='chat-agent');select.value=value;
    if(!select.value)select.value='deepseek';
  }
  if($('#agents-dialog').open)renderAgentList();
  memberSignature='';renderRoomMembers();
}
function renderRoomMembers(){
  const box=$('#chat-room-members');
  const group=$('#chat-mode').value==='group';box.classList.toggle('hidden',!group);
  const signature=JSON.stringify([currentChat,chatData?.id,chatData?.members,profiles().map(p=>[p.id,p.enabled])])+AgentBoardI18n.language;
  if(signature!==memberSignature){
    const previous=Array.from(box.querySelectorAll('input:checked')).map(el=>el.value);
    const members=chatData?.members || (previous.length?previous:profiles().filter(p=>p.enabled).slice(0,6).map(p=>p.id));
    box.innerHTML=`<legend>${say('房间成员（最多6位）','Room members (up to 6)')}</legend>`+profiles().filter(p=>p.enabled||members.includes(p.id)).map(p=>`<label class="checkline"><input type="checkbox" value="${esc(p.id)}" ${members.includes(p.id)?'checked':''} ${currentChat?'disabled':''}>${esc(p.name)}${p.kind==='mock'?' [SIMULATION]':''}</label>`).join('');
    memberSignature=signature;
  }
  const allowed=currentChat?chatData?.members:null;
  const members=allowed || selectedMembers();
  $('#group-chat-help').textContent=say('成员：','Members: ')+members.map(profileName).join(' · ')+say('。/成员ID 定向回复，/all 全体回复，最多六次回复。',' · /agent-id addresses one member; /all invites everyone. Up to six replies.');
  for(const option of $('#group-rounds').options){const n=Number(option.value),count=Math.min(6,members.length*n);option.textContent=say(`最多${n}轮 / ${count}次回复`,`Up to ${n} ${n===1?'round':'rounds'} / ${count} ${count===1?'reply':'replies'}`);}
  for(const option of $('#chat-agent').options){
    if(option.value==='all'){option.hidden=!group;continue;}
    option.disabled=Boolean(group&&allowed&&!allowed.includes(option.value)) || !profiles().some(p=>p.id===option.value&&p.enabled);
  }
}
function selectedMembers(){return Array.from($('#chat-room-members').querySelectorAll('input:checked')).map(el=>el.value);}
function renderAgentList(){
  $('#agent-list').innerHTML=profiles().map(p=>`<article class="agent-setting"><strong data-agent-name>${esc(p.name)}</strong> <code>/${esc(p.id)}</code> <span>${esc(p.kind)}${p.kind==='mock'?' · SIMULATION':''}</span><p>${p.configured?say('配置检查通过；未验证真实账号','Configuration present; live account not verified'):say('程序或密钥环境变量未就绪','Executable or key environment variable missing')} · ${p.enabled?say('已启用','Enabled'):say('已停用','Disabled')}</p><button type="button" class="ghost" data-agent-check="${esc(p.id)}">${say('检查配置（不调用模型）','Check configuration (no model call)')}</button>${p.kind!=='builtin'?` <button type="button" class="ghost" data-agent-edit="${esc(p.id)}">${say('编辑','Edit')}</button>`:''}</article>`).join('');
  document.querySelectorAll('[data-agent-edit]').forEach(b=>b.onclick=()=>fillAgentForm(profiles().find(p=>p.id===b.dataset.agentEdit)));
  document.querySelectorAll('[data-agent-check]').forEach(b=>b.onclick=async()=>{try{const result=(await api('/api/agents/check',{id:b.dataset.agentCheck})).data;$('#agent-check-result').textContent=(result.configured?say('本地配置检查通过。','Local configuration present.'):say('配置未就绪。','Configuration is incomplete.'))+' '+say('没有调用模型；登录状态和服务连接仍未验证。','No model was called; authentication and provider connectivity remain unverified.');}catch(e){toast(e.message);}});
}
function fillAgentForm(profile={}){
  const form=$('#agent-form');form.reset();
  for(const key of ['id','name','kind','executable','endpoint','model','key_env'])if(profile[key]!==undefined)form.elements[key].value=profile[key];
  form.elements.args.value=JSON.stringify(profile.args||[],null,2);
  form.elements.id.readOnly=Boolean(profile.id);
  form.elements.enabled.checked=profile.enabled??true;
  form.elements.can_implement.checked=profile.can_implement??false;
  toggleAdapterFields();
}
function toggleAdapterFields(){
  const kind=$('#agent-form').elements.kind.value;
  $('#agent-cli-fields').classList.toggle('hidden',kind!=='cli');
  $('#agent-api-fields').classList.toggle('hidden',kind!=='api');
}
$('#manage-agents').onclick=()=>{fillAgentForm();renderAgentList();$('#agent-check-result').textContent='';$('#agents-dialog').showModal();};
$('#agent-new').onclick=()=>fillAgentForm();
$('#agent-form').elements.kind.onchange=toggleAdapterFields;
$('#chat-room-members').onchange=renderRoomMembers;
$('#agent-form').onsubmit=async event=>{
  event.preventDefault();const form=event.target;
  try{
    const body=Object.fromEntries(new FormData(form));body.args=JSON.parse(form.elements.args.value||'[]');body.enabled=form.elements.enabled.checked;body.can_implement=form.elements.can_implement.checked;
    await api('/api/agents',body);await refresh();renderAgentList();fillAgentForm();toast(say('Agent配置已保存','Agent configuration saved'));
  }catch(e){toast(e.message);}
};
document.addEventListener('agentboard:language',()=>{agentOptionsSignature='';renderAgents();});
