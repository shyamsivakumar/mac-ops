"""Replay T0 (skip the clock tick when no wake-class fact is new) over the journal.

T0 keeps the 30-minute clock. At each tick it reads facts newer than the last
tick that ran. With no wake-class fact it exits before the model call, except
that a tick always runs when none ran for 2 hours. Read-only.

Usage: python3 t0_replay.py [journal.jsonl]
"""
import collections
import datetime as dt
import sys

sys.argv = sys.argv[:1] + sys.argv[1:2]
src = open(__file__.replace("t0_replay.py", "replay_wakes.py")).read().split("fs = facts()")[0]
wakes = {}
exec(src, wakes)
facts, URGENT, ALL5 = wakes["facts"], wakes["URGENT"], wakes["ALL5"]

TICK, CAP, EST_H = 1800, 7200, -5
fs = facts()
t0, t1 = fs[0]["ts"], fs[-1]["ts"]
hours = (t1 - t0) / 3600
tick_times = []
t = t0 + TICK
while t <= t1:
    tick_times.append(t)
    t += TICK


def day(ts):
    return (dt.datetime.utcfromtimestamp(ts) + dt.timedelta(hours=EST_H)).strftime("%m-%d")


def replay(name, pred):
    ran, last_ran, last_seen = [], t0, t0
    lat = []
    for tk in tick_times:
        new = [r for r in fs if last_seen < r["ts"] <= tk and pred(r)]
        if new or tk - last_ran >= CAP:
            ran.append(tk)
            last_ran = tk
            lat += [tk - r["ts"] for r in new]
        last_seen = tk
    per = collections.Counter(day(x) for x in ran)
    q = lambda L, p: round(sorted(L)[int(p * (len(L) - 1))] / 60, 1) if L else None
    print(f"{name}: {len(ran)} of {len(tick_times)} clock ticks run in {hours:.1f} h "
          f"({len(ran) / hours * 24:.1f} a day); by day {dict(sorted(per.items()))}; "
          f"skipped {len(tick_times) - len(ran)} ({100 * (len(tick_times) - len(ran)) / len(tick_times):.0f}%)")
    print(f"  new wake-class row to the tick that handles it (min): median {q(lat, .5)}, p90 {q(lat, .9)} ({len(lat)} rows)")


print(f"window {hours:.1f} h; nominal clock {len(tick_times)} ticks ({len(tick_times) / hours * 24:.1f} a day); "
      "measured launcher runs 88 in about 52 h (41 a day)")
replay("T0 with urgent kinds (variant B list)", lambda r: r["event"] in URGENT)
replay("T0 with all five kinds", lambda r: r["event"] in ALL5)
