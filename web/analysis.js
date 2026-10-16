'use strict';
const $=id=>document.getElementById(id);
let token='',accounts=[],generation=0,preview=null,report=null,job=null,busy=false,loaded=null,activity=null,cacheState=null,undoId=null,autoTimer=null,cancelRequested=false;
const categories=['邀约','事项推进','待办','决策','截止提醒','其他重要信息'];
const fmt=d=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);
const today=()=>fmt(new Date());
const stamp=s=>s?new Date(s).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'未知';
const state=()=>({account_id:$('account').value,start:$('start').value,end:$('end').value,metric:$('metric').value});
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
async function api(path,body){const r=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json','X-Vault-Token':token},body:body===undefined?undefined:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(v.error||'请求失败');return v;}
function text(tag,value,cls){const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e;}
function error(e){$('error').textContent=e||'';$('error').hidden=!e;}
function controls(){for(const id of ['account','start','end','metric','prepare'])$(id).disabled=busy||!!job||!accounts.length;document.querySelectorAll('[data-days]').forEach(b=>b.disabled=busy||!!job);}
function reset(){generation++;preview=null;report=null;cacheState=null;$('cache-status').hidden=true;$('categories').replaceChildren();$('todos').replaceChildren(text('p','点击“一键提取并分析”，找出需要跟进的事。','analysis-empty'));$('events').replaceChildren(text('p','完成分析后显示简短概述。','small'));$('event-total').textContent='等待提取';$('report-coverage').textContent='尚未进行 AI 分析';error('');}
function range(days){$('end').value=today();const d=new Date(today()+'T12:00:00+08:00');d.setUTCDate(d.getUTCDate()-days+1);$('start').value=fmt(d);document.querySelectorAll('[data-days]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.days)===days)));}
function coverage(){if(!loaded)return;$('page-title').textContent=loaded.start===today()&&loaded.end===today()?'今天，先关注这些事。':'这段时间，先关注这些事。';const a=accounts.find(a=>a.id===loaded.account_id);$('coverage').textContent=(a?.overview.nickname||a?.label||'')+' · '+loaded.start+(loaded.end!==loaded.start?' 至 '+loaded.end:'')+' · 本地快照'+(activity?.status==='partial'?'（部分统计）':'')+(!same(loaded,state())?' · 即将按新范围自动分析':'');}
function renderPeople(){
 $('people').replaceChildren();if(!activity)return;
 const rows=[...activity.private].sort((a,b)=>loaded.metric==='mine'?(b.mine??-1)-(a.mine??-1):b.total-a.total).slice(0,8);
 for(const row of rows){
  const line=text('div','','contact-row'),avatar=text('span',Array.from(row.name)[0]||'聊','contact-avatar'),name=text('div','','contact-name'),heading=text('div',row.name,'contact-title');
  const relation=report?.relationships.find(r=>r.chat_id? r.chat_id===row.chat_id:r.name===row.name&&activity.private.filter(x=>x.name===r.name).length===1);
  if(relation){const tag=document.createElement('details');tag.className='relation-tag';tag.append(text('summary',relation.label+' · 推测'));const more=text('div','','relation-pop');more.append(text('p',relation.reason+'（置信程度：'+relation.confidence+'）'),evidence(relation.evidence));tag.append(more);heading.append(tag);}
  name.append(heading,text('small','双方 '+row.total+' 条 · 我发 '+(row.mine??'未知')+' 条'));line.append(avatar,name);$('people').append(line);const accountId=loaded.account_id;api('/api/avatar',{account_id:accountId,chat_id:row.chat_id}).then(r=>{if(!r.image||!avatar.isConnected||loaded?.account_id!==accountId)return;const img=document.createElement('img');img.src=r.image;img.alt='';img.onerror=()=>{avatar.textContent=Array.from(row.name)[0]||'聊';};avatar.replaceChildren(img);}).catch(()=>{});
 }
 if(!rows.length)$('people').append(text('p','这段时间没有已读取的私聊。','small'));
}
function saveView(){try{localStorage.setItem('wechat-analysis-view',JSON.stringify({...loaded,saved_on:today()}));}catch{}}
function cacheLabel(){
 const saved=cacheState?.report;
 $('cache-status').hidden=!saved&&!undoId&&!cacheState?.summary?.reports;
 if(saved){$('cache-label').textContent='已保存在本机 · '+stamp(cacheState.saved_at*1000)+(cacheState.snapshot_changed?' · 快照已更新，可重新提取':cacheState.version_changed?' · 分析规则已更新，可重新提取':'');}
 else $('cache-label').textContent=undoId?'已移除此范围缓存，可以撤销。':'本机已保存 '+(cacheState?.summary?.reports||0)+' 份分析，可从历史中查看。';
 $('cache-history').hidden=!cacheState?.history?.length;
 $('cache-history-list').replaceChildren(...(cacheState?.history||[]).map(h=>{const b=text('button',h.start+(h.end!==h.start?' 至 '+h.end:''));b.disabled=busy||!!job;b.onclick=()=>{$('start').value=h.start;$('end').value=h.end;document.querySelectorAll('[data-days]').forEach(x=>x.setAttribute('aria-pressed','false'));void overview();};return b;}));
 $('cache-clear').hidden=!saved;$('cache-undo').hidden=!undoId;
 $('cache-clear').disabled=!!job||busy;
 const mark=document.createElement('img');mark.src='/assets/codex.png';mark.alt='';mark.className='codex-button-logo';$('prepare').replaceChildren(mark,document.createTextNode(saved?'重新分析':'一键提取并分析'));
}
async function restore(n){
 const r=await api('/api/analysis/cache',loaded);if(n!==generation)return;
 cacheState=r;undoId=r.undo_id||null;if(r.report){report=r.report;render();}cacheLabel();
 if(r.pending&&!job)void watchJob(r.pending.id,n,loaded.account_id);
 else if(r.last_failure&&!r.report)error(r.last_failure.error||'上次分析未完成，可重新提取。');
}
async function watchJob(id,n,aid){
 job={id,status:'running'};$('progress').hidden=false;$('progress-text').textContent='正在分析，离开页面后仍会自动保存…';$('cancel').hidden=false;controls();
 try{
  let r=await api('/api/analysis/result',{account_id:aid,job_id:id});
  while(['queued','running'].includes(r.status)){await new Promise(resolve=>setTimeout(resolve,1200));r=await api('/api/analysis/result',{account_id:aid,job_id:id});if(n!==generation)return;}
  if(n!==generation)return;if(r.status!=='completed')throw Error(r.error||'分析已中断，已保存结果仍保留。');
  report=r;render();cacheState=await api('/api/analysis/cache',loaded);cacheLabel();
 }catch(e){if(n===generation)error(e.message);}
 finally{job=null;$('progress').hidden=true;controls();cacheLabel();}
}
async function overview(){
 if(busy||job)return false;reset();undoId=null;const n=generation,selection=state();busy=true;controls();$('people').replaceChildren(text('p','正在读取…','small'));
 try{const r=await api('/api/analysis/overview',selection);if(n!==generation)return false;activity=r;loaded=selection;saveView();coverage();renderPeople();await restore(n);return true;
 }catch(e){error(e.message);activity=null;loaded=null;$('people').replaceChildren(text('p','统计未完成。','small'));return false;}finally{busy=false;controls();cacheLabel();}
}
async function analyzeRange(force=false){
 clearTimeout(autoTimer);autoTimer=null;
 if(busy||job)return;
 if(!loaded||!same(loaded,state())){if(!await overview())return;}
 if(job)return;
 if(!force&&report&&!cacheState?.snapshot_changed&&!cacheState?.version_changed)return;
 const n=++generation,aid=loaded.account_id;preview=null;cancelRequested=false;busy=true;error('');controls();cacheLabel();
 $('progress').hidden=false;$('progress-text').textContent='正在读取聊天，随后自动分析…';$('cancel').hidden=false;
 try{
  preview=await api('/api/analysis/prepare',loaded);
  if(cancelRequested||n!==generation)return;
  $('progress-text').textContent='已读取 '+preview.message_count+' 条消息，正在启动 AI 分析…';
  job={status:'queued'};
  const created=await api('/api/analysis/start',{account_id:aid,preview_id:preview.preview_id,consent:true});
  job=created;busy=false;
  if(cancelRequested)await api('/api/jobs/'+created.id+'/cancel',{});
  await watchJob(created.id,n,aid);
 }catch(e){if(n===generation)error(e.message);job=null;}
 finally{busy=false;preview=null;$('progress').hidden=true;controls();cacheLabel();}
}
function scheduleAnalysis(){
 clearTimeout(autoTimer);preview=null;coverage();
 autoTimer=setTimeout(()=>{
  const s=state(),first=Date.parse(s.start),last=Date.parse(s.end);
  if(!Number.isFinite(first)||!Number.isFinite(last)||last<first||last-first>30*86400000){error('请选择有效的 1–31 天日期范围。');return;}
  void analyzeRange(false);
 },700);
}
function evidence(refs){const d=document.createElement('details');d.append(text('summary','查看依据'));const box=text('div','','evidence');for(const ref of refs){const m=report.evidence[ref];if(m)box.append(text('p','['+ref+'] '+m.conversation+' · '+m.time+' · '+(m.is_self?'我':m.sender)+'\n'+m.content));}d.append(box);return d;}
function render(){
 renderPeople();
 const active=e=>['待办','截止提醒'].includes(e.category)&&!['已完成','已取消'].includes(e.status);
 const todos=report.events.filter(active),others=report.events.filter(e=>!active(e));
 $('event-total').textContent=todos.length+' 项待跟进';
 $('todos').replaceChildren();
 for(const e of todos){const c=text('article','','todo-card'),meta=text('p',[e.owner!=='待确认'?'负责人：'+e.owner:'负责人待确认',e.due!=='待确认'?e.due:'时间待确认'].join(' · '),'todo-meta'),details=document.createElement('details');details.append(text('summary','详情与依据'),text('p',e.detail),evidence(e.evidence));c.append(text('span',e.status,'todo-status'),text('h3',e.title),meta,details);$('todos').append(c);}
 if(!todos.length)$('todos').append(text('p','本次材料中未提取到待跟进事项。','analysis-empty'));
 $('events').replaceChildren();
 for(const e of others){const row=text('article','','brief-event');row.append(text('span',e.category+' · '+e.status,'small'),text('h3',e.title),text('p',e.detail.length>100?e.detail.slice(0,100)+'…':e.detail));const d=document.createElement('details');d.append(text('summary','查看详情'),text('p',e.detail),evidence(e.evidence));row.append(d);$('events').append(row);}
 if(!others.length)$('events').append(text('p','暂无其他重要动态。','small'));
 $('categories').replaceChildren(...categories.map(c=>text('span',c+' '+report.counts[c],'count-chip')));
 $('report-coverage').textContent=report.start+' 至 '+report.end+' · 快照 '+stamp(report.snapshot_at)+(report.partial?' · 部分材料分析，不代表全部事项':'')+(report.discarded?' · 已剔除 '+report.discarded+' 项无有效依据的结果':'');
}
$('cache-clear').onclick=async()=>{
 if(!loaded||job||busy)return;
 try{const r=await api('/api/analysis/cache/clear',loaded);undoId=r.undo_id;reset();await restore(generation);cacheLabel();renderPeople();}
 catch(e){error(e.message);}
};
$('cache-undo').onclick=async()=>{
 if(!undoId||!loaded)return;
 try{await api('/api/analysis/cache/undo',{account_id:loaded.account_id,undo_id:undoId});undoId=null;await restore(generation);}
 catch(e){error(e.message);}
};
$('cancel').onclick=async()=>{
 cancelRequested=true;
 if(job?.id)try{await api('/api/jobs/'+job.id+'/cancel',{});}catch(e){error(e.message);}
 else $('progress-text').textContent='已停止，正在结束本地读取…';
};
$('prepare').onclick=()=>analyzeRange(true);
for(const id of ['account','start','end'])$(id).onchange=()=>{
 if(['start','end'].includes(id))document.querySelectorAll('[data-days]').forEach(b=>b.setAttribute('aria-pressed','false'));
 scheduleAnalysis();
};
$('metric').onchange=()=>{
 if(loaded&&loaded.account_id===state().account_id&&loaded.start===state().start&&loaded.end===state().end){
  loaded.metric=$('metric').value;saveView();renderPeople();
 }
};
document.querySelectorAll('[data-days]').forEach(b=>b.onclick=()=>{range(Number(b.dataset.days));scheduleAnalysis();});
(async()=>{range(1);$('end').max=today();$('start').max=today();try{token=(await api('/api/bootstrap')).token;const r=await api('/api/scan',{});accounts=r.accounts;for(const a of accounts)$('account').add(new Option(a.overview.nickname||a.label,a.id));
 try{const saved=JSON.parse(localStorage.getItem('wechat-analysis-view'));if(saved?.saved_on===today()&&accounts.some(a=>a.id===saved.account_id)&&/^\d{4}-\d{2}-\d{2}$/.test(saved.start)&&/^\d{4}-\d{2}-\d{2}$/.test(saved.end)){
 $('account').value=saved.account_id;$('start').value=saved.start;$('end').value=saved.end;$('metric').value=saved.metric==='mine'?'mine':'total';
 document.querySelectorAll('[data-days]').forEach(b=>b.setAttribute('aria-pressed',String(saved.start===today()&&saved.end===today()&&b.dataset.days==='1')));
 }}catch{}
 await overview();}catch(e){error(e.message);}})();
