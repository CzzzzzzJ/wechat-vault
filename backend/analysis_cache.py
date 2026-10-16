"""Private SQLite storage for completed reports and resumable task metadata."""
import json,os,sqlite3,threading,time,uuid
from pathlib import Path

class AnalysisCache:
    def __init__(self,root):
        root=Path(root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=root/'analysis.sqlite3';self.lock=threading.RLock()
        with self.db() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS reports(
              id TEXT PRIMARY KEY, account TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
              signature TEXT NOT NULL, saved_at REAL NOT NULL, body TEXT NOT NULL, archived TEXT);
            CREATE INDEX IF NOT EXISTS reports_lookup ON reports(account,start,end,saved_at);
            CREATE TABLE IF NOT EXISTS tasks(
              id TEXT PRIMARY KEY, account TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
              status TEXT NOT NULL, created_at REAL NOT NULL, error TEXT);
            """)
            c.execute("UPDATE tasks SET status='interrupted',error='服务已重启，本次未完成；已保存的分析仍可查看。' WHERE status IN ('queued','running')")
        os.chmod(self.path,0o600)
    def db(self):
        c=sqlite3.connect(self.path,timeout=15);c.row_factory=sqlite3.Row
        return c
    def task(self,jid,account,start,end,status='running'):
        with self.lock,self.db() as c:
            c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)',(jid,account,start,end,status,time.time(),None))
    def complete(self,jid,account,signature,report):
        body=json.dumps(report,ensure_ascii=False)
        with self.lock,self.db() as c:
            c.execute('INSERT OR REPLACE INTO reports VALUES(?,?,?,?,?,?,?,NULL)',(jid,account,report['start'],report['end'],signature,time.time(),body))
            c.execute("UPDATE tasks SET status='completed',error=NULL WHERE id=? AND account=?",(jid,account))
    def fail(self,jid,account,status,error):
        with self.lock,self.db() as c:
            c.execute('UPDATE tasks SET status=?,error=? WHERE id=? AND account=?',(status,error,jid,account))
    def lookup(self,account,start,end,signature):
        with self.lock,self.db() as c:
            row=c.execute('SELECT * FROM reports WHERE account=? AND start=? AND end=? AND archived IS NULL ORDER BY saved_at DESC LIMIT 1',(account,start,end)).fetchone()
            archived=c.execute('SELECT archived FROM reports WHERE account=? AND start=? AND end=? AND archived IS NOT NULL ORDER BY saved_at DESC LIMIT 1',(account,start,end)).fetchone()
            task=c.execute('SELECT id,status,error FROM tasks WHERE account=? AND start=? AND end=? ORDER BY created_at DESC LIMIT 1',(account,start,end)).fetchone()
            history=c.execute('SELECT start,end,MAX(saved_at) AS saved_at FROM reports WHERE account=? AND archived IS NULL GROUP BY start,end ORDER BY saved_at DESC LIMIT 20',(account,)).fetchall()
            summary=c.execute('SELECT COUNT(*),COALESCE(SUM(length(CAST(body AS BLOB))),0) FROM reports WHERE account=? AND archived IS NULL',(account,)).fetchone()
        return {'report':json.loads(row['body']) if row else None,
                'saved_at':row['saved_at'] if row else None,'report_id':row['id'] if row else None,
                'version_changed':bool(row and row['signature']!=signature),
                'undo_id':archived['archived'] if archived and not row else None,
                'pending':dict(task) if task and task['status'] in ('queued','running') else None,
                'last_failure':dict(task) if task and task['status'] in ('failed','interrupted','cancelled') else None,
                'summary':{'reports':summary[0],'bytes':summary[1]},'history':[dict(r) for r in history]}
    def get_report(self,account,jid):
        with self.lock,self.db() as c:row=c.execute('SELECT body FROM reports WHERE account=? AND id=? AND archived IS NULL',(account,jid)).fetchone()
        return json.loads(row['body']) if row else None
    def task_status(self,account,jid):
        with self.lock,self.db() as c:row=c.execute('SELECT status,error FROM tasks WHERE account=? AND id=?',(account,jid)).fetchone()
        return dict(row) if row else None
    def archive(self,account,start,end):
        batch=uuid.uuid4().hex
        with self.lock,self.db() as c:
            c.execute('UPDATE reports SET archived=? WHERE account=? AND start=? AND end=? AND archived IS NULL',(batch,account,start,end))
        return batch
    def undo(self,account,batch):
        with self.lock,self.db() as c:c.execute('UPDATE reports SET archived=NULL WHERE account=? AND archived=?',(account,batch))
