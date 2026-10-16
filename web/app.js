'use strict';
const $=id=>document.getElementById(id);let token='',data=null,selected='',job=null,scanning=false;
const date=s=>s?new Date(s).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}):'—';
const bytes=n=>n>1048576?(n/1048576).toFixed(1)+' MB':(n/1024).toFixed(1)+' KB';
function note(t){$('notice').textContent=t||'';$('notice').hidden=!t;}
async function api(path,body){const r=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json','X-Vault-Token':token},body:body===undefined?undefined:JSON.stringify(body)});const result=await r.json();if(!r.ok)throw Error(result.error||'请求失败');return result;}
function current(){return data?.accounts.find(a=>a.id===selected);}
const number=n=>n===null||n===undefined?'—':n.toLocaleString('zh-CN');
const stateName=s=>({ready:'已读取聊天数据',partial:'已读取 · 部分数据',not_read:'尚未读取聊天数据',unavailable:'快照暂不可用'}[s]||'待检测');
function render(){
 const a=current(),o=a?.overview;
 $('accounts').replaceChildren();
 for(const account of data.accounts){
  const overview=account.overview,b=document.createElement('button');
  b.textContent=overview.nickname||account.label+'（昵称未读取）';
  const sub=document.createElement('small');sub.textContent=stateName(overview.status);b.append(sub);
  b.className=account.id===selected?'selected':'';
  b.onclick=()=>{selected=account.id;$('category').value='';$('include-context').checked=false;render();if(account.overview.status==='not_read'&&!sessionStorage.getItem('import-seen-'+selected)){sessionStorage.setItem('import-seen-'+selected,'1');openImport();}else ingestStatus();};$('accounts').append(b);
 }
 $('account-title').textContent=o?.nickname||(a?a.label+' · 昵称待读取':'未发现本地账号');
 $('avatar').textContent=o?.nickname?o.nickname.slice(0,1):'微';
 $('identity-detail').textContent=o?.nickname?'账号标识：'+o.username:o?'本地目录标识：'+o.username+'（非昵称）':'请先登录 macOS 微信并同步记录';
 $('read-state').textContent=stateName(o?.status);
 $('read-account').textContent=o?.snapshot_at?'更新聊天快照':'读取并解密此账号';
 $('conversation-count').textContent=number(o?.conversation_count);$('group-count').textContent=number(o?.group_count);
 $('message-count').textContent=number(o?.message_count);$('group-messages').textContent=number(o?.group_message_count);
 $('group-note').textContent=o?.unclassified_message_count?'另有 '+number(o.unclassified_message_count)+' 条消息未分类':'已识别群聊中的消息';
 $('first-message').textContent=o?.first_message_at?date(o.first_message_at):'尚无可用记录';
 $('last-message').textContent=o?.last_message_at?date(o.last_message_at):'尚无可用记录';
 $('snapshot-time').textContent=o?.snapshot_at?date(o.snapshot_at):'尚未生成快照';
 $('coverage-badge').textContent=o?.partial?'部分统计 · 见下方说明':'本地已读取范围';
 $('coverage-note').textContent=o?.status==='not_read'?'已发现账号的源文件，但还没有可用于查询的聊天快照。上方的“—”表示尚未读取，不是没有聊天记录。':o?.errors.length?o.errors.join(' '):'按本地快照中的消息记录统计，不代表手机或云端全部历史；消息条数按各分库保存的记录计数。';
 const snap=a?.snapshot;
 $('snapshot-title').textContent=o?.status==='ready'||o?.status==='partial'?(a.source_newer_than_snapshot>0?'源数据有变化，可更新聊天快照':'当前展示已读取的数据快照'):'下一步：读取这个账号的聊天数据';
 $('snapshot-detail').textContent=o?.status==='ready'||o?.status==='partial'?'数据读取于 '+date(o.snapshot_at)+'。源文件时间仅用于提示变化，实际记录截止时间见“已读取至”。':'点击下方按钮，依次检查密钥、解密快照并统计数据。采集密钥时需登录此账号；密钥就绪后需正常退出微信，再点击继续生成快照。';
 $('recent-conversations').replaceChildren();
 if(!o?.recent_conversations.length){const box=document.createElement('div');box.className='empty-state';const title=document.createElement('strong');title.textContent=o?.status==='not_read'?'聊天内容尚未就绪':'暂无可展示的会话';box.append(title,document.createTextNode('读取成功后，这里会显示会话名称、已获取的消息量与最新记录时间。'));$('recent-conversations').append(box);}
 for(const c of o?.recent_conversations||[]){const row=document.createElement('div');row.className='recent-row';const icon=document.createElement('span');icon.className='recent-icon';icon.textContent=c.kind==='group'?'群':'聊';const name=document.createElement('div');name.className='recent-name';const title=document.createElement('strong');title.textContent=c.name;const detail=document.createElement('small');detail.textContent=c.last_message_at?'记录至 '+date(c.last_message_at):'未读取到该会话的消息';name.append(title,detail);const count=document.createElement('span');count.className='recent-count';count.textContent=number(c.message_count)+' 条';row.append(icon,name,count);$('recent-conversations').append(row);}
 $('next-step-copy').textContent=o?.status==='ready'||o?.status==='partial'?'选择当天的群聊或联系人，预览消息后让 Codex 提取话题、重要信息和待办。':'先完成账号数据读取，再确认覆盖范围。当前可以咨询读取流程；Codex 尚不能访问聊天正文。';
 $('count').textContent=(a?.database_count||0)+' 个源文件';$('size').textContent=a?bytes(a.total_bytes):'—';$('modified').textContent='源文件更新 '+date(a?.latest_modified_at);$('changes').textContent='本次变化 '+(a?.changed_count||0);$('scan-time').textContent='本次删除 '+(a?.removed_databases.length||0);
 $('source-path').textContent=a?.source_path||'没有可用目录';$('scan-footer').textContent='最近检测 '+date(data.scanned_at)+' · 文件时间不代表消息时间';
 const filter=$('category').value;$('category').replaceChildren(new Option('全部分类',''));for(const c of new Set(a?.databases.map(d=>d.category)||[]))$('category').add(new Option(c,c));$('category').value=filter;renderRows();document.dispatchEvent(new CustomEvent('vault-account-updated',{detail:{id:a?.id,snapshot:a?.overview.snapshot_at}}));if(a?.errors.length)note(a.errors.join(' '));
}
function renderRows(){const a=current(),q=$('search').value.toLowerCase(),category=$('category').value;const rows=(a?.databases||[]).filter(d=>d.relative_path.toLowerCase().includes(q)&&(!category||d.category===category));$('rows').replaceChildren();for(const d of rows){const tr=document.createElement('tr');const name=document.createElement('td');name.textContent=d.name;name.title=d.relative_path;const sub=document.createElement('small');sub.textContent=d.category+(d.wal_present?' · WAL '+bytes(d.wal_size):'');name.append(sub);tr.append(name);for(const t of [bytes(d.size),date(d.modified_at)]){const td=document.createElement('td');td.textContent=t;tr.append(td);}const td=document.createElement('td'),badge=document.createElement('span');badge.className='badge '+d.change;badge.textContent={first_scan:'首次检测',new:'新增',changed:'有更新',unchanged:'无变化'}[d.change];td.append(badge);tr.append(td);$('rows').append(tr);}$('empty').hidden=rows.length>0;$('file-count').textContent=rows.length+' 个文件';}
async function scan(){if(scanning)return;scanning=true;$('refresh').disabled=true;try{note('');data=await api('/api/scan',{});if(!data.accounts.some(a=>a.id===selected))selected=data.accounts[0]?.id||'';render();if(current()?.overview.status==='not_read'&&!sessionStorage.getItem('import-seen-'+selected)&&!$('import-dialog').open){sessionStorage.setItem('import-seen-'+selected,'1');openImport();}}catch(e){note(e.message);}finally{scanning=false;$('refresh').disabled=false;}}
async function status(){try{const s=await api('/api/codex/status');$('cli-state').textContent=s.probe?.ok?'● 连接验证成功':s.logged_in?'● 已安装 · 已登录':s.installed?'○ 等待登录':'○ 未检测到 CLI';$('cli-detail').textContent=(s.version||'')+' '+(s.hint||(s.probe?.ok?'验证于 '+date(s.probe.tested_at*1000):'点击测试连接，确认模型可正常响应。'));$('probe').disabled=!!job||!s.logged_in;$('send').disabled=!!job||!s.logged_in;}catch(e){note(e.message);}}
function message(t,role){document.querySelector('.welcome')?.remove();const p=document.createElement('div');p.className='message '+role;p.textContent=t;$('conversation').append(p);return p;}
async function run(path,body,label){if(job)return;message(label,'user');const output=message('正在连接本机 Codex…','assistant-message');$('send').disabled=true;$('probe').disabled=true;$('cancel').hidden=false;job={status:'queued'};try{job=await api(path,body);while(['queued','running'].includes(job.status)){$('job-state').textContent=job.events.some(e=>e.type==='reconnecting')?'网络重连中…':'正在思考…';output.textContent=job.text||'正在等待 Codex 返回，网络重连可能需要约两分钟…';await new Promise(r=>setTimeout(r,1200));job=await api('/api/jobs/'+job.id);}output.textContent=job.text||job.error||(job.status==='cancelled'?'任务已取消。':'未返回回答。');$('job-state').textContent={completed:'已完成',failed:'请求失败',cancelled:'已取消'}[job.status]||job.status;}catch(e){output.textContent=e.message;$('job-state').textContent='请求失败';}finally{job=null;$('cancel').hidden=true;await status();}}
$('explain-data').onclick=()=>{$('prompt').value='请根据当前账号的统计，解释已获取多少微信数据、覆盖到什么时候，以及下一步适合做什么。';$('include-context').checked=!!current();$('prompt').focus();};
$('refresh').onclick=scan;$('search').oninput=renderRows;$('category').onchange=renderRows;$('probe').onclick=()=>run('/api/codex/probe',{},'测试本机 Codex 连接');$('cancel').onclick=async()=>{if(job?.id)try{await api('/api/jobs/'+job.id+'/cancel',{});}catch(e){note(e.message);}};
$('ask').onsubmit=e=>{e.preventDefault();const prompt=$('prompt').value.trim();if(!prompt||job)return;if($('include-context').checked&&!current()){note('请先选择一个本地账号。');return;}run('/api/codex/ask',{prompt,include_context:$('include-context').checked,account_id:selected},prompt+($('include-context').checked?'\n（附带 '+(current().overview.nickname||current().overview.username)+' 的聚合统计）':''));$('prompt').value='';};document.querySelectorAll('.suggestion').forEach(b=>b.onclick=()=>{$('prompt').value=b.textContent;$('prompt').focus();});setInterval(()=>{if($('auto').checked)scan();},30000);
(async()=>{try{token=(await api('/api/bootstrap')).token;await Promise.all([scan(),status()]);}catch(e){note('启动失败：'+e.message);}})();


let importAccount=null,importState=null,importPolling=false,lastCompletion='',waitExitReady=false;
const guides={
 SOURCE_BUSY:['请正常退出微信','密钥已验证。请使用微信菜单“退出微信”或 ⌘Q，不能只退出登录或关闭窗口。系统每 2 秒检测一次，退出后会自动继续解密。'],
 PROCESS_ACCESS_DENIED:['需要处理客户端权限','macOS 拒绝访问当前微信。请正常退出微信；勾选下方说明后可创建并签名独立副本。'],
 COPY_SIGNATURE_CHANGED:['副本签名发生变化','微信更新可能恢复正式签名。请正常退出微信后，重新签名副本；无需修改原微信应用。'],
 COPY_READY:['副本已启动，先停留在登录页','点击“开始监听”，看到“监听已就绪”后再登录选中的账号。系统会验证密钥是否匹配，不会导入其他账号。'],
 SELECT_PROCESS:['等待微信客户端','请打开微信并停留在登录页；如有多个微信主程序，请只保留一个。然后点击重新验证。'],
 ACCOUNT_NOT_ACTIVE:['请切换到所选账号','当前微信打开的是另一个账号。请登录本次选中的账号，再重新验证。'],
 PROCESS_RESTARTED:['微信进程已重启','系统需要重新识别微信进程。请等待微信启动完成，再重新验证。'],
 PROCESS_ATTACH_TIMEOUT:['微信启动或连接超时','请等待副本正常打开并停留在登录页，然后重新验证；监听就绪后再进入微信。'],
 NO_KEYS_CAPTURED:['等待重新登录验证','没有采集到验证通过的密钥。请先退回副本的登录页，点击重新验证，看到监听就绪后再登录。'],
 KEYS_INCOMPLETE:['部分数据库尚未验证','请打开相关会话后重试；若仍缺少密钥，在监听期间重新登录该账号。'],
 RUNTIME_MISSING:['需要安装读取环境','先安装 mdldm-wechat-vault Skill 并运行 scripts/bootstrap.py，安装完成后重新验证。'],
 REPAIR_FAILED:['副本准备失败','请确认微信已完全退出，且应用目录可写，再重试准备副本。']
};
function openImport(){if(!selected)return;importAccount=selected;const a=current();$('import-title').textContent='导入 '+(a.overview.nickname||a.label);$('repair-consent').checked=false;importState={status:'idle',step:0};drawImport(importState);$('import-dialog').showModal();ingestStatus();}
function drawImport(s){importState=s;const running=s.status==='running',done=s.status==='completed';const repair=['PROCESS_ACCESS_DENIED','COPY_SIGNATURE_CHANGED','REPAIR_FAILED'].includes(s.code);const guide=guides[s.code];$('import-status').textContent=running?'正在验证':done?'验证通过':s.status==='waiting_user'?'等待你完成操作':s.status==='cancelled'?'已取消':'准备开始';$('import-heading').textContent=guide?.[0]||s.stage||'导入前先检查微信状态';$('import-help').textContent=guide?.[1]||(running?(s.step===2?'保持微信打开。只有显示“监听已就绪”后再登录；这一步可能需要几分钟。':'正在执行本地验证，请等待实际结果。'):done?('快照已导入；生成时间不代表消息已经同步到今天。'+(s.summary?.last_message_at?'已读取消息截至 '+date(s.summary.last_message_at)+'。':'所选账号尚无可显示的消息时间。')):'先检查本地环境与已有密钥。若客户端权限或登录状态需要处理，向导会给出下一步操作。');$('import-error').hidden=!s.error;$('import-error').textContent=(s.error||'').replace(/^[A-Z_]+:\s*/, '');$('repair-consent-row').hidden=!repair;$('import-repair').hidden=!repair;$('import-repair').disabled=!$('repair-consent').checked||!waitExitReady;$('import-next').hidden=repair||s.code==='SOURCE_BUSY';$('import-next').disabled=running;$('import-next').textContent=done?'查看账号数据':s.code==='COPY_READY'?'开始监听':s.status==='idle'?'开始检查':'重新验证';$('import-cancel').hidden=done||s.status==='idle'||s.status==='cancelled';document.querySelectorAll('#import-steps li').forEach((li,i)=>{li.className=i<(s.step||0)?'done':i===(s.step||0)?'current':'';});}
async function ingestStatus(){if(importPolling)return;const aid=$('import-dialog').open?importAccount:selected;if(!aid)return;importPolling=true;try{const s=await api('/api/ingest/'+aid);if(aid===selected){$('read-account').disabled=false;$('ingest-state').textContent=s.status==='idle'?'':s.stage;}if($('import-dialog').open&&aid===importAccount){drawImport(s);if(['SOURCE_BUSY','PROCESS_ACCESS_DENIED','COPY_SIGNATURE_CHANGED','REPAIR_FAILED'].includes(s.code)){const client=await api('/api/wechat/state');waitExitReady=!client.running;$('import-check').textContent=client.running?'○ 仍检测到微信运行，等待正常退出…':'✓ 已验证微信完全退出';$('import-repair').disabled=!$('repair-consent').checked||!waitExitReady;if(s.code==='SOURCE_BUSY'&&!client.running){drawImport({status:'running',stage:'退出验证通过，继续生成快照',step:3});await api('/api/ingest',{account_id:aid});}}else{$('import-check').textContent=s.status==='running'?'正在等待真实验证结果，请勿重复提交。':'';}}if(s.status==='completed'&&lastCompletion!==aid+String(s.updated_at)){lastCompletion=aid+String(s.updated_at);await scan();}}catch(e){if($('import-dialog').open)$('import-check').textContent='状态检测失败：'+e.message;}finally{importPolling=false;}}
$('read-account').onclick=openImport;
$('import-close').onclick=()=>{$('import-dialog').close();};
$('import-next').onclick=async()=>{if(importState?.status==='completed'){$('import-dialog').close();document.dispatchEvent(new CustomEvent('vault-show-latest'));return;}try{drawImport({status:'running',stage:'开始验证',step:0});await api('/api/ingest',{account_id:importAccount});await ingestStatus();}catch(e){$('import-check').textContent=e.message;drawImport({status:'failed',stage:'无法开始导入',error:e.message,step:0});}};
$('repair-consent').onchange=()=>{$('import-repair').disabled=!$('repair-consent').checked||!waitExitReady;};
$('import-repair').onclick=async()=>{try{const s=await api('/api/ingest/repair',{account_id:importAccount,consent:$('repair-consent').checked});drawImport(s);}catch(e){$('import-check').textContent=e.message;}};
$('import-cancel').onclick=async()=>{try{drawImport(await api('/api/ingest/cancel',{account_id:importAccount}));}catch(e){$('import-check').textContent=e.message;}};
setInterval(ingestStatus,2000);
