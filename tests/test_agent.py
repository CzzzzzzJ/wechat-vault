import json,unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock
from backend.agent import AgentBridge
class AgentTests(unittest.TestCase):
 def setUp(self):
  self.plan={'intent':'summary','date':'2026-10-16','scope':'all','target':''}
  self.codex=Mock();self.codex.start.return_value={'id':'j','status':'queued'}
  self.codex.get.side_effect=lambda _: {'status':'completed','text':json.dumps(self.plan)}
  self.rows=[{'chat_id':str(i),'name':'测试群'+str(i),'mine':i,'total':20,'kind':'group'} for i in range(7)]
  self.activity=SimpleNamespace(read=lambda *_:{'groups':self.rows,'private':[]})
  self.chats=Mock();import threading
  self.chats.lock=threading.Lock();self.chats.previews={}
  self.chats.preview.side_effect=lambda a,d,c:{'preview_id':c}
  self.chats.approved.side_effect=lambda c,*_:{'conversation':'测试群'+c,'snapshot_at':'s','partial':False,'messages':[{'ref':'M1','content':'测试','time':'t'}]}
  self.chats.remember.return_value='receipt'
  self.agent=AgentBridge(SimpleNamespace(latest={'accounts':[{'id':'a','source_path':'/source'}]}),self.activity,self.chats,self.codex)
  self.agent.start('a','2026-10-16','总结今天')
 def test_bounded_retrieval_and_unique_refs(self):
  r=self.agent.prepare('j','a')
  self.assertEqual(r['message_count'],5);self.assertTrue(r['partial'])
  self.assertEqual([m['ref'] for m in r['messages']],['M1','M2','M3','M4','M5'])
  self.assertEqual(self.chats.preview.call_args_list[0].args[2],'6')
 def test_ambiguous_then_choice(self):
  self.plan['target']='测试群'
  r=self.agent.prepare('j','a');self.assertEqual(r['status'],'clarify');self.chats.preview.assert_not_called()
  r=self.agent.prepare('j','a','2');self.assertEqual(r['message_count'],1)
 def test_invalid_scope_and_account(self):
  with self.assertRaises(ValueError):self.agent.prepare('j','b')
  self.plan['scope']='any path'
  with self.assertRaises(ValueError):self.agent.prepare('j','a')
  self.chats.preview.assert_not_called()
 def test_statistics_does_not_read_messages(self):
  self.plan.update(intent='statistics',metric='mine')
  r=self.agent.prepare('j','a');self.assertEqual(r['status'],'answer');self.assertIn('测试群6',r['text'].splitlines()[1]);self.chats.preview.assert_not_called()
 def test_unknown_target_does_not_fallback(self):
  self.plan['target']='不存在'
  r=self.agent.prepare('j','a');self.assertEqual(r['status'],'clarify');self.chats.preview.assert_not_called()
