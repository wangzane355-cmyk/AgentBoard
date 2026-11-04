/* Local preferences. Cached capabilities do not prove account access. */
let modelSettingsDraft=null;
const modelSay=(zh,en)=>AgentBoardI18n.choose(zh,en);
function codexModelSettings(){return state.model_settings?.codex;}
function effortName(v){return ({none:modelSay('关闭','None'),minimal:modelSay('最低','Minimal'),low:modelSay('低','Low'),medium:modelSay('中','Medium'),high:modelSay('高','High'),xhigh:modelSay('很高','Extra high'),max:modelSay('最高','Maximum'),ultra:modelSay('极高（可自动委派）','Ultra (may delegate)')})[v]||v;}
function modelControlValues(root){return {model:root.querySelector('[data-model-select]').value,reasoning_effort:root.querySelector('[data-effort-select]').value};}
function populateModelControls(root,values={},task=false){
  const config=codexModelSettings(),model=root.querySelector('[data-model-select]'),effort=root.querySelector('[data-effort-select]');
  const inherit=modelSay(task?'继承Agent设置':'跟随Codex默认配置',task?'Inherit agent settings':'Follow Codex defaults'),list=config?.models||[];
  model.innerHTML=`<option value="">${inherit}</option>`+list.map(m=>`<option value="${esc(m.id)}">${esc(m.name)} · ${esc(m.id)}</option>`).join('');
  if(values.model&&!list.some(m=>m.id===values.model))model.innerHTML+=`<option value="${esc(values.model)}">${esc(values.model)} (${modelSay('目录中已缺失','missing from catalog')})</option>`;
  model.value=values.model||'';
  const selected=model.value||(task?config?.preferences?.model:'')||config?.local_defaults?.model;
  const levels=list.find(m=>m.id===selected)?.efforts||[];
  effort.innerHTML=`<option value="">${inherit}</option>`+levels.map(v=>`<option value="${esc(v)}">${esc(effortName(v))}</option>`).join('');
  if(values.reasoning_effort&&!levels.includes(values.reasoning_effort))effort.innerHTML+=`<option value="${esc(values.reasoning_effort)}" disabled>${esc(values.reasoning_effort)} (${modelSay('不支持','unsupported')})</option>`;
  effort.value=values.reasoning_effort||'';effort.disabled=!levels.length;
}
function renderModelSettings(){
  const host=$('#codex-model-settings'),config=codexModelSettings();if(!host||!config)return;
  host.innerHTML=`<form id="model-settings-form"><h3>${modelSay('Codex 模型与推理强度','Codex model and reasoning')}</h3><p class="hint">${modelSay('本机默认配置参考：','Local default reference: ')}<span data-model-value>${esc(config.local_defaults.model||'—')} · ${esc(config.local_defaults.reasoning_effort||'—')}</span></p><div class="model-controls"><label>${modelSay('模型版本','Model version')}<select data-model-select aria-label="${modelSay('Codex模型版本','Codex model version')}"></select></label><label>${modelSay('推理强度','Reasoning effort')}<select data-effort-select aria-label="${modelSay('Codex推理强度','Codex reasoning effort')}"></select></label></div><p class="hint">${modelSay('目录来自本机缓存，不代表账号权限已验证。推理越充分，通常耗时和用量越高。仅影响AgentBoard后续调用。','The catalog comes from the local cache; account access is unverified. More reasoning usually takes more time and usage. Applies only to future AgentBoard calls.')}</p><button class="primary" type="submit">${modelSay('保存模型设置','Save model settings')}</button> <button class="ghost" type="button" id="model-settings-reset">${modelSay('恢复跟随默认','Restore defaults')}</button><p role="status" id="model-settings-result"></p></form>`;
  const form=$('#model-settings-form');populateModelControls(form,modelSettingsDraft||config.preferences||{});
  form.querySelector('[data-model-select]').onchange=()=>{modelSettingsDraft={model:form.querySelector('[data-model-select]').value,reasoning_effort:''};populateModelControls(form,modelSettingsDraft);};
  form.querySelector('[data-effort-select]').onchange=()=>{modelSettingsDraft=modelControlValues(form);};
  async function save(options){try{await api('/api/agents/model-settings',options);modelSettingsDraft=null;await refresh();renderModelSettings();$('#model-settings-result').textContent=modelSay('已保存，仅影响后续调用；没有调用模型。','Saved for future calls; no model was called.');}catch(e){toast(e.message);}}
  form.onsubmit=e=>{e.preventDefault();save(modelControlValues(form));};$('#model-settings-reset').onclick=()=>save({model:'',reasoning_effort:''});
}
function updateTaskModelControls(values=null){
  const form=$('#task-form'),host=$('#task-model-options');if(!host)return;
  host.classList.toggle('hidden',form.elements.agent.value!=='codex');populateModelControls(host,values||modelControlValues(host),true);
}
function modelRecordLabel(record){
  if(!record)return '';
  const c=record.confirmed||{},r=record.requested||{};
  const text=c.model?`${modelSay('运行日志','Runtime log')}: ${c.model} · ${c.reasoning_effort||modelSay('强度未确认','effort unconfirmed')}`:`${modelSay('请求设置（未确认）','Requested (unconfirmed)')}: ${r.model||modelSay('默认型号','default model')} · ${r.reasoning_effort||modelSay('默认强度','default effort')}`;
  return `<small class="model-record" data-model-value>${esc(text)}</small>`;
}
$('#task-form').elements.agent.addEventListener('change',()=>updateTaskModelControls({}));
$('#task-model-options [data-model-select]').addEventListener('change',()=>updateTaskModelControls({model:$('#task-model-options [data-model-select]').value,reasoning_effort:''}));
document.addEventListener('agentboard:language',()=>{if($('#task-dialog').open)updateTaskModelControls();});
