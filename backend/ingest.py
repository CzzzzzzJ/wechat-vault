"""Explicit account-scoped adapter to the standalone Skill CLI."""
import json, subprocess, threading, time, os, signal
from pathlib import Path

class IngestBridge:
    def __init__(self, monitor, skill_dir=None, python=None):
        self.monitor=monitor
        self.skill=Path(skill_dir or Path.home()/'.codex/skills/mdldm-wechat-vault')
        self.python=str(python or monitor.vault_root/'runtime/bin/python')
        self.jobs={};self.lock=threading.RLock();self.local=threading.local();self.processes={};self.active=set()
    def status(self,aid):
        with self.lock:return dict(self.jobs.get(aid,{'status':'idle','stage':'等待开始','error':None,'step':0,'code':None}))
    def start(self,aid):
        with self.lock:
            if self.active or any(j['status']=='running' for j in self.jobs.values()) or any(p.poll() is None for p in self.processes.values()):raise ValueError('已有读取任务运行中。')
            account=next((a for a in (self.monitor.latest or {}).get('accounts',[]) if a['id']==aid),None)
            if not account:raise ValueError('请先选择已发现的账号。')
            self.jobs[aid]={'status':'running','stage':'检查读取环境','error':None,'updated_at':time.time(),'step':0,'code':None}
            self.active.add(aid)
            threading.Thread(target=self._run,args=(aid,account),daemon=True).start()
            return self.status(aid)
    def _call(self,alias,operation,*args):
        aid=getattr(self.local,'aid',None)
        if aid and self.jobs[aid]['status']=='cancelled':raise ValueError('CANCELLED: 已取消读取。')
        command=[self.python,str(self.skill/'scripts/vault.py'),'--root',str(self.monitor.vault_root),'--account',alias,operation,*args]
        aid=getattr(self.local,'aid',None)
        p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        if aid:self.processes[aid]=p
        def progress():
            for line in p.stderr:
                try:event=json.loads(line)
                except ValueError:continue
                if aid and event.get('capture_status')=='hook_ready':
                    self.jobs[aid].update(stage='监听已就绪，请在微信副本中登录所选账号',step=2)
        reader=threading.Thread(target=progress,daemon=True);reader.start()
        output=[]
        drain=threading.Thread(target=lambda:output.append(p.stdout.read()),daemon=True);drain.start()
        try:p.wait(timeout=600)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM);p.wait();raise
        finally:
            drain.join(timeout=3);reader.join(timeout=3)
            p.stdout.close();p.stderr.close()
            if aid:self.processes.pop(aid,None)
        if aid and self.jobs[aid]['status']=='cancelled':raise ValueError('CANCELLED: 已取消读取。')
        r=type('Result',(),{'stdout':''.join(output)})()
        try:result=json.loads(r.stdout)
        except ValueError:raise ValueError('SKILL_FAILED: Skill 没有返回有效结果。')
        if not result.get('ok'):
            err=result.get('error',{});raise ValueError(err.get('code','SKILL_FAILED')+': '+err.get('message','读取失败'))
        return result.get('items',{})
    def _run(self,aid,account):
        job=self.jobs[aid];self.local.aid=aid
        try:
            if not Path(self.python).is_file() or not (self.skill/'scripts/vault.py').is_file():
                raise ValueError('RUNTIME_MISSING: 请先安装独立 Skill 的运行环境，或配置 --skill-dir / --skill-python。')
            alias=account['snapshot'].get('account') or 'web_'+aid
            self._call(alias,'init','--db-dir',account['source_path'],'--scope','messages')
            job.update(stage='验证账号密钥',step=1)
            doctor=self._call(alias,'doctor')
            if not doctor.get('all_keys_verified'):
                job.update(stage='检查微信客户端与当前账号',step=2)
                processes=subprocess.run(['ps','-axo','pid=,comm='],capture_output=True,text=True,timeout=10).stdout
                targets=[]
                for line in processes.splitlines():
                    fields=line.strip().split(None,1)
                    if len(fields)!=2:continue
                    path=Path(fields[1])
                    if path.name in ('WeChat','Weixin') and path.parent.name=='MacOS' and path.parent.parent.name=='Contents' and path.parent.parent.parent.name in ('WeChat.app','Weixin.app'):
                        targets.append(fields[0])
                if len(targets)!=1:raise ValueError('SELECT_PROCESS: 请只运行一个微信主程序，并登录当前选中的账号。')
                opened=subprocess.run(['lsof','-p',targets[0],'-Fn'],capture_output=True,text=True,timeout=20).stdout
                prefix='n'+account['source_path']+'/'
                copy_path=str(self.monitor.vault_root/'apps/WeChat.app/Contents/MacOS/WeChat')
                is_copy=any(line.strip().split(None,1)==[targets[0],copy_path] for line in processes.splitlines())
                if not is_copy and not any(line.startswith(prefix) for line in opened.splitlines()):
                    raise ValueError('ACCOUNT_NOT_ACTIVE: 当前微信未打开所选账号的数据，请切换到该账号登录后重试。')
                self._call(alias,'capture-keys','--pid',targets[0],'--seconds','300')
                if not self._call(alias,'doctor').get('all_keys_verified'):
                    raise ValueError('KEYS_INCOMPLETE: 部分消息库尚未取得密钥，请打开相关会话后重试。')
            job.update(stage='解密并逐页验证快照',step=3)
            self._call(alias,'refresh')
            job.update(stage='验证读取结果与账号资料',step=4)
            checked=self.monitor.scan()
            loaded=next((a for a in checked['accounts'] if a['id']==aid),None)
            overview=loaded.get('overview',{}) if loaded else {}
            if overview.get('status') not in ('ready','partial') or overview.get('message_count') is None:
                job.update(status='failed',stage='快照读取尚未验证',error='生成快照后仍未读出消息统计，请检查快照完整性。',step=4,code='SNAPSHOT_UNREADABLE')
                return
            summary={k:overview.get(k) for k in ('message_count','last_message_at','snapshot_at','partial')}
            job.update(status='completed',stage='导入完成，部分数据可用' if overview.get('partial') else '快照导入完成',error=None,step=5,code=None,summary=summary)
        except ValueError as e:
            if job['status']=='cancelled':return
            code=str(e).split(':',1)[0]
            job.update(status='cancelled' if code=='CANCELLED' else 'waiting_user',stage='等待验证' if code in ('SOURCE_BUSY','SELECT_PROCESS','ACCOUNT_NOT_ACTIVE') else '需要处理客户端问题',error=str(e),code=code)
        except subprocess.TimeoutExpired:
            if job['status']=='cancelled':return
            job.update(status='failed',stage='读取超时',error='读取超时，旧快照保持不变。')
        except Exception:
            if job['status']=='cancelled':return
            job.update(status='failed',stage='读取失败',error='本地读取失败，请检查 Skill 与运行环境。')
        finally:
            job['updated_at']=time.time()
            self.active.discard(aid)

    def cancel(self,aid):
        with self.lock:
            job=self.jobs.get(aid)
            if not job:return self.status(aid)
            job.update(status='cancelled',stage='已取消导入',error=None,code='CANCELLED',updated_at=time.time())
            p=self.processes.get(aid)
            if p and p.poll() is None:
                try:os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError:pass
            return self.status(aid)

    def client_state(self):
        running=any(subprocess.run(['pgrep','-x',name],capture_output=True).returncode==0 for name in ('WeChat','Weixin'))
        return {'running':running,'checked_at':time.time()}

    def repair(self,aid,consent):
        if consent is not True:raise ValueError('需要明确同意创建或重新签名微信副本。')
        with self.lock:
            if self.active or any(j['status']=='running' for j in self.jobs.values()) or any(p.poll() is None for p in self.processes.values()):raise ValueError('请先取消当前读取任务。')
            account=next((a for a in (self.monitor.latest or {}).get('accounts',[]) if a['id']==aid),None)
            if not account:raise ValueError('请先选择账号。')
            if self.client_state()['running']:raise ValueError('请用 ⌘Q 正常退出微信，检测到退出后才能修复副本。')
            self.jobs[aid]={'status':'running','stage':'准备微信副本','step':1,'error':None,'code':None,'updated_at':time.time()}
        self.active.add(aid)
        threading.Thread(target=self._repair,args=(aid,account),daemon=True).start()
        return self.status(aid)

    def _repair(self,aid,account):
        self.local.aid=aid;job=self.jobs[aid]
        try:
            if self.client_state()['running']:raise ValueError('微信尚未退出。')
            alias=account['snapshot'].get('account') or 'web_'+aid
            copy=self.monitor.vault_root/'apps/WeChat.app'
            if copy.is_symlink():raise ValueError('副本路径不能是符号链接。')
            if not copy.exists():self._call(alias,'prepare-copy','--acknowledge-app-copy')
            else:
                result=subprocess.run(['codesign','--force','--deep','--sign','-',str(copy)],capture_output=True,text=True,timeout=180)
                if result.returncode:raise ValueError('副本签名失败，请重试。')
            signature=subprocess.run(['codesign','-dv',str(copy)],capture_output=True,text=True,timeout=20)
            if 'Signature=adhoc' not in signature.stderr:raise ValueError('副本签名验证失败。')
            if job['status']=='cancelled':return
            subprocess.run(['open','-n',str(copy)],check=True,capture_output=True,timeout=30)
            job.update(status='waiting_user',stage='副本已准备好，请停留在登录页',step=2,code='COPY_READY',error=None)
        except Exception:
            if job['status']!='cancelled':job.update(status='waiting_user',stage='副本处理未完成',code='REPAIR_FAILED',error='请检查微信已退出，且副本目录可写。')
        finally:
            job['updated_at']=time.time()
            self.active.discard(aid)

    def close(self):
        for aid in list(self.jobs):
            if self.jobs[aid]["status"]=="running":self.cancel(aid)
