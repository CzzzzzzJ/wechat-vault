import json,unittest
from backend.analysis import AnalysisService
import test_activity
class AnalysisTests(unittest.TestCase):
 def context(self):
  return {'start':'2026-10-10','end':'2026-10-16','snapshot_at':'s','partial':True,'conversations':[{'conversation_id':'C1','conversation':'测试同事','kind':'private','messages':[{'ref':'M1','content':'周五一起开需求评审','time':'t'}]},{'conversation_id':'C2','conversation':'群','kind':'group','messages':[{'ref':'M2','content':'收到','time':'t'}]}]}
 def test_evidence_categories_and_dedup(self):
  e={'category':'邀约','title':'需求评审','evidence':['M1']}
  data={'relationships':[{'conversation_id':'C1','label':'工作协作','evidence':['M1'],'confidence':'中'},{'conversation_id':'C2','label':'朋友交流','evidence':['M2']}],'events':[e,e,{'category':'邀约','title':'无依据','evidence':['fake']}],'counts':{'邀约':999}}
  r=AnalysisService.validate(json.dumps(data),self.context())
  self.assertEqual(r['counts']['邀约'],1);self.assertEqual(len(r['relationships']),1);self.assertTrue(r['partial'])
 def test_relationship_cannot_cite_other_conversation(self):
  r=AnalysisService.validate(json.dumps({'relationships':[{'conversation_id':'C1','label':'工作协作','evidence':['M2']}],'events':[]}),self.context())
  self.assertEqual(r['relationships'],[])
 def test_invalid_model_output(self):
  for text in ('not json','{}','[]'):
   with self.assertRaises(ValueError):AnalysisService.validate(text,self.context())
class RangeTests(unittest.TestCase):
 setUp=test_activity.ActivityTests.setUp
 def test_inclusive_range_and_limits(self):
  from backend.activity import ActivityReader
  r=ActivityReader(self.root/'vault')
  a=r.read(self.source,'2026-10-16')
  b=r.read(self.source,'2026-10-16','2026-10-17')
  self.assertGreater(sum(x['total'] for x in b['groups']),sum(x['total'] for x in a['groups']))
  with self.assertRaises(ValueError):r.read(self.source,'2026-10-16','2026-10-15')
  with self.assertRaises(ValueError):r.read(self.source,'2026-09-01','2026-10-16')
