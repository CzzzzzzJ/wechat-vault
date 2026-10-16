import unittest,tempfile,copy
from pathlib import Path
from types import SimpleNamespace
from backend.workflow import WorkflowService
class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.report={'start':'2026-01-01','end':'2026-01-01','events':[{'title':'确认方案','owner':'本人','due':'周五','status':'拟议','category':'待办','detail':'确认后回复','evidence':['M1']}],'evidence':{'M1':{'conversation':'同名','chat_id':'friend1','content':'请确认方案','time':'2026-01-01','sender':'朋友'}}}
  def account(a):
   if a not in ('a','b'):raise ValueError('account')
   return {}
  self.analysis=SimpleNamespace(account=account,cached=lambda *args:{'report':copy.deepcopy(self.report)})
  self.service=WorkflowService(SimpleNamespace(state_root=self.root),self.analysis,None)
  self.service.contacts=lambda aid:[{'chat_id':'friend1','name':'同名','kind':'private'},{'chat_id':'friend2','name':'同名','kind':'private'}]
 def add(self,aid='a',target=None):return self.service.import_event(aid,'2026-01-01','2026-01-01',0,'确认方案',target)
 def test_idempotent_and_isolated(self):
  x=self.add();self.assertEqual(self.add()['id'],x['id']);self.assertNotEqual(self.add('b')['id'],x['id'])
  self.assertEqual(len(self.service.list('a')['items']),1)
  with self.assertRaises(ValueError):self.service.update('b',x['id'],1,'已完成','','','')
 def test_state_not_overwritten_by_new_evidence(self):
  x=self.add()['id'];self.service.update('a',x,1,'已完成','2026-01-02','我','已回复')
  self.report['events'][0]['detail']='对方补充了报价';self.add(target=x)
  item=self.service.list('a')['items'][0];self.assertEqual(item['status'],'已完成');self.assertEqual(item['due'],'2026-01-02');self.assertEqual(len(item['entries']),3)
  reopened=WorkflowService(SimpleNamespace(state_root=self.root),self.analysis,None)
  self.assertEqual(reopened.list('a')['items'][0]['status'],'已完成')
 def test_conflict_and_bad_date(self):
  x=self.add()['id'];self.service.update('a',x,1,'进行中','','我','')
  with self.assertRaises(ValueError):self.service.update('a',x,1,'已完成','','我','')
  with self.assertRaises(ValueError):self.service.update('a',x,2,'进行中','昨天','我','')
 def test_exact_contact_no_same_name_leak(self):
  self.add();self.assertEqual(len(self.service.list('a','friend1')['items']),1);self.assertEqual(len(self.service.list('a','friend2')['items']),0)
 def test_legacy_ambiguous_name_not_linked(self):
  del self.report['evidence']['M1']['chat_id'];self.add();self.assertEqual(self.service.list('a')['items'][0]['contacts'],[])
 def test_no_cross_account_target_or_stale_event(self):
  x=self.add()['id'];self.report['events'][0]['detail']='new'
  with self.assertRaises(ValueError):self.add('b',x)
  with self.assertRaises(ValueError):self.service.import_event('a','2026-01-01','2026-01-01',0,'old')
 def test_reopen_and_postpone_audited(self):
  x=self.add()['id'];self.service.update('a',x,1,'已完成','2026-01-02','我','完成')
  self.service.update('a',x,2,'待处理','2026-01-05','我','需要补充')
  i=self.service.list('a')['items'][0];self.assertEqual(i['entries'][-1]['body']['changes']['due']['from'],'2026-01-02');self.assertEqual(i['status'],'待处理')
