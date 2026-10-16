'use strict';
(()=>{
 let seq=0,scope='',pending=null,planning=null;
 const panel=$('agent-flow');
 const cancelOriginal=$('cancel').onclick;
 $('cancel').onclick=async()=>{if(!planning)return cancelOriginal();seq++;block('已停止本次分析','不会发送本次读取的聊天内容。');if(job?.id)await api('/api/jobs/'+job.id+'/cancel',{});};
 const scopeKey=()=>selected+'|'+$('activity-date').value;
 function invalidate(){if(scope===scopeKey())return;scope=scopeKey();seq++;pending=null;panel.replaceChildren();if(planning?.id)api('/api/jobs/'+planning.id+'/cancel',{}).catch(()=>{});}
 document.addEventListener('vault-account-updated',invalidate);
 document.addEventListener('daily-loading',invalidate);
 document.addEventListener('chat-select',e=>{$('prompt').value='总结 '+$('activity-date').value+' '+e.detail.name+' 当天聊了什么，有哪些重要信息和待办';$('prompt').focus();});
 function block(title,text){panel.replaceChildren();const h=document.createElement('strong');h.textContent=title;const p=document.createElement('p');p.textContent=text;panel.append(h,p);}
 async function retrieve(id,aid,n,choice){
  $('job-state').textContent='正在读取聊天…';block('正在读取相关聊天','已理解你的需求，正在本地查找会话和消息。');
  const r=await api('/api/agent/prepare',{job_id:id,account_id:aid,choice});if(n!==seq)return;
  if(r.status==='answer'){message(r.text,'assistant-message');panel.replaceChildren();return;}
  if(r.status==='clarify'){
   block('需要补充一点信息',r.question);
   for(const c of r.choices){const b=document.createElement('button');b.textContent=c.name;b.onclick=()=>retrieve(id,aid,n,c.id).catch(e=>block('读取未完成',e.message));panel.append(b);}
   return;
  }
  pending=r;$('job-state').textContent='等待确认分析范围';block('已找到本次分析材料',r.date+' · '+r.conversations.length+' 个会话 · '+r.message_count+' 条消息');
  const list=document.createElement('ul');
  for(const c of r.conversations){const li=document.createElement('li');li.textContent=c.name+' · '+c.count+' 条';list.append(li);}panel.append(list);
  const note=document.createElement('p');note.className='small';note.textContent=r.selection+(r.partial?'。材料已截断或只覆盖部分会话，结果不会代表全部聊天。':'。')+' 图片、语音及其他未解析消息仅作占位。';panel.append(note);
  const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='查看消息依据';details.append(summary);const evidence=document.createElement('div');evidence.className='agent-evidence';
  for(const m of r.messages){const p=document.createElement('p');p.textContent='['+m.ref+'] '+m.conversation+' · '+m.time+' · '+(m.is_self?'我':m.sender)+'\n'+m.content;evidence.append(p);}details.append(evidence);panel.append(details);
  const privacy=document.createElement('p');privacy.className='privacy';privacy.textContent='点击下方按钮，将这些会话的所列消息正文、发送者名称和时间发送给当前 Codex 模型服务。';panel.append(privacy);
  const send=document.createElement('button');send.className='primary';send.textContent='用这些消息分析';
  send.onclick=()=>{if(n!==seq||job)return;send.disabled=true;run('/api/chat/ask',{account_id:aid,preview_id:r.preview_id,consent:true,prompt:r.prompt},r.date+' · '+r.conversations.map(c=>c.name).join('、')+'\n'+r.prompt).finally(()=>{if(n===seq)send.disabled=false;});};panel.append(send);
  const reset=document.createElement('button');reset.textContent='调整需求';reset.onclick=()=>{$('prompt').value=r.prompt;$('prompt').focus();};panel.append(reset);
 }
 $('ask').onsubmit=async e=>{
  e.preventDefault();const q=$('prompt').value.trim();if(!q||job||planning)return;
  if(!current()){note('请先选择一个本地账号。');return;}
  const n=++seq,aid=selected;scope=scopeKey();pending=null;
  message(q,'user');$('job-state').textContent='正在理解需求…';block('正在理解你的需求','识别日期、会话和分析目标。此步骤只发送你的问题，不发送聊天记录。');
  $('send').disabled=true;$('probe').disabled=true;$('cancel').hidden=false;job={status:'queued'};planning=job;
  try{
   planning=await api('/api/agent/plan',{account_id:aid,date:$('activity-date').value,prompt:q});job=planning;
   if(n!==seq){await api('/api/jobs/'+planning.id+'/cancel',{});return;}
   while(['queued','running'].includes(planning.status)){
    await new Promise(r=>setTimeout(r,1200));planning=await api('/api/jobs/'+planning.id);job=planning;
    if(n!==seq)return;
   }
   if(planning.status!=='completed')throw Error(planning.error||'需求理解已取消。');
   await retrieve(planning.id,aid,n);
  }catch(e){if(n===seq)block('这次没有完成',e.message+' 可以修改问题后重试。');}
  finally{planning=null;job=null;$('cancel').hidden=true;await status();}
 };
})();
