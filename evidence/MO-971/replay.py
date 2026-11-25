import sys, json, time, re
from pathlib import Path
sys.path.insert(0, 'coordinator/bin')
import tick_health as t
jd = Path.home() / ".local/state/coordinator/journal/events-2026-11.jsonl"
rows = [json.loads(l) for l in open(jd) if l.strip()]
ticks = t.finished_ticks(open(Path.home() / "Library/Logs/coordinator/tick.log").read())
start = time.mktime((2026, 11, 23, 0, 0, 0, 0, 0, 0))
end = time.time()
def fmt(x): return time.strftime("%d %b %H:%M", time.localtime(x))
def run(label, fn, params):
    for p in params:
        episodes = {}
        now = start
        while now <= end:
            vis = [r for r in rows if r["ts"] <= now]
            tk = [x for x in ticks if x <= now]
            out = fn(vis, tk, now, p)
            for line in out.splitlines():
                key = re.sub(r" held [\d.]+ h", "", line) if label == "held" else line.split(";")[1]
                ep = episodes.setdefault(key, [now, now, line])
                ep[1] = now
            now += 900
        print(f"\n{label} at {p}: {len(episodes)} alert(s)")
        for key, (a, b, line) in sorted(episodes.items(), key=lambda kv: kv[1][0]):
            print(f"  from {fmt(a)} to {fmt(b)} | {line}")
run("held", lambda r, tk, now, p: t.held_alarm(r, now=now, hours=p), (4, 6, 12))
run("idle", lambda r, tk, now, p: t.idle_alarm(r, tk, now=now, count=p), (6, 8, 12))
print("\nvia_tick rows:", sum(1 for r in rows if isinstance(r.get('data'),dict) and r['data'].get('via_tick')), "first at", fmt(min(r['ts'] for r in rows if isinstance(r.get('data'),dict) and r['data'].get('via_tick'))))
print("finished ticks since 23 Nov:", len([x for x in ticks if x>=start]))
