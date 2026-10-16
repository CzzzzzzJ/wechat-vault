import argparse,json,mimetypes,os,secrets,signal,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .database import DatabaseMonitor
from .codex import CodexBridge
from .ingest import IngestBridge
from .activity import ActivityReader
from .chat import ChatReader
from .agent import AgentBridge
from .analysis import AnalysisService
from .avatar import AvatarReader
from .profile import ProfileService
from .search import SearchService
WEB=Path(__file__).resolve().parents[1]/'web'

def make_handler(monitor,codex,port,token,ingest=None):
    activity=ActivityReader(monitor.vault_root)
    chats=ChatReader(monitor,activity,ingest)
    agent=AgentBridge(monitor,activity,chats,codex)
    analysis=AnalysisService(monitor,activity,chats,codex)
    search=SearchService(monitor,codex)
    avatars=AvatarReader(monitor)
    profiles=ProfileService(monitor,activity,avatars)
    allowed_hosts={f'127.0.0.1:{port}',f'localhost:{port}'}
    allowed_origins={'http://'+h for h in allowed_hosts}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def valid_host(self):return self.headers.get('Host') in allowed_hosts
        def authenticated(self):
            return any(part.strip()=='vault_session='+token for part in self.headers.get('Cookie','').split(';'))
        def reply(self,status,data,kind='application/json; charset=utf-8',cookie=False):
            body=json.dumps(data,ensure_ascii=False).encode() if kind.startswith('application/json') else data
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if cookie:self.send_header('Set-Cookie','vault_session='+token+'; HttpOnly; SameSite=Strict; Path=/')
            self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_GET(self):
            if not self.valid_host():return self.reply(403,{'error':'Host not allowed'})
            path=urlparse(self.path).path
            if path=='/api/bootstrap':
                if self.headers.get('Sec-Fetch-Site') not in (None,'same-origin','none'):return self.reply(403,{'error':'Origin not allowed'})
                return self.reply(200,{'token':token,'version':'0.1.0'},cookie=True)
            if path.startswith('/api/'):
                if not self.authenticated():return self.reply(401,{'error':'请刷新页面建立本地会话。'})
                try:
                    if path=='/api/wechat/state' and ingest:return self.reply(200,ingest.client_state())
                    if path.startswith('/api/ingest/') and ingest:return self.reply(200,ingest.status(path.rsplit('/',1)[1]))
                    if path=='/api/codex/status':return self.reply(200,codex.status())
                    if path.startswith('/api/jobs/'):
                        jid=path.rsplit('/',1)[1];return self.reply(200,codex.get(jid))
                except KeyError:return self.reply(404,{'error':'任务不存在。'})
                return self.reply(404,{'error':'Not found'})
            files={'/brief':'brief.html','/search':'search.html','/insights.js':'insights.js','/insights.css':'insights.css','/':'index.html','/app.js':'app.js','/style.css':'style.css','/activity.js':'activity.js','/chat.js':'chat.js','/analysis':'analysis.html','/analysis.js':'analysis.js','/analysis.css':'analysis.css','/profile.js':'profile.js','/assets/codex.png':'assets/codex.png'}
            if path not in files:return self.reply(404,{'error':'Not found'})
            file=WEB/files[path]
            return self.reply(200,file.read_bytes(),(mimetypes.guess_type(file)[0] or 'application/octet-stream')+'; charset=utf-8')
        def do_POST(self):
            if not self.valid_host() or self.headers.get('Origin') not in allowed_origins:return self.reply(403,{'error':'Origin not allowed'})
            if not self.authenticated() or not secrets.compare_digest(self.headers.get('X-Vault-Token',''),token):return self.reply(403,{'error':'本地会话校验失败，请刷新页面。'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<=size<=40000:raise ValueError('请求过大。')
                if 'application/json' not in self.headers.get('Content-Type',''):raise ValueError('需要 JSON 请求。')
                body=json.loads(self.rfile.read(size) or b'{}')
                if not isinstance(body,dict):raise ValueError('请求格式错误。')
                path=urlparse(self.path).path
                if path=='/api/ingest/cancel' and ingest:return self.reply(200,ingest.cancel(body.get('account_id')))
                if path=='/api/ingest/repair' and ingest:return self.reply(202,ingest.repair(body.get('account_id'),body.get('consent')))
                if path=='/api/ingest' and ingest:return self.reply(202,ingest.start(body.get('account_id')))
                if path=='/api/search':
                    return self.reply(200,search.start(body.get('account_id'),body.get('query'),body.get('start'),body.get('end'),body.get('semantic',True)))
                if path=='/api/search/result':
                    return self.reply(200,search.result(body.get('account_id'),body.get('job_id')))
                if path=='/api/profile':
                    return self.reply(200,profiles.read(body.get('account_id')))
                if path=='/api/profile/update':
                    return self.reply(200,profiles.update(body.get('account_id'),body.get('fields')))
                if path=='/api/avatar':
                    return self.reply(200,avatars.read(body.get('account_id'),body.get('chat_id')))
                if path=='/api/analysis/cache':
                    return self.reply(200,analysis.cached(body.get('account_id'),body.get('start'),body.get('end')))
                if path=='/api/analysis/cache/clear':
                    return self.reply(200,analysis.clear_cache(body.get('account_id'),body.get('start'),body.get('end')))
                if path=='/api/analysis/cache/undo':
                    return self.reply(200,analysis.undo_cache(body.get('account_id'),body.get('undo_id')))
                if path=='/api/analysis/overview':
                    return self.reply(200,analysis.overview(body.get('account_id'),body.get('start'),body.get('end')))
                if path=='/api/analysis/prepare':
                    return self.reply(200,analysis.prepare(body.get('account_id'),body.get('start'),body.get('end')))
                if path=='/api/analysis/start':
                    return self.reply(202,analysis.start(body.get('account_id'),body.get('preview_id'),body.get('consent')))
                if path=='/api/analysis/result':
                    return self.reply(200,analysis.result(body.get('account_id'),body.get('job_id')))
                if path=='/api/agent/plan':
                    return self.reply(202,agent.start(body.get('account_id'),body.get('date'),body.get('prompt')))
                if path=='/api/agent/prepare':
                    return self.reply(200,agent.prepare(body.get('job_id'),body.get('account_id'),body.get('choice')))
                if path=='/api/chat/preview':
                    return self.reply(200,chats.preview(body.get('account_id'),body.get('date'),body.get('chat_id')))
                if path=='/api/chat/ask':
                    context=chats.approved(body.get('preview_id'),body.get('account_id'),body.get('consent'))
                    return self.reply(202,codex.start(body.get('prompt'),context=context,chat=True))
                if path=='/api/activity':
                    account=next((a for a in (monitor.latest or {}).get('accounts',[]) if a['id']==body.get('account_id')),None)
                    if not account:raise ValueError('请先选择已发现的账号。')
                    return self.reply(200,activity.read(Path(account['source_path']),body.get('date')))
                if path=='/api/scan':return self.reply(200,monitor.scan())
                if path=='/api/codex/probe':return self.reply(202,codex.start('只回复：连接成功。',probe=True))
                if path=='/api/codex/ask':
                    context=monitor.context(body.get('account_id')) if body.get('include_context') is True else None
                    return self.reply(202,codex.start(body.get('prompt'),context=context))
                if path.startswith('/api/jobs/') and path.endswith('/cancel'):
                    return self.reply(200,codex.cancel(path.split('/')[-2]))
                return self.reply(404,{'error':'Not found'})
            except (ValueError,KeyError) as e:return self.reply(400,{'error':str(e)[:200]})
            except Exception:return self.reply(500,{'error':'本地处理失败，请检查数据目录的访问权限。'})
    return Handler

def main():
    os.umask(0o077)
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765)
    p.add_argument('--source-root');p.add_argument('--vault-root');p.add_argument('--state-root');p.add_argument('--codex-bin');p.add_argument('--skill-dir');p.add_argument('--skill-python')
    a=p.parse_args();monitor=DatabaseMonitor(a.source_root,a.vault_root,a.state_root);bridge=CodexBridge(monitor.state_root,a.codex_bin)
    ingest=IngestBridge(monitor,a.skill_dir,a.skill_python)
    server=ThreadingHTTPServer(('127.0.0.1',a.port),make_handler(monitor,bridge,a.port,secrets.token_urlsafe(32),ingest))
    def stop(*_):ingest.close();bridge.close();threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    print(f'微信本地 Vault: http://127.0.0.1:{a.port}',flush=True)
    try:server.serve_forever()
    finally:ingest.close();bridge.close();server.server_close()
if __name__=='__main__':main()
