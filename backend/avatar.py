"""Bounded avatar fetch from known WeChat image hosts; no arbitrary URL input."""
import base64,hashlib,json,re,threading,time
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from .overview import connect
HOSTS={'wx.qlogo.cn','wework.qpic.cn','mmhead.c2c.wechat.com','mmhead.hk.wechat.com','p.qpic.cn'}
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
class AvatarReader:
    def __init__(self,monitor):self.monitor=monitor;self.cache={};self.lock=threading.Lock();self.slots=threading.Semaphore(4)
    @staticmethod
    def safe_url(value):
        if not isinstance(value,str):return None
        u=urlsplit(value)
        try:port=u.port
        except ValueError:return None
        if u.scheme not in ('http','https') or u.hostname not in HOSTS or u.username or u.password or port not in (None,80,443):return None
        return urlunsplit(('https',u.hostname,u.path,u.query,''))
    def read(self,aid,chat):
        if not isinstance(chat,str) or len(chat)>512:raise ValueError('联系人无效。')
        a=next((a for a in (self.monitor.latest or {}).get('accounts',[]) if a['id']==aid),None)
        if not a:raise ValueError('账号无效。')
        url=None
        for config in (self.monitor.vault_root/'accounts').glob('*/config.json'):
            conf=json.loads(config.read_text())
            if Path(conf.get('db_dir','')).resolve()!=Path(a['source_path']).resolve():continue
            try:
                sid=json.loads((config.parent/'current.json').read_text())['snapshot']
                if not re.fullmatch('[a-f0-9]{32}',sid):return {'image':None}
                snap=config.parent/'snapshots'/sid
                if snap.is_symlink() or not snap.resolve().is_relative_to(config.parent.resolve()):return {'image':None}
                c=connect(snap/'data/contact/contact.db',snap)
                try:row=c.execute('SELECT small_head_url,big_head_url FROM contact WHERE username=? LIMIT 1',(chat,)).fetchone()
                finally:c.close()
                if row:url=self.safe_url(row[0]) or self.safe_url(row[1])
            except Exception:return {'image':None}
            break
        if not url:return {'image':None}
        key=(aid,chat,hashlib.sha256(url.encode()).hexdigest())
        with self.lock:
            hit=self.cache.get(key)
            if hit and hit[0]>time.time():return {'image':hit[1]}
        image=None
        try:
            with self.slots:
                with build_opener(NoRedirect()).open(Request(url,headers={'User-Agent':'WechatVault/1.0'}),timeout=4) as r:
                    raw=r.read(300001)
            kind='image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else 'image/webp' if raw[:4]==b'RIFF' and raw[8:12]==b'WEBP' else None
            if kind and len(raw)<=300000:image='data:'+kind+';base64,'+base64.b64encode(raw).decode()
        except Exception:pass
        with self.lock:
            if len(self.cache)>=256:self.cache.pop(next(iter(self.cache)))
            self.cache[key]=(time.time()+(3600 if image else 120),image)
        return {'image':image}
