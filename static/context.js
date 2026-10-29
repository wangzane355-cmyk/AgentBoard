let contextProject = null;
function referenceLines(value){return String(value||'').split('\n').map(x=>x.trim()).filter(Boolean);}
function openProjectContext(){
  const project=state.projects.find(p=>p.id===activeProject);
  if(!project)return toast('请先选择项目');
  contextProject=project.id;
  $('#context-project-title').textContent=project.name;
  $('#context-project-path').value=project.path;
  const form=$('#context-form');
  form.elements.context_files.value=(project.context_files||[]).join('\n');
  form.elements.context_urls.value=(project.context_urls||[]).join('\n');
  $('#context-preview').classList.add('hidden');
  $('#context-dialog').showModal();
}
function referenceBody(){const f=$('#context-form');return {project_id:contextProject,context_files:referenceLines(f.elements.context_files.value),context_urls:referenceLines(f.elements.context_urls.value)};}
$('#project-context').onclick=openProjectContext;
document.querySelectorAll('[data-pick]').forEach(button=>button.onclick=async()=>{
  button.disabled=true;
  try{
    const result=await api('/api/pick-path',{kind:button.dataset.pick});
    if(result.data.path){const area=$('#context-local'),paths=referenceLines(area.value);if(!paths.includes(result.data.path))paths.push(result.data.path);area.value=paths.join('\n');}
  }catch(e){toast(e.message);}finally{button.disabled=false;}
});
$('#preview-context').onclick=async()=>{
  const button=$('#preview-context'),box=$('#context-preview');
  button.disabled=true;box.classList.remove('hidden');box.textContent='正在重新读取关联资料…';
  try{
    const result=(await api('/api/context/preview',referenceBody())).data;
    box.textContent=`读取时间：${new Date(result.read_at).toLocaleString()}\n读取 ${result.sources.length} 项，目录另省略 ${result.omitted} 项${result.directory_scan_limited?'（目录扫描已达上限）':''}\n\n`+result.sources.map(s=>`${s.truncated?'[截取]':'[全文]'} ${s.source}\n快照 ${s.characters} 字符 · ${s.sha256.slice(0,12)}`).join('\n\n')+'\n\n内容预览：\n'+result.prompt;
  }catch(e){box.textContent='读取失败：'+e.message;}finally{button.disabled=false;}
};
$('#context-form').onsubmit=async e=>{
  e.preventDefault();const button=$('#save-context');button.disabled=true;
  try{await api(`/api/projects/${contextProject}/update`,referenceBody());$('#context-dialog').close();await refresh();toast('资料关联已保存，下次讨论和派工会自动重新读取。');}catch(err){toast(err.message);}finally{button.disabled=false;}
};
