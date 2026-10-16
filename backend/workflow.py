"""Account-isolated user-owned tasks and append-only progress."""
import json,sqlite3,uuid,time,hashlib
from datetime import date
from .overview import connect
STATES=('待处理','进行中','等待对方','已完成','已取消')
class WorkflowService:
 def __init__(self,monitor,analysis,search):
  self.monitor=monitor;self.analysis=analysis;self.search=search
  root=monitor.state_root/'workflow';root.mkdir(parents=True,exist_ok=True,mode=0o700);self.path=root/'workflow.sqlite3'
  with self.db() as c:c.executescript('CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,account TEXT,title TEXT,status TEXT,owner TEXT,due TEXT,created REAL,updated REAL,version INTEGER);CREATE TABLE IF NOT EXISTS entries(id TEXT PRIMARY KEY,item TEXT,account TEXT,kind TEXT,body TEXT,created REAL,source_key TEXT,UNIQUE(account,source_key));CREATE INDEX IF NOT EXISTS item_account ON items(account,updated);')
  self.path.chmod(0o600)
 def db(self):
  c=sqlite3.connect(self.path,timeout=15);c.row_factory=sqlite3.Row;return c
 def account(self,aid):return self.analysis.account(aid)
 def contacts(self,aid):
  self.account(aid);snap,_=self.search.snapshot(aid)
  with connect(snap/'data/contact/contact.db',snap) as c:return [{'chat_id':r[0],'name':r[2] or r[1] or r[0],'kind':'group' if r[0].endswith('@chatroom') else 'private'} for r in c.execute('SELECT username,nick_name,remark FROM contact') if r[0]]
 def list(self,aid,chat=None):
  self.account(aid)
  with self.db() as c:
   items=[dict(r) for r in c.execute('SELECT * FROM items WHERE account=? ORDER BY updated DESC',(aid,))]
   for item in items:
    item['entries']=[{**dict(r),'body':json.loads(r['body'])} for r in c.execute('SELECT * FROM entries WHERE account=? AND item=? ORDER BY created,id',(aid,item['id']))]
    item['contacts']=list({x['chat_id']:x for e in item['entries'] for x in e['body'].get('contacts',[])}.values())
  return {'items':[x for x in items if not chat or any(c['chat_id']==chat for c in x['contacts'])]}
 def import_event(self,aid,start,end,index,title,target=None):
  self.account(aid);report=self.analysis.cached(aid,start,end).get('report')
  if not report or type(index)!=int or not 0<=index<len(report['events']):raise ValueError('分析结果不存在，请重新打开报告。')
  event=report['events'][index]
  if event['title']!=title:raise ValueError('报告已更新，请刷新后重新选择。')
  evidence=[report['evidence'][r] for r in event['evidence'] if r in report['evidence']]
  contacts=self.contacts(aid);known={x['chat_id']:x for x in contacts};linked={}
  for m in evidence:
   cid=m.get('chat_id')
   if not cid:
    candidates=[x for x in contacts if x['name']==m.get('conversation')]
    if len(candidates)==1:cid=candidates[0]['chat_id']
   if cid in known:linked[cid]=known[cid]
  body={'event':event,'evidence':evidence,'contacts':list(linked.values()),'range':[start,end],'snapshot_at':report.get('snapshot_at')}
  source=hashlib.sha256(json.dumps([event,evidence],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
  with self.db() as c:
   c.execute('BEGIN IMMEDIATE');prior=c.execute('SELECT item FROM entries WHERE account=? AND source_key=?',(aid,source)).fetchone()
   if prior:return {'id':prior[0],'existing':True}
   if target:
    if not c.execute('SELECT id FROM items WHERE account=? AND id=?',(aid,target)).fetchone():raise ValueError('事项不存在。')
    ident=target;c.execute('UPDATE items SET updated=?,version=version+1 WHERE account=? AND id=?',(time.time(),aid,ident))
   else:
    ident=uuid.uuid4().hex;c.execute('INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?)',(ident,aid,event['title'],'待处理',event['owner'],'',time.time(),time.time(),1))
   c.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,?)',(uuid.uuid4().hex,ident,aid,'聊天进展',json.dumps(body,ensure_ascii=False),time.time(),source))
  return {'id':ident,'existing':False}
 def update(self,aid,ident,version,status,due,owner,note):
  self.account(aid)
  if status not in STATES:raise ValueError('无效事项状态。')
  if not isinstance(due,str) or (due and date.fromisoformat(due).isoformat()!=due):raise ValueError('日期格式错误。')
  if not isinstance(owner,str) or len(owner)>150:raise ValueError('负责人最多 150 字。')
  if not isinstance(note,str) or len(note)>2000:raise ValueError('进展备注最多 2000 字。')
  with self.db() as c:
   c.execute('BEGIN IMMEDIATE');old=c.execute('SELECT * FROM items WHERE account=? AND id=?',(aid,ident)).fetchone()
   if not old:raise ValueError('事项不存在。')
   if old['version']!=version:raise ValueError('事项已被更新，请刷新后再修改。')
   changes={k:{'from':old[k],'to':v} for k,v in {'status':status,'due':due,'owner':owner}.items() if old[k]!=v}
   if changes or note.strip():
    c.execute('UPDATE items SET status=?,due=?,owner=?,updated=?,version=version+1 WHERE account=? AND id=?',(status,due,owner,time.time(),aid,ident))
    c.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,NULL)',(uuid.uuid4().hex,ident,aid,'手动更新',json.dumps({'changes':changes,'note':note.strip()},ensure_ascii=False),time.time()))
  return {'ok':True}
 def contact(self,aid,chat):
  person=next((x for x in self.contacts(aid) if x['chat_id']==chat),None)
  if not person:raise ValueError('联系人不属于当前账号快照。')
  account=self.account(aid);latest=account.get('overview',{}).get('last_message_at');activity=None
  if latest:
   from datetime import datetime,timedelta
   from .activity import TZ
   from pathlib import Path
   end=datetime.fromisoformat(latest).astimezone(TZ).date();start=end-timedelta(days=29)
   stats=self.analysis.activity.read(Path(account['source_path']),start.isoformat(),end.isoformat())
   row=next((r for r in stats.get('private',[])+stats.get('groups',[]) if r['chat_id']==chat),None)
   activity={'start':start.isoformat(),'end':end.isoformat(),'total':row['total'] if row else (0 if stats.get('status')=='ready' else None),'mine':row['mine'] if row else (0 if stats.get('status')=='ready' else None),'partial':stats.get('status')!='ready'}
  return {**person,**self.list(aid,chat),'activity':activity}
