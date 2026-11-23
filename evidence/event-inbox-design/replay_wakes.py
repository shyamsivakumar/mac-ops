"""Replay the journal through the proposed wake rules and report wakes a day,
event to run latency, and the first-replay row count. Read-only.

Usage: python3 replay_wakes.py [journal.jsonl]
Days are US Eastern (UTC-5). Rules: debounce 60 s after the first wake row,
at least 600 s between runs (at most 6 an hour), the fallback timer fires
only when no run happened for 7200 s.
"""
import collections
import json
import statistics
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "/Users/shyamsivakumar/.local/state/coordinator/journal/events-2026-11.jsonl"
DEBOUNCE, FALLBACK = 60, 7200
GAP = 600
EST = -5 * 3600
ALL5 = {"gate_queued", "gate_verdict", "merged", "merged_outside_lane", "alarm_raised"}
URGENT = {"alarm_raised", "round_cap", "merge_held", "close_failed", "launch_failed", "recut"}
KNOWN = ALL5 | URGENT | {"alarm_withdrawn"}
SRW = "strategy-replay-workbench"

rows = []
for line in open(PATH):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    if r["event"] in KNOWN:
        rows.append(r)
rows.sort(key=lambda r: r["ts"])


def fact_key(r):
    d = r.get("data") or {}
    if r["event"] in ("alarm_raised", "alarm_withdrawn"):
        return ("alarm", d.get("alarm"))
    return (r["event"], r.get("repo"), r.get("pr"), r.get("ticket"), r.get("head"))


def facts():
    seen, generation, out = set(), collections.Counter(), []
    for r in rows:
        k = fact_key(r)
        if r["event"] == "alarm_withdrawn":
            generation[k] += 1
            continue
        k = k + (generation[k],) if k[0] == "alarm" else k
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def simulate(facts_, wake_pred):
    wake_ts = [r["ts"] for r in facts_ if wake_pred(r)]
    all_ts = [r["ts"] for r in facts_]
    runs, i, last = [], 0, None
    t_end = all_ts[-1]
    now = all_ts[0]
    while True:
        pending = [t for t in wake_ts if t > (runs[-1] if runs else 0) and t <= t_end]
        nxt_wake = next((t for t in wake_ts if t > (runs[-1] if runs else 0)), None)
        due_fb = (runs[-1] if runs else all_ts[0]) + FALLBACK
        cand = []
        if nxt_wake is not None:
            cand.append(max(nxt_wake + DEBOUNCE, (runs[-1] + GAP) if runs else 0))
        cand.append(due_fb)
        t = min(cand)
        if t > t_end:
            break
        runs.append(t)
    return runs, wake_ts


def day(ts):
    import datetime as dt
    return (dt.datetime.utcfromtimestamp(ts) + dt.timedelta(seconds=EST)).strftime("%m-%d")


fs = facts()
print(f"journal wake-kind lines {len(rows)}, distinct facts after alarm generations {len(fs)}")
print("first replay from month start would enqueue", len(fs), "pending rows; by day:",
      dict(sorted(collections.Counter(day(r['ts']) for r in fs).items())))
variants = {
    "A all five kinds wake": lambda r: r["event"] in ALL5,
    "B urgent kinds wake, others batch": lambda r: r["event"] in URGENT,
    "C urgent plus non-SRW merged/gate_verdict wake": lambda r: r["event"] in URGENT or (r["event"] in ("merged", "merged_outside_lane", "gate_verdict") and not (r.get("repo") or "").endswith(SRW)),
}
for GAP in (600, 1800, 3600):
  print(f"\n=== minimum gap between runs {GAP//60} min ===")
  for name, pred in variants.items():
      runs, wake_ts = simulate(fs, pred)
      per = collections.Counter(day(t) for t in runs)
      lat = []
      quiet = []
      for w in wake_ts:
          nxt = next((t for t in runs if t >= w), None)
          if nxt:
              lat.append(nxt - w)
              if not any(w - GAP <= t < w for t in runs):
                  quiet.append(nxt - w)
      batch_lat = []
      for r in fs:
          if not pred(r):
              nxt = next((t for t in runs if t >= r["ts"]), None)
              if nxt:
                  batch_lat.append(nxt - r["ts"])
      p = lambda L, q: round(sorted(L)[int(q * (len(L) - 1))] / 60, 1) if L else None
      print(f"\n{name}\n  wake rows {len(wake_ts)}; runs by day {dict(sorted(per.items()))}; total {len(runs)}")
      print(f"  wake row to run start (min): median {p(lat, .5)}, p90 {p(lat, .9)}")
      print(f"  same, only rows with no run in the previous gap ({len(quiet)} rows): median {p(quiet, .5)}, p90 {p(quiet, .9)}")
      print(f"  batch-only row to next run (min): median {p(batch_lat, .5)}, p90 {p(batch_lat, .9)}")
