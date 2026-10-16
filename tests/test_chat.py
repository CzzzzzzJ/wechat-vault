import json,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backend.chat import ChatReader
class ChatTests(unittest.TestCase):
 def setUp(self):
  self.monitor=SimpleNamespace(latest={'accounts':[{'id':'a','source_path':'/source','snapshot':{'account':'alias'}}]},vault_root=Path('/vault'))
  self.activity=SimpleNamespace(read=lambda *_:{'groups':[{'chat_id':'g','name':'测试群','kind':'group'}],'private':[]})
  self.config=patch('backend.chat.Path.read_text',return_value=json.dumps({'db_dir':'/source'}));self.config.start();self.addCleanup(self.config.stop)
  self.reader=ChatReader(self.monitor,self.activity,SimpleNamespace(python='python',skill=Path('/skill')))
 def result(self,n=2):
  return SimpleNamespace(stdout=json.dumps({'ok':True,'items':[{'time':'2026-10-16T12:00:00+08:00','type':1,'sender':'测试','content':'明天交稿'} for _ in range(n)],'meta':{'snapshot_at':'2026-10-16','has_more':False}}))
 def test_receipt_bound_and_consent(self):
  with patch('backend.chat.subprocess.run',return_value=self.result()):
   p=self.reader.preview('a','2026-10-16','g')
  for aid,consent in [('b',True),('a',False)]:
   with self.assertRaises(ValueError):self.reader.approved(p['preview_id'],aid,consent)
  self.assertEqual(self.reader.approved(p['preview_id'],'a',True)['messages'][0]['ref'],'M1')
  self.reader.previews[p['preview_id']]['expires']=0
  with self.assertRaises(ValueError):self.reader.approved(p['preview_id'],'a',True)
 def test_no_arbitrary_chat_or_account(self):
  with patch('backend.chat.subprocess.run') as run:
   for aid,chat in [('x','g'),('a','other')]:
    with self.assertRaises(ValueError):self.reader.preview(aid,'2026-10-16',chat)
   run.assert_not_called()
 def test_media_and_truncation(self):
  r=json.loads(self.result().stdout);r['items'][0].update(type=34,content='private binary');r['items'][1]['content']='x'*60001
  with patch('backend.chat.subprocess.run',return_value=SimpleNamespace(stdout=json.dumps(r))):
   p=self.reader.preview('a','2026-10-16','g')
  self.assertTrue(p['partial']);self.assertEqual(p['message_count'],1);self.assertNotIn('binary',str(p))
