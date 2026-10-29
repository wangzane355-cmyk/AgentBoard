/* Runs before paint; preference is browser-local and never calls an API. */
(() => {
  'use strict';
  const ids = ['default','graphite','construct','obsidian'];
  let selected='default';
  try { const stored=localStorage.getItem('agentboard.theme'); if(ids.includes(stored))selected=stored; } catch (_) { /* Optional local persistence. */ }
  document.documentElement.dataset.theme=selected;
  function choose(id){
    if(!ids.includes(id))return;
    selected=id;document.documentElement.dataset.theme=id;
    try {localStorage.setItem('agentboard.theme',id);} catch (_) { /* Still usable without storage. */ }
    update();
  }
  function update(){
    document.querySelectorAll('[name="appearance-theme"]').forEach(input=>{input.checked=input.value===selected;});
    const names={default:['原始深色','Original dark'],graphite:['静灰 · 极简','Graphite · Minimal'],construct:['构成 · 酒红','Construct · Burgundy'],obsidian:['黑曜 · 金属','Obsidian · Metal']};
    const label=document.getElementById('appearance-current');
    if(label)label.textContent=window.AgentBoardI18n?AgentBoardI18n.choose(...names[selected]):names[selected][0];
  }
  document.addEventListener('DOMContentLoaded',()=>{
    document.getElementById('open-settings').addEventListener('click',()=>{update();document.getElementById('appearance-dialog').showModal();});
    document.querySelectorAll('[name="appearance-theme"]').forEach(input=>input.addEventListener('change',()=>{if(input.checked)choose(input.value);}));
    document.getElementById('appearance-reset').addEventListener('click',()=>choose('default'));
    document.addEventListener('agentboard:language',update);
    update();
  });
})();
