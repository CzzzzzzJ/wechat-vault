import tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from backend.ingest import IngestBridge
from backend.database import DatabaseMonitor
from test_overview import fixture

class IngestTests(unittest.TestCase):
    def test_verified_keys_decrypt_then_update(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source,_=fixture(root,username='a')
            skill=root/'skill/scripts';skill.mkdir(parents=True);(skill/'vault.py').touch();exe=root/'python';exe.touch()
            monitor=DatabaseMonitor(root/'source',root/'vault',root/'state');aid=monitor.scan()['accounts'][0]['id']
            bridge=IngestBridge(monitor,skill.parent,exe);calls=[]
            def call(alias,op,*args):
                calls.append(op)
                return {'all_keys_verified':True} if op=='doctor' else {}
            with patch.object(bridge,'_call',side_effect=call):
                bridge.start(aid)
                for _ in range(100):
                    if bridge.status(aid)['status']!='running':break
                    time.sleep(.01)
            self.assertEqual(calls,['init','doctor','refresh']);self.assertEqual(bridge.status(aid)['status'],'completed')
            self.assertEqual(bridge.status(aid)['summary']['message_count'],4)
            self.assertIsNotNone(bridge.status(aid)['summary']['last_message_at'])
    def test_refresh_without_readable_messages_is_not_completed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'source/a/db_storage';source.mkdir(parents=True)
            skill=root/'skill/scripts';skill.mkdir(parents=True);(skill/'vault.py').touch();exe=root/'python';exe.touch()
            m=DatabaseMonitor(root/'source',root/'vault',root/'state');aid=m.scan()['accounts'][0]['id']
            b=IngestBridge(m,skill.parent,exe);b.jobs[aid]={'status':'running'}
            with patch.object(b,'_call',return_value={'all_keys_verified':True}):b._run(aid,m.latest['accounts'][0])
            self.assertEqual(b.status(aid)['status'],'failed');self.assertEqual(b.status(aid)['code'],'SNAPSHOT_UNREADABLE')
    def test_verified_empty_snapshot_is_distinguished_from_unread(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);fixture(root,username='a',count=0)
            skill=root/'skill/scripts';skill.mkdir(parents=True);(skill/'vault.py').touch();exe=root/'python';exe.touch()
            m=DatabaseMonitor(root/'source',root/'vault',root/'state');aid=m.scan()['accounts'][0]['id']
            b=IngestBridge(m,skill.parent,exe);b.jobs[aid]={'status':'running'}
            with patch.object(b,'_call',return_value={'all_keys_verified':True}):b._run(aid,m.latest['accounts'][0])
            self.assertEqual(b.status(aid)['status'],'completed');self.assertEqual(b.status(aid)['summary']['message_count'],0)
            self.assertIsNone(b.status(aid)['summary']['last_message_at'])
    def test_source_busy_is_not_success(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);m=DatabaseMonitor(root/'source',root/'vault',root/'state')
            s=root/'skill/scripts';s.mkdir(parents=True);(s/'vault.py').touch();exe=root/'python';exe.touch()
            b=IngestBridge(m,s.parent,exe);b.jobs['id']={'status':'running'}
            def call(alias,op,*args):
                if op=='refresh':raise ValueError('SOURCE_BUSY: 请正常退出微信')
                return {'all_keys_verified':True}
            with patch.object(b,'_call',side_effect=call):b._run('id',{'source_path':str(root/'source'),'snapshot':{}})
            self.assertEqual(b.status('id')['status'],'waiting_user');self.assertIn('SOURCE_BUSY',b.status('id')['error'])

    def test_repair_requires_explicit_consent(self):
        with tempfile.TemporaryDirectory() as t:
            b=IngestBridge(DatabaseMonitor(Path(t)/'source',Path(t)/'vault',Path(t)/'state'))
            with self.assertRaises(ValueError):b.repair('unknown',False)
    def test_cancel_waiting_does_not_start_process(self):
        with tempfile.TemporaryDirectory() as t:
            b=IngestBridge(DatabaseMonitor(Path(t)/'source',Path(t)/'vault',Path(t)/'state'))
            b.jobs['a']={'status':'waiting_user','stage':'等待退出','code':'SOURCE_BUSY'}
            self.assertEqual(b.cancel('a')['status'],'cancelled')
            self.assertEqual(b.processes,{})
    def test_repair_refuses_running_wechat(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);m=DatabaseMonitor(root/'source',root/'vault',root/'state');m.latest={'accounts':[{'id':'a'}]}
            b=IngestBridge(m)
            with patch.object(b,'client_state',return_value={'running':True}):
                with self.assertRaises(ValueError):b.repair('a',True)
            self.assertEqual(b.jobs,{})
    def test_repair_verifies_signature_before_launch(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);m=DatabaseMonitor(root/'source',root/'vault',root/'state');(m.vault_root/'apps/WeChat.app').mkdir(parents=True)
            b=IngestBridge(m);b.jobs['a']={'status':'running'}
            with patch.object(b,'client_state',return_value={'running':False}),patch('backend.ingest.subprocess.run',return_value=SimpleNamespace(returncode=0,stderr='Signature=adhoc')) as run:
                b._repair('a',{'snapshot':{}})
            self.assertEqual(b.status('a')['code'],'COPY_READY');self.assertEqual(run.call_args_list[-1].args[0],['open','-n',str(m.vault_root/'apps/WeChat.app')])
    def test_capture_readiness_event_is_forwarded(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);m=DatabaseMonitor(root/'source',root/'vault',root/'state');exe=root/'fake-python'
            exe.write_text('#!/usr/bin/env python3\nimport sys,json\nprint(json.dumps({"capture_status":"hook_ready"}),file=sys.stderr,flush=True)\nprint(json.dumps({"ok":True,"items":{"verified_keys":4}}))\n');exe.chmod(0o700)
            b=IngestBridge(m,root,exe);b.jobs['a']={'status':'running'};b.local.aid='a'
            self.assertEqual(b._call('one','capture-keys')['verified_keys'],4)
            self.assertIn('监听已就绪',b.status('a')['stage'])
