"""Local preview receipts: only explicitly approved, bounded messages reach Codex."""
import json,secrets,subprocess,threading,time,re
from datetime import datetime,timedelta
from pathlib import Path
from .activity import TZ

class ChatReader:
    def __init__(self,monitor,activity,ingest):
        self.monitor=monitor;self.activity=activity;self.ingest=ingest
        self.previews={};self.lock=threading.Lock()
    def preview(self,aid,day,chat_id,end_day=None):
        account=next((a for a in (self.monitor.latest or {}).get('accounts',[]) if a['id']==aid),None)
        if not account:raise ValueError('请先选择已发现的账号。')
        stats=self.activity.read(Path(account['source_path']),day,end_day) if end_day else self.activity.read(Path(account['source_path']),day)
        chat=next((c for c in stats.get('groups',[])+stats.get('private',[]) if c['chat_id']==chat_id),None)
        if not chat:raise ValueError('该账号当天没有这个会话，请重新选择。')
        alias=account.get('snapshot',{}).get('account')
        if not alias or not self.ingest:raise ValueError('账号快照尚未绑定。')
        config=json.loads((self.monitor.vault_root/'accounts'/alias/'config.json').read_text())
        if Path(config.get('db_dir','')).resolve()!=Path(account['source_path']).resolve():raise ValueError('账号绑定已变化，请重新检测。')
        username=config.get('account_username') or re.sub(r'_[0-9a-f]{4}$','',Path(account['source_path']).parent.name)
        start=datetime.strptime(day,'%Y-%m-%d').replace(tzinfo=TZ)
        until=datetime.strptime(end_day,'%Y-%m-%d').replace(tzinfo=TZ)+timedelta(days=1) if end_day else start+timedelta(days=1)
        args=[self.ingest.python,str(self.ingest.skill/'scripts/vault.py'),'--root',str(self.monitor.vault_root),'--account',alias,'history','--chat',chat_id,'--start',start.isoformat(),'--end',until.isoformat(),'--limit','1000']
        try:
            p=subprocess.run(args,capture_output=True,text=True,timeout=45)
            result=json.loads(p.stdout)
        except (OSError,ValueError,subprocess.TimeoutExpired):raise ValueError('本地消息读取失败，请检查 Skill 运行环境。')
        if not result.get('ok'):raise ValueError('Skill 未能读取该会话，请检查快照与消息表。')
        meta=result['meta'];messages=[];chars=0;omitted=0
        truncated=bool(meta.get('has_more'))
        for item in result['items']:
            if item['type'] in (10000,10002):continue
            body=item.get('content','')
            if item['type']!=1:
                body={3:'[图片：未识别]',34:'[语音：未转写]',43:'[视频：未解析]',47:'[表情]'}.get(item['type'],'[非文本消息：未解析]')
                omitted+=1
            if chars+len(body)>60000:truncated=True;break
            chars+=len(body)
            messages.append({'ref':'M'+str(len(messages)+1),'time':item['time'],'sender':item.get('sender') or '未知发送者','is_self':item.get('sender_id')==username,'type':item['type'],'content':body[:60000]})
        if not messages:raise ValueError('当天没有可供分析的消息。')
        payload={'chat_id':chat_id,'conversation':chat['name'],'kind':chat['kind'],'date':day,'end_date':end_day or day,'timezone':'Asia/Shanghai','snapshot_at':meta.get('snapshot_at'),'partial':truncated,'attachments_unread':omitted,'messages':messages}
        receipt=self.remember(aid,payload)
        return {'preview_id':receipt,**payload,'message_count':len(messages),'characters':chars,'first':messages[0]['time'],'last':messages[-1]['time'],'expires_in':900}
    def remember(self,aid,payload):
        receipt=secrets.token_urlsafe(24)
        with self.lock:
            self.previews={k:v for k,v in self.previews.items() if v['expires']>time.time()}
            if len(self.previews)>=20:self.previews.pop(next(iter(self.previews)))
            self.previews[receipt]={'account_id':aid,'expires':time.time()+900,'payload':payload}
        return receipt
    def approved(self,receipt,aid,consent):
        if consent is not True:raise ValueError('请确认将预览消息发送给 Codex 模型服务。')
        with self.lock:
            item=self.previews.get(receipt)
            if not item or item['expires']<time.time() or item['account_id']!=aid:raise ValueError('消息预览已过期或账号已切换，请重新预览。')
            return item['payload']
