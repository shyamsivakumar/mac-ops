import json,re,subprocess,datetime as dt
UTC=dt.timezone.utc
def iso(s): return dt.datetime.fromisoformat(s.replace('Z','+00:00'))
prs=json.loads(subprocess.run(['gh','pr','list','-R','shyamsivakumar/mac-ops','--state','all','--limit','60','--json','number,createdAt,mergedAt'],capture_output=True,text=True).stdout)
P={p['number']:p for p in prs}
J={}
for l in open('/Users/shyamsivakumar/.local/state/coordinator/journal/events-2026-11.jsonl'):
    try:r=json.loads(l)
    except: continue
    if r.get('repo')=='shyamsivakumar/mac-ops' and r.get('pr') in P and r['event'] in('gate_queued','gate_verdict','merged','merged_outside_lane','fix_sent'):
        J.setdefault(r['pr'],[]).append((r['ts'],r['event'],r.get('head')))
ticks=[]
off={'PT':-8,'PST':-8,'EST':-5,'UTC':0,'Z':0}
for l in open('/Users/shyamsivakumar/Code/coordinator/loop/ticks.log',errors='replace'):
    m=re.match(r'(\d{4}-\d\d-\d\d) (\d\d:\d\d) (\w+) \| tick \(launchd\): (.*)',l)
    if m:
        d,t,tz,rest=m.groups()
        ts=dt.datetime.fromisoformat(d+'T'+t).replace(tzinfo=dt.timezone(dt.timedelta(hours=off.get(tz,-8))))
        ticks.append((ts,rest))
ticks.sort()
def nxt(t): 
    for ts,_ in ticks:
        if ts>t: return ts
def named(n,after):
    for ts,rest in ticks:
        if ts>=after and re.search(rf'(mac-ops)?#{n}\b',rest): return ts
mins=lambda a,b:round((b-a).total_seconds()/60,1)
out=[]
for n in sorted(P):
    if n<851: continue
    p=P[n]; c=iso(p['createdAt']); m=iso(p['mergedAt']) if p['mergedAt'] else None
    ev=sorted(J.get(n,[]))
    gq=next((dt.datetime.fromtimestamp(t,UTC) for t,e,h in ev if e=='gate_queued'),None)
    gv=next((dt.datetime.fromtimestamp(t,UTC) for t,e,h in ev if e=='gate_verdict'),None)
    mj=next((dt.datetime.fromtimestamp(t,UTC) for t,e,h in ev if e in('merged','merged_outside_lane')),None)
    row=[n,'opened',c.strftime('%d %H:%M'),'->gate_queued',mins(c,gq) if gq else None]
    row+=['verdict->merged',mins(gv,mj) if gv and mj else None]
    nt=nxt(m) if m else None
    row+=['merge->next tick',mins(m,nt) if nt else None]
    nm=named(n,c)
    row+=['open->first tick naming it',mins(c,nm) if nm else None]
    print(*row)
