import json, tempfile, unittest, time, threading, http.client, os
from pathlib import Path
from backend.database import DatabaseMonitor
from backend.codex import CodexBridge
from backend.server import make_handler, ThreadingHTTPServer

class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.db=self.root/'source/account/db_storage/message/message.db';self.db.parent.mkdir(parents=True);self.db.write_bytes(b'encrypted')
        self.m=DatabaseMonitor(self.root/'source',self.root/'vault',self.root/'state')
    def test_changes_wal_and_removal(self):
        a=self.m.scan()['accounts'][0];self.assertEqual(a['databases'][0]['change'],'first_scan')
        self.assertEqual(self.m.scan()['accounts'][0]['changed_count'],0)
        Path(str(self.db)+'-wal').write_bytes(b'new transaction')
        a=self.m.scan()['accounts'][0];self.assertEqual(a['changed_count'],1);self.assertTrue(a['databases'][0]['wal_present'])
        self.db.unlink();self.assertEqual(self.m.scan()['accounts'][0]['removed_databases'],['message/message.db'])
    def test_context_and_account_isolation(self):
        a=self.m.scan()['accounts'][0];ctx=self.m.context(a['id']);self.assertNotIn(str(self.root),json.dumps(ctx));self.assertNotIn('source_path',ctx)
        with self.assertRaises(ValueError):self.m.context('another-account')
        self.assertEqual(a['snapshot']['status'],'unbound')
    def test_snapshot_comparison(self):
        account=self.root/'vault/accounts/test';snap=account/'snapshots'/('a'*32);snap.mkdir(parents=True)
        (account/'config.json').write_text(json.dumps({'db_dir':str(self.db.parent.parent)}))
        (account/'current.json').write_text(json.dumps({'snapshot':'a'*32}))
        (snap/'manifest.json').write_text(json.dumps({'created_at':'2000-01-01T00:00:00+00:00','databases':[]}))
        a=self.m.scan()['accounts'][0];self.assertEqual(a['snapshot']['status'],'available');self.assertEqual(a['source_newer_than_snapshot'],1)
    def test_http_guards(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.m,None,1,'test-token'));port=server.server_port
        server.RequestHandlerClass=make_handler(self.m,None,port,'test-token')
        threading.Thread(target=server.serve_forever,daemon=True).start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def request(method,path,headers={}):
            c=http.client.HTTPConnection('127.0.0.1',port);c.request(method,path,body='{}' if method=='POST' else None,headers=headers);r=c.getresponse();r.read();c.close();return r.status
        self.assertEqual(request('GET','/api/codex/status'),401)
        self.assertEqual(request('GET','/api/bootstrap',{'Sec-Fetch-Site':'cross-site'}),403)
        self.assertEqual(request('GET','/api/bootstrap',{'Host':'evil.example'}),403)
        self.assertEqual(request('POST','/api/scan'),403)
        headers={'Origin':f'http://127.0.0.1:{port}','Cookie':'vault_session=test-token','X-Vault-Token':'test-token','Content-Type':'application/json'}
        self.assertEqual(request('POST','/api/scan',headers),200)
        self.assertEqual(request('GET','/../../backend/server.py'),404)

class CodexTests(unittest.TestCase):
    def test_reconnect_then_success(self):
        with tempfile.TemporaryDirectory() as t:
            exe=Path(t)/'fake-codex';exe.write_text('#!/usr/bin/env python3\nimport json,sys\nsys.stdin.read()\nfor e in [{"type":"error","message":"Reconnecting"},{"type":"item.completed","item":{"type":"agent_message","text":"OK"}},{"type":"turn.completed"}]: print(json.dumps(e),flush=True)\n');exe.chmod(0o700)
            b=CodexBridge(t,str(exe));j=b.start('test',probe=True)
            for _ in range(100):
                j=b.get(j['id'])
                if j['status'] not in ('queued','running'):break
                time.sleep(.02)
            self.assertEqual(j['status'],'completed');self.assertTrue(b.last_probe['ok']);b.close()
    def test_cancel(self):
        with tempfile.TemporaryDirectory() as t:
            exe=Path(t)/'fake-codex';exe.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(20)\n');exe.chmod(0o700)
            b=CodexBridge(t,str(exe));j=b.start('test');time.sleep(.1);self.assertEqual(b.cancel(j['id'])['status'],'cancelled');b.close()
if __name__=='__main__':unittest.main()
