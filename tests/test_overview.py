import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from backend.overview import OverviewReader
from backend.database import DatabaseMonitor


def fixture(base,username='alice',label='测试昵称',alias='one',count=2):
    source=base/'source'/(username+'_1234')/'db_storage';source.mkdir(parents=True)
    account=base/'vault/accounts'/alias;snap=account/'snapshots'/('a'*32)
    for folder in ('contact','session','message'):(snap/'data'/folder).mkdir(parents=True)
    (account/'config.json').write_text(json.dumps({'db_dir':str(source)}))
    (account/'current.json').write_text(json.dumps({'snapshot':'a'*32}))
    (snap/'manifest.json').write_text(json.dumps({'created_at':'2026-01-01T00:00:00Z'}))
    with sqlite3.connect(snap/'data/contact/contact.db') as c:
        c.execute('CREATE TABLE contact(username TEXT,nick_name TEXT,remark TEXT)')
        c.executemany('INSERT INTO contact VALUES(?,?,?)',[(username,label,'不应使用备注作为本人昵称'),('g@chatroom','测试群',''),('friend','测试好友','')])
    with sqlite3.connect(snap/'data/session/session.db') as c:
        c.execute('CREATE TABLE SessionTable(username TEXT,last_timestamp INTEGER)')
        c.executemany('INSERT INTO SessionTable VALUES(?,?)',[('g@chatroom',2000),('friend',3000)])
    with sqlite3.connect(snap/'data/message/message_0.db') as c:
        for user in ('g@chatroom','friend'):
            table='Msg_'+hashlib.md5(user.encode()).hexdigest()
            c.execute(f'CREATE TABLE "{table}"(create_time INTEGER,message_content TEXT)')
            c.executemany(f'INSERT INTO "{table}" VALUES (?,?)',[(1000+i,'PRIVATE BODY') for i in range(count)])
    return source,snap

class OverviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def test_identity_counts_and_body_exclusion(self):
        source,snap=fixture(self.root);o=OverviewReader(self.root/'vault').read(source)
        self.assertEqual(o['nickname'],'测试昵称');self.assertEqual(o['conversation_count'],2)
        self.assertEqual(o['group_count'],1);self.assertEqual(o['group_message_count'],2)
        self.assertEqual(o['message_count'],4);self.assertEqual(o['status'],'ready')
        self.assertIsNotNone(o['last_message_at']);self.assertNotIn('PRIVATE BODY',json.dumps(o))
    def test_account_isolation_and_context(self):
        source,_=fixture(self.root);other,_=fixture(self.root,'bob','另一个昵称','two',4)
        monitor=DatabaseMonitor(self.root/'source',self.root/'vault',self.root/'state');a,b=monitor.scan()['accounts']
        self.assertEqual(a['overview']['message_count'],4);self.assertEqual(b['overview']['message_count'],8)
        ctx=monitor.context(a['id']);self.assertEqual(ctx['message_count'],4)
        self.assertNotIn('nickname',ctx);self.assertNotIn('recent_conversations',ctx);self.assertNotIn('username',ctx)
    def test_no_snapshot_is_unknown_not_zero(self):
        source=self.root/'source/person_1234/db_storage';source.mkdir(parents=True)
        o=OverviewReader(self.root/'vault').read(source)
        self.assertEqual(o['status'],'not_read');self.assertIsNone(o['message_count']);self.assertIsNone(o['nickname'])
    def test_unmapped_group_is_not_silently_classified(self):
        source,snap=fixture(self.root)
        with sqlite3.connect(snap/'data/message/message_0.db') as c:
            c.execute('CREATE TABLE Msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa(create_time INTEGER)')
            c.execute('INSERT INTO Msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa VALUES(4000)')
        o=OverviewReader(self.root/'vault').read(source)
        self.assertEqual(o['message_count'],5);self.assertEqual(o['unclassified_message_count'],1)
        self.assertTrue(o['partial']);self.assertEqual(o['group_message_count'],2)
    def test_unsupported_message_table_is_partial(self):
        source,snap=fixture(self.root)
        with sqlite3.connect(snap/'data/message/message_1.db') as c:c.execute('CREATE TABLE Msg_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa(x INTEGER)')
        o=OverviewReader(self.root/'vault').read(source)
        self.assertEqual(o['status'],'partial');self.assertEqual(o['message_count'],4)
