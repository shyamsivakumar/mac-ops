import re,collections
POS=re.compile(r'(?<![#\w.])([1-9]\d*) (queue items?|sends?|launch(?:es)?(?: by hand)?|gates?(?: by (?:me|hand|this tick))?|merges?(?: by me)?|repo (?:code )?writes?|parks?|cards?(?: added| changed)?|decisions? raised|restacks?|resends?)\b')
rows=[]
for l in open('/Users/shyamsivakumar/Code/coordinator/loop/ticks.log',errors='replace'):
    m=re.match(r'(\d{4}-\d\d-\d\d) (\d\d:\d\d) (\w+) \| tick \(launchd\): (.*)',l)
    if not m: continue
    d,t,tz,rest=m.groups()
    head=re.split(r';|\. Board| Board \d| Jobs alive',rest,1)[0]
    acted=bool(POS.search(head)) or bool(re.search(r'\b(restored|re-cut|resent)\b',head))
    rows.append((d,t,tz,acted,head[:160]))
by=collections.defaultdict(lambda:[0,0])
for d,t,tz,a,h in rows:
    by[d][0]+=1; by[d][1]+= (not a)
tot=0;emp=0
for d in sorted(by):
    if '2026-11-16'<=d<='2026-11-22':
        tot+=by[d][0]; emp+=by[d][1]
    print(d,by[d][0],'noaction',by[d][1])
print('7d (11-16..11-22):',tot,'ticks, no-action',emp,round(100*emp/tot,1),'%')
import random;random.seed(1)
samp=[r for r in rows if '2026-11-16'<=r[0]<='2026-11-22']
for r in random.sample(samp,14): print(r[3],r[0],r[1],r[4])
win=[r for r in rows if '2026-11-16'<=r[0]<='2026-11-22']
st=[r for r in win if re.match(r'\d+ (launch|queue|send|gates?)|1 park',r[4]) or re.search(r'\b0 (sends|launches|gates)',r[4])]
print('structured-count era (from 2026-11-19 13:39):',len(st),'ticks, no-action',sum(1 for r in st if not r[3]),round(100*sum(1 for r in st if not r[3])/len(st),1),'%')
print('prose era:',len(win)-len(st),'ticks, no-action',sum(1 for r in win if not r[3])-sum(1 for r in st if not r[3]))
