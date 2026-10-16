import json,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from backend.analysis_cache import AnalysisCache
from backend.analysis import AnalysisService
class CacheTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def report(self):return {'start':'2026-10-16','end':'2026-10-16','snapshot_at':'s','events':[],'relationships':[],'evidence':{},'counts':{}}
 def test_restart_isolation_and_version(self):
  c=AnalysisCache(self.root);c.task('j','a','2026-10-16','2026-10-16');c.complete('j','a','v1',self.report())
  c=AnalysisCache(self.root)
  self.assertEqual(c.lookup('a','2026-10-16','2026-10-16','v1')['report'],self.report())
  self.assertTrue(c.lookup('a','2026-10-16','2026-10-16','v2')['version_changed'])
  self.assertIsNone(c.lookup('b','2026-10-16','2026-10-16','v1')['report'])
  self.assertIsNone(c.get_report('b','j'))
  self.assertEqual(c.path.stat().st_mode&0o777,0o600)
 def test_failed_rerun_preserves_success_and_archive_undo(self):
  c=AnalysisCache(self.root);c.task('j','a','2026-10-16','2026-10-16');c.complete('j','a','v',self.report())
  c.task('j2','a','2026-10-16','2026-10-16');c.fail('j2','a','failed','offline')
  r=c.lookup('a','2026-10-16','2026-10-16','v');self.assertEqual(r['report_id'],'j');self.assertEqual(r['last_failure']['error'],'offline')
  batch=c.archive('b','2026-10-16','2026-10-16');self.assertIsNotNone(c.get_report('a','j'))
  batch=c.archive('a','2026-10-16','2026-10-16');self.assertIsNone(c.get_report('a','j'))
  c.undo('b',batch);self.assertIsNone(c.get_report('a','j'))
  c.undo('a',batch);self.assertIsNotNone(c.get_report('a','j'))
 def test_restart_marks_incomplete_task_interrupted(self):
  c=AnalysisCache(self.root);c.task('j','a','2026-10-16','2026-10-16')
  self.assertEqual(c.lookup('a','2026-10-16','2026-10-16','v')['pending']['id'],'j')
  c=AnalysisCache(self.root);r=c.lookup('a','2026-10-16','2026-10-16','v')
  self.assertIsNone(r['pending']);self.assertEqual(r['last_failure']['status'],'interrupted')
 def test_background_saves_without_browser_poll_and_survives_service_restart(self):
  event=threading.Event()
  context={'purpose':'range_analysis','start':'2026-10-16','end':'2026-10-16','snapshot_at':'s','partial':False,'conversations':[]}
  monitor=SimpleNamespace(state_root=self.root,latest={'accounts':[{'id':'a','source_path':'/source'}]},snapshot_for=lambda _:{'created_at':'s'})
  class Codex:
   def start(self,*a,**k):return {'id':'j','status':'queued'}
   def get(self,j):return {'id':j,'status':'completed' if event.is_set() else 'running','text':json.dumps({'events':[],'relationships':[]})}
  service=AnalysisService(monitor,None,SimpleNamespace(approved=lambda *a:context),Codex())
  service.start('a','receipt',True)
  self.assertEqual(service.cached('a',context['start'],context['end'])['pending']['id'],'j')
  event.set()
  for _ in range(100):
   if service.cache.get_report('a','j'):break
   time.sleep(.02)
  self.assertIsNotNone(service.cache.get_report('a','j'))
  # New service, no CLI job state: report and references still come from disk.
  fresh=AnalysisService(monitor,None,None,None)
  saved=fresh.cached('a',context['start'],context['end'])
  self.assertEqual(saved['report']['snapshot_at'],'s');self.assertFalse(saved['snapshot_changed'])
  monitor.snapshot_for=lambda _:{'created_at':'new'}
  self.assertTrue(fresh.cached('a',context['start'],context['end'])['snapshot_changed'])
  self.assertEqual(fresh.result('a','j')['status'],'completed')
