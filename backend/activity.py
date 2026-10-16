"""Per-account daily activity, local metadata aggregates only; no message bodies."""
import hashlib,json,re
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from .overview import connect,columns,quote
TZ=ZoneInfo('Asia/Shanghai')
SYSTEM={'filehelper','weixin','newsapp','fmessage','medianote','floatbottle','qqmail','qmessage','tmessage','qqsync','brandsessionholder','notification_messages','weixinreminder','officialaccounts'}

class ActivityReader:
    def __init__(self,root):self.root=root;self.cache={}
    def read(self,source,day,end_day=None):
        try:
            start=datetime.strptime(day,'%Y-%m-%d').replace(tzinfo=TZ)
            if start.strftime('%Y-%m-%d')!=day:raise ValueError()
        except (ValueError,TypeError):raise ValueError('请选择有效日期（YYYY-MM-DD）。')
        try:
            end_date=datetime.strptime(end_day,'%Y-%m-%d').replace(tzinfo=TZ) if end_day else start
            if end_day and end_date.strftime('%Y-%m-%d')!=end_day:raise ValueError()
        except (ValueError,TypeError):raise ValueError('请选择有效的结束日期。')
        if not 0<=(end_date-start).days<31:raise ValueError('时间范围须为 1–31 天。')
        until=end_date+timedelta(days=1)
        empty={'date':day,'timezone':'Asia/Shanghai','status':'not_read','groups':[],'private':[],'errors':[], 'snapshot_at':None,'coverage_until':None,'self_attribution_complete':False}
        for config in sorted((self.root/'accounts').glob('*/config.json')):
            try:
                conf=json.loads(config.read_text())
                if str(source.resolve())!=str(Path(conf.get('db_dir','')).resolve()):continue
                pointer=json.loads((config.parent/'current.json').read_text());sid=pointer.get('snapshot','')
                if not re.fullmatch(r'[a-f0-9]{32}',sid):raise ValueError('无效快照')
                snap=config.parent/'snapshots'/sid
                if snap.is_symlink() or not snap.resolve().is_relative_to(config.parent.resolve()):raise ValueError('无效快照目录')
                manifest=json.loads((snap/'manifest.json').read_text())
                key=(str(source),str(snap),day,end_day,(snap/'manifest.json').stat().st_mtime_ns)
                if key in self.cache:return self.cache[key]
                username=conf.get('account_username') or re.sub(r'_[0-9a-f]{4}$','',source.parent.name)
                result=self.aggregate(snap,username,start,manifest,until)
                if len(self.cache)>40:self.cache.clear()
                if not result['errors']:self.cache[key]=result
                return result
            except FileNotFoundError:return empty
        return empty
    def aggregate(self,snap,username,start,manifest,until=None):
        begin=int(start.timestamp());end=int((until or start+timedelta(days=1)).timestamp());names={};errors=[]
        try:
            c=connect(snap/'data/contact/contact.db',snap)
            try:
                fields=[x for x in ('username','remark','nick_name') if x in columns(c,'contact')]
                for r in c.execute('SELECT '+','.join(map(quote,fields))+' FROM contact'):
                    d=dict(r);names[d['username']]=d.get('remark') or d.get('nick_name') or d['username']
            finally:c.close()
        except Exception:errors.append('联系人资料不可用，无法完整识别私聊。')
        items={};unmapped=unknown_sender=excluded=0;self_complete=True;latest=None
        shards=sorted(p for p in (snap/'data/message').glob('message_*.db') if re.fullmatch(r'message_\d+\.db',p.name))
        if not shards:errors.append('快照没有消息分库。')
        for p in shards:
            try:
                c=connect(p,snap)
                try:
                    tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    ids={r[0]:r[1] for r in c.execute('SELECT rowid,user_name FROM Name2Id')} if 'Name2Id' in tables else {}
                    self_id=next((i for i,u in ids.items() if u==username),None)
                    mapping={'Msg_'+hashlib.md5(u.encode()).hexdigest():u for u in set(names)|set(ids.values()) if isinstance(u,str)}
                    for table in sorted(t for t in tables if re.fullmatch(r'Msg_[a-fA-F0-9]{32}',t)):
                        cols=columns(c,table)
                        if not {'create_time','real_sender_id','local_type'}<=cols:
                            errors.append('存在不支持的消息表，结果为部分统计。');self_complete=False;continue
                        user=mapping.get(table)
                        query='SELECT create_time,real_sender_id,COUNT(*) FROM '+quote(table)+' WHERE create_time>=? AND create_time<? AND (local_type & 4294967295) NOT IN (10000,10002) GROUP BY create_time,real_sender_id'
                        rows=c.execute(query,(begin,end)).fetchall()
                        if not rows:continue
                        if self_id is None:self_complete=False
                        if user is None:unmapped+=sum(r[2] for r in rows);continue
                        group=user.endswith('@chatroom')
                        if not group and (user not in names or user in SYSTEM or user==username or user.startswith(('gh_','weixin','notification_'))):
                            excluded+=sum(r[2] for r in rows);continue
                        item=items.setdefault(user,{'chat_id':user,'name':names.get(user,user),'kind':'group' if group else 'private','total':0,'mine':0,'hours':[0]*24,'my_hours':[0]*24,'unknown_sender':0})
                        for ts,sender,n in rows:
                            hour=datetime.fromtimestamp(ts,TZ).hour;item['total']+=n;item['hours'][hour]+=n
                            if sender==self_id and self_id is not None:item['mine']+=n;item['my_hours'][hour]+=n
                            if sender not in ids:item['unknown_sender']+=n;unknown_sender+=n
                            latest=max(latest or ts,ts)
                finally:c.close()
            except Exception:errors.append('部分消息分库无法读取，结果为部分统计。');self_complete=False
        groups=sorted((i for i in items.values() if i['kind']=='group'),key=lambda i:(-i['total'],i['name']))
        private=sorted((i for i in items.values() if i['kind']=='private'),key=lambda i:(-i['total'],i['name']))
        if not self_complete:
            for item in items.values():item['mine']=None;item['my_hours']=None
        hours=[sum(i['hours'][h] for i in items.values()) for h in range(24)]
        my_hours=[sum(i['my_hours'][h] for i in items.values()) for h in range(24)] if self_complete else None
        return {'date':start.strftime('%Y-%m-%d'),'timezone':'Asia/Shanghai','status':'partial' if errors or unmapped or unknown_sender or not self_complete else 'ready',
            'snapshot_at':manifest.get('created_at'),'coverage_until':datetime.fromtimestamp(latest,TZ).isoformat() if latest else None,
            'groups':groups,'private':private,'hours':hours,'my_hours':my_hours,'self_attribution_complete':self_complete,
            'unmapped_messages':unmapped,'unknown_sender_messages':unknown_sender,'excluded_messages':excluded,'errors':list(dict.fromkeys(errors)),
            'totals':{'group_messages':sum(i['total'] for i in groups),'my_group_messages':sum(i['mine'] for i in groups) if self_complete else None,'private_messages':sum(i['total'] for i in private),'my_private_messages':sum(i['mine'] for i in private) if self_complete else None},
            'counting':'本地快照按物理消息记录计数，含图片语音等，排除系统通知；未跨分库去重。私聊按已识别联系人筛选，排除已知公众号、系统会话和自己。'}
