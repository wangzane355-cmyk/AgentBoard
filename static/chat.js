let currentChat = null;
let chatData = null;
let chatProject = null;
let chatRefreshing = null;
let chatSending = false;
let lastMessageSignature = '';
let lastSessionSignature = '';
let chatSelectionChanged = false;
let chatViewVersion = 0;
let chatProjectBusy = false;
let chatAttachTarget = null;
let chatCreateTarget = null;
let chatCreatedProject = null;
let chatConsensusTarget = null;
const chatDrafts = new Map();
const chatText = (zh, en) => AgentBoardI18n.choose(zh, en);
const chatScopeId = value => typeof value === 'string' && value ? value : null;
const chatDraftKey = () => currentChat ? `chat:${currentChat}` : `scope:${chatProject || 'free'}`;
const chatCompactLayout = window.matchMedia('(max-width:760px)');
function configureChatLayout(){ $('#chat-settings').open = !chatCompactLayout.matches; }
chatCompactLayout.addEventListener('change', configureChatLayout);

function agentName(agent){ return agent ? profileName(agent) : chatText('Python监督', 'Python supervisor'); }
function chatBubblePalettes(messages){
  const room = chatData?.mode === 'group' ? chatData.members || [] : [];
  const agents = [...new Set([...room, ...messages.filter(message => message.role === 'assistant').map(message => message.agent)])]
    .filter(agent => typeof agent === 'string' && agent).sort();
  const colors = {codex:'codex', deepseek:'deepseek'};
  const pool = ['teal','amber','rose','slate','codex','deepseek'];
  const used = new Set(agents.filter(agent => agent === 'codex' || agent === 'deepseek'));
  for(const agent of agents.filter(agent => agent !== 'codex' && agent !== 'deepseek')){
    const hash = [...agent].reduce((value, char) => (Math.imul(value, 31) + char.codePointAt(0)) >>> 0, 0);
    const choices = pool.map((_, index) => pool[(hash + index) % pool.length]);
    colors[agent] = choices.find(color => !used.has(color)) || choices[0];
    used.add(colors[agent]);
  }
  return colors;
}
function saveChatDraft(){ chatDrafts.set(chatDraftKey(), $('#chat-input').value); }
function restoreChatDraft(){ $('#chat-input').value = chatDrafts.get(chatDraftKey()) || ''; }
function chatProjectName(){ return state.projects.find(project => project.id === chatProject)?.name || chatText('自由讨论', 'Free discussion'); }
function setChatMode(mode, agent = null){
  const group = mode === 'group';
  $('#chat-mode').value = group ? 'group' : 'single';
  if(typeof renderAgents === 'function') renderAgents();
  $('#chat-agent').querySelector('option[value="all"]').hidden = !group;
  $('#chat-agent').value = group ? (agent || 'all') : (agent && agent !== 'all' ? agent : 'codex');
  $('#group-chat-help').classList.toggle('hidden', !group);
  $('#group-discussion-controls').classList.toggle('hidden', !group);
  $('#chat-agent').setAttribute('aria-label', group ? chatText('群聊回复对象', 'Room recipient') : chatText('对话执行者', 'Chat executor'));
  if(typeof renderRoomMembers === 'function') renderRoomMembers();
  updateChatSendSummary();
}
function chatProjectOptions(selected, includeFree = true){
  return (includeFree ? `<option value="">${esc(chatText('自由讨论（暂不关联项目）', 'Free discussion (no project yet)'))}</option>` : '') +
    state.projects.map(project => `<option data-chat-user-value value="${esc(project.id)}" ${project.id === selected ? 'selected' : ''}>${esc(project.name)}</option>`).join('');
}
function renderChatScope(){
  const select = $('#chat-scope');
  const signature = JSON.stringify([chatProject, state.projects.map(project => [project.id, project.name]), AgentBoardI18n.language]);
  if(select.dataset.signature !== signature){
    select.innerHTML = chatProjectOptions(chatProject);
    select.value = chatProject || '';
    select.dataset.signature = signature;
  }
  select.disabled = chatSending || chatProjectBusy;
  $('#chat-project-name').textContent = chatProjectName();
  $('#chat-project-name').setAttribute('data-chat-user-value', '');
  $('#chat-scope-note').textContent = chatProject
    ? chatText('新消息会带上这个项目的资料。切换范围会打开另一段对话。', 'New messages include this project’s context. Switching scope opens another conversation.')
    : chatText('先聊想法，不读取项目文件；确定方向后再关联或新建项目。', 'Explore an idea without project files, then link it to a project when ready.');
  const running = chatData?.status === 'running';
  $('#chat-attach-open').textContent = chatProject ? chatText('更改当前讨论关联', 'Change conversation link') : chatText('将当前讨论关联到项目', 'Link this conversation to a project');
  $('#chat-project-from-discussion').textContent = chatText('从这段讨论新建项目', 'Create a project from this discussion');
  $('#chat-attach-open').disabled = !currentChat || running || chatSending || chatProjectBusy || !state.projects.length;
  $('#chat-project-from-discussion').disabled = !currentChat || running || chatSending || chatProjectBusy;
  $('#chat-new-project').disabled = chatSending || chatProjectBusy;
  const background = (state.chats || []).filter(chat => chat.status === 'running' && chat.id !== currentChat).length;
  $('#chat-background-status').textContent = background ? chatText(`另有 ${background} 段对话仍在后台回复。`, `${background} other conversation${background === 1 ? ' is' : 's are'} still replying in the background.`) : '';
}
function rebuildChatTasks(selected = ''){
  const tasks = chatProject ? state.tasks.filter(task => task.project_id === chatProject) : [];
  const signature = JSON.stringify([chatProject, tasks.map(task => [task.id, task.title]), AgentBoardI18n.language]);
  const select = $('#chat-task');
  if(select.dataset.signature !== signature){
    select.innerHTML = `<option value="">${esc(chatText('先聊想法，暂不关联任务', 'Discuss first without linking a task'))}</option>` + tasks.map(task => `<option value="${esc(task.id)}">${esc(task.title)}</option>`).join('');
    select.dataset.signature = signature;
  }
  select.value = tasks.some(task => task.id === selected) ? selected : '';
}
function resetChatView(){
  chatViewVersion++;
  chatRefreshing = null;
  lastMessageSignature = '';
  lastSessionSignature = '';
  chatSelectionChanged = false;
  $('#chat-messages').innerHTML = '';
  $('#chat-status').textContent = '';
}
function beginNewChat(projectId, {draft, mode = 'single'} = {}){
  saveChatDraft();
  chatProject = chatScopeId(projectId);
  currentChat = null;
  chatData = null;
  resetChatView();
  rebuildChatTasks();
  $('#chat-source').checked = false;
  setChatMode(mode);
  if(draft !== undefined){ $('#chat-input').value = draft; saveChatDraft(); }
  else restoreChatDraft();
  renderChatScope();
}
async function showChat(taskId = '', mode = 'single', projectId = null){
  if(typeof taskId !== 'string') taskId = '';
  const task = state.tasks.find(item => item.id === taskId);
  const scope = task?.project_id || chatScopeId(projectId);
  beginNewChat(scope, {mode});
  if(task){
    const existing = (state.chats || []).filter(chat => chat.project_id === scope && (chat.task_id === taskId || (chat.id === task.discussion_id && !chat.task_id))).at(-1);
    if(existing){ currentChat = existing.id; chatSelectionChanged = true; restoreChatDraft(); }
    rebuildChatTasks(taskId);
  }
  configureChatLayout();
  if(!$('#chat-dialog').open) $('#chat-dialog').showModal();
  await refreshChat();
}
async function openSavedChat(id){
  if(chatSending || chatProjectBusy) return;
  const saved = (state.chats || []).find(chat => chat.id === id);
  if(!saved) return;
  saveChatDraft();
  chatProject = chatScopeId(saved.project_id);
  currentChat = id;
  chatData = null;
  resetChatView();
  chatSelectionChanged = true;
  rebuildChatTasks(saved.task_id || '');
  restoreChatDraft();
  configureChatLayout();
  if(!$('#chat-dialog').open) $('#chat-dialog').showModal();
  updateChatControls();
  await refreshChat();
  document.dispatchEvent(new CustomEvent('agentboard:chat-selected'));
}
function updateChatFocus(){
  const task = state.tasks.find(item => item.id === $('#chat-task').value && item.project_id === chatProject);
  $('#chat-focus-title').textContent = task
    ? chatText(`正在商量：${task.title}`, `Discussing: ${task.title}`)
    : chatProject ? chatText(`正在商量：${chatProjectName()}的下一步`, `Planning next steps: ${chatProjectName()}`) : chatText('先把想法聊清楚', 'Explore your idea first');
  $('#chat-start-plan').textContent = task ? chatText('先帮我梳理这张任务', 'Help clarify this task') : chatProject ? chatText('帮我判断下一步', 'Help plan the next step') : chatText('帮我梳理这个想法', 'Help shape this idea');
  const note = $('#chat-focus-title').nextElementSibling;
  if(note) note.textContent = chatProject ? chatText('自动带入已关联日志、任务目标、依赖和进度，无需重新介绍。', 'Linked references, tasks, dependencies and progress are included automatically.') : chatText('可以直接说想法，不需要先准备项目文件夹。', 'Start with an idea; a project folder can come later.');
}
function chatSendRouting(message = $('#chat-input').value,forDisplay = false){
  const catalog = typeof profiles === 'function' ? profiles() : [{id:'codex',name:'Codex'},{id:'deepseek',name:'DeepSeek'}];
  const members = currentChat && Array.isArray(chatData?.members) ? chatData.members : typeof selectedMembers === 'function' ? selectedMembers() : ['codex','deepseek'];
  const resolve = forDisplay ? AgentBoardChatRouting.resolveComposer : AgentBoardChatRouting.resolveSend;
  return resolve({mode:$('#chat-mode').value,agent:$('#chat-agent').value,message,running:chatData?.status === 'running',batch:chatData?.batch,
    selectedRounds:$('#group-rounds').value,members,agentIds:catalog.filter(profile => profile.enabled !== false).map(profile => profile.id),
    agentNames:Object.fromEntries(catalog.map(profile => [profile.id,profile.name]))});
}
function updateChatSendSummary(){
  if(!$('#chat-send-summary')) return;
  const routing = chatSendRouting($('#chat-input').value,true), running = chatData?.status === 'running';
  const label = chatText(routing.labelZh,routing.labelEn);
  if($('#chat-send-summary').textContent !== label) $('#chat-send-summary').textContent = label;
  $('#chat-send-summary').classList.toggle('chat-send-invalid',Boolean(routing.invalid));
  $('#group-discussion-controls').classList.toggle('hidden',$('#chat-mode').value !== 'group');
  $('#group-rounds').disabled = running || chatSending || routing.directed || routing.kind === 'broadcast' || routing.explicitRounds;
  $('#group-rounds').title = routing.directed ? chatText('指定的 Agent 只回复一次。','A directed message gets one reply.')
    : routing.kind === 'broadcast' ? chatText('这条消息让全体成员各回复一次。','This message asks each member to reply once.')
    : routing.explicitRounds ? chatText('这条消息已指定讨论轮数。','The message already specifies the round count.') : '';
  $('#chat-send-limit-note').classList.toggle('hidden',routing.kind !== 'discussion');
  $('#chat-send-limit-note').textContent = chatText('每轮每位回复一次；每批讨论最多25分钟，可提前结束。','One reply per member each round; 25 minutes for the whole discussion batch, which may end early.');
}
function updateChatControls(){
  const running = chatData?.status === 'running';
  const messages = chatData?.messages || [];
  $('#chat-task').disabled = !chatProject || running || chatSending;
  $('#chat-agent').disabled = running || chatSending;
  $('#chat-mode').disabled = Boolean(currentChat) || running || chatSending;
  updateChatSendSummary();
  $('#chat-source').disabled = !chatProject || Boolean(currentChat) || chatSending;
  if(!chatProject) $('#chat-source').checked = false;
  else if(chatData) $('#chat-source').checked = Boolean(chatData.include_source);
  $('#chat-send').disabled = running || chatSending || chatSelectionChanged;
  $('#chat-send').textContent = running ? chatText('正在回复…', 'Replying…') : chatText('发送', 'Send');
  $('#chat-input').disabled = chatSending;
  $('#chat-stop').classList.toggle('hidden', !running);
  $('#new-chat').disabled = chatSending || chatProjectBusy;
  $('#chat-to-task').disabled = !chatProject || running || chatSending || !messages.some(message => message.role === 'assistant');
  $('#chat-to-task').title = chatProject ? '' : chatText('先将讨论关联到项目，再创建任务。', 'Link this discussion to a project before creating a task.');
  const linked = state.tasks.find(task => task.id === chatData?.task_id && task.project_id === chatProject);
  $('#chat-to-task').textContent = linked && ['ready', 'blocked'].includes(linked.status) ? chatText('更新关联任务', 'Update linked task') : chatText('转成任务卡', 'Create task draft');
  $('#chat-organize').disabled = running || chatSending || !messages.length;
  $('#chat-start-plan').disabled = running || chatSending;
  $('#chat-consensus').disabled = running || chatSending || !currentChat;
  $('#chat-context-note').textContent = chatProject
    ? chatText('默认携带项目名称和任务概况。历史自动保存；每次回复携带最近最多约4.2万字，每批讨论最多25分钟。', 'Project and task context is included. History is saved automatically; each reply includes up to about 42,000 recent characters. Each discussion batch lasts at most 25 minutes.')
    : chatText('自由讨论只带入当前聊天记录，不读取项目源码。历史自动保存；每批讨论最多25分钟。', 'Free discussion uses this conversation without project source files. History is saved automatically; each discussion batch lasts at most 25 minutes.');
  updateChatFocus();
  renderChatScope();
  document.dispatchEvent(new CustomEvent('agentboard:chat-layout'));
}
async function refreshChat(){
  if(!$('#chat-dialog').open) return;
  if(chatProject && !state.projects.some(project => project.id === chatProject)){
    const draft = $('#chat-input').value;
    beginNewChat(null, {draft});
    toast(chatText('原项目已不在工作区，已切到自由讨论。未发送的文字已保留。', 'The project is no longer in the workspace. Your unsent text is preserved in free discussion.'));
  }
  const version = chatViewVersion;
  if(chatRefreshing === version) return;
  chatRefreshing = version;
  try{
    renderChatScope();
    const sessions = (state.chats || []).filter(chat => chatScopeId(chat.project_id) === chatProject).slice().reverse();
    const sessionSignature = JSON.stringify([chatProject, currentChat, sessions, AgentBoardI18n.language]);
    if(sessionSignature !== lastSessionSignature){
      $('#chat-sessions').innerHTML = sessions.map(chat => `<button class="chat-session ${chat.id === currentChat ? 'active' : ''}" data-chat="${esc(chat.id)}"><strong>${esc(chat.title)}</strong><small>${chat.mode === 'group' ? esc((chat.members || []).map(agentName).join(' / ')) : esc(agentName(chat.agent))} · ${chat.status === 'running' ? chatText('回复中', 'Replying') : chat.status === 'error' ? chatText('需查看', 'Needs attention') : chatText('已保存', 'Saved')}</small></button>`).join('') || `<p class="hint">${chatProject ? chatText('这个项目还没有对话', 'No conversations in this project yet') : chatText('还没有自由讨论，直接说说你的想法吧。', 'No free discussions yet. Share an idea to begin.')}</p>`;
      $('#chat-sessions').querySelectorAll('[data-chat]').forEach(button => button.onclick = () => openSavedChat(button.dataset.chat));
      lastSessionSignature = sessionSignature;
    }
    if(currentChat){
      const id = currentChat;
      const fetched = await api(`/api/chats/${id}`);
      if(version !== chatViewVersion || id !== currentChat) return;
      chatData = fetched;
      if(chatScopeId(fetched.project_id) !== chatProject){
        chatProject = chatScopeId(fetched.project_id);
        lastSessionSignature = '';
      }
      if(chatSelectionChanged){ setChatMode(fetched.mode || 'single', fetched.mode === 'group' ? 'all' : fetched.agent); chatSelectionChanged = false; }
    }
    if(version !== chatViewVersion) return;
    const messages = chatData?.messages || [];
    const signature = JSON.stringify([messages, AgentBoardI18n.language]);
    if(signature !== lastMessageSignature || !$('#chat-messages').innerHTML){
      const box = $('#chat-messages'), nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 90;
      const palettes = chatBubblePalettes(messages);
      box.innerHTML = messages.map(message => `<article ${message.role === 'assistant' && message.agent ? `data-chat-palette="${esc(palettes[message.agent] || '')}"` : ''} class="chat-message ${message.role === 'user' ? 'user' : message.role === 'system' ? 'system' : 'assistant'} ${message.agent === 'codex' ? 'from-codex' : message.agent === 'deepseek' ? 'from-deepseek' : ''}"><div class="chat-message-label">${esc(message.role === 'user' ? chatText('你', 'You') : message.role === 'system' ? chatText('Python监督', 'Python supervisor') : agentName(message.agent))}${message.audience && chatData?.mode === 'group' ? ` <span class="chat-audience">→ ${message.directed ? esc(message.audience.map(agentName).join('、')) : chatText('全体', 'Everyone')}</span>` : ''}${message.simulation ? ' [SIMULATION]' : ''}${message.handoff_to ? ` <span class="chat-audience">${chatText('请 ', 'Invite ')}${esc(agentName(message.handoff_to))}${chatText(' 接话', ' to reply')}</span>` : ''}</div>${message.agent === 'codex' ? modelRecordLabel(message.model_record) : ''}<div data-chat-user-value>${esc(message.text)}</div></article>`).join('') || `<div class="chat-empty">${chatProject ? chatText('先说说你的想法', 'Share your idea') : chatText('想做什么，先聊聊', 'Start with an idea')}<small>${chatProject ? chatText('项目资料会随消息带入', 'Project references are included with your messages') : chatText('不用先建项目，确定方向后再开始', 'A project can come after you choose a direction')}</small></div>`;
      if(nearBottom || lastMessageSignature === '') box.scrollTop = box.scrollHeight;
      lastMessageSignature = signature;
    }
    rebuildChatTasks(chatData?.task_id || $('#chat-task').value);
    if(typeof renderRoomMembers === 'function') renderRoomMembers();
    updateChatControls();
    const linked = state.tasks.find(task => task.id === chatData?.task_id && task.project_id === chatProject);
    const project = state.projects.find(item => item.id === chatProject);
    const referenceCount = (project?.context_files || []).length + (project?.context_urls || []).length + (linked?.context_files || []).length + (linked?.context_urls || []).length;
    $('#chat-reference-status').textContent = !chatProject ? chatText('未关联项目资料。', 'No project references are linked.') : chatData?.context_read_at
      ? chatText(`最近自动读取 ${chatData.context_sources?.length || 0} 项资料 · `, `Last refreshed ${chatData.context_sources?.length || 0} references · `) + new Date(chatData.context_read_at).toLocaleString() + (chatData.consensus ? (chatData.consensus_needs_review ? chatText(' · 项目或任务已变，共识需核对', ' · Context changed; review consensus') : chatText(' · 已保存共识', ' · Consensus saved')) : '')
      : chatText(`已关联 ${referenceCount} 处资料，发送时自动读取；无需勾选源码。`, `${referenceCount} references linked; refreshed when sending. Source snapshot is optional.`);
    const running = chatData?.status === 'running', batch = chatData?.mode === 'group' ? chatData.batch : null;
    const finished = batch && ['done','stopped','error'].includes(batch.status);
    const batchSummary = finished ? AgentBoardChatRouting.describeBatch(batch) : null;
    $('#chat-status').textContent = batchSummary ? chatText(batchSummary.labelZh,batchSummary.labelEn)+(chatData?.error ? ' '+chatData.error : '') : chatData?.error || '';
    if(running){
      const phase = chatData.phase === 'waiting_reply' ? chatText('等待执行器回复', 'Waiting for executor reply') : chatText('正在准备执行器', 'Preparing executor');
      const started = batch?.started_at || chatData.reply_started_at || chatData.updated_at;
      $('#chat-status').textContent = `${phase} · ${agentName(batch?.active_agent || chatData.agent)} · ${elapsed(started)} / 25:00${batch ? ` · ${batch.completed}/${batch.max_replies}` : ''} · ${chatText('关闭面板或切换范围后仍会继续，可随时停止', 'Continues when closed or when you switch scope; stop anytime')}`;
    }
    $('#chat-status').classList.toggle('chat-error', Boolean(chatData?.error));
  }catch(error){
    if(version === chatViewVersion){ chatSelectionChanged = false; toast(error.message); updateChatControls(); }
  }finally{ if(chatRefreshing === version) chatRefreshing = null; }
}

