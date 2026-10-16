"""Model plans intent; local code validates scope and retrieves bounded evidence."""
import json,re,threading,time
from pathlib import Path
from datetime import datetime
from .activity import TZ

class AgentBridge:
    def __init__(self,monitor,activity,chats,codex):
        self.monitor=monitor;self.activity=activity;self.chats=chats;self.codex=codex;self.plans={};self.lock=threading.Lock()
    def start(self,aid,day,prompt):
        account=self.account(aid)
        datetime.strptime(day,'%Y-%m-%d')
        today=datetime.now(TZ).strftime('%Y-%m-%d')
        j=self.codex.start(prompt,context={'today':today,'selected_date':day},planner=True)
        with self.lock:
            self.plans={k:v for k,v in self.plans.items() if v['expires']>time.time()}
            self.plans[j['id']]={'account':aid,'day':day,'prompt':prompt,'expires':time.time()+900}
        return j
    def account(self,aid):
        a=next((a for a in (self.monitor.latest or {}).get('accounts',[]) if a['id']==aid),None)
        if not a:raise ValueError('请先选择已发现的账号。')
        return a
    def prepare(self,jid,aid,choice=None):
        p=self.plans.get(jid)
        if not p or p['account']!=aid or p['expires']<time.time():raise ValueError('需求已过期或账号已切换，请重新提问。')
        j=self.codex.get(jid)
        if j['status']!='completed':raise ValueError('需求理解尚未完成，请重试。')
        try:
            raw=re.sub(r'^```(?:json)?\s*|\s*```$','',j['text'].strip())
            plan=json.loads(raw)
            if plan.get('intent') not in ('summary','todos','important','statistics','clarify'):raise ValueError()
            day=plan.get('date');datetime.strptime(day,'%Y-%m-%d')
            if plan.get('scope') not in ('group','private','all'):raise ValueError()
            target=plan.get('target','')
            if not isinstance(target,str) or len(target)>200:raise ValueError()
        except (ValueError,TypeError,AttributeError):raise ValueError('未能确定查询范围，请换个说法，例如“总结今天会员群的重要信息”。')
        if plan['intent']=='clarify':return {'status':'clarify','question':'请说明要查看哪一天、哪个会话，以及想了解什么。目前支持单日聊天分析。','choices':[]}
        a=self.account(aid);stats=self.activity.read(Path(a['source_path']),day)
        rows=(stats.get('groups',[]) if plan['scope']=='group' else stats.get('private',[]) if plan['scope']=='private' else stats.get('groups',[])+stats.get('private',[]))
        if target:
            exact=[r for r in rows if r['name'].casefold()==target.casefold()]
            rows=exact or [r for r in rows if target.casefold() in r['name'].casefold()]
            if len(rows)>1:
                if choice:rows=[r for r in rows if r['chat_id']==choice]
                else:return {'status':'clarify','question':'找到多个同名或相近会话，你指的是哪一个？','choices':[{'id':r['chat_id'],'name':r['name']} for r in rows[:20]]}
        elif choice:raise ValueError('无效会话选择。')
        if not rows:return {'status':'clarify','question':'这个账号在 '+day+' 没有匹配到已读取的会话。请换个名称、日期，或先更新数据。','choices':[]}
        if plan['intent']=='statistics':
            metric='mine' if plan.get('metric')=='mine' else 'total'
            rows=sorted(rows,key=lambda r:-(r[metric] or 0))
            return {'status':'answer','text':day+' 的本地快照统计：\n'+'\n'.join(r['name']+'：'+str(r['total'])+' 条，我发送 '+('未知' if r['mine'] is None else str(r['mine']))+' 条' for r in rows[:10])+'\n仅代表已导入记录；最多显示前 10 个会话。'}
        # Broad requests intentionally use a visible, bounded shortlist, never claim exhaustive coverage.
        rows=sorted(rows,key=lambda r:(-(r['mine'] or 0),-r['total']))
        chosen=rows[:5];parts=[];remaining=60000;total=0;partial=len(rows)>5
        for row in chosen:
            local=self.chats.preview(aid,day,row['chat_id'])
            item=self.chats.approved(local['preview_id'],aid,True)
            with self.chats.lock:self.chats.previews.pop(local['preview_id'],None)
            messages=[]
            for m in item['messages']:
                if len(m['content'])>remaining:partial=True;break
                remaining-=len(m['content']);total+=1
                messages.append({**m,'ref':'M'+str(total)})
            if len(messages)<len(item['messages']):partial=True
            partial=partial or item['partial']
            parts.append({**item,'messages':messages})
        if not total:raise ValueError('没有可分析的消息。')
        payload={'date':day,'partial':partial,'selection':'精确会话匹配' if target else '按本人发言数优先，最多 5 个会话；不是全账号穷尽检索','conversations':parts}
        receipt=self.chats.remember(aid,payload)
        return {'status':'ready','preview_id':receipt,'date':day,'prompt':p['prompt'],'intent':plan['intent'],'partial':partial,'selection':payload['selection'],'message_count':total,'conversations':[{'name':x['conversation'],'count':len(x['messages']),'snapshot_at':x['snapshot_at']} for x in parts],'messages':[{'conversation':x['conversation'],**m} for x in parts for m in x['messages']]}
