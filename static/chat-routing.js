/* One source of truth for the visible send summary and the outgoing round budget.
   The Python router remains authoritative for membership, commands and execution. */
(function(root,factory){
  'use strict';
  const routing=factory();
  if(typeof module==='object'&&module.exports)module.exports=routing;
  if(root)root.AgentBoardChatRouting=routing;
})(typeof globalThis==='object'?globalThis:this,function(){
  'use strict';
  const unique=values=>[...new Set((Array.isArray(values)?values:[]).filter(value=>typeof value==='string'&&value))];
  function resolveSend(input={}) {
    const mode=input.mode==='group'?'group':'single',agent=String(input.agent||'codex'),message=String(input.message||'');
    const members=unique(input.members),ids=unique(input.agentIds?.length?input.agentIds:['codex','deepseek',...members]);
    const names=input.agentNames||{};
    const selected=Number(input.selectedRounds??2),selection=Number.isInteger(selected)&&selected>=1&&selected<=3?selected:2;
    let kind=mode==='group'?(agent==='all'?'discussion':'directed'):'single';
    let recipients=agent==='all'?members:[agent],rounds=kind==='discussion'?selection:1,discussionRounds=kind==='discussion'?selection:0;
    let explicitRounds=false,invalid='';
    const parts=message.trim().split(/\s+/),command=parts[0].toLowerCase();
    if(command.startsWith('/')) {
      const target=command==='/ds'?'deepseek':command.slice(1);
      if(ids.includes(target)) {
        kind='directed';recipients=[target];rounds=1;discussionRounds=0;
      } else if(['/all','/讨论','/discuss'].includes(command)) {
        if(mode!=='group')invalid='group';
        else {
          recipients=members;
          if(command==='/all') { kind='broadcast';rounds=1;discussionRounds=0; }
          else {
            kind='discussion';rounds=selection;
            // Match the usual decimal forms accepted by the Python command parser.
            const numeral=(parts[1]||'').replace(/[０-９]/g,char=>String(char.charCodeAt(0)-0xff10));
            if(/^\d+$/.test(numeral)) { rounds=Number(numeral);explicitRounds=true; }
            if(!Number.isInteger(rounds)||rounds<1||rounds>3)invalid='rounds';
            discussionRounds=invalid?selection:rounds;
          }
        }
      } else invalid='command';
    }
    const directed=['single','directed'].includes(kind);
    if(!invalid&&mode==='group'&&!members.length)invalid='members';
    if(!invalid&&directed&&(!ids.includes(recipients[0])||(mode==='group'&&!members.includes(recipients[0]))))invalid='recipient';
    // A one-member room has nobody to discuss with; never schedule self replies.
    if(!invalid&&!directed&&recipients.length===1) { kind='broadcast';rounds=1;discussionRounds=0; }
    const maxReplies=invalid?0:directed?1:Math.min(6,recipients.length*rounds);
    const route={kind:invalid?'invalid':kind,directed,recipients,discussion_rounds:discussionRounds,rounds,max_replies:maxReplies,
      explicitRounds,invalid,body:{message,agent,discussion_rounds:discussionRounds}};
    return {...route,...routeLabels(route,names)};
  }
  function routeLabels(route,names={}) {
    const {kind,recipients,invalid,rounds,max_replies:maxReplies}=route;
    const name=id=>String(names[id]||id);
    let labelZh,labelEn;
    if(invalid) {
      const labels={group:['请先切换到 Agent 群聊','Switch to an agent room first'],members:['群聊 · 请先选择参与成员','Group · Choose room members first'],
        rounds:['群聊 · 讨论轮数需为1至3','Group · Choose 1 to 3 rounds'],recipient:['请检查回复对象是否在房间内','Check that the recipient is a room member'],command:['请检查消息开头的指令','Check the command at the start of the message']};
      [labelZh,labelEn]=labels[invalid];
    } else if(kind==='discussion') {
      labelZh=`群聊 · 全体 · 最多${rounds}轮 · ${maxReplies}次回复`;
      labelEn=`Group · Everyone · Up to ${rounds} ${rounds===1?'round':'rounds'} · ${maxReplies} ${maxReplies===1?'reply':'replies'}`;
    } else if(kind==='broadcast') {
      labelZh=recipients.length===1?`群聊 · ${name(recipients[0])} · 仅1位成员，回复1次`:`群聊 · 全体每位1次 · 最多${maxReplies}次回复`;
      labelEn=recipients.length===1?`Group · ${name(recipients[0])} · One member, 1 reply`:`Group · Everyone once · Up to ${maxReplies} ${maxReplies===1?'reply':'replies'}`;
    } else if(kind==='single') {
      labelZh=`单聊 · ${name(recipients[0])} · 1次回复`;labelEn=`Single chat · ${name(recipients[0])} · 1 reply`;
    } else {
      labelZh=`仅${name(recipients[0])} · 1次回复`;labelEn=`Only ${name(recipients[0])} · 1 reply`;
    }
    return {labelZh,labelEn};
  }
  function resolveComposer(input={}) {
    const batch=input.running&&input.batch,recipients=unique(batch?.recipients);
    if(!batch||!recipients.length)return resolveSend(input);
    // While running, describe the accepted batch rather than the next unsent draft.
    const directed=Boolean(batch.directed),rawRounds=Number(batch.rounds??batch.requested_rounds??0);
    const discussionRounds=directed?0:Number.isInteger(rawRounds)&&rawRounds>0?Math.min(3,rawRounds):0;
    const kind=directed?'directed':discussionRounds>0?'discussion':'broadcast',rounds=Math.max(1,discussionRounds);
    const reportedMax=Number(batch.max_replies),fallbackMax=Math.min(6,recipients.length*rounds);
    const maxReplies=directed?1:Number.isInteger(reportedMax)&&reportedMax>0?Math.min(6,reportedMax):fallbackMax;
    const route={kind,directed,recipients,discussion_rounds:discussionRounds,rounds,max_replies:maxReplies,explicitRounds:false,invalid:'',
      body:{message:String(batch.user_message||''),agent:directed?recipients[0]:'all',discussion_rounds:discussionRounds}};
    return {...route,...routeLabels(route,input.agentNames)};
  }
  function describeBatch(batch={}) {
    const completed=Number.isFinite(Number(batch.completed))?Math.max(0,Number(batch.completed)):0;
    let labelZh=`本批次结束，${completed}次回复。`,labelEn=`Batch finished: ${completed} ${completed===1?'reply':'replies'}.`;
    const reasons={
      agents_done:['所有成员表示可以结束。','All members indicated that the discussion can end.'],
      broadcast_complete:['全体成员已各回复一次。','Each member has replied once.'],
      directed_complete:['指定成员已完成回复。','The selected member has replied.'],
      round_limit:['已完成所选轮数。','The selected rounds are complete.'],
      reply_limit:['已达到本批次回复上限。','The batch reply limit was reached.'],
      quota_limited:['额度不足，已提前结束。','The discussion ended early because quota was unavailable.'],
      stopped:['已按要求停止。','Stopped as requested.'],
      deadline:['已达到时限，讨论停止。','The time limit was reached.'],
      reply_failed:['有回复未完成，请查看错误说明。','A reply did not finish. Check the error details.'],
      failed:['有回复未完成，请查看错误说明。','A reply did not finish. Check the error details.']
    };
    const requested=Number(batch.requested_rounds),rounds=Number(batch.completed_rounds);
    if(Number.isInteger(requested)&&requested>0&&Number.isInteger(rounds)&&rounds>=0) {
      labelZh+=` 已完成${rounds}/${requested}轮。`;labelEn+=` Completed ${rounds}/${requested} rounds.`;
    }
    const reason=reasons[batch.end_reason];
    if(reason){labelZh+=' '+reason[0];labelEn+=' '+reason[1];}
    else if(batch.finish_detail){labelZh+=' '+String(batch.finish_detail);labelEn+=' '+String(batch.finish_detail);}
    return {labelZh,labelEn};
  }
  return {resolveSend,resolveComposer,describeBatch};
});
