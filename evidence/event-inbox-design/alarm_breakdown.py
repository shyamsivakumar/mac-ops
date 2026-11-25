"""Break the journal's alarm raises down by alarm name and family. Read-only.

Usage: python3 alarm_breakdown.py [journal.jsonl]
"""
import collections
import re
import sys

sys.argv = sys.argv[:1] + sys.argv[1:2]
src = open(__file__.replace("alarm_breakdown.py", "replay_wakes.py")).read().split("fs = facts()")[0]
wakes = {}
exec(src, wakes)
facts, rows, URGENT = wakes["facts"], wakes["rows"], wakes["URGENT"]

fs = facts()
raises = collections.Counter()
for r in rows:
    if r["event"] == "alarm_raised":
        raises[(r.get("data") or {}).get("alarm")] += 1
gens = collections.Counter((r.get("data") or {}).get("alarm") for r in fs if r["event"] == "alarm_raised")


def family(name):
    n = (name or "?").replace("shyamsivakumar-strategy-replay-workbench", "SRW")
    return re.sub(r"\d+", "N", n)


fam_raise, fam_gen, fam_names = collections.Counter(), collections.Counter(), collections.defaultdict(set)
for name, n in raises.items():
    f = family(name)
    fam_raise[f] += n
    fam_gen[f] += gens[name]
    fam_names[f].add(name)

urgent_rows = [r for r in fs if r["event"] in URGENT]
by_kind = collections.Counter(r["event"] for r in urgent_rows)
print(f"wake rows in variant B: {len(urgent_rows)}  " + ", ".join(f"{k} {v}" for k, v in by_kind.most_common()))
alarm_rows = by_kind["alarm_raised"]
print(f"alarm rows are {100 * alarm_rows / len(urgent_rows):.0f}% of wake rows; with the close_failed and recut "
      f"events that repeat alarm families, {100 * (alarm_rows + by_kind['close_failed'] + by_kind['recut']) / len(urgent_rows):.0f}%\n")
print(f"{'family':48} {'raise lines':>11} {'generations':>11} {'names':>6}")
for f, n in fam_raise.most_common():
    print(f"{f[:48]:48} {n:>11} {fam_gen[f]:>11} {len(fam_names[f]):>6}")
print("\nTop 10 single alarm names by raise lines (generations in brackets):")
for name, n in raises.most_common(10):
    print(f"  {n:>3} ({gens[name]}) {name}")