$('#open-chat').onclick = () => showChat();
$('#plan-next').onclick = () => showChat('', 'single', activeProject);
$('#chat-dialog').addEventListener('close', saveChatDraft);
$('#chat-input').addEventListener('input', () => { saveChatDraft(); updateChatSendSummary(); });
$('#group-rounds').onchange = updateChatSendSummary;
$('#chat-scope').onchange = async event => {
  if(chatSending || chatProjectBusy) return;
  beginNewChat(event.target.value);
  await refreshChat();
};
$('#chat-mode').onchange = () => { setChatMode($('#chat-mode').value); updateChatControls(); };
$('#chat-agent').onchange = updateChatControls;
$('#new-chat').onclick = async () => {
  if(chatSending || chatProjectBusy) return;
  const draft = $('#chat-input').value;
  beginNewChat(chatProject, {draft, mode: $('#chat-mode').value});
  await refreshChat();
  document.dispatchEvent(new CustomEvent('agentboard:chat-selected'));
};
$('#chat-task').onchange = async () => {
  updateChatFocus();
  if(!currentChat || !chatProject) return;
  const id = currentChat, version = chatViewVersion, taskId = $('#chat-task').value;
  chatSending = true; updateChatControls();
  try{
    const result = await api(`/api/chats/${id}/task`, {task_id: taskId});
    if(id === currentChat && version === chatViewVersion) chatData = result.data;
    await refresh();
    toast(chatText('已关联到这张任务，之前的讨论会保留。', 'Task linked; previous discussion is preserved.'));
  }catch(error){ if(id === currentChat) $('#chat-task').value = chatData?.task_id || ''; toast(error.message); }
  finally{ chatSending = false; updateChatControls(); await refreshChat(); }
};
$('#chat-start-plan').onclick = () => {
  const input = $('#chat-input'), task = state.tasks.find(item => item.id === $('#chat-task').value && item.project_id === chatProject);
  const request = !chatProject
    ? chatText('我想先聊清楚这个想法。请根据我们已有的讨论，帮我整理想解决的问题、可能的做法和最小的下一步。不需要读取项目文件或开始开发；还没确定的地方给我两三个容易理解的选择。', 'Help shape this idea using our conversation: identify the problem, possible approaches and the smallest next step. Do not read project files or start implementation. Offer two or three clear choices for unresolved points.')
    : task ? chatText('请根据这张任务、已带入的开发日志及依赖，帮我梳理目标、当前进展和可能做法。先给建议和理由，未确定的地方给我两三个容易理解的选择。不要执行开发。', 'Using this task, its supplied logs and dependencies, clarify the goal, current progress and possible approaches. Give recommendations and reasons, with two or three clear choices for open questions. Do not implement changes.')
    : chatText('请查看已带入的项目资料、任务详情、依赖和运行记录，说明当前进展，推荐最适合先做的一件小事及理由。不要把待处理任务当成已完成，也不要推进暂停或待定事项。先讨论，不改文件。', 'Read the supplied project context, tasks, dependencies and run records. Explain progress and recommend one small next step with reasons. Do not treat pending tasks as complete or advance paused work. Discuss without changing files.');
  input.value = (input.value.trim() ? input.value.trim() + '\n\n' : '') + request;
  saveChatDraft(); $('#chat-form').requestSubmit();
};
$('#chat-form').onsubmit = async event => {
  event.preventDefault();
  const input = $('#chat-input'), text = input.value.trim();
  if(!text || chatSending || chatData?.status === 'running') return;
  if(chatSelectionChanged) return toast(chatText('正在读取这段对话，请稍后发送。', 'Loading the conversation; please send again shortly.'));
  const version = chatViewVersion, projectId = chatProject, routing = chatSendRouting(text);
  chatSending = true; updateChatControls();
  try{
    if(!currentChat){
      const created = await api('/api/chats', {project_id: projectId, agent: $('#chat-agent').value === 'all' ? 'codex' : $('#chat-agent').value,
        mode: $('#chat-mode').value, include_source: Boolean(projectId && $('#chat-source').checked), task_id: projectId ? $('#chat-task').value : '', members: selectedMembers()});
      if(version !== chatViewVersion) return;
      currentChat = created.data.id;
      chatDrafts.delete(`scope:${projectId || 'free'}`);
      saveChatDraft();
    }
    const id = currentChat;
    const sent = await api(`/api/chats/${id}/send`, routing.body);
    if(version === chatViewVersion && id === currentChat){
      const accepted = sent.data ?? sent;
      if(accepted?.id === id) chatData = accepted;
      input.value = ''; saveChatDraft(); updateChatControls();
    }
    await refresh();
  }catch(error){ toast(error.message); }
  finally{ chatSending = false; updateChatControls(); await refreshChat(); }
};
$('#chat-input').onkeydown = event => { if((event.ctrlKey || event.metaKey) && event.key === 'Enter'){ event.preventDefault(); $('#chat-form').requestSubmit(); } };
$('#chat-stop').onclick = async () => { const id = currentChat; if(!id) return; try{ await api(`/api/chats/${id}/stop`, {}); await refresh(); await refreshChat(); }catch(error){ toast(error.message); } };
$('#chat-organize').onclick = () => {
  const input = $('#chat-input');
  input.value = (input.value.trim() ? input.value.trim() + '\n\n' : '') + (chatProject
    ? chatText('请结合关联任务、已带入的项目资料和我们的讨论，整理当前共识：目标、已选方案、修改范围、验收条件、尚待决定的问题和下一步。区分已确定与未确定内容，先不要执行。', 'Using the task, supplied project context and our discussion, summarize the goal, chosen approach, scope, checks, open decisions and next steps. Separate agreed points from unresolved ones. Do not execute yet.')
    : chatText('请整理我们的讨论：想解决的问题、已经确定的方向、还没确定的选择，以及最小的下一步。先不要读取项目文件或开始开发。', 'Summarize our idea, agreed direction, open choices and the smallest next step. Do not read project files or start implementation.'));
  saveChatDraft(); $('#chat-form').requestSubmit();
};
$('#chat-consensus').onclick = () => {
  if(!chatData) return;
  chatConsensusTarget = currentChat;
  const latest = (chatData.messages || []).filter(message => message.role === 'assistant').at(-1);
  $('#consensus-input').value = (chatData.consensus || latest?.text || '').slice(0, 12000);
  $('#consensus-dialog').showModal();
};
$('#consensus-form').onsubmit = async event => {
  event.preventDefault();
  if(!chatConsensusTarget) return;
  try{
    await api(`/api/chats/${chatConsensusTarget}/consensus`, {consensus: $('#consensus-input').value});
    $('#consensus-dialog').close(); await refreshChat();
    toast(chatText('当前共识已保存。', 'Consensus saved.'));
  }catch(error){ toast(error.message); }
};
$('#chat-to-task').onclick = () => {
  if(!chatData || !chatProject) return toast(chatText('先将讨论关联到项目，再创建任务。', 'Link this discussion to a project before creating a task.'));
  saveChatDraft();
  const messages = chatData.messages || [], latest = messages.filter(message => message.role === 'assistant').at(-1), question = messages.filter(message => message.role === 'user').at(-1), original = messages.find(message => message.role === 'user');
  const context = messages.slice(-8).map(message => `${message.role === 'user' ? chatText('用户', 'User') : message.role === 'system' ? chatText('Python监督', 'Python supervisor') : agentName(message.agent)}：${message.text}`).join('\n\n');
  $('#chat-dialog').close(); activeProject = chatProject;
  const linked = state.tasks.find(task => task.id === chatData.task_id && task.project_id === chatProject), update = linked && ['ready', 'blocked'].includes(linked.status);
  openTaskForm(update ? linked : null);
  const form = $('#task-form');
  form.elements.title.value = update ? linked.title : chatData.title.slice(0, 120);
  form.elements.description.value = `${chatText('来自对话', 'Conversation')}: ${chatData.id}\n\n${chatData.consensus_needs_review ? chatText('旧共识（关联改变后尚待核对）', 'Earlier consensus (link changed; review required)') : chatText('当前共识', 'Consensus')}:\n${chatData.consensus || chatText('尚未保存；请核对下列讨论', 'Not saved; review the discussion below')}\n\n${chatText('初始目标', 'Original goal')}:\n${original?.text || linked?.description || ''}\n\n${chatText('最新要求', 'Latest request')}:\n${question?.text || ''}\n\n${chatText('讨论方案', 'Proposed approach')}:\n${latest?.text || ''}\n\n${chatText('近期讨论（供核对约束）', 'Recent discussion (check constraints)')}:\n${context.slice(-24000)}`;
  form.elements.agent.value = $('#chat-agent').value === 'all' ? (linked?.agent || 'codex') : $('#chat-agent').value;
  form.elements.discussion_id.value = chatData.id;
  toast(chatText('已填入任务草稿；补齐范围和验收条件后创建。', 'Draft prepared. Set scope and acceptance rules before creating the task.'));
};

