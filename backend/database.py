"""Filesystem metadata only: never opens a WeChat database or reads message contents."""
import hashlib,json,os,tempfile,threading
from datetime import datetime,timezone
from pathlib import Path
from .overview import OverviewReader

def iso(value):return datetime.fromtimestamp(value,timezone.utc).isoformat() if value else None

def read(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return None

class DatabaseMonitor:
    def __init__(self,source_root=None,vault_root=None,state_root=None):
        home=Path.home()
        self.source_root=Path(source_root or home/'Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files')
        self.vault_root=Path(vault_root or home/'Library/Application Support/mdldm-wechat-vault')
        self.state_root=Path(state_root or home/'Library/Application Support/mdldm-wechat-web')
        self.state_root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.lock=threading.Lock();self.latest=None
        self.overview=OverviewReader(self.vault_root)
    def snapshot_for(self,source):
        for config in sorted((self.vault_root/'accounts').glob('*/config.json')):
            conf=read(config)
            if not isinstance(conf,dict) or conf.get('db_dir')!=str(source):continue
            account=config.parent;current=read(account/'current.json')
            sid=current.get('snapshot','') if isinstance(current,dict) else ''
            if len(sid)!=32 or any(c not in '0123456789abcdef' for c in sid):
                return {'status':'none','account':account.name,'created_at':None}
            manifest=read(account/'snapshots'/sid/'manifest.json')
            if not isinstance(manifest,dict):return {'status':'invalid','account':account.name,'created_at':None}
            return {'status':'available','account':account.name,'created_at':manifest.get('created_at'),
                    'scope':manifest.get('scope'),'consistency':manifest.get('consistency'),
                    'database_count':len(manifest.get('databases',[]))}
        return {'status':'unbound','account':None,'created_at':None}
    def scan(self):
        with self.lock:
            prior=read(self.state_root/'scan.json') or {};old=prior.get('accounts',{});saved={};accounts=[]
            try:sources=sorted(self.source_root.glob('*/db_storage')) if self.source_root.exists() else []
            except OSError:sources=[]
            for idx,source in enumerate(sources):
                if source.is_symlink():continue
                aid=hashlib.sha256(str(source).encode()).hexdigest()[:16]
                previous=old.get(aid,{});rows=[];signatures={};errors=[]
                try:paths=sorted(source.rglob('*.db'))
                except OSError:paths=[];errors.append('无法列出数据库，请检查目录访问权限。')
                for path in paths:
                    if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):continue
                    rel=path.relative_to(source).as_posix();wal=Path(str(path)+'-wal')
                    try:
                        st=path.stat();ws=wal.stat() if wal.exists() and not wal.is_symlink() else None
                        stamp=max(st.st_mtime,ws.st_mtime if ws else 0)
                        signature=[st.st_size,st.st_mtime_ns,ws.st_size if ws else 0,ws.st_mtime_ns if ws else 0]
                        signatures[rel]=signature
                        change='first_scan' if aid not in old else ('new' if rel not in previous else ('changed' if previous[rel]!=signature else 'unchanged'))
                        rows.append({'name':path.name,'relative_path':rel,'category':rel.split('/')[0],
                                     'size':st.st_size,'wal_size':ws.st_size if ws else 0,'wal_present':ws is not None,
                                     'database_modified_at':iso(st.st_mtime),'wal_modified_at':iso(ws.st_mtime) if ws else None,
                                     'modified_at':iso(stamp),'change':change})
                    except OSError:errors.append('部分数据库无法读取文件状态。')
                snap=self.snapshot_for(source);newer=None
                if snap.get('created_at'):
                    try:
                        snapshot_time=datetime.fromisoformat(snap['created_at'].replace('Z','+00:00')).timestamp()
                        newer=sum(datetime.fromisoformat(r['modified_at']).timestamp()>snapshot_time for r in rows)
                    except ValueError:snap['status']='invalid'
                removed=sorted(set(previous)-set(signatures));saved[aid]=signatures
                accounts.append({'id':aid,'label':f'微信账号 {idx+1:02d}','source_path':str(source),
                    'databases':rows,'database_count':len(rows),'total_bytes':sum(r['size']+r['wal_size'] for r in rows),
                    'latest_modified_at':max((r['modified_at'] for r in rows),default=None),
                    'changed_count':sum(r['change'] in ('changed','new') for r in rows),'removed_databases':removed,
                    'snapshot':snap,'source_newer_than_snapshot':newer,'errors':errors,
                    'overview':self.overview.read(source)})
            now=datetime.now(timezone.utc).isoformat()
            payload={'scanned_at':now,'previous_scan_at':prior.get('scanned_at'),'accounts':accounts,
                     'metadata_only':True,'source_exists':self.source_root.exists(),
                     'message':'仅检查数据库与 WAL 文件状态，不读取聊天正文。'}
            fd,tmp=tempfile.mkstemp(dir=self.state_root)
            try:
                os.fchmod(fd,0o600)
                with os.fdopen(fd,'w') as f:json.dump({'scanned_at':now,'accounts':saved},f)
                os.replace(tmp,self.state_root/'scan.json')
            finally:
                if os.path.exists(tmp):os.unlink(tmp)
            self.latest=payload;return payload
    def context(self,account_id):
        with self.lock:
            account=next((a for a in (self.latest or {}).get('accounts',[]) if a['id']==account_id),None)
            if account is None:raise ValueError('请先选择已检测的账号。')
            # Only aggregate statistics, never names, paths, conversations or message content.
            overview=account['overview']
            return {k:overview[k] for k in ('status','conversation_count','group_count',
                'message_count','group_message_count','unclassified_message_count',
                'first_message_at','last_message_at','snapshot_at','partial','coverage')}
