import sys, json, time
from pathlib import Path
sys.path.insert(0, "coordinator/bin")
import gh_gateway
import tick_health as t

OPEN_PR = ("shyamsivakumar/strategy-replay-workbench", 2558)
journal = Path.home() / ".local/state/coordinator/journal/events-2026-11.jsonl"
ticks = t.finished_ticks((Path.home() / "Library/Logs/coordinator/tick.log").read_text())
rows = []
with open(journal) as handle:
    for line in handle:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
now = time.time()
idle_now = time.mktime((2026, 11, 24, 2, 15, 0, 0, 0, 0))
seen = []


def spied(state):
    def spy(repo, pr, head):
        verdict = state(repo, pr, head)
        seen.append(f"  {repo}#{pr} head={str(head)[:8]} -> {verdict}")
        return verdict
    return spy


head = json.loads(gh_gateway.run(["gh", "api", f"repos/{OPEN_PR[0]}/pulls/{OPEN_PR[1]}"], timeout=30).stdout)["head"]["sha"]
open_hold = {"ts": now - 7 * 3600, "event": "merge_held", "repo": OPEN_PR[0], "pr": OPEN_PR[1], "head": head, "data": {"reason": "loop code hold"}}
print("held_alarm over the journal plus one in-memory hold on the open PR (the journal has no row for any open PR):")
print("without state:")
print(t.held_alarm(rows + [open_hold], now=now, hours=6))
print("with pr_state:")
print(t.held_alarm(rows + [open_hold], now=now, hours=6, state=spied(t.pr_state_reader())) or "  (none)")
print("\nidle_alarm as of 24 Nov 02:15 local, journal rows and finished ticks up to then:")
vis = [r for r in rows if r["ts"] <= idle_now]
vis_ticks = [x for x in ticks if x <= idle_now]
print("without state:")
print(t.idle_alarm(vis, vis_ticks, now=idle_now, count=8))
print("with pr_state:")
print(t.idle_alarm(vis, vis_ticks, now=idle_now, count=8, state=spied(t.pr_state_reader())) or "  (none)")
print("\nreads:")
print("\n".join(seen))
