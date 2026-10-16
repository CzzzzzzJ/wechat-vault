import unittest,tempfile,sqlite3,hashlib,json
from pathlib import Path
from backend.search import SearchService
from backend.database import DatabaseMonitor
from test_overview import fixture
class SearchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
  source,snap=fixture(root)
  with sqlite3.connect(snap/'data/message/message_0.db') as c:
   for name in ('g@chatroom','friend'):
    t='Msg_'+hashlib.md5(name.encode()).hexdigest();c.execute('DROP TABLE "'+t+'"');c.execute('CREATE TABLE "'+t+'"(local_id INTEGER,create_time INTEGER,local_type INTEGER,message_content TEXT,real_sender_id INTEGER)')
    c.executemany('INSERT INTO "'+t+'" VALUES(?,?,?,?,?)',[(1,1770000000,1,'课程合作报价 100% _',1),(2,1770000001,3,'课程图片',1)])
   c.execute('CREATE TABLE Name2Id(user_name TEXT)');c.execute("INSERT INTO Name2Id VALUES('alice')")
  self.m=DatabaseMonitor(root/'source',root/'vault',root/'state');self.a=self.m.scan()['accounts'][0]['id'];self.s=SearchService(self.m,None)
 def test_text_only_and_literal_wildcards(self):
  r=self.s.find(self.a,['课程']);self.assertEqual(r['matched'],2);self.assertEqual(r['indexed'],2)
  self.assertEqual(self.s.find(self.a,['% _'])['matched'],2)
  self.assertEqual(self.s.find(self.a,['图片'])['matched'],0)
 def test_date_and_account_isolation(self):
  self.assertEqual(self.s.find(self.a,['课程'],'2026-10-16','2026-10-16')['matched'],0)
  with self.assertRaises(ValueError):self.s.find('other',['课程'])
  with self.assertRaises(ValueError):self.s.result('other','job')
 def test_persistent_index_and_dates(self):
  path,_=self.s.index(self.a);before=path.stat().st_mtime_ns
  self.s.index(self.a);self.assertEqual(before,path.stat().st_mtime_ns)
  self.assertEqual(path.stat().st_mode&0o777,0o600)
  with self.assertRaises(ValueError):self.s.bounds('2026-10-16',None)
 def test_semantic_expansion(self):
  class Fake:
   def start(self,*args,**kwargs):return {'id':'s1','status':'running'}
   def get(self,jid):return {'status':'completed','text':'{"terms":["合作","报价"]}'}
  self.s.codex=Fake();j=self.s.start(self.a,'以前谈过的价格');r=self.s.result(self.a,j['id'])
  self.assertEqual(r['terms'],['合作','报价']);self.assertEqual(r['matched'],2)
  self.assertIs(self.s.result(self.a,j['id']),r)
 def test_failed_rebuild_preserves_old_index(self):
  path,_=self.s.index(self.a);old=path.read_bytes()
  account=next((self.m.vault_root/'accounts').iterdir())
  (account/'current.json').write_text(json.dumps({'snapshot':'b'*32}))
  other=account/'snapshots'/('b'*32);other.mkdir();(other/'manifest.json').write_text('{}')
  with self.assertRaises(Exception):self.s.index(self.a)
  self.assertEqual(path.read_bytes(),old)
