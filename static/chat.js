let currentChat = null;
let chatData = null;
let chatProject = null;
let chatRefreshing = false;
let chatSending = false;
let lastMessageSignature = '';
let lastSessionSignature = '';
let chatSelectionChanged = false;
const chatCompactLayout=window.matchMedia('(max-width:760px)');
function configureChatLayout(){ $('#chat-settings').open=!chatCompactLayout.matches; }
chatCompactLayout.addEventListener('change',configureChatLayout);

function agentName(agent){return agent?profileName(agent):'Python监督';}
function setChatMode(mode, agent=null){
  const group=mode==='group';
  $('#chat-mode').value=group?'group':'single';
  if(typeof renderAgents==='function')renderAgents();
  $('#chat-agent').querySelector('option[value="all"]').hidden=!group;
  $('#chat-agent').value=group?(agent||'all'):(agent&&agent!=='all'?agent:'deepseek');
  $('#group-chat-help').classList.toggle('hidden',!group);
  $('#group-discussion-controls').classList.toggle('hidden',!group);
  $('#chat-agent').setAttribute('aria-label',group?'群聊回复对象':'对话执行者');
  if(typeof renderRoomMembers==='function')renderRoomMembers();
  $('#chat-discuss').disabled=chatSending||chatData?.status==='running'||$('#chat-agent').value!=='all';
}
async function showChat(taskId='', mode='single') {
  if(!activeProject)await refresh();
  if (!activeProject) return toast('请先选择项目');
  if(typeof taskId!=='string')taskId='';
  const task=state.tasks.find(t=>t.id===taskId);
  chatProject = activeProject;
  currentChat = null; chatData = null; lastMessageSignature = '';
  chatSelectionChanged=false;
  const existing=task?(state.chats||[]).filter(c=>c.project_id===chatProject&&(c.task_id===taskId||(c.id===task.discussion_id&&!c.task_id))).at(-1):null;
  if(existing)currentChat=existing.id;
  $('#chat-task').innerHTML='<option value="">先聊想法，暂不关联任务</option>'+state.tasks.filter(t=>t.project_id===chatProject).map(t=>`<option value="${esc(t.id)}">${esc(t.title)}</option>`).join('');
  $('#chat-task').value=taskId;
  $('#chat-input').value = '';
  setChatMode(existing?.mode||mode,existing?.mode==='group'?'all':existing?.agent);
  $('#chat-source').checked = false;
  configureChatLayout();
  $('#chat-dialog').showModal();
  refreshChat();
}
function updateChatFocus(){
  const task=state.tasks.find(t=>t.id===($('#chat-task').value||''));
  const project=state.projects.find(p=>p.id===chatProject);
  $('#chat-focus-title').textContent=task?`正在商量：${task.title}`:`正在商量：${project?.name||'当前项目'}的下一步`;
  $('#chat-start-plan').textContent=task?'先帮我梳理这张任务':'帮我判断下一步';
}
async function refreshChat() {
  if (!$('#chat-dialog').open || chatRefreshing) return;
  chatRefreshing = true;
  try {
    $('#chat-project-name').textContent = state.projects.find(p=>p.id===chatProject)?.name || '项目对话';
    const sessions = (state.chats||[]).filter(c=>c.project_id===chatProject).slice().reverse();
    const sessionSignature=JSON.stringify([chatProject,currentChat,sessions]);
    if(sessionSignature!==lastSessionSignature){
      $('#chat-sessions').innerHTML = sessions.map(c=>`<button class="chat-session ${c.id===currentChat?'active':''}" data-chat="${esc(c.id)}"><strong>${esc(c.title)}</strong><small>${c.mode==='group'?esc((c.members||[]).map(agentName).join(' / ')):esc(agentName(c.agent))} · ${c.status==='running'?'回复中':c.status==='error'?'需查看':'已保存'}</small></button>`).join('') || '<p class="hint">当前项目还没有对话</p>';
      document.querySelectorAll('[data-chat]').forEach(b=>b.onclick=async()=>{
      if(chatSending)return;
      currentChat=b.dataset.chat; chatData=null; lastMessageSignature='';
      chatSelectionChanged=true;$('#chat-send').disabled=true;
      $('#chat-input').value='';
      await refreshChat();
      });
      lastSessionSignature=sessionSignature;
    }
    if (currentChat) {
      const id=currentChat;
      const fetched=await api(`/api/chats/${id}`);
      if(id!==currentChat)return;
      chatData=fetched;
      if(chatSelectionChanged){setChatMode(chatData.mode||'single',chatData.mode==='group'?'all':chatData.agent);chatSelectionChanged=false;}
    }
    const messages=chatData?.messages||[];
    const signature=JSON.stringify(messages);
    if(signature!==lastMessageSignature || !$('#chat-messages').innerHTML){
      const box=$('#chat-messages'), nearBottom=box.scrollHeight-box.scrollTop-box.clientHeight<90;
      box.innerHTML=messages.map(m=>`<article class="chat-message ${m.role==='user'?'user':m.role==='system'?'system':'assistant'} ${m.agent==='codex'?'from-codex':m.agent==='deepseek'?'from-deepseek':''}"><div class="chat-message-label">${esc(m.role==='user'?'你':m.role==='system'?'Python监督':agentName(m.agent))}${m.audience&&chatData?.mode==='group'?` <span class="chat-audience">→ ${m.directed?esc(m.audience.map(agentName).join('、')):'全体'}</span>`:''}${m.simulation?' [SIMULATION]':''}${m.handoff_to?` <span class="chat-audience">请 ${esc(agentName(m.handoff_to))} 接话</span>`:''}</div><div>${esc(m.text)}</div></article>`).join('') || '<div class="chat-empty">先说说你的想法<br><small>群聊支持全体发言和斜杠定向消息</small></div>';
      if(nearBottom || lastMessageSignature==='')box.scrollTop=box.scrollHeight;
      lastMessageSignature=signature;
    }
    renderRoomMembers();
    const running=chatData?.status==='running';
    if(chatData)$('#chat-task').value=chatData.task_id||'';
    $('#chat-task').disabled=running||chatSending;
    updateChatFocus();
    $('#chat-agent').disabled=running||chatSending;
    $('#chat-mode').disabled=Boolean(currentChat)||running||chatSending;
    $('#chat-discuss').disabled=running||chatSending||$('#chat-agent').value!=='all';
    $('#group-rounds').disabled=running||chatSending;
    $('#chat-source').disabled=Boolean(currentChat);
    if(chatData)$('#chat-source').checked=chatData.include_source;
    $('#chat-send').disabled=running||chatSending;
    $('#chat-send').textContent=running?'正在回复…':'发送';
    $('#chat-stop').classList.toggle('hidden',!running);
    $('#chat-to-task').disabled=running||chatSending||!messages.some(m=>m.role==='assistant');
    const linked=state.tasks.find(t=>t.id===chatData?.task_id);
    $('#chat-to-task').textContent=linked&&['ready','blocked'].includes(linked.status)?'更新关联任务':'转成任务卡';
    $('#chat-organize').disabled=running||chatSending||!messages.length;
    $('#chat-start-plan').disabled=running||chatSending;
    $('#chat-consensus').disabled=running||chatSending||!currentChat;
    const project=state.projects.find(p=>p.id===chatProject);
    const referenceCount=(project?.context_files||[]).length+(project?.context_urls||[]).length+(linked?.context_files||[]).length+(linked?.context_urls||[]).length;
    $('#chat-reference-status').textContent=chatData?.context_read_at?`最近自动读取 ${chatData.context_sources?.length||0} 项资料 · ${new Date(chatData.context_read_at).toLocaleString()}${chatData.consensus?(chatData.consensus_needs_review?' · 关联任务已变，共识需核对':' · 已保存共识'):''}`:`已关联 ${referenceCount} 处资料，发送时自动读取；无需勾选源码。`;
    const batch=chatData?.mode==='group'?chatData.batch:null;
    $('#chat-status').textContent=running?(batch?`群聊：${batch.active_agent?agentName(batch.active_agent)+' 回复中':'准备中'} · 已完成 ${batch.completed}/${batch.max_replies} 次回复；关闭面板后继续，可随时停止。`:'Agent 正在回复，关闭面板后仍会继续。'):chatData?.error||(batch?.status==='done'?`本批次结束，${batch.completed} 次回复。`:'');
    $('#chat-status').classList.toggle('chat-error',Boolean(chatData?.error));
  } catch(e) {toast(e.message);} finally {chatRefreshing=false;}
}
$('#open-chat').onclick=()=>showChat();
$('#open-group-chat').onclick=()=>showChat('','group');
$('#chat-mode').onchange=()=>setChatMode($('#chat-mode').value);
$('#chat-agent').onchange=()=>{$('#chat-discuss').disabled=$('#chat-agent').value!=='all'||chatData?.status==='running';};
$('#plan-next').onclick=()=>showChat();
$('#chat-task').onchange=async()=>{
  updateChatFocus();
  if(!currentChat)return;
  const taskId=$('#chat-task').value;
  chatSending=true;
  try{chatData=(await api(`/api/chats/${currentChat}/task`,{task_id:taskId})).data;await refresh();toast('已关联到这张任务，之前的讨论会保留。');}
  catch(e){$('#chat-task').value=chatData?.task_id||'';toast(e.message);}
  finally{chatSending=false;await refreshChat();}
};
$('#chat-start-plan').onclick=()=>{
  const input=$('#chat-input');
  const task=state.tasks.find(t=>t.id===$('#chat-task').value);
  const chineseRequest=task?'请先根据这张任务、最新开发日志及前置依赖，帮我梳理它要解决什么、现在做到哪里、有哪些做法；先给建议和理由，未确定的地方给我两三个容易理解的选择。':'我想先商量下一步。请先查看已带入的项目日志、任务详情、依赖和运行记录，告诉我当前进展，并推荐现在最适合讨论的一张任务及理由。不要把待处理任务当成已完成，也不要推进标明暂停或待定的事项；只在确实需要我选择时问一个关键问题。';
  input.value=(input.value.trim()?input.value.trim()+'\n\n':'')+AgentBoardI18n.choose(chineseRequest,task?'Based on this task, the latest development logs and its dependencies, clarify the problem, current progress and possible approaches. Give recommendations and reasons first, with two or three clear choices for unresolved decisions.':'Read the included project logs, task details, dependencies and execution records. Summarize progress and recommend the next task to discuss with reasons. Do not treat pending tasks as complete or advance paused or undecided work. Ask one key question only if a decision is needed.');
  $('#chat-form').requestSubmit();
};
$('#new-chat').onclick=()=>{
  if(chatSending)return;
  currentChat=null; chatData=null; lastMessageSignature='';
  chatSelectionChanged=false;
  $('#chat-input').value=''; $('#chat-source').checked=false;
  $('#chat-task').value='';
  setChatMode($('#chat-mode').value);
  refreshChat();
};
$('#chat-form').onsubmit=async e=>{
  e.preventDefault();
  const input=$('#chat-input'), text=input.value.trim();
  if(!text||chatSending)return;
  if(chatSelectionChanged)return toast('正在读取这段对话，请稍后发送。');
  chatSending=true; $('#chat-send').disabled=true;
  try{
    if(!currentChat){
      const created=await api('/api/chats',{project_id:chatProject,agent:$('#chat-agent').value==='all'?'deepseek':$('#chat-agent').value,mode:$('#chat-mode').value,include_source:$('#chat-source').checked,task_id:$('#chat-task').value,members:selectedMembers()});
      currentChat=created.data.id;
    }
    await api(`/api/chats/${currentChat}/send`,{message:text,agent:$('#chat-agent').value});
    input.value='';
    await refresh();
  }catch(err){toast(err.message);}finally{chatSending=false;await refreshChat();}
};
$('#chat-input').onkeydown=e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();$('#chat-form').requestSubmit();}};
$('#chat-stop').onclick=async()=>{try{await api(`/api/chats/${currentChat}/stop`,{});await refreshChat();}catch(e){toast(e.message);}};
$('#chat-discuss').onclick=()=>{
  const input=$('#chat-input');
  if(new RegExp('^/('+profiles().map(p=>p.id).concat('ds').join('|')+')(\\s|$)','i').test(input.value.trim()))return toast('这是一条定向消息，请直接发送；需要群聊讨论时再使用 /讨论。');
  input.value=`${AgentBoardI18n.choose('/讨论','/discuss')} ${$('#group-rounds').value} ${input.value.trim()||AgentBoardI18n.choose('请围绕当前方案互相审查，明确分歧与下一步建议，不要执行开发。','Review the current plan together, identify disagreements and recommend next steps. Do not implement changes.')}`;
  $('#chat-form').requestSubmit();
};
$('#chat-organize').onclick=()=>{
  const input=$('#chat-input');
  input.value=(input.value.trim()?input.value.trim()+'\n\n':'')+AgentBoardI18n.choose('请结合关联任务、最新开发日志和我们的讨论，整理当前共识：目标、已选方案、修改范围、验收条件、尚待决定的问题和下一步。区分已确定与未确定内容，先不要执行。','Using the linked task, latest development logs and our discussion, summarize the current consensus: goal, chosen approach, allowed scope, acceptance criteria, open decisions and next steps. Distinguish agreed points from unresolved ones. Do not execute yet.');
  $('#chat-form').requestSubmit();
};
$('#chat-consensus').onclick=()=>{
  if(!chatData)return;
  const latest=(chatData.messages||[]).filter(m=>m.role==='assistant').at(-1);
  $('#consensus-input').value=(chatData.consensus||latest?.text||'').slice(0,12000);
  $('#consensus-dialog').showModal();
};
$('#consensus-form').onsubmit=async e=>{
  e.preventDefault();try{await api(`/api/chats/${currentChat}/consensus`,{consensus:$('#consensus-input').value});$('#consensus-dialog').close();await refreshChat();toast('当前共识已保存，更新关联任务后会带入执行。');}catch(err){toast(err.message);}
};
$('#chat-to-task').onclick=()=>{
  if(!chatData)return;
  const messages=chatData.messages||[];
  const latest=messages.filter(m=>m.role==='assistant').at(-1);
  const question=messages.filter(m=>m.role==='user').at(-1);
  const original=messages.find(m=>m.role==='user');
  const context=messages.slice(-8).map(m=>`${m.role==='user'?'用户':m.role==='system'?'Python监督':agentName(m.agent)}：${m.text}`).join('\n\n');
  $('#chat-dialog').close(); activeProject=chatProject;
  const linked=state.tasks.find(t=>t.id===chatData.task_id);
  const update=linked&&['ready','blocked'].includes(linked.status);
  openTaskForm(update?linked:null);
  const form=$('#task-form');
  form.elements.title.value=update?linked.title:chatData.title.slice(0,120);
  form.elements.description.value=`来自对话：${chatData.id}\n\n${chatData.consensus_needs_review?'旧共识（关联任务改变后尚待核对）':'当前共识'}：\n${chatData.consensus||'尚未保存；请核对下列讨论'}\n\n初始目标：\n${original?.text||linked?.description||''}\n\n最新要求：\n${question?.text||''}\n\n讨论方案：\n${latest?.text||''}\n\n近期讨论（供核对约束）：\n${context.slice(-24000)}`;
  form.elements.agent.value=$('#chat-agent').value==='all'?(linked?.agent||'deepseek'):$('#chat-agent').value;
  form.elements.discussion_id.value=chatData.id;
  toast('已填入任务草稿；补齐范围和验收条件后创建。');
};
setInterval(refreshChat,2000);
