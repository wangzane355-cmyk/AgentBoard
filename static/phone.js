/* Phone access is opt-in. Only the loopback workspace can manage pairing. */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  const text = (zh, en) => window.AgentBoardI18n ? AgentBoardI18n.choose(zh, en) : zh;
  let status = null, busy = false, refreshing = false, isRemote = false, expiring = false, lastError = '', selectedAddress = '', statusVersion = 0;
  const devices = new Map();
  const words = {
    title: ['手机访问', 'Phone access'], back: ['返回设置', 'Back to settings'], close: ['返回工作区', 'Back to workspace'],
    intro: ['在手机上继续讨论，查看进度、管理任务。电脑负责运行 Agent。', 'Continue conversations and manage work from your phone. Agents keep running on this computer.'],
    networkLabel: ['电脑的 Wi-Fi / 局域网地址', 'Computer Wi-Fi / local network address'],
    networkHint: ['手机和电脑需要连接同一个家庭 Wi-Fi。关闭电脑后，手机将无法连接。', 'Connect the phone and computer to the same home Wi-Fi. The computer must remain on.'],
    transport: ['配对后的手机可以查看项目和启动 Agent，请只配对自己的设备。此连接使用 HTTP、没有 TLS 加密，仅在可信任的家庭 Wi-Fi 使用。', 'Paired phones can view projects and start agents. Pair only your own devices. This HTTP connection has no TLS encryption; use trusted home Wi-Fi only.'],
    stepOne: ['1 · 手机打开这个地址', '1 · Open this address on the phone'], copy: ['复制地址', 'Copy address'],
    copyHint: ['也可以长按或选中地址复制。不要使用 127.0.0.1。', 'You can also select or long-press the address to copy it. Do not use 127.0.0.1.'],
    stepTwo: ['2 · 输入一次配对码', '2 · Enter the one-time pairing code'], refreshCode: ['换一个配对码', 'New pairing code'],
    codeHint: ['配对成功后，这个码立即失效；已配对手机不需要每次输码。', 'The code expires after one successful pairing. Paired phones do not need a code every time.'],
    paired: ['已配对设备', 'Paired devices'], empty: ['还没有设备。先在手机打开上面的地址。', 'No paired devices yet. Open the address above on your phone.'],
    firewallTitle: ['Windows 连接许可', 'Windows connection permission'], firewallAllow: ['允许 Windows 手机连接', 'Allow phone connections in Windows'],
    firewallCheck: ['检查许可', 'Check permission'], firewallHint: ['Windows 会弹出管理员确认，请点“是”；只允许 AgentBoard 本地网段连接。', 'Windows will ask for administrator approval. Select “Yes” to allow AgentBoard connections from your local network only.'],
    disable: ['关闭手机访问', 'Turn off phone access'], enable: ['开启手机访问', 'Turn on phone access'],
    disabledNote: ['默认关闭。开启后，只向下方选定的局域网地址提供配对入口，不会把工作区公开到互联网。', 'Off by default. Enabling creates a pairing entry on the selected local address; it does not publish the workspace to the internet.'],
    heading: ['把工作区带到手机', 'Take your workspace with you'], onLabel: ['已开启', 'Enabled'], offLabel: ['未开启', 'Off'], failedLabel: ['尚未连接', 'Not ready']
  };
  const setText = (element, value) => { if (element && element.textContent !== value) element.textContent = value; };
  function localize(root = document) {
    root.querySelectorAll('[data-phone-copy]').forEach(element => {
      const pair = words[element.dataset.phoneCopy]; if (pair) setText(element, text(...pair));
    });
    if ($('#phone-access-dialog')) {
      $('#phone-access-dialog [data-language]').value = AgentBoardI18n.language;
      $('#phone-access-close').setAttribute('aria-label', text('返回工作区', 'Back to workspace'));
      $('#phone-network').setAttribute('aria-label', text('电脑局域网地址', 'Computer local network address'));
      $('#phone-origin').setAttribute('aria-label', text('手机访问地址', 'Phone access address'));
      renderStatus();
    }
    if ($('#phone-remote-name')) setText($('#phone-remote-label'), text('已连接电脑', 'Connected to computer'));
    if ($('#phone-logout')) setText($('#phone-logout'), text('退出手机', 'Sign out'));
  }
  async function request(path, body) {
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),15000);
    let response;
    try { response = await fetch(path, body === undefined ? {cache:'no-store',signal:controller.signal} : {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body), credentials:'same-origin', cache:'no-store',signal:controller.signal
    }); } catch (error) { if(error.name==='AbortError') throw new Error(text('连接超时，请确认电脑上的 AgentBoard 仍在运行。','Connection timed out. Check that AgentBoard is still running on the computer.'));throw error; }
    finally { clearTimeout(timer); }
    if(response.status===401)sessionExpired();
    let data;
    try { data = await response.json(); } catch (_) { throw new Error(text('服务没有返回有效结果，请检查电脑上的 AgentBoard。', 'The service returned no valid result. Check AgentBoard on the computer.')); }
    if (!response.ok || data.ok === false) throw new Error(data.error || text('操作失败，请稍后再试。', 'The request failed. Try again.'));
    return data.data ?? (data.status && typeof data.status === 'object' ? data.status : data);
  }
  function installLocalPanel() {
    const nav = $('#appearance-dialog .settings-nav'); if (!nav || $('#phone-settings-open')) return;
    const entry = document.createElement('button'); entry.id='phone-settings-open';entry.type='button';entry.className='phone-settings-entry';entry.dataset.phoneCopy='title';nav.append(entry);
    const dialog = document.createElement('dialog');dialog.id='phone-access-dialog';dialog.className='dialog phone-access-dialog';dialog.setAttribute('aria-labelledby','phone-access-title');
    dialog.innerHTML = `<div class="dialog-head phone-access-head"><div><span class="phone-eyebrow">CONNECTED WORKSPACE</span><h2 id="phone-access-title" data-phone-copy="title"></h2></div><label class="language-control"><select data-language aria-label="Language / 界面语言"><option value="zh-CN">简体中文</option><option value="en">English</option></select></label><button type="button" class="icon-btn" id="phone-access-close">×</button></div>
      <div class="phone-access-body"><div class="phone-intro"><span class="phone-device-art" aria-hidden="true"><span></span></span><div><h3 data-phone-copy="heading"></h3><p data-phone-copy="intro"></p></div><span id="phone-status-pill" role="status"></span></div>
      <div id="phone-access-error" class="phone-error hidden" role="alert"></div>
      <div class="phone-network-settings"><p id="phone-off-note" data-phone-copy="disabledNote"></p><label for="phone-network" data-phone-copy="networkLabel"></label><select id="phone-network"></select><p class="phone-help" data-phone-copy="networkHint"></p><button type="button" id="phone-enable" class="primary" data-phone-copy="enable"></button></div>
      <section id="phone-firewall" class="phone-firewall hidden" aria-labelledby="phone-firewall-title"><h3 id="phone-firewall-title" data-phone-copy="firewallTitle"></h3><p class="phone-help" data-phone-copy="firewallHint"></p><p id="phone-firewall-status" role="status"></p><div class="phone-firewall-actions"><button id="phone-firewall-allow" type="button" class="soft" data-phone-copy="firewallAllow"></button><button id="phone-firewall-check" type="button" class="ghost" data-phone-copy="firewallCheck"></button></div></section>
      <section id="phone-live" class="hidden"><div class="phone-step"><span class="phone-step-number" aria-hidden="true">1</span><div><h3 data-phone-copy="stepOne"></h3><div class="phone-address-row"><input id="phone-origin" readonly spellcheck="false" autocomplete="off" data-phone-user-value><button id="phone-copy-address" type="button" class="ghost" data-phone-copy="copy"></button></div><p class="phone-help" id="phone-copy-note" data-phone-copy="copyHint"></p></div></div>
      <div class="phone-step"><span class="phone-step-number" aria-hidden="true">2</span><div><h3 data-phone-copy="stepTwo"></h3><div class="phone-code-row"><output id="phone-code" aria-label="Pairing code / 配对码" data-phone-user-value>—</output><div><p id="phone-code-countdown" role="status"></p><button id="phone-new-code" type="button" class="phone-text-button" data-phone-copy="refreshCode"></button></div></div><p class="phone-help" data-phone-copy="codeHint"></p></div></div>
      </section><section class="phone-devices" aria-labelledby="phone-devices-heading"><h3 id="phone-devices-heading" data-phone-copy="paired"></h3><p id="phone-devices-empty" class="phone-help" data-phone-copy="empty"></p><div id="phone-device-list"></div></section>
      <div class="phone-trust-note"><span aria-hidden="true">◇</span><p data-phone-copy="transport"></p></div></div>
      <div class="phone-access-footer"><button type="button" class="ghost" id="phone-back-settings" data-phone-copy="back"></button><button type="button" class="danger hidden" id="phone-disable" data-phone-copy="disable"></button></div>`;
    document.body.append(dialog);
    entry.onclick = openAccess;
    $('#phone-access-close').onclick = () => dialog.close();
    $('#phone-back-settings').onclick = () => { dialog.close(); $('#appearance-dialog').showModal(); };
    $('#phone-network').onchange = () => { selectedAddress=$('#phone-network').value; };
    $('#phone-enable').onclick = () => perform('enable', selectedAddress ? {address:selectedAddress,port:8767} : {port:8767});
    $('#phone-disable').onclick = () => perform('disable');
    $('#phone-new-code').onclick = () => perform('code');
    $('#phone-firewall-allow').onclick = () => perform('firewall');
    $('#phone-firewall-check').onclick = () => perform('firewall-check');
    $('#phone-copy-address').onclick = copyAddress;
    $('#phone-device-list').onclick = event => {
      const button=event.target.closest('[data-phone-revoke]');if (button) perform('revoke',{device_id:button.dataset.phoneRevoke});
    };
    localize();
  }
  function openAccess() {
    if (isRemote) return;
    installLocalPanel();
    if (!$('#phone-access-dialog')) return;
    $('#appearance-dialog')?.close();
    if (!$('#phone-access-dialog').open) $('#phone-access-dialog').showModal();
    refreshStatus();
  }
  function updateNetworkOptions() {
    const select=$('#phone-network');if (!select || !status) return;
    const interfaces=(status.interfaces || []).filter(item => item && typeof item.address === 'string' && item.address);
    const signature=JSON.stringify([interfaces,AgentBoardI18n.language]);
    if (select.dataset.signature !== signature && document.activeElement !== select) {
      const previous=selectedAddress || status.bound_address || select.value;
      select.replaceChildren();
      if (!interfaces.length) { const option=new Option(text('没有可用的 Wi-Fi / 局域网地址','No Wi-Fi / local network address found'),'');select.append(option); }
      for (const item of interfaces) { const label=[item.label,item.address,item.prefix ? '/'+String(item.prefix).replace(/^\//,'') : ''].filter(Boolean).join(' · '); const option=new Option(label,item.address);option.dataset.phoneUserValue='';select.append(option); }
      selectedAddress=interfaces.some(item => item.address===previous) ? previous : interfaces[0]?.address || '';
      select.value=selectedAddress;select.dataset.signature=signature;
    }
  }
  function dateLabel(value) {
    if (!value || !Number.isFinite(Date.parse(value))) return text('尚未连接','Not connected yet');
    return new Date(value).toLocaleString(AgentBoardI18n.language==='en'?'en':'zh-CN',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
  }
  function renderDevices() {
    const list=$('#phone-device-list');if (!list) return;
    const current=status?.devices || [], ids=new Set(current.map(device=>String(device.id)));
    for (const [id,row] of devices) if (!ids.has(id)) { row.remove();devices.delete(id); }
    for (const device of current) {
      const id=String(device.id);let row=devices.get(id);
      if (!row) {
        row=document.createElement('div');row.className='phone-device-row';
        row.innerHTML='<span class="phone-device-dot" aria-hidden="true"></span><div><strong data-phone-user-value></strong><small></small></div><button type="button" class="ghost" data-phone-revoke></button>';
        row.querySelector('button').dataset.phoneRevoke=id;devices.set(id,row);list.append(row);
      }
      setText(row.querySelector('strong'),String(device.name || text('手机设备','Phone device')));
      setText(row.querySelector('small'),text('最近连接：','Last connected: ')+dateLabel(device.last_seen));
      setText(row.querySelector('button'),text('撤销','Revoke'));
      row.querySelector('button').disabled=busy;
      row.querySelector('button').setAttribute('aria-label',text('撤销设备：','Revoke device: ')+String(device.name || text('手机设备','Phone device')));
    }
    $('#phone-devices-empty').classList.toggle('hidden',current.length>0);
  }
  function renderCountdown() {
    const output=$('#phone-code-countdown');if (!output) return;
    const code=String(status?.pairing_code || '').replace(/\D/g,'');
    const expiry=Date.parse(status?.pairing_expires_at || '');
    const seconds=Number.isFinite(expiry) ? Math.max(0,Math.ceil((expiry-Date.now())/1000)) : 0;
    if (!/^\d{8}$/.test(code) || !seconds) {
      setText($('#phone-code'),'—');setText(output,text('点“换一个配对码”生成新码','Select “New pairing code” to generate one'));
    } else {
      setText($('#phone-code'),code.slice(0,4)+' '+code.slice(4));
      setText(output,text('剩余 ','Expires in ')+Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0'));
    }
  }
  function renderFirewall(running,demo) {
    const box=$('#phone-firewall'),firewall=status?.firewall;
    if(!box)return;
    box.classList.toggle('hidden',!firewall || firewall.state==='not_required');
    if(!firewall)return;
    const state=firewall.state || 'unknown',requesting=state==='requesting',ready=state==='ready';
    box.dataset.state=state;
    const labels={
      unknown:['尚未检查 Windows 连接许可。','Windows connection permission has not been checked.'],
      needs_permission:['尚未允许手机连接，请在这台电脑上完成一次 Windows 确认。','Phone connections need permission. Complete the Windows approval on this computer.'],
      requesting:['请查看 Windows 管理员确认窗口，完成后会自动检查许可。','Check the Windows administrator prompt. Permission will be checked after you respond.'],
      ready:['Windows 连接许可已就绪。','Windows connection permission is ready.'],
      error:['Windows 许可尚未完成，可以重试。','Windows permission is incomplete. You can retry.']
    };
    setText($('#phone-firewall-status'),text(...(labels[state]||labels.unknown))+(firewall.message?' '+String(firewall.message):''));
    setText($('#phone-firewall-allow'),ready?text('已允许 Windows 连接','Windows connections allowed'):requesting?text('等待 Windows 确认…','Waiting for Windows approval…'):text(...words.firewallAllow));
    $('#phone-firewall-allow').disabled=busy || !running || requesting || ready || demo;
    $('#phone-firewall-check').disabled=busy || !running || requesting || demo;
  }
  function renderStatus() {
    if (!$('#phone-access-dialog')) return;
    const running=Boolean(status?.enabled && status?.running && status?.origin), enabled=Boolean(status?.enabled);
    const demo=typeof state!=='undefined' && state.demo;
    updateNetworkOptions();
    setText($('#phone-status-pill'),text(...words[running?'onLabel':enabled?'failedLabel':'offLabel']));
    $('#phone-status-pill').className=running?'phone-status-on':enabled?'phone-status-error':'phone-status-off';
    $('#phone-live').classList.toggle('hidden',!running);
    $('#phone-enable').classList.toggle('hidden',running);
    $('#phone-disable').classList.toggle('hidden',!enabled);
    $('#phone-off-note').classList.toggle('hidden',running);
    $('#phone-network').disabled=busy || !status || enabled;
    $('#phone-enable').disabled=busy || !status || !(status.interfaces || []).length || demo;
    $('#phone-disable').disabled=busy || demo;
    $('#phone-new-code').disabled=busy || !running || demo;
    $('#phone-copy-address').disabled=!running;
    setText($('#phone-devices-empty'),running?text(...words.empty):text('开启手机访问后，可以用一次配对码连接自己的手机。','Enable phone access to pair your own phone with a one-time code.'));
    if ($('#phone-origin').value !== (status?.origin || '')) $('#phone-origin').value=status?.origin || '';
    const failure=demo ? text('只读演示不能开启手机访问。请在正式工作区设置。','The read-only demo cannot enable phone access. Use your own workspace.') : lastError || status?.error || (status && !(status.interfaces || []).length ? text('没有找到可用地址。请让电脑连接家庭 Wi-Fi 后重试；VPN 和虚拟网卡可能无法用于手机连接。','No usable address was found. Connect the computer to home Wi-Fi and retry; VPN or virtual adapters may not work for phones.') : '');
    setText($('#phone-access-error'),String(failure));$('#phone-access-error').classList.toggle('hidden',!failure);
    renderDevices();renderCountdown();renderFirewall(running,demo);
  }
  async function refreshStatus() {
    if (isRemote || refreshing || busy || !$('#phone-access-dialog')?.open) return;
    refreshing=true;const version=statusVersion;
    try { const result=await request('/api/phone-access');if(version===statusVersion){status=result;lastError='';renderStatus();} }
    catch (error) { if(version===statusVersion){lastError=error.message;renderStatus();} }
    finally { refreshing=false; }
  }
  async function perform(action,body={}) {
    if (busy || isRemote) return;
    if (typeof state!=='undefined' && state.demo) return;
    busy=true;lastError='';statusVersion++;renderStatus();
    try { status=await request('/api/phone-access/'+action,body); }
    catch (error) { lastError=error.message; }
    finally { busy=false;renderStatus(); }
  }
  async function copyAddress() {
    const field=$('#phone-origin');if (!field?.value) return;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(field.value);
      else { field.select();if (!document.execCommand('copy')) throw new Error('copy unavailable'); }
      setText($('#phone-copy-note'),text('地址已复制，在手机浏览器打开即可。','Address copied. Open it in the phone browser.'));
    } catch (_) { field.focus();field.select();setText($('#phone-copy-note'),text('请长按或选中地址，手动复制到手机浏览器。','Select or long-press the address and copy it to the phone browser.')); }
  }
  function installRemote(client) {
    isRemote=true;document.documentElement.dataset.phoneClient='remote';
    const banner=document.createElement('div');banner.className='phone-remote-banner';banner.id='phone-remote-banner';
    banner.innerHTML='<span class="phone-remote-dot" aria-hidden="true"></span><div><strong id="phone-remote-label"></strong><span id="phone-remote-name" data-phone-user-value></span></div><button type="button" id="phone-logout"></button>';
    setText(banner.querySelector('#phone-remote-name'),String(client.name || text('此手机','This phone')));
    const main=$('.main');if (main) main.prepend(banner);else document.body.prepend(banner);
    if ($('#add-project')) $('#add-project').onclick=async()=>{if(typeof showChat==='function' && typeof openChatProjectDialog==='function'){await showChat();openChatProjectDialog(false);}};
    $('#phone-logout').onclick=async()=>{
      const button=$('#phone-logout');if(button.disabled)return;button.disabled=true;
      try { await request('/phone/logout',{});location.replace('/phone/login'); }
      catch(error) { button.disabled=false;if(typeof toast==='function')toast(error.message);else setText($('#phone-remote-label'),error.message); }
    };
    localize();
  }
  function sessionExpired() {
    if(!isRemote || expiring)return;
    expiring=true;location.replace('/phone/login');
  }
  window.AgentBoardPhone={open:openAccess,sessionExpired,get remote(){return isRemote;}};
  document.addEventListener('agentboard:language',()=>localize());
  setInterval(refreshStatus,3000);setInterval(renderCountdown,1000);
  (async()=>{
    try { const response=await fetch('/phone/client',{cache:'no-store',credentials:'same-origin'});if(response.status===401){isRemote=true;sessionExpired();return;}if(response.ok){const payload=await response.json();const client=payload.data ?? payload;if(client.remote){installRemote(client);return;}} } catch (_) { /* Loopback has no phone session; pairing management remains local. */ }
    installLocalPanel();
  })();
})();
