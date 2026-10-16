import json,shutil,sqlite3,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from backend.database import DatabaseMonitor
from backend.profile import ProfileService
from test_overview import fixture
class ProfileTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.source,self.snap=fixture(self.root)
  with sqlite3.connect(self.snap/'data/contact/contact.db') as c:
   c.execute('ALTER TABLE contact ADD COLUMN alias TEXT')
   c.execute('UPDATE contact SET alias=? WHERE username=?',('my_wechat','alice'))
  self.monitor=DatabaseMonitor(self.root/'source',self.root/'vault',self.root/'state')
  self.aid=self.monitor.scan()['accounts'][0]['id']
  self.calls=0
  def read(*a):
   self.calls+=1
   return {'errors':[],'self_attribution_complete':True,'totals':{'my_group_messages':80,'my_private_messages':20},'my_hours':[0]*14+[100]+[0]*9}
  self.activity=SimpleNamespace(read=read);self.avatars=SimpleNamespace(read=lambda *a:{'image':None})
  self.service=ProfileService(self.monitor,self.activity,self.avatars)
 def test_verified_self_identity_no_other_person_or_body(self):
  p=self.service.read(self.aid)
  self.assertEqual(p['identity']['nickname'],'测试昵称');self.assertEqual(p['identity']['wechat_id'],'my_wechat')
  self.assertNotIn('PRIVATE BODY',json.dumps(p));self.assertNotIn('不应使用备注',json.dumps(p))
  self.assertEqual(p['signals'][0]['label'],'群聊沟通更多')
  self.assertEqual(p['signals'][1]['label'],'下午交流较多')
 def test_repeated_view_does_not_count_new_observation(self):
  self.service.read(self.aid);p=self.service.read(self.aid)
  self.assertEqual(p['observation_count'],1);self.assertEqual(self.calls,1)
 def test_manual_profile_survives_new_snapshot_and_restart(self):
  fields={'role':'内容创作者','bio':'我的手动介绍','interests':['产品','AI']}
  self.service.update(self.aid,fields)
  second=self.snap.parent/('b'*32);shutil.copytree(self.snap,second)
  with sqlite3.connect(second/'data/contact/contact.db') as c:c.execute('UPDATE contact SET nick_name=? WHERE username=?',('新昵称','alice'))
  (second/'manifest.json').write_text(json.dumps({'created_at':'2026-02-01T00:00:00Z'}))
  (self.snap.parent.parent/'current.json').write_text(json.dumps({'snapshot':'b'*32}))
  p=self.service.read(self.aid);self.assertEqual(p['manual'],fields);self.assertEqual(p['identity']['nickname'],'新昵称');self.assertEqual(p['observation_count'],2)
  fresh=ProfileService(self.monitor,self.activity,self.avatars)
  self.assertEqual(fresh.read(self.aid)['manual'],fields)
  self.assertEqual(fresh.path.stat().st_mode&0o777,0o600)
 def test_account_isolation_and_field_validation(self):
  self.service.update(self.aid,{'role':'我的身份','bio':'私有介绍','interests':[]})
  other,_=fixture(self.root,'bob','另一个账号','two')
  aid=next(a['id'] for a in self.monitor.scan()['accounts'] if a['source_path']==str(other))
  self.assertEqual(self.service.read(aid)['manual']['bio'],'')
  with self.assertRaises(ValueError):self.service.read('unknown')
  with self.assertRaises(ValueError):self.service.update(self.aid,{'role':'','bio':'','interests':[],'nickname':'篡改微信昵称'})
 def test_sparse_or_unknown_senders_do_not_invent_traits(self):
  self.assertEqual(ProfileService.observe({'totals':{'my_group_messages':1,'my_private_messages':2},'self_attribution_complete':True,'my_hours':[0]*24})['signals'],[])
  self.assertEqual(ProfileService.observe({'self_attribution_complete':False})['signals'],[])