async function linkCurrentConversation(targetId, projectId){
  const draft = $('#chat-input').value;
  saveChatDraft();
  if(chatData?.id === targetId && chatScopeId(chatData.project_id) === chatScopeId(projectId)) return;
  const result = await api(`/api/chats/${targetId}/project`, {project_id: chatScopeId(projectId)});
  await refresh();
  currentChat = targetId;
  chatData = result.data;
  chatProject = chatScopeId(chatData.project_id);
  resetChatView();
  setChatMode(chatData.mode || 'single', chatData.mode === 'group' ? 'all' : chatData.agent);
  rebuildChatTasks(chatData.task_id || '');
  $('#chat-input').value = draft; saveChatDraft();
  await refreshChat();
}
$('#chat-attach-open').onclick = () => {
  if(!currentChat || chatData?.status === 'running') return;
  chatAttachTarget = currentChat;
  $('#chat-attach-project').innerHTML = chatProjectOptions(chatProject);
  $('#chat-attach-project').value = chatProject || state.projects[0]?.id || '';
  $('#chat-attach-error').classList.add('hidden');
  $('#chat-attach-dialog').showModal();
};
$('#chat-attach-form').onsubmit = async event => {
  event.preventDefault();
  if(!chatAttachTarget || chatProjectBusy) return;
  chatProjectBusy = true; $('#chat-attach-submit').disabled = true; updateChatControls();
  try{
    await linkCurrentConversation(chatAttachTarget, $('#chat-attach-project').value);
    $('#chat-attach-dialog').close();
    toast(chatText('讨论关联已更新，历史记录已保留。', 'Conversation link updated; history preserved.'));
  }catch(error){ $('#chat-attach-error').textContent = error.message; $('#chat-attach-error').classList.remove('hidden'); }
  finally{ chatProjectBusy = false; $('#chat-attach-submit').disabled = false; updateChatControls(); }
};
function updateProjectDialogText(){
  const attaching = Boolean(chatCreateTarget);
  $('#chat-project-create-title').textContent = attaching ? chatText('从这段讨论新建项目', 'Create a project from this discussion') : chatText('新建项目', 'Create a project');
  $('#chat-project-create-note').textContent = attaching
    ? chatText('创建成功后，会把这段讨论关联到新项目。聊天历史和未发送的文字会保留。', 'After creation, this conversation will be linked to the new project. History and unsent text are preserved.')
    : !$('#chat-dialog').open && window.matchMedia('(max-width:760px)').matches
      ? chatText('创建成功后进入项目页面，可以继续讨论、安排任务或添加资料。', 'After creation, open the project page to discuss, assign tasks or add references.')
      : chatText('创建成功后，会切到新项目的新对话；当前聊天记录和未发送的文字会保留。', 'After creation, a new conversation opens for this project. The current history and unsent text are preserved.');
  $('#chat-project-create-submit').textContent = chatCreatedProject ? chatText('重试关联已创建的项目', 'Retry linking the created project') : attaching ? chatText('创建并关联讨论', 'Create & link conversation') : chatText('创建项目', 'Create project');
}
function updateChatProjectFolderMode(){
  const form=$('#chat-project-create-form'), automatic=form.elements.folder_mode.value==='auto';
  $('#chat-project-auto-folder').classList.toggle('hidden', !automatic);
  $('#chat-project-custom-folder').classList.toggle('hidden', automatic);
  form.elements.path.required=!automatic;
  form.elements.path.disabled=automatic || Boolean(chatCreatedProject);
  form.elements.create_directory.disabled=automatic || Boolean(chatCreatedProject);
  form.elements.folder_mode.disabled=Boolean(chatCreatedProject);
  $('#chat-project-folder-note').textContent=automatic
    ? chatText('创建项目不会启动模型或开发任务。可以继续讨论，准备好后再派任务。','Creating a project does not start a model or task. Continue discussing, then start work when ready.')
    : chatText('使用已有文件夹时不用勾选。创建项目不会启动模型或开发任务。','Leave unchecked for an existing folder. Creating a project does not start a model or task.');
}
$('#chat-project-folder-mode').onchange=updateChatProjectFolderMode;
function openChatProjectDialog(fromCurrent){
  if(chatSending || chatProjectBusy || fromCurrent && (!currentChat || chatData?.status === 'running')) return;
  chatCreateTarget = fromCurrent ? currentChat : null;
  chatCreatedProject = null;
  const form = $('#chat-project-create-form'); form.reset();
  form.querySelectorAll('input').forEach(input => input.disabled = false);
  form.elements.folder_mode.value=(window.AgentBoardPhone?.remote || document.documentElement.dataset.phoneClient==='remote')?'auto':'custom';
  updateChatProjectFolderMode();
  $('#chat-project-create-error').classList.add('hidden');
  updateProjectDialogText(); $('#chat-project-create-dialog').showModal();
}
$('#chat-new-project').onclick = () => openChatProjectDialog(false);
$('#chat-project-from-discussion').onclick = () => openChatProjectDialog(true);
$('#chat-project-create-form').onsubmit = async event => {
  event.preventDefault();
  if(chatProjectBusy) return;
  const form = event.target, draft = $('#chat-input').value, fromChat = $('#chat-dialog').open;
  if(!chatCreatedProject && !form.reportValidity()) return;
  chatProjectBusy = true; $('#chat-project-create-submit').disabled = true; updateChatControls();
  try{
    if(!chatCreatedProject){
      const folder=form.elements.folder_mode.value==='auto' ? {managed_directory:true} : {path:form.elements.path.value.trim(),create_directory:form.elements.create_directory.checked};
      const response = await api('/api/projects', {name: form.elements.name.value.trim(), ...folder, check: 'none', protected_paths: [], context_files: [], context_urls: []});
      chatCreatedProject = response.data;
      activeProject = chatCreatedProject.id;
      form.querySelectorAll('input').forEach(input => input.disabled = true);
      updateChatProjectFolderMode();
      await refresh();
    }
    if(chatCreateTarget) await linkCurrentConversation(chatCreateTarget, chatCreatedProject.id);
    else{ beginNewChat(chatCreatedProject.id, {draft}); await refreshChat(); }
    document.dispatchEvent(new CustomEvent('agentboard:project-created',{detail:{id:chatCreatedProject.id,fromChat}}));
    $('#chat-project-create-dialog').close();
    toast(chatText('项目已创建，可以继续讨论。', 'Project created. Continue the conversation when ready.'));
  }catch(error){
    $('#chat-project-create-error').textContent = chatCreatedProject ? chatText('项目已创建，关联尚未完成：', 'The project was created, but the conversation was not linked: ') + error.message : error.message;
    $('#chat-project-create-error').classList.remove('hidden');
  }finally{ chatProjectBusy = false; $('#chat-project-create-submit').disabled = false; updateProjectDialogText(); updateChatControls(); }
};
document.querySelectorAll('[data-chat-close]').forEach(button => button.onclick = () => {
  if(chatProjectBusy) return;
  document.getElementById(button.dataset.chatClose).close();
});
for(const dialog of [$('#chat-attach-dialog'), $('#chat-project-create-dialog')]) dialog.addEventListener('cancel', event => { if(chatProjectBusy) event.preventDefault(); });
function localizeChat(){
  for(const element of document.querySelectorAll('[data-chat-zh]')) element.textContent = chatText(element.dataset.chatZh, element.dataset.chatEn);
  renderChatScope();
  rebuildChatTasks(chatData?.task_id || $('#chat-task').value);
  updateProjectDialogText();
  updateChatProjectFolderMode();
  updateChatControls();
  lastMessageSignature = ''; lastSessionSignature = '';
  if($('#chat-dialog').open) refreshChat();
}
document.addEventListener('agentboard:language', localizeChat);
document.addEventListener('agentboard:render', () => { if($('#chat-dialog').open) refreshChat(); });
localizeChat();
setInterval(refreshChat, 2000);
