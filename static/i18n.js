/* Local UI catalog. Project data and conversation bodies are never translated. */
(() => {
  'use strict';
  const catalog = Object.fromEntries(String.raw`
◐ 设置	◐ Settings
设置	Settings
关闭设置	Close settings
设置分类	Settings categories
◐ 外观	◐ Appearance
给专注，一点个性。	Make room for your focus.
三种视觉语言，同一个工作空间。选择后即时应用，仅保存在本机浏览器。	Three visual languages. One workspace. Applied instantly and remembered in this browser.
选择外观主题	Choose an appearance theme
静灰 · 极简	Graphite · Minimal
构成 · 酒红	Construct · Burgundy
黑曜 · 金属	Obsidian · Metal
冷灰留白，细线秩序。轻盈、清晰、专注。	Cool neutrals. Fine lines. Light, clear and focused.
米白与酒红。几何、节奏、纸感。	Warm paper and burgundy. Geometry with rhythm.
深黑分层，钢色高光。沉静而有力量。	Layered black and steel highlights. Quiet strength.
自动记住选择 · 不改变项目内容 · 不调用模型	Remembered locally · Project content stays intact · No model calls
恢复原始深色	Restore original dark
原始深色	Original dark
DeepSeek 后台版本与启动检查	DeepSeek runtime versions and startup checks
固定后台入口，保留旧版本。检查不调用模型；新版本准备完成后仍需手动切换。	Pin the runtime and retain previous versions. Checks never call a model. Prepared versions require explicit activation.
固定当前安装（不下载）	Pin installed copy (no download)
检查当前版本	Check current version
回退旧版本	Roll back
检查官方更新	Check official updates
指定执行器版本	Exact runtime version
准备指定版本	Prepare version
密钥和登录资料仍保留在原配置中。这里只检查程序版本及headless参数，不代表真实账号连通性已验证。	Credentials remain in the existing configuration. Version and headless argument checks do not verify live account connectivity.
⚙ Agent 管理	⚙ Manage agents
Agent 管理	Manage agents
无需新账号即可添加本地模拟Agent。检查配置不调用模型，也不代表账号登录或服务连接成功。	Add a local simulator without an account. Configuration checks do not call models or verify authentication or provider connectivity.
添加 / 编辑 Agent	Add / edit agent
显示名称	Display name
接入类型	Adapter type
本地模拟（无需账号）	Local simulator (no account)
命令行程序	Command-line executable
兼容 Chat Completions API	Compatible Chat Completions API
可执行程序	Executable
参数 JSON 数组	Arguments as a JSON array
提示词通过标准输入传入，纯文本结果从标准输出读取。参数可用 {workspace}、{answer_file}。程序在隔离副本运行；权限边界仍取决于执行器本身。	The prompt is sent on stdin; plain text replies are read from stdout. Arguments support {workspace} and {answer_file}. Runs in an isolated copy; permissions depend on the executor.
允许该命令行Agent执行开发任务	Allow implementation tasks with this CLI
完整接口地址	Full endpoint URL
模型名称	Model name
密钥环境变量名	API key environment variable name
只填写变量名，不填写密钥。API模式仅支持讨论和只读调查；发送时会把关联项目上下文提交到你配置的服务，可能产生费用。	Enter the environment variable name, not the secret. API mode supports discussion and read-only investigation. Sending submits linked project context to the configured provider and may incur charges.
启用Agent	Enable agent
清空表单	Clear form
保存Agent	Save agent
本地任务调度	Local agent workspace
工作空间	Workspaces
＋ 添加项目	＋ Add project
◌ 与 Agent 对话	◌ Chat with an agent
◎ Agent 群聊	◎ Agent room
Python 看门脚本运行中	Python supervisor running
运行和文件检查由 Python 完成。所有任务在隔离副本执行。	Python supervises execution and file checks. Tasks run in isolated copies.
任务看板	Task board
一句临时想法也可以直接建卡。	Turn an idea into a task card.
Codex 5h：读取中	Codex 5h: loading
Codex 5h：读取失败 · 点击重试	Codex 5h: unavailable · retry
点击自动刷新用量	Refresh account usage
通过本机 Codex app-server 自动读取；点击立即刷新	Read through the local Codex app-server; click to refresh
商量下一步	Plan next steps
项目资料	Project references
刷新	Refresh
＋ 新任务	＋ New task
运行中	Running
待你处理	Needs attention
已完成	Done
Codex / DeepSeek 可按任务自由选择。默认不自动调用 Codex。	Choose Codex or DeepSeek per task. Codex is not invoked automatically by default.
任务详情	Task details
关闭	Close
创建任务卡	Create task card
编辑任务卡	Edit task card
任务名称	Task title
例如：训练界面太乱，先调查原因	For example: investigate the cluttered training screen
你想达到什么效果	Desired outcome
用自己的话写就行；不确定怎么做也没关系。	Describe the goal in your own words; the approach can be decided later.
项目	Project
交给谁	Executor
任务方式	Task mode
先调查，不改文件	Investigate without editing
开发，修改隔离副本	Implement in an isolated copy
最多运行几分钟	Time limit in minutes
允许修改的相对路径	Allowed relative paths
开发任务必填，一行一个；如 Assets/Scripts/UI/**	Required for implementation; one per line, e.g. Assets/Scripts/UI/**
Python 验收规则	Python acceptance rules
可留空，一行一条；exists:路径 / absent:路径 / contains:路径 | 文字	Optional, one per line: exists:path / absent:path / contains:path | text
任务补充资料（自动继承项目资料，可留空）	Extra task references (project references are inherited)
额外的本地文件或文件夹	Additional local files or folders
一行一个绝对路径，例如 D:\项目\Docs\开发日志.md	One absolute path per line, e.g. D:\Projects\Notes\Docs\CHANGELOG.md
额外的网址	Additional URLs
一行一个 http/https 网址	One http/https URL per line
前置任务 ID	Dependency task IDs
可留空，多个用逗号分隔	Optional; separate IDs with commas
例如 abc123, def456	For example: abc123, def456
前置任务完成后自动开始这张卡	Start automatically after dependencies finish
Codex 额度不足或读数过期时改派 DeepSeek	Fall back to DeepSeek if Codex quota is low or unavailable
取消	Cancel
创建任务	Create task
保存修改	Save changes
添加本地项目	Add local project
项目名称	Project name
例如：我的新游戏	For example: My new game
项目目录	Project folder
需保护的目录	Protected folders
一行一个，例如玩家存档目录	One per line, e.g. a player save folder
自动检查	Automatic checks
仅检查文件与保护路径	File scope and protected paths only
编译 Python 文件	Compile Python files
Unity 隔离副本批处理编译	Compile isolated Unity copy in batch mode
关联开发日志 / 本地资料	Development logs / local references
文件或文件夹的绝对路径，一行一个	Absolute file or folder paths, one per line
关联网页	Web references
http/https 网址，一行一个	One http/https URL per line
添加项目	Add project
项目资料关联	Project references
关闭项目资料	Close project references
每次讨论和派工前重新读取。文件夹优先选取开发日志与交接资料；读取范围和截取情况会记录在快照中。	References are refreshed before discussions and tasks. Logs and handoff notes are prioritized; snapshots record coverage and truncation.
当前项目源文件夹	Current project source folder
关联日志、文件或文件夹	Linked logs, files or folders
例如 D:\我的项目\Docs\开发日志.md	For example: D:\Projects\Notes\Docs\CHANGELOG.md
选择日志文件	Choose log file
选择资料文件夹	Choose reference folder
关联网页地址	Linked webpage URLs
http/https，一行一个。读取网页正文，不包含登录页面后的内容。	One http/https URL per line. Reads public page text, not content behind a login.
支持 md/txt/json/yaml 等文本资料。每轮最多24个本地文件，共约4.8万字；长文件保留开头与末尾，网页保留开头。	Supports md/txt/json/yaml and other text files. Up to 24 local files and about 48,000 characters per turn. Long files keep their beginning and end; webpages keep their beginning.
检查并预览读取内容	Check and preview references
保存关联	Save references
保存当前共识	Save current consensus
关闭共识	Close consensus
确认目标、已选方案、待定问题及下一步。共识会随关联任务交给执行者。	Confirm the goal, chosen approach, open questions and next steps. The consensus is passed to the linked task executor.
当前共识	Current consensus
保存共识	Save consensus
与 Agent 对话	Chat with an agent
关闭对话	Close chat
会话与设置	Sessions and settings
展开 / 收起	Expand / collapse
当前项目	Current project
聊天方式	Chat mode
单聊	Single agent
Agent 群聊	Agent room
回复对象	Recipient
对话执行者	Chat executor
群聊回复对象	Room recipient
发给全体	Everyone
成员：DeepSeek · Codex。普通消息全体回复；	Members: DeepSeek · Codex. Normal messages invite everyone;
或	or
仅指定AI回复。所有消息在房间内共享。	only the selected agent replies. All messages share the room history.
自动带入已关联日志、任务目标、依赖和进度，无需重新介绍。	Linked logs, goals, dependencies and progress are included automatically.
帮我判断下一步	Help plan the next step
先帮我梳理这张任务	Help clarify this task
关联任务	Linked task
请 Agent 整理共识	Ask agent to summarize
查看 / 保存共识	View / save consensus
群聊讨论上限	Room discussion limit
最多1轮 / 2次回复	Up to 1 round / 2 replies
最多2轮 / 4次回复	Up to 2 rounds / 4 replies
最多3轮 / 6次回复	Up to 3 rounds / 6 replies
让他们讨论	Let agents discuss
附带项目源码快照（供只读查阅）	Include a source snapshot for read-only reference
默认携带项目名称和任务概况。历史记录自动保存；每轮携带最近最多约4.2万字。每轮最多25分钟。	Project and task context is included by default. History is saved automatically; each turn includes up to about 42,000 recent characters. Limit: 25 minutes per turn.
转成任务卡	Create task draft
更新关联任务	Update linked task
历史对话	Chat history
＋ 新对话	＋ New chat
聊天记录	Messages
对话记录	Conversation history
先聊想法、问问题，或一起整理下一张任务卡…	Discuss an idea, ask a question, or plan the next task…
发送给 Agent 的消息	Message to agent
Ctrl / ⌘ + Enter 发送	Ctrl / ⌘ + Enter to send
停止回复	Stop reply
发送	Send
暂无项目	No projects yet
用任务卡调度 Codex 和 DeepSeek；Python 负责监督。	Coordinate Codex and DeepSeek with task cards; Python supervises execution.
先添加一个本地项目。	Add a local project to get started.
可用	Available
未找到	Not found
演示工作区 · 示例数据 · 不调用真实Agent	Demo workspace · Sample data · No live model calls
只读演示	Read-only demo
待处理	Ready
进行中	In progress
决策收件箱	Decision inbox
待你查收	Ready for review
已阻塞	Blocked
已排队	Queued
需要你决定	Decision needed
目前没有任务	No tasks here
准备中	Preparing
先调查	Investigate
开发任务	Implement
(还没有结果)	(No result yet)
(任务胶囊正在生成)	(Preparing task capsule)
(暂无诊断日志)	(No diagnostic log)
讨论这张任务	Discuss task
重新运行	Run again
启动任务	Start task
编辑任务	Edit task
取消排队	Cancel queued task
停止运行	Stop task
标记已了解	Mark reviewed
接入原项目	Integrate into source
撤回本次接入	Roll back integration
Python 正在检查	Python is checking
尚未运行	Not started
状态	Status
指定执行者	Assigned executor
实际执行者	Actual executor
方式	Mode
只读调查	Read-only investigation
开发修改	Implementation
时限	Time limit
任务 ID	Task ID
开始	Started
允许改动	Allowed changes
无 · 只读	None · Read-only
关联资料	Linked references
未配置；可在项目资料中选择	Not configured; add project references
已关联讨论与共识，执行时会自动带入。	Discussion and consensus are linked and included during execution.
前置任务	Dependencies
接下来依赖这张卡	Dependent tasks
机器验收规则	Acceptance rules
Python 验收证据	Python check evidence
只需要你决定这一点	Your decision is needed
也可以写自己的决定	Or enter your own decision
提交决定并继续	Submit decision and continue
这张卡还没有自动编译通过的证据；接入前请查看结果或先配置项目检查。	No successful automatic compilation evidence is available. Review the result or configure project checks before integration.
自动编译已过，但画面、手感和玩法仍需要你查看；Python 无法判断这些体验。	Automatic compilation passed. Visuals, interaction and gameplay still need human review.
跨模型任务胶囊	Cross-model task capsule
读取中…	Loading…
交付结果	Delivery result
技术诊断日志（本地私有）	Diagnostic log (local and private)
展开后读取	Load on expansion
本次生成的画面	Generated images
改动文件	Changed files
暂无	None yet
接入原项目会复制本次改动。请先查看结果；确认接入吗？	Integration copies these changes into the source project. Review the result first. Proceed?
确认撤回本次接入的文件改动？若文件已被再次修改，系统会拒绝撤回。	Roll back this integration? Files edited again since integration will not be overwritten.
任务已启动	Task started
已请求停止	Stop requested
已撤回改动	Changes rolled back
决定已提交，任务继续	Decision submitted; task continues
任务已完成	Task completed
请先添加项目	Add a project first
Codex 用量已自动刷新	Codex usage refreshed
任务卡已修改	Task card updated
任务卡已创建	Task card created
项目已添加	Project added
请先选择项目	Select a project first
Python监督	Python supervisor
先聊想法，暂不关联任务	Discuss first without linking a task
项目对话	Project chat
当前项目还没有对话	No conversations in this project yet
你	You
全体	Everyone
先说说你的想法	Share your idea
群聊支持全体发言和斜杠定向消息	Invite everyone or address an agent with a slash command
正在回复…	Replying…
Agent 正在回复，关闭面板后仍会继续。	Agent is replying; closing this panel does not stop it.
已关联到这张任务，之前的讨论会保留。	Task linked; previous discussion is preserved.
正在读取这段对话，请稍后发送。	Loading the conversation; please send again shortly.
这是一条定向消息，请直接发送；需要群聊讨论时再使用 /讨论。	This message is directed to one agent. Send it directly; use /discuss for a group discussion.
当前共识已保存，更新关联任务后会带入执行。	Consensus saved; it will be included when the linked task is updated.
已填入任务草稿；补齐范围和验收条件后创建。	Draft prepared. Set scope and acceptance rules before creating the task.
资料关联已保存，下次讨论和派工会自动重新读取。	References saved; they will be refreshed before the next discussion or task.
操作失败	Operation failed
正在重新读取关联资料…	Refreshing linked references…
`.trim().split('\n').map(line => line.split('\t')));

  const patterns = [
    [/^Codex 5h：剩余 (\d+(?:\.\d+)?)%( · 已过期)?$/, (_, n, stale) => `Codex 5h: ${n}% remaining${stale ? ' · stale' : ''}`],
    [/^(Codex|DeepSeek) (可用|未找到)$/, (_, name, status) => `${name} ${catalog[status]}`],
    [/^(\d+) 分钟$/, (_, n) => `${n} minutes`],
    [/^准备中 \/ (\d+):00$/, (_, n) => `Preparing / ${n}:00`],
    [/^例如 D:\\我的项目\\Docs\\开发日志\.md\nD:\\我的项目\\Docs$/, () => 'For example: D:\\Projects\\Notes\\Docs\\CHANGELOG.md\nD:\\Projects\\Notes\\Docs'],
    [/^正在商量：(.+)的下一步$/, (_, name) => `Planning next steps: ${name}`],
    [/^正在商量：(.+)$/, (_, name) => `Discussing: ${name}`],
    [/^已关联 (\d+) 处资料，发送时自动读取；无需勾选源码。$/, (_, n) => `${n} references linked; refreshed when sending. Source snapshot is optional.`],
    [/^请 (Codex|DeepSeek) 接话$/, (_, name) => `Invite ${name} to reply`],
    [/^→ 全体$/, () => '→ Everyone'],
    [/^群聊 · DeepSeek \/ Codex · (回复中|需查看|已保存)$/, (_, status) => `Agent room · DeepSeek / Codex · ${{'回复中':'Replying','需查看':'Needs attention','已保存':'Saved'}[status]}`],
    [/^(Codex|DeepSeek) · (回复中|需查看|已保存)$/, (_, name, status) => `${name} · ${{'回复中':'Replying','需查看':'Needs attention','已保存':'Saved'}[status]}`],
    [/^本批次结束，(\d+) 次回复。$/, (_, n) => `Batch finished: ${n} replies.`],
    [/^群聊：(Codex 回复中|DeepSeek 回复中|准备中) · 已完成 (\d+)\/(\d+) 次回复；关闭面板后继续，可随时停止。$/, (_, status, n, total) => `Room: ${status === '准备中' ? 'Preparing' : status.replace(' 回复中', ' replying')} · ${n}/${total} replies complete. Continues when closed; stop anytime.`],
    [/^最近自动读取 (\d+) 项资料 · (.+?)( · 关联任务已变，共识需核对| · 已保存共识)?$/, (_, n, date, note) => `Last refreshed ${n} references · ${date}${note ? (note.includes('需核对') ? ' · Task changed; review consensus' : ' · Consensus saved') : ''}`],
    [/^(added|modified|deleted) · (.+) · 查看差异$/, (_, kind, path) => `${kind} · ${path} · View diff`]
  ];
  let language;
  try { language = localStorage.getItem('agentboard.language'); } catch (_) { /* Storage may be disabled. */ }
  if (!['zh-CN', 'en'].includes(language)) language = navigator.language?.startsWith('zh') ? 'zh-CN' : 'en';
  function translate(value) {
    if (language !== 'en' || typeof value !== 'string') return value;
    const text = value.trim();
    let result = catalog[text];
    if (result === undefined) {
      for (const [pattern, replacement] of patterns) {
        if (pattern.test(text)) { result = text.replace(pattern, replacement); break; }
      }
    }
    return result === undefined ? value : value.slice(0, value.indexOf(text)) + result + value.slice(value.indexOf(text) + text.length);
  }
  // Exclude all user-authored content, source paths, result bodies and logs.
  const protectedContent = '[data-agent-name],[data-agent-option],#agent-status,#chat-room-members label,#group-chat-help,#project-nav,#project-title,#chat-project-name,#context-project-title,.card-title,.card-description,.card-error,.detail-desc,#drawer-body>h2,.chat-session>strong,.chat-message>div:not(.chat-message-label),.result-box,textarea,input,pre,code,figcaption,.tag-list,.decision-panel p,.decision-options,#task-project option,#chat-task option:not([value=""])';
  const textSources = new WeakMap(), attributeSources = new WeakMap();
  function localizeText(node) {
    if (!node.parentElement || node.parentElement.closest(`script,style,${protectedContent}`)) return;
    let record = textSources.get(node);
    if (!record || node.data !== record.rendered) record = {source:node.data};
    const rendered = translate(record.source);
    record.rendered = rendered; textSources.set(node, record);
    if (node.data !== rendered) node.data = rendered;
  }
  function localizeAttribute(element, name) {
    const value = element.getAttribute(name);
    if (value === null) return;
    const records = attributeSources.get(element) || {};
    let record = records[name];
    if (!record || value !== record.rendered) record = {source:value};
    record.rendered = translate(record.source); records[name] = record;
    attributeSources.set(element, records);
    if (value !== record.rendered) element.setAttribute(name, record.rendered);
  }
  function apply(root = document.body) {
    if (root.nodeType === Node.TEXT_NODE) return localizeText(root);
    if (root.nodeType !== Node.ELEMENT_NODE) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) localizeText(walker.currentNode);
    for (const element of [root, ...root.querySelectorAll('[placeholder],[aria-label],[title]')]) {
      if (element.closest('#project-nav,.chat-message,.result-box,.card-error')) continue;
      for (const name of ['placeholder','aria-label','title']) localizeAttribute(element, name);
    }
  }
  const observer = new MutationObserver(records => {
    observer.disconnect();
    for (const record of records) {
      if (record.type === 'childList') record.addedNodes.forEach(node => apply(node));
      else if (record.type === 'characterData') localizeText(record.target);
      else localizeAttribute(record.target, record.attributeName);
    }
    observe();
  });
  function observe() { observer.observe(document.body, {subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:['placeholder','aria-label','title']}); }
  function setLanguage(next) {
    language = next === 'zh-CN' ? 'zh-CN' : 'en';
    try { localStorage.setItem('agentboard.language', language); } catch (_) { /* Optional persistence. */ }
    observer.disconnect();
    document.documentElement.lang = language;
    document.title = language === 'en' ? 'AgentBoard · Local agent workspace' : 'AgentBoard · 本地任务调度';
    document.querySelectorAll('[data-language]').forEach(select => {
      for (const option of select.options) option.defaultSelected = option.value === language;
      select.value = language;
    });
    apply(); observe();
    document.dispatchEvent(new CustomEvent('agentboard:language', {detail:language}));
  }
  const mainSelect = document.getElementById('language-select');
  mainSelect.dataset.language = '';
  // Modal dialogs make the page header inert, so offer the same switch inside them.
  document.querySelectorAll('dialog .dialog-head').forEach(head => {
    const control = mainSelect.closest('label').cloneNode(true);
    control.querySelector('select').removeAttribute('id');
    head.insertBefore(control, head.lastElementChild);
  });
  window.AgentBoardI18n = {translate, setLanguage, choose:(zh, en) => language === 'en' ? en : zh, get language() { return language; }};
  document.addEventListener('change', event => {
    if (event.target.matches('[data-language]')) setLanguage(event.target.value);
  });
  setLanguage(language);
})();
