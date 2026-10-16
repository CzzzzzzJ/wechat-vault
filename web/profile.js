'use strict';
(()=>{
 let value=null,account='',request=0;
 const cached=new Map(),dialog=$('profile-dialog');
 function show(p){
  if(value?.account_id===p.account_id&&value.updated_at>p.updated_at)return;
  value=p;const id=p.identity,manual=p.manual;
  $('account-title').textContent=id.nickname||current()?.label||'微信账号';
  $('identity-detail').textContent=(id.wechat_id?'微信号 · '+id.wechat_id:'账号标识 · '+id.username)+(p.status==='saved'?' · 上次同步资料':'');
  const fallback=Array.from(id.nickname||'微')[0];
  $('avatar').textContent=fallback;
  if(p.avatar){const image=document.createElement('img');image.src=p.avatar;image.alt=(id.nickname||'当前账号')+'的头像';image.onerror=()=>{$('avatar').textContent=fallback;};$('avatar').replaceChildren(image);}
  const selectedButton=document.querySelector('#accounts button.selected');
  if(selectedButton){selectedButton.querySelector('.sidebar-avatar')?.remove();const mini=document.createElement('span');mini.className='sidebar-avatar';mini.setAttribute('aria-hidden','true');
   if(p.avatar){const image=document.createElement('img');image.src=p.avatar;image.alt='';mini.append(image);}else mini.textContent=fallback;selectedButton.prepend(mini);}
  $('profile-role').textContent=manual.role||'';
  $('profile-bio').textContent=manual.bio||'每次同步，让这张名片更了解你。';
  $('profile-interests').replaceChildren(...manual.interests.map(x=>{const tag=document.createElement('span');tag.textContent=x;return tag;}));
  $('profile-count').textContent=p.observation_count?'已积累 '+p.observation_count+' 次资料同步':'等待首次资料同步';
  $('profile-signals').replaceChildren(...p.signals.map(s=>{const tag=document.createElement('span');tag.textContent=s.label;tag.title=s.basis;return tag;}));
  $('profile-status').textContent=p.warning||(p.observed_range.start?'最近可见记录 '+p.observed_range.start+' 至 '+p.observed_range.end+' · 沟通特征基于本人发言统计':'更多数据就绪后，会逐步补充沟通特征。');
  $('profile-history').replaceChildren();
  const source=document.createElement('p');source.textContent='账号资料：'+(id.source==='own_contact'?'微信本人联系人资料':'本地账号目录标识')+' · 介绍与关注方向：本人填写。';$('profile-history').append(source);
  for(const h of p.history){const line=document.createElement('p');line.textContent=date(h.snapshot_at||h.recorded_at*1000)+' · '+(h.signals.map(s=>s.label).join('，')||'账号资料已同步，沟通特征待积累');$('profile-history').append(line);}
  $('edit-profile').disabled=false;
  $('edit-profile').textContent=manual.bio||manual.role?'编辑资料 ↗':'完善资料 ↗';
 }
 async function load(){
  const a=current(),n=++request;if(!a)return;
  if(account!==a.id){
   account=a.id;value=null;if(dialog.open)dialog.close();
   $('profile-role').textContent='';$('profile-bio').textContent='每次同步，让这张名片更了解你。';$('profile-signals').replaceChildren();$('profile-interests').replaceChildren();$('profile-history').replaceChildren();$('profile-count').textContent='正在同步资料';$('profile-status').textContent='账号资料与近期沟通特征，只保存在本机。';$('edit-profile').disabled=true;
  }
  if(cached.has(a.id))show(cached.get(a.id));
  try{const p=await api('/api/profile',{account_id:a.id});if(n!==request||a.id!==selected)return;cached.set(a.id,p);show(p);}
  catch(e){if(n===request)$('profile-status').textContent='资料暂未更新：'+e.message;}
 }
 document.addEventListener('vault-account-updated',load);
 $('edit-profile').onclick=()=>{
  if(!value)return;
  $('profile-role-input').value=value.manual.role;$('profile-bio-input').value=value.manual.bio;$('profile-interests-input').value=value.manual.interests.join('，');$('profile-error').hidden=true;dialog.showModal();
 };
 $('close-profile').onclick=()=>dialog.close();
 $('profile-form').onsubmit=async e=>{
  e.preventDefault();if(!value)return;const aid=account,n=request;
  $('save-profile').disabled=true;$('profile-error').hidden=true;
  try{const p=await api('/api/profile/update',{account_id:aid,fields:{role:$('profile-role-input').value,bio:$('profile-bio-input').value,interests:$('profile-interests-input').value.split(/[,，、\n]/).map(x=>x.trim()).filter(Boolean)}});if(account!==aid)return;cached.set(aid,p);show(p);dialog.close();}
  catch(e){$('profile-error').textContent=e.message;$('profile-error').hidden=false;}
  finally{$('save-profile').disabled=false;}
 };
})();
