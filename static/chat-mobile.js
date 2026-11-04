/* A full-screen phone conversation. The existing chat still owns drafts and routing. */
(() => {
  'use strict';
  const dialog = document.querySelector('#chat-dialog');
  const input = document.querySelector('#chat-input');
  const settings = document.querySelector('#chat-settings');
  const back = document.querySelector('#chat-mobile-back');
  const options = document.querySelector('#chat-mobile-options');
  const title = document.querySelector('#chat-mobile-title');
  const subtitle = document.querySelector('#chat-mobile-subtitle');
  const main = dialog.querySelector('.chat-main');
  const compact = window.matchMedia('(max-width:760px)');
  const text = (zh, en) => AgentBoardI18n.choose(zh, en);
  let scheduled = false;
  let panelReading = null;
  let desktopInputLayout = null;
  let page = 'menu';
  const pageNames = () => ({menu:text('会话设置','Conversation settings'), context:text('项目与资料','Project & context'), members:text('聊天成员','Chat members'), history:text('历史对话','Conversation history'), actions:text('共识与任务','Consensus & tasks')});
  const menu = document.createElement('div');
  menu.id = 'chat-mobile-menu';
  dialog.querySelector('#chat-mobile-bar').after(menu);
  const groups = {
    context:'.chat-project-label,.chat-focus-panel,.chat-task-label,#chat-reference-status,#chat-source-label,#chat-context-note',
    members:'.chat-mode-controls,#chat-room-members,#group-chat-help',
    history:'.chat-history-head,#chat-sessions',
    actions:'.chat-reference-actions,#chat-to-task'
  };
  for(const [group,selector] of Object.entries(groups)) dialog.querySelectorAll(selector).forEach(el=>el.dataset.mobileGroup=group);
  let menuLanguage = '';
  function renderMenu() {
    if(menuLanguage===AgentBoardI18n.language) return;
    menuLanguage=AgentBoardI18n.language;
    const names=pageNames();
    const descriptions={context:text('切换项目、创建项目、选择资料','Switch projects, create a project, choose context'),members:text('单聊或群聊，选择参与的 Agent','Choose who takes part in the conversation'),history:text('查看这个讨论范围内的记录','Past conversations in this scope'),actions:text('保存讨论结论，再整理成任务','Save the outcome and prepare a task')};
    menu.innerHTML=Object.entries(descriptions).map(([key,description])=>`<button type="button" data-chat-mobile-page="${key}"><span><strong>${names[key]}</strong><small>${description}</small></span><span aria-hidden="true">›</span></button>`).join('');
  }
  function setPage(next) {
    page=next;
    dialog.dataset.mobilePage=next;
    dialog.querySelector('.chat-sidebar').scrollTop=0;
    update();
  }
  menu.addEventListener('click',event=>{
    const button=event.target.closest('[data-chat-mobile-page]');
    if(button)setPage(button.dataset.chatMobilePage);
  });
  const conversationKey = () => currentChat || `scope:${chatProject || 'free'}`;

  function setText(element, value) {
    if (element.textContent !== value) element.textContent = value;
  }
  function updateViewport() {
    const viewport = window.visualViewport;
    if (!compact.matches || !dialog.open || viewport && Math.abs(viewport.scale - 1) > .05) {
      dialog.style.removeProperty('--chat-mobile-height');
      dialog.style.removeProperty('--chat-mobile-top');
      return;
    }
    const height = Math.round(viewport?.height || window.innerHeight);
    const offset = Math.max(0, Math.round(viewport?.offsetTop || 0));
    for (const [property, value] of [['--chat-mobile-height', `${height}px`], ['--chat-mobile-top', `${offset}px`]]) {
      if (dialog.style.getPropertyValue(property) !== value) dialog.style.setProperty(property, value);
    }
  }
  function resizeInput() {
    if (!compact.matches) {
      if (desktopInputLayout) {
        input.rows = desktopInputLayout.rows;
        for (const [property, value] of [['height', desktopInputLayout.height], ['overflow-y', desktopInputLayout.overflow]]) {
          if (value) input.style.setProperty(property, value);
          else input.style.removeProperty(property);
        }
        desktopInputLayout = null;
      }
      return;
    }
    if (!desktopInputLayout) desktopInputLayout = {rows:input.rows, height:input.style.height, overflow:input.style.overflowY};
    input.rows = 1;
    if (!dialog.open || !input.getClientRects().length) return;
    const box = dialog.querySelector('#chat-messages');
    const followBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 90;
    input.style.height = 'auto';
    const maximum = Math.min(120, Math.max(64, Math.round((window.visualViewport?.height || window.innerHeight) * .24)));
    const border = input.offsetHeight - input.clientHeight;
    const height = Math.max(44, Math.min(maximum, input.scrollHeight + border));
    input.style.height = `${height}px`;
    input.style.overflowY = input.scrollHeight > height + 1 ? 'auto' : 'hidden';
    if (followBottom) box.scrollTop = box.scrollHeight;
  }
  function update() {
    scheduled = false;
    const mobile = compact.matches && dialog.open;
    const panelOpen = mobile && dialog.classList.contains('chat-mobile-panel-open');
    const placeholder = compact.matches ? text('输入消息…', 'Message…')
      : text('先聊想法、问问题，或一起整理下一张任务卡…', 'Share an idea, ask a question, or shape the next task…');
    if (input.placeholder !== placeholder) input.placeholder = placeholder;
    document.documentElement.classList.toggle('chat-mobile-open', mobile);
    if (!mobile) dialog.classList.remove('chat-mobile-panel-open');
    main.inert = panelOpen;
    options.setAttribute('aria-expanded', String(panelOpen));
    options.setAttribute('aria-label', panelOpen ? text('返回聊天', 'Back to chat') : text('项目与会话设置', 'Project and conversation settings'));
    back.setAttribute('aria-label', panelOpen ? page==='menu' ? text('返回聊天', 'Back to chat') : text('返回会话设置','Back to conversation settings') : text('返回工作区', 'Back to workspace'));
    back.title = back.getAttribute('aria-label');
    const group = document.querySelector('#chat-mode').value === 'group';
    const recipient = document.querySelector('#chat-agent').value;
    const heading = group && recipient === 'all' ? text('Agent 群聊', 'Agent room') : agentName(recipient);
    renderMenu();
    setText(title, panelOpen ? pageNames()[page] : heading);
    const members = group && typeof selectedMembers === 'function' ? selectedMembers().length : 0;
    setText(subtitle, chatProjectName() + (members ? text(` · ${members} 位成员`, ` · ${members} members`) : ''));
    if (panelOpen) settings.open = true;
    updateViewport();
    resizeInput();
  }
  function schedule() {
    if (!scheduled) { scheduled = true; requestAnimationFrame(update); }
  }
  function setPanel(open) {
    if (!compact.matches || !dialog.open) return;
    const box = dialog.querySelector('#chat-messages');
    if (open) panelReading = {key:conversationKey(), top:box.scrollTop,
      follow:box.scrollHeight - box.scrollTop - box.clientHeight < 90};
    if(open){page='menu';dialog.dataset.mobilePage=page;}
    dialog.classList.toggle('chat-mobile-panel-open', open);
    settings.open = open;
    update();
    if (open) menu.querySelector('button').focus({preventScroll:true});
    else {
      const reading = panelReading;
      panelReading = null;
      options.focus({preventScroll:true});
      requestAnimationFrame(() => {
        if (!dialog.open || dialog.classList.contains('chat-mobile-panel-open')) return;
        box.scrollTop = !reading || reading.key !== conversationKey() || reading.follow ? box.scrollHeight : reading.top;
      });
    }
  }
  options.addEventListener('click', () => setPanel(!dialog.classList.contains('chat-mobile-panel-open')));
  back.addEventListener('click', () => {
    if (dialog.classList.contains('chat-mobile-panel-open') && page!=='menu') setPage('menu');
    else if (dialog.classList.contains('chat-mobile-panel-open')) setPanel(false);
    else dialog.close();
  });
  dialog.addEventListener('cancel', event => {
    if (compact.matches && dialog.classList.contains('chat-mobile-panel-open')) {
      event.preventDefault(); if(page!=='menu')setPage('menu');else setPanel(false);
    }
  });
  dialog.addEventListener('close', () => {
    dialog.classList.remove('chat-mobile-panel-open');
    panelReading = null;
    main.inert = false; schedule();
  });
  new MutationObserver(schedule).observe(dialog, {attributes:true, attributeFilter:['open']});
  input.addEventListener('input', schedule);
  input.addEventListener('focus', schedule);
  compact.addEventListener('change', () => {
    dialog.classList.remove('chat-mobile-panel-open');
    settings.open = !compact.matches;
    schedule();
  });
  window.visualViewport?.addEventListener('resize', schedule);
  window.visualViewport?.addEventListener('scroll', schedule);
  window.addEventListener('resize', schedule);
  document.addEventListener('agentboard:chat-layout', schedule);
  document.addEventListener('agentboard:chat-selected', () => { if(compact.matches && dialog.classList.contains('chat-mobile-panel-open'))setPanel(false); });
  document.addEventListener('agentboard:language', schedule);
  document.addEventListener('change', event => {
    if (dialog.contains(event.target)) schedule();
  });
  update();
})();
