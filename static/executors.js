/* Preparation and selection are separate, explicit user actions. */
let executorSignature='';
let executorBusy=false;
function renderExecutorManager(){
  const root=document.querySelector('#executor-manager');if(!root)return;
  const data=state.executors;
  const signature=JSON.stringify(data)+AgentBoardI18n.language;
  if(signature===executorSignature)return;executorSignature=signature;
  if(!data){root.querySelector('#executor-status').textContent=say('需重启后台以加载版本管理','Restart the service to load version management');root.querySelectorAll('button').forEach(b=>b.disabled=true);return;}
  const current=data.versions?.[data.current],previous=data.versions?.[data.previous];
  const operation=data.operation||{};
  $('#executor-status').textContent=data.error||say('当前：','Current: ')+(current?current.version:say('自动查找入口（未固定）','Auto-discovered (not pinned)'))+say(' · 旧版本：',' · Previous: ')+(previous?.version||'—')+(current?say(' · 启动检查：',' · Startup check: ')+(current.health?.status||'—'):'');
  $('#executor-operation').textContent=operation.status==='running'?say('正在准备，原版本继续可用：','Preparing; current version remains available: ')+(operation.phase||''):operation.status==='failed'?operation.error:operation.status==='ready'?say('新版本已就绪，尚未切换。','Prepared and checked; not activated.') :'';
  const busy=operation.status==='running';
  $('#executor-pin').disabled=busy||Boolean(current);$('#executor-prepare').disabled=busy;$('#executor-check').disabled=busy||!current;$('#executor-rollback').disabled=busy||!previous;
  $('#executor-versions').innerHTML=Object.entries(data.versions||{}).map(([slot,record])=>`<div class="runtime-row"><span><strong>${esc(record.version)}</strong> · ${esc(record.health?.status||'unchecked')}${slot===data.current?' · '+say('正在使用','Active'):slot===data.previous?' · '+say('可回退','Previous'):''}</span><button type="button" class="ghost" data-runtime-slot="${esc(slot)}" ${slot===data.current||busy?'disabled':''}>${say('切换到此版本','Use this version')}</button></div>`).join('');
  root.querySelectorAll('[data-runtime-slot]').forEach(button=>button.onclick=()=>{
    if(confirm(say('检查通过后切换到此版本？当前版本会保留，可回退。','Check and switch to this version? The current version will be retained for rollback.')))executorAction('activate',{slot:button.dataset.runtimeSlot});
  });
}
async function executorAction(action,body={}){
  if(executorBusy)return;executorBusy=true;
  try{const result=await api('/api/executors/'+action,body);if(action==='latest'){
    $('#executor-version').value=result.data.version;$('#executor-update-result').textContent=say('官方发布版本：','Official registry version: ')+result.data.version+say('。未下载、未切换。',' · Nothing downloaded or activated.');
  }await refresh();executorSignature='';renderExecutorManager();}
  catch(error){toast(error.message);}finally{executorBusy=false;}
}
$('#executor-pin').onclick=()=>executorAction('prepare');
$('#executor-latest').onclick=()=>executorAction('latest');
$('#executor-check').onclick=()=>executorAction('check');
$('#executor-prepare').onclick=()=>{
  const version=$('#executor-version').value.trim();if(!version)return toast(say('请先填写指定版本','Enter an exact version first'));
  if(confirm(say('从官方npm源准备指定版本？此操作下载程序，不调用模型，也不会自动切换。','Prepare this exact version from the official npm registry? This downloads software, makes no model call and does not activate it.')))executorAction('prepare',{version});
};
$('#executor-rollback').onclick=()=>{if(confirm(say('检查并切回上一个版本？','Check and switch back to the previous version?')))executorAction('rollback');};
document.addEventListener('agentboard:language',()=>{executorSignature='';renderExecutorManager();});
