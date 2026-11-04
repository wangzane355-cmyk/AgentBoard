/* The pairing code exists only in this form and its same-origin POST body. */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  let language=navigator.language?.startsWith('zh')?'zh-CN':'en',busy=false,stage='pair';
  try { const saved=localStorage.getItem('agentboard.language');if(['zh-CN','en'].includes(saved))language=saved; } catch (_) { /* Pairing works without browser storage. */ }
  const copy={
    brandNote:['你的工作区，随身继续','Your workspace, wherever you sit'],
    title:['连接电脑上的 AgentBoard','Connect to AgentBoard'],
    intro:['先在电脑打开“设置 → 手机访问”，再输入那里显示的 8 位一次配对码。','On the computer, open Settings → Phone access. Enter the 8-digit one-time code shown there.'],
    codeLabel:['一次配对码','One-time pairing code'],codeHelp:['配对码只用一次，不是你的账号密码。','The code works once. It is not your account password.'],
    nameLabel:['这台手机的名称','Name this phone'],optional:['可选','Optional'],submit:['配对并打开工作区 ↗','Pair & open workspace ↗'],
    requirements:['手机和电脑需连接同一个家庭 Wi-Fi，电脑上的 AgentBoard 需要保持运行。','Keep the phone and computer on the same home Wi-Fi, with AgentBoard running on the computer.'],
    privacy:['只在可信任的 Wi-Fi 使用。此连接使用 HTTP，没有 TLS 加密。无需安装 App 或注册新账号。','Use trusted Wi-Fi only. This HTTP connection has no TLS encryption. No app installation or new account is needed.']
  };
  const choose=(zh,en)=>language==='en'?en:zh;
  function localize(){
    document.documentElement.lang=language;document.title=choose('AgentBoard · 手机配对','AgentBoard · Pair phone');
    $('#pair-language').value=language;
    document.querySelectorAll('[data-pair-copy]').forEach(element=>{const pair=copy[element.dataset.pairCopy];if(pair)element.textContent=choose(...pair);});
    $('#pair-device-name').placeholder=choose('例如：我的安卓手机','For example: My Android phone');
    $('#pair-submit').textContent=busy?(stage==='verify'?choose('正在检查连接…','Checking connection…'):choose('正在配对…','Pairing…')):choose(...copy.submit);
  }
  $('#pair-language').onchange=event=>{language=event.target.value==='en'?'en':'zh-CN';try{localStorage.setItem('agentboard.language',language);}catch(_){}localize();};
  $('#pair-code').addEventListener('input',event=>{
    const input=event.target,atEnd=input.selectionStart===input.value.length;
    const digits=input.value.replace(/\D/g,'').slice(0,8),formatted=digits.length>4?digits.slice(0,4)+' '+digits.slice(4):digits;
    if(input.value!==formatted){input.value=formatted;if(atEnd)input.setSelectionRange(formatted.length,formatted.length);}
  });
  $('#pair-form').onsubmit=async event=>{
    event.preventDefault();if(busy)return;
    const code=$('#pair-code').value.replace(/\D/g,'');
    const error=$('#pair-error');error.hidden=true;
    if(!/^\d{8}$/.test(code)){error.textContent=choose('请输入电脑上显示的完整 8 位配对码。','Enter the full 8-digit code shown on the computer.');error.hidden=false;$('#pair-code').focus();return;}
    busy=true;stage='pair';$('#pair-submit').disabled=true;$('#pair-code').disabled=true;$('#pair-device-name').disabled=true;localize();
    $('#pair-status').textContent=choose('正在连接这台电脑…','Connecting to this computer…');
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    let pairingAccepted=false;
    try{
      const response=await fetch('/phone/pair',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',signal:controller.signal,body:JSON.stringify({code,device_name:$('#pair-device-name').value.trim()||choose('我的手机','My phone')})});
      let result;try{result=await response.json();}catch(_){throw new Error(choose('电脑没有返回有效结果，请确认 AgentBoard 仍在运行。','No valid response. Check that AgentBoard is still running on the computer.'));}
      if(!response.ok || result.ok===false)throw new Error(result.error || choose('配对未成功，请换一个配对码再试。','Pairing failed. Try a new pairing code.'));
      pairingAccepted=true;$('#pair-code').value='';stage='verify';localize();
      $('#pair-status').textContent=choose('配对码已接受，正在检查浏览器登录状态…','Code accepted. Checking this browser’s sign-in…');
      const confirmation=await fetch('/phone/client',{method:'GET',credentials:'same-origin',cache:'no-store',signal:controller.signal});
      const cookieHelp=choose('浏览器没有保存登录状态。请允许此站点保存 Cookie，或在 Chrome 地址栏直接打开此地址；原码可能已使用，电脑可换新码。','This browser did not save the sign-in. Allow cookies for this site, or open this address directly in the Chrome address bar. The original code may have been used; generate a new code on the computer.');
      if(confirmation.status===401)throw new Error(cookieHelp);
      if(confirmation.status!==200)throw new Error(choose('配对码已接受，但暂时无法检查登录状态。请在电脑换新码后重试。','The code was accepted, but sign-in could not be checked. Generate a new code on the computer and retry.'));
      let client;
      try{client=await confirmation.json();}catch(_){throw new Error(choose('配对码已接受，但电脑没有返回有效的登录状态。请在电脑换新码后重试。','The code was accepted, but the computer returned no valid sign-in state. Generate a new code and retry.'));}
      if((client?.data??client)?.remote!==true)throw new Error(cookieHelp);
      $('#pair-status').textContent=choose('连接已确认，正在打开工作区…','Connection confirmed. Opening the workspace…');location.replace('/');
    }catch(problem){
      const connectionFailure=problem instanceof TypeError || problem.name==='AbortError';
      error.textContent=connectionFailure?choose('连接中断或超时。请确认手机与电脑在同一 Wi-Fi，且电脑上的手机访问仍开启。','Connection lost or timed out. Check that both devices use the same Wi-Fi and phone access is still enabled.')+(pairingAccepted?choose(' 原配对码可能已使用，请在电脑换新码后重试。',' The original code may have been used. Generate a new code on the computer and retry.'):''):problem.message;
      error.hidden=false;$('#pair-status').textContent='';
    }
    finally{clearTimeout(timer);busy=false;$('#pair-submit').disabled=false;$('#pair-code').disabled=false;$('#pair-device-name').disabled=false;localize();}
  };
  localize();
})();
