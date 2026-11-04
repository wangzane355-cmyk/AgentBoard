/* Phone pages reuse the desktop actions. Navigation itself never starts work. */
(() => {
  'use strict';
  const compact = matchMedia('(max-width:760px)');
  const L = (zh, en) => AgentBoardI18n.choose(zh, en), E = esc;
  const $m = selector => document.querySelector(selector);
  const icons = {
    chats:'<path d="M20 11.5a8 8 0 0 1-8 7.5 9 9 0 0 1-3-.5L4 20l1.4-4A7 7 0 0 1 4 11.5 8 8 0 0 1 12 4a8 8 0 0 1 8 7.5Z"/><path d="M8 11h.01M12 11h.01M16 11h.01"/>',
    projects:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M3 10h18"/>',
    tasks:'<rect x="5" y="4" width="15" height="17" rx="2"/><path d="M9 4V2h6v2M9 10l1 1 2-2M14 10h3M9 16l1 1 2-2M14 16h3"/>',
    me:'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    back:'<path d="m15 5-7 7 7 7"/>', plus:'<path d="M12 5v14M5 12h14"/>',
    arrow:'<path d="m9 5 7 7-7 7"/>', gear:'<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
    file:'<path d="M14 3H6v18h12V7Z M14 3v5h4M9 12h6M9 16h6"/>',
    trash:'<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
    moon:'<path d="M20 14a8 8 0 0 1-10-10 8 8 0 1 0 10 10Z"/>',
    language:'<path d="M3 5h12M9 3v2M5 5c0 7 8 10 8 10M13 5C12 12 3 15 3 15M13 21l4-10 4 10M15 17h4"/>',
    link:'<path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0"/>'
  };
  const svg = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.file}</svg>`;
  const labels = () => ({chats:L('聊天','Chats'), projects:L('项目','Projects'), tasks:L('任务','Tasks'), me:L('我的','Me')});
  let route = {tab:'chats', project:null, sub:null};
  let taskKind = 'deliveries', taskFilter = 'all', projectFilter = '';
  let signature = '', routeKey = '', opening = false;
  let createdProjectRoute = null;
  const positions = new Map();
  const root = document.createElement('section');
  root.id = 'mobile-workspace';
  root.setAttribute('aria-label', 'AgentBoard');
  root.innerHTML = '<header class="mw-header"><button id="mw-back" type="button" class="mw-icon"></button><h1 id="mw-title" data-chat-user-value></h1><button id="mw-action" type="button" class="mw-icon"></button></header><main id="mw-content" tabindex="-1"></main><nav id="mw-tabs"></nav>';
  document.body.append(root);
  const content = $m('#mw-content');
  const row = (action, id, title, subtitle, icon = 'file', extra = '') => `<button type="button" class="mw-row" data-mw-action="${action}" data-mw-id="${E(id || '')}"><span class="mw-avatar ${E(icon)}">${svg(icon)}</span><span class="mw-row-copy"><strong data-chat-user-value>${E(title)}</strong>${subtitle ? `<small data-chat-user-value>${E(subtitle)}</small>` : ''}</span>${extra}<span class="mw-chevron">${svg('arrow')}</span></button>`;
  const empty = (icon, title, hint, action, button) => `<div class="mw-empty"><span>${svg(icon)}</span><h2>${title}</h2><p>${hint}</p>${action ? `<button class="primary" type="button" data-mw-action="${action}">${button}</button>` : ''}</div>`;
  const activePhases = ['queued','preparing','planning','building','checking','reviewing','repairing'];
  const phaseText = phase => ({queued:L('已排队','Queued'),preparing:L('准备中','Preparing'),planning:L('制定计划','Planning'),building:L('实现中','Building'),checking:L('检查中','Checking'),reviewing:L('审查中','Reviewing'),repairing:L('修复中','Repairing'),paused:L('已暂停','Paused'),blocked:L('需要处理','Needs attention'),review:L('待查收','For review'),accepted:L('已接入','Integrated'),cancelled:L('已停止','Stopped'),rolled_back:L('已撤回','Reverted')})[phase] || phase;
  const projectName = id => state.projects.find(p => p.id === id)?.name || L('自由讨论','Free discussion');
  const isChild = () => Boolean(route.project || route.sub);
  const key = () => JSON.stringify(route);
  function savePosition() { if(routeKey) positions.set(routeKey, content.scrollTop); }
  function navigate(next, replace = false) {
    savePosition();
    const target = {tab:next.tab || route.tab, project:next.project || null, sub:next.sub || null};
    if(JSON.stringify(target)===key()) return;
    route = target;
    if (!replace) history.pushState({...history.state, agentboardMobile:route, mobileOverlays:[]}, '');
    signature = ''; renderPages();
    content.scrollTop = positions.get(key()) || 0;
    $m('#mw-title').focus({preventScroll:true});
  }
  function backPage() {
    if(history.state?.agentboardMobile && isChild()) history.back();
    else navigate({tab:route.tab}, true);
  }
  // Each dialog is a page on a phone; browser Back closes it before leaving a tab.
  let overlays = [];
  let syncingHistory = false;
  function visibleOverlays() {
    return [...document.querySelectorAll('dialog[open]')].map(d => d.id)
      .concat(!$m('#drawer').classList.contains('hidden') ? ['drawer'] : []);
  }
  function syncOverlays() {
    if(!compact.matches || syncingHistory) return;
    const next = visibleOverlays();
    if(JSON.stringify(next) === JSON.stringify(overlays)) return;
    const added = next.some(id => !overlays.includes(id));
    overlays = next;
    if(createdProjectRoute && !next.includes('chat-project-create-dialog')) {
      route=createdProjectRoute;createdProjectRoute=null;
      history.replaceState({...history.state,agentboardMobile:route,mobileOverlays:next},'');
      signature='';renderPages();
      root.inert=next.length>0;
      return;
    }
    if(added) history.pushState({...history.state, agentboardMobile:route, mobileOverlays:next}, '');
    else if(history.state?.mobileOverlays?.length) history.back();
    root.inert = next.length > 0;
  }
  addEventListener('popstate', event => {
    if(!compact.matches) return;
    const target = event.state?.mobileOverlays || [];
    syncingHistory = true;
    for(const id of visibleOverlays().reverse()) {
      if(target.includes(id)) continue;
      if(id === 'drawer') closeDrawer();
      else {
        const modal=$m('#'+id);
        const cancel=new Event('cancel',{cancelable:true});
        if(!modal.dispatchEvent(cancel)) {
          // A chat subpage consumed Back, or a busy form is protecting its submit.
          overlays=visibleOverlays();
          history.pushState({...history.state,agentboardMobile:route,mobileOverlays:overlays},'');
          syncingHistory=false;
          return;
        }
        modal.close();
      }
    }
    overlays = visibleOverlays();
    root.inert = overlays.length > 0;
    syncingHistory = false;
    history.replaceState({...history.state,mobileOverlays:overlays},'');
    if(event.state?.agentboardMobile) {
      savePosition(); route = event.state.agentboardMobile; signature=''; renderPages();
      content.scrollTop = positions.get(key()) || 0;
    }
  });
  const overlayObserver = new MutationObserver(syncOverlays);
  overlayObserver.observe(document.body,{subtree:true,attributes:true,attributeFilter:['open','class']});

  function chatRows() {
    const chats = [...(state.chats || [])].sort((a,b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
    return `<p class="mw-section-note">${L('聊想法、继续讨论，或从一句话开始。','Explore an idea or pick up a conversation.')}</p><div class="mw-list">${row('new-chat','',L('开始新对话','Start a conversation'),L('还没有项目也可以先聊聊','No project needed to start'),'plus')}${chats.map(chat => row('chat',chat.id,chat.title || L('未命名对话','Untitled conversation'),projectName(chat.project_id)+' · '+(chat.mode==='group'?L('群聊','Group'):agentName(chat.agent)), 'chats',chat.status==='running'?`<span class="mw-pill live">${L('回复中','Replying')}</span>`:chat.status==='error'?`<span class="mw-pill attention">${L('需查看','Attention')}</span>`:'')).join('')}</div>`;
  }
  function projectRows() {
    if(route.project) {
      const project = state.projects.find(p => p.id === route.project);
      if(!project) { route.project=null; return projectRows(); }
      const tasks = state.tasks.filter(t => t.project_id === project.id);
      return `<div class="mw-project-card"><span class="mw-project-mark">${svg('projects')}</span><h2 data-chat-user-value>${E(project.name)}</h2><p>${L('讨论、安排任务、查收成果。','Discuss, assign work and review results.')}</p><div class="mw-project-counts"><span>${tasks.length} ${L('项任务','tasks')}</span><span>${tasks.filter(t=>['review','decision','blocked'].includes(t.status)).length} ${L('待处理','need attention')}</span></div></div><div class="mw-list">${row('project-chat',project.id,L('和 Agent 聊这个项目','Discuss this project'),L('自动带上项目范围','Project context stays attached'),'chats')}${row('project-tasks',project.id,L('查看项目任务','Project tasks'),L('进度、待查收和执行结果','Progress, reviews and results'),'tasks')}${row('mission-new',project.id,L('开始自主任务','New autonomous task'),L('先写目标，再设置验收','Set a goal and verification'),'plus')}${row('context',project.id,L('项目资料','Project references'),L('开发日志、文档和网址','Logs, documents and links'),'file')}</div><div class="mw-list mw-separated">${row('delete-project',project.id,L('删除项目','Delete project'),L('移入回收站，电脑文件保留','Move to recycle bin; local files stay'),'trash')}</div>`;
    }
    return `<p class="mw-section-note">${L('每个项目一个入口，点进去再安排。','Open a project to continue your work.')}</p><div class="mw-list">${state.projects.map(p=>row('project',p.id,p.name,`${state.tasks.filter(t=>t.project_id===p.id).length} ${L('项任务','tasks')} · ${L('点击进入','Open project')}`,'projects')).join('')}</div>${!state.projects.length?empty('projects',L('从第一个项目开始','Your first project'),L('先聊聊想法，也可以直接创建项目。','Discuss an idea or create a project.'),'new-project',L('创建项目','Create project')):''}`;
  }
  function taskRows() {
    if(projectFilter && !state.projects.some(p=>p.id===projectFilter)) projectFilter='';
    const options = `<option value="">${L('全部项目','All projects')}</option>`+state.projects.map(p=>`<option value="${E(p.id)}" data-chat-user-value ${p.id===projectFilter?'selected':''}>${E(p.name)}</option>`).join('');
    const missions = state.autonomy?.missions || state.autonomy_demo || [];
    const items = taskKind==='deliveries' ? missions : state.tasks.filter(t=>!t.mission_id);
    const filtered = items.filter(item => (!projectFilter || item.project_id===projectFilter) && (taskFilter==='all' || (taskFilter==='active' ? taskKind==='deliveries'?activePhases.includes(item.phase):['queued','running'].includes(item.status) : taskKind==='deliveries'?['review','blocked','paused'].includes(item.phase):['review','blocked','decision'].includes(item.status))));
    return `<div class="mw-task-tools"><label class="mw-project-filter">${L('项目','Project')}<select id="mw-project-filter" aria-label="${L('筛选项目','Filter projects')}">${options}</select></label><div class="mw-segment" role="group" aria-label="${L('任务类型','Task type')}">${['deliveries','manual'].map(kind=>`<button type="button" data-mw-kind="${kind}" aria-pressed="${kind===taskKind}">${kind==='deliveries'?L('自主任务','Autonomous'):L('普通任务','Manual')}</button>`).join('')}</div><div class="mw-filters" role="group" aria-label="${L('任务状态','Task status')}">${[['all',L('全部','All')],['active',L('进行中','Active')],['attention',L('待处理','Attention')]].map(([value,label])=>`<button type="button" data-mw-filter="${value}" aria-pressed="${taskFilter===value}">${label}</button>`).join('')}</div></div><div class="mw-list">${filtered.map(item=>row(taskKind==='deliveries'?'mission':'task',item.id,item.title,projectName(item.project_id),'tasks',`<span class="mw-pill ${['review','blocked','decision'].includes(item.phase||item.status)?'attention':''}">${E(taskKind==='deliveries'?phaseText(item.phase):AgentBoardI18n.translate(statusText[item.status]||item.status))}</span>`)).join('')}</div>${!filtered.length?empty('tasks',L('这里暂时没有任务','No tasks here yet'),L('可切换筛选，或点右上角新建。','Change the filters or tap + to create one.')):''}`;
  }
  function meRows() {
    if(route.sub==='language') return `<p class="mw-section-note">${L('只切换界面文字，项目和聊天内容保持原样。','Changes interface text; your content stays as written.')}</p><div class="mw-list mw-language"><label>${L('界面语言','Interface language')}<select data-language aria-label="Language / 界面语言"><option value="zh-CN" ${AgentBoardI18n.language==='zh-CN'?'selected':''}>简体中文</option><option value="en" ${AgentBoardI18n.language==='en'?'selected':''}>English</option></select></label></div>`;
    const remote = document.documentElement.dataset.phoneClient==='remote';
    const connected = $m('#supervisor-connection')?.textContent || L('正在连接电脑','Connecting to computer');
    return `<div class="mw-profile"><span>A<span></span></span><div><h2>AgentBoard</h2><p data-chat-user-value>${E(connected)}</p></div></div><div class="mw-list">${row('appearance','',L('外观','Appearance'),L('选择你喜欢的主题','Choose your theme'),'moon')}${row('language','',L('语言','Language'),AgentBoardI18n.language==='en'?'English':'简体中文','language')}${row('trash','',L('回收站','Recycle bin'),L('恢复删除的项目和任务','Restore projects and tasks'),'trash')}</div><p class="mw-section-note">${L('电脑保持开启，Agent 就可以继续工作。','Keep the computer on so agents can continue working.')}</p>${remote?`<div class="mw-list">${row('logout','',L('退出这台手机','Sign out this phone'),L('再次访问需要重新配对','Pair again to sign back in'),'link')}</div>`:''}<p class="mw-version">AGENTBOARD · ${L('本地协作工作台','LOCAL WORKSPACE')}</p>`;
  }
  function renderPages() {
    document.documentElement.classList.toggle('mobile-pages', compact.matches);
    if(!compact.matches) { root.inert=true; return; }
    const project = state.projects.find(p=>p.id===route.project);
    if(route.project && !project) route={tab:'projects',project:null,sub:null};
    const snapshot = JSON.stringify([route,taskKind,taskFilter,projectFilter,state.projects,state.tasks,state.chats,state.autonomy,state.autonomy_demo,state.trash,AgentBoardI18n.language,document.documentElement.dataset.phoneClient,$m('#supervisor-connection')?.textContent]);
    if(snapshot===signature) return;
    signature=snapshot;
    const oldTop=content.scrollTop, oldFocus=content.contains(document.activeElement)?document.activeElement.id:'';
    const sameRoute=routeKey===key();routeKey=key();
    const names=labels();
    root.dataset.tab=route.tab;root.dataset.child=String(isChild());
    $m('#mw-title').textContent=project?.name || (route.sub==='language'?L('语言','Language'):names[route.tab]);
    $m('#mw-title').tabIndex=-1;
    const back=$m('#mw-back');back.innerHTML=svg('back');back.hidden=!isChild();back.setAttribute('aria-label',L('返回','Back'));
    const action=$m('#mw-action');action.innerHTML=svg('plus');action.hidden=route.tab==='me'||Boolean(route.project);action.setAttribute('aria-label',route.tab==='chats'?L('新对话','New conversation'):route.tab==='projects'?L('新建项目','New project'):L('新建任务','New task'));
    $m('#mw-tabs').setAttribute('aria-label',L('主要页面','Main pages'));
    $m('#mw-tabs').innerHTML=Object.entries(names).map(([tab,label])=>`<button type="button" data-mw-tab="${tab}" ${tab===route.tab?'aria-current="page"':''}>${svg(tab)}<span>${label}</span></button>`).join('');
    content.innerHTML=route.tab==='chats'?chatRows():route.tab==='projects'?projectRows():route.tab==='tasks'?taskRows():meRows();
    if(sameRoute){ content.scrollTop=oldTop;if(oldFocus)document.getElementById(oldFocus)?.focus({preventScroll:true}); }
    root.inert=visibleOverlays().length>0;
  }
  async function perform(action,id) {
    if(opening) return;
    opening=true;
    try {
      if(action==='chat') await openSavedChat(id);
      else if(action==='new-chat') await showChat();
      else if(action==='new-project') openChatProjectDialog(false);
      else if(action==='project') navigate({tab:'projects',project:id});
      else if(action==='project-chat') await showChat('','single',id);
      else if(action==='project-tasks') {
        projectFilter=id;taskFilter='all';
        const missions=state.autonomy?.missions || [];
        taskKind=missions.some(m=>m.project_id===id)?'deliveries':'manual';
        navigate({tab:'tasks',sub:'project-tasks'});
      }
      else if(action==='task') openDrawer(id);
      else if(action==='mission') await AgentBoardAutonomy.showMission(id);
      else if(action==='mission-new') {activeProject=id;render();AgentBoardAutonomy.showMissionForm();}
      else if(action==='context') {activeProject=id;openProjectContext();}
      else if(action==='delete-project') await archiveItem('project',id);
      else if(action==='language') navigate({tab:'me',sub:'language'});
      else if(action==='appearance') $m('#open-settings').click();
      else if(action==='trash') $m('#open-trash').click();
      else if(action==='logout') $m('#phone-logout')?.click();
      else if(action==='new-task') {
        if(projectFilter) activeProject=projectFilter;
        if(taskKind==='deliveries') AgentBoardAutonomy.showMissionForm(); else openTaskForm();
      }
    } catch(error) { toast(error.message); }
    finally {opening=false;}
  }
  root.addEventListener('click', event => {
    const tab=event.target.closest('[data-mw-tab]');
    if(tab){navigate({tab:tab.dataset.mwTab});return;}
    const kind=event.target.closest('[data-mw-kind]');
    if(kind){taskKind=kind.dataset.mwKind;signature='';renderPages();return;}
    const filter=event.target.closest('[data-mw-filter]');
    if(filter){taskFilter=filter.dataset.mwFilter;signature='';renderPages();return;}
    const button=event.target.closest('[data-mw-action]');
    if(button) perform(button.dataset.mwAction,button.dataset.mwId);
  });
  root.addEventListener('change',event=>{if(event.target.id==='mw-project-filter'){projectFilter=event.target.value;signature='';renderPages();}});
  $m('#mw-action').onclick=()=>perform(route.tab==='chats'?'new-chat':route.tab==='projects'?'new-project':'new-task');
  $m('#mw-back').onclick=backPage;
  document.addEventListener('agentboard:render',renderPages);
  document.addEventListener('agentboard:language',()=>{signature='';renderPages();});
  document.addEventListener('agentboard:project-created',event=>{
    if(compact.matches && !event.detail.fromChat)createdProjectRoute={tab:'projects',project:event.detail.id,sub:null};
  });
  new MutationObserver(renderPages).observe(document.documentElement,{attributes:true,attributeFilter:['data-phone-client']});
  compact.addEventListener('change',()=>{
    if(compact.matches){overlays=visibleOverlays();history.replaceState({...history.state,agentboardMobile:route,mobileOverlays:overlays},'');}
    signature='';renderPages();
  });
  history.replaceState({...history.state,agentboardMobile:route},'');
  renderPages();
})();
