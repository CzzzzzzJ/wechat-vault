"""Account-owned local identity and evolving, evidence-based communication observations."""
import json,os,re,sqlite3,threading,time
from contextlib import contextmanager
from datetime import datetime,timedelta
from pathlib import Path
from .activity import TZ
from .overview import connect,columns,quote

class ProfileService:
    def __init__(self,monitor,activity,avatars):
        self.monitor=monitor;self.activity=activity;self.avatars=avatars;self.lock=threading.RLock()
        root=monitor.state_root/'profiles';root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=root/'profiles.sqlite3'
        with self.db() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS profiles(account TEXT PRIMARY KEY, identity TEXT NOT NULL, manual TEXT NOT NULL,
              avatar TEXT, avatar_key TEXT, avatar_attempt REAL DEFAULT 0, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS observations(account TEXT NOT NULL,snapshot TEXT NOT NULL,snapshot_at TEXT,
              recorded_at REAL NOT NULL,body TEXT NOT NULL,PRIMARY KEY(account,snapshot));
            """)
        os.chmod(self.path,0o600)
    @contextmanager
    def db(self):
        c=sqlite3.connect(self.path,timeout=15);c.row_factory=sqlite3.Row
        try:
            with c:yield c
        finally:c.close()
    def account(self,aid):
        a=next((a for a in (self.monitor.latest or {}).get('accounts',[]) if a['id']==aid),None)
        if not a:raise ValueError('请先选择已发现的账号。')
        return a
    def snapshot(self,a):
        source=Path(a['source_path'])
        for config in (self.monitor.vault_root/'accounts').glob('*/config.json'):
            try:
                conf=json.loads(config.read_text())
                if Path(conf.get('db_dir','')).resolve()!=source.resolve():continue
                sid=json.loads((config.parent/'current.json').read_text())['snapshot']
                if not isinstance(sid,str) or not re.fullmatch('[a-f0-9]{32}',sid):return None
                snap=config.parent/'snapshots'/sid
                if snap.is_symlink() or not snap.resolve().is_relative_to(config.parent.resolve()):return None
                manifest=json.loads((snap/'manifest.json').read_text())
                username=conf.get('account_username') or re.sub(r'_[0-9a-f]{4}$','',source.parent.name)
                identity={'username':username,'nickname':None,'wechat_id':None,'snapshot_at':manifest.get('created_at'),'source':'directory'}
                c=connect(snap/'data/contact/contact.db',snap)
                try:
                    fields=[x for x in ('username','nick_name','alias') if x in columns(c,'contact')]
                    row=c.execute('SELECT '+','.join(map(quote,fields))+' FROM contact WHERE username=? LIMIT 1',(username,)).fetchone()
                    if row:
                        d=dict(row);identity.update(nickname=d.get('nick_name') or None,wechat_id=d.get('alias') or None,source='own_contact')
                finally:c.close()
                return sid,identity
            except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):return None
        return None
    @staticmethod
    def observe(stats):
        totals=stats.get('totals',{});group=totals.get('my_group_messages');private=totals.get('my_private_messages')
        hours=stats.get('my_hours');signals=[]
        if stats.get('self_attribution_complete') and group is not None and private is not None and group+private>=20:
            total=group+private;ratio=group/total
            label='群聊沟通更多' if ratio>=.6 else '私聊沟通更多' if ratio<=.4 else '群聊与私聊均衡'
            signals.append({'key':'communication','label':label,'basis':'本人群聊 '+str(group)+' 条，私聊 '+str(private)+' 条。','kind':'local_statistic'})
            if hours and sum(hours)>0:
                periods=[('凌晨',0,6),('上午',6,12),('下午',12,18),('傍晚',18,20),('夜间',20,24)]
                label,start,end=max(periods,key=lambda p:sum(hours[p[1]:p[2]]))
                if sum(hours[start:end])/sum(hours)>=.35:
                    signals.append({'key':'active_time','label':label+'交流较多','basis':str(start).zfill(2)+':00–'+str(end).zfill(2)+':00，共 '+str(sum(hours[start:end]))+' 条本人发言。','kind':'local_statistic'})
        return {'signals':signals,'group_sent':group,'private_sent':private,'self_verified':bool(stats.get('self_attribution_complete'))}
    def read(self,aid):
        a=self.account(aid)
        with self.lock:
            found=self.snapshot(a);now=time.time()
            with self.db() as c:
                old=c.execute('SELECT * FROM profiles WHERE account=?',(aid,)).fetchone()
            identity=json.loads(old['identity']) if old else {'username':a['overview']['username'],'nickname':None,'wechat_id':None,'source':'directory','snapshot_at':None}
            manual=json.loads(old['manual']) if old else {'role':'','bio':'','interests':[]}
            avatar=old['avatar'] if old else None;avatar_key=old['avatar_key'] if old else None;attempt=old['avatar_attempt'] if old else 0
            updated=old['updated_at'] if old else now;warning=None
            if found:
                sid,fresh=found
                # A failed contact lookup never erases previously verified identity from this account.
                if fresh['source']=='own_contact' or identity.get('source')!='own_contact':
                    if fresh!=identity:updated=now
                    identity=fresh
                with self.db() as c:observed=c.execute('SELECT 1 FROM observations WHERE account=? AND snapshot=?',(aid,sid)).fetchone()
                if not observed:
                    latest=a['overview'].get('last_message_at') or fresh['snapshot_at']
                    try:
                        end=datetime.fromisoformat(latest.replace('Z','+00:00')).astimezone(TZ).date()
                        start=end-timedelta(days=6)
                        stats=self.activity.read(Path(a['source_path']),start.isoformat(),end.isoformat())
                        observation={**self.observe(stats),'start':start.isoformat(),'end':end.isoformat(),'identity':fresh}
                        if stats.get('errors'):warning='部分数据尚未读取，沟通特征会在后续同步中补充。'
                        else:
                            with self.db() as c:c.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?)',(aid,sid,fresh['snapshot_at'],now,json.dumps(observation,ensure_ascii=False)))
                            updated=now
                    except (ValueError,TypeError,AttributeError):warning='目前数据不足，暂不生成沟通特征。'
                key=sid+'|'+fresh['username']
                if avatar_key!=key and (now-attempt>120):
                    v=self.avatars.read(aid,fresh['username']);attempt=now
                    if v.get('image'):avatar=v['image'];avatar_key=key
            with self.db() as c:
                c.execute('INSERT INTO profiles VALUES(?,?,?,?,?,?,?) ON CONFLICT(account) DO UPDATE SET identity=excluded.identity,avatar=excluded.avatar,avatar_key=excluded.avatar_key,avatar_attempt=excluded.avatar_attempt,updated_at=excluded.updated_at',
                          (aid,json.dumps(identity,ensure_ascii=False),json.dumps(manual,ensure_ascii=False),avatar,avatar_key,attempt,updated))
                rows=c.execute('SELECT snapshot_at,recorded_at,body FROM observations WHERE account=? ORDER BY recorded_at DESC',(aid,)).fetchall()
            recent=json.loads(rows[0]['body']) if rows else {'signals':[]}
            return {'account_id':aid,'identity':identity,'manual':manual,'avatar':avatar,'updated_at':updated,
                    'observation_count':len(rows),'signals':recent['signals'],'observed_range':{'start':recent.get('start'),'end':recent.get('end')},
                    'history':[{'snapshot_at':r['snapshot_at'],'recorded_at':r['recorded_at'],'signals':json.loads(r['body'])['signals']} for r in rows[:12]],
                    'status':'ready' if found else 'saved' if old else 'not_read','warning':warning,'local_only':True}
    def update(self,aid,fields):
        self.account(aid)
        if not isinstance(fields,dict) or set(fields)-{'role','bio','interests'}:raise ValueError('只允许修改身份介绍、简介与关注方向。')
        if not isinstance(fields.get('role'),str) or len(fields['role'])>60:raise ValueError('身份介绍应不超过 60 字。')
        if not isinstance(fields.get('bio'),str) or len(fields['bio'])>300:raise ValueError('简介应不超过 300 字。')
        interests=fields.get('interests')
        if not isinstance(interests,list) or len(interests)>8 or any(not isinstance(x,str) or len(x)>24 for x in interests):raise ValueError('关注方向最多 8 项，每项不超过 24 字。')
        fields={'role':fields['role'].strip(),'bio':fields['bio'].strip(),'interests':list(dict.fromkeys(x.strip() for x in interests if x.strip()))}
        with self.lock:
            self.read(aid)
            with self.db() as c:c.execute('UPDATE profiles SET manual=?,updated_at=? WHERE account=?',(json.dumps(fields,ensure_ascii=False),time.time(),aid))
            return self.read(aid)
