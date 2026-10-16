import sqlite3,tempfile,unittest,hashlib
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from test_overview import fixture
from backend.activity import ActivityReader

class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source,self.snap=fixture(self.root)
        self.start=int(datetime(2026,10,16,tzinfo=ZoneInfo('Asia/Shanghai')).timestamp())
        self.group='Msg_'+hashlib.md5(b'g@chatroom').hexdigest();self.friend='Msg_'+hashlib.md5(b'friend').hexdigest()
        with sqlite3.connect(self.snap/'data/message/message_0.db') as c:
            c.execute('CREATE TABLE Name2Id(user_name TEXT)');c.executemany('INSERT INTO Name2Id(rowid,user_name) VALUES(?,?)',[(1,'friend'),(2,'alice'),(3,'g@chatroom')])
            for table in (self.group,self.friend):
                c.execute(f'ALTER TABLE "{table}" ADD COLUMN real_sender_id INTEGER')
                c.execute(f'ALTER TABLE "{table}" ADD COLUMN local_type INTEGER DEFAULT 1')
            c.executemany(f'INSERT INTO "{self.group}"(create_time,real_sender_id,local_type) VALUES(?,?,?)',[(self.start,2,1),(self.start+3600,1,3),(self.start-1,2,1),(self.start+86400,2,1),(self.start+4,2,10000)])
            c.executemany(f'INSERT INTO "{self.friend}"(create_time,real_sender_id,local_type) VALUES(?,?,?)',[(self.start+7200,2,1),(self.start+7201,1,1)])
        with sqlite3.connect(self.snap/'data/message/message_1.db') as c:
            c.execute('CREATE TABLE Name2Id(user_name TEXT)');c.execute('INSERT INTO Name2Id(rowid,user_name) VALUES(10,"alice")')
            c.execute(f'CREATE TABLE "{self.group}"(create_time INTEGER,real_sender_id INTEGER,local_type INTEGER)')
            c.execute(f'INSERT INTO "{self.group}" VALUES(?,?,?)',(self.start+3601,10,34))
    def read(self,day='2026-10-16'):return ActivityReader(self.root/'vault').read(self.source,day)
    def test_day_boundary_sender_per_shard_and_heatmap(self):
        r=self.read();g=r['groups'][0];p=r['private'][0]
        self.assertEqual((g['total'],g['mine']),(3,2));self.assertEqual((p['total'],p['mine']),(2,1))
        self.assertEqual(g['hours'][:3],[1,2,0]);self.assertEqual(g['my_hours'][:3],[1,1,0])
        self.assertEqual(sum(r['hours']),5);self.assertEqual(sum(r['my_hours']),3)
        self.assertEqual(r['status'],'ready');self.assertEqual(r['totals']['my_group_messages'],2)
    def test_empty_day_is_not_import_failure(self):
        r=self.read('2026-10-14');self.assertEqual(r['status'],'ready');self.assertEqual(r['groups'],[]);self.assertEqual(sum(r['hours']),0)
    def test_missing_self_mapping_never_claims_zero(self):
        with sqlite3.connect(self.snap/'data/message/message_1.db') as c:c.execute('DELETE FROM Name2Id')
        r=self.read();self.assertFalse(r['self_attribution_complete']);self.assertIsNone(r['groups'][0]['mine']);self.assertEqual(r['status'],'partial')
    def test_invalid_date_rejected(self):
        for day in ['2026-02-30','../test',None]:
            with self.assertRaises(ValueError):self.read(day)
    def test_other_account_stays_separate(self):
        other,_=fixture(self.root,'bob','Bob','two',5)
        r=ActivityReader(self.root/'vault').read(other,'2026-10-16');self.assertEqual(r['groups'],[])
