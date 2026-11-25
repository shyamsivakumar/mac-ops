# MO-979 runs

## Ticket proof

Command (from the ticket, `HOME=/nonexistent`, repo root):

```text
HOME=/nonexistent python3 -c "import runpy,sys;sys.path.insert(0,'coordinator/bin');s=runpy.run_path('coordinator/bin/tick_health.py',run_name='p');h={'ts':0,'event':'merge_held','repo':'o/r','pr':7,'head':'a'*40,'data':{'reason':'loop code hold'}};f=lambda v:s['held_alarm']([h],now=7*3600,hours=6,state=lambda *a:v);assert 'o/r#7' in f('live') and not f('stale') and 'not read' in f('unknown')"
```

Red on origin/main (a5993dc6, `git archive` copy), exit 1:

```text
TypeError: held_alarm() got an unexpected keyword argument 'state'
```

Green on the branch head, exit 0 (no output).

## Selftest eval `stop-rules`

Cases added to the existing eval in `coordinator/overnight/selftest.py`, run alone with temp `COORD_JOURNAL_DIR` and `COORDQ_DIR`.
Branch: `ok`. The new selftest on origin/main code fails with
`TypeError: held_alarm() got an unexpected keyword argument 'state'`.
`gh_gateway.run` is replaced by a fake in every case; no real GitHub read.

Covered: live, stale and unknown for `held_alarm` and `idle_alarm`; the callable called only for a PR that would alarm; idle drops only stale PRs and returns nothing when all are stale; a FAIL row with `head` None or missing passes `None` and does not crash; open on the same head (also upper-case), open on another head, closed, merged-closed; answers that are not JSON, a list, `{}`, no head, empty head, odd state, nonzero exit (404), `None` stdout; `ApiBudgetExhausted`, `TimeoutExpired`, `FileNotFoundError`, `KeyError`, `ValueError` from the gateway; invalid repo names (`../x/y`, `a/b/../c`, spaces, `;`, trailing newline, empty, `None`, int) never reach `gh_gateway.run`; a bool PR number; one read per PR per reader (three asks, one read); the 10-read cap (9 live, 3 unknown with 12 asked after the first, 10 reads); the 30 second deadline with a fake clock (third PR unknown, read timeouts 10 and 10); the argv is a list `["gh","api","repos/o/r/pulls/7"]` with `limit=floor()`; the switch off with `pr_state_reader` patched to raise.

## Where the limits sit

`gh_gateway.run(..., timeout=T, limit=...)` runs the quota probe inside `T`: the probe gets `T // 2` and the read gets what is left. So the probe counts toward each read's 10 seconds and toward the 30 second total, which `pr_state_reader` computes as `min(10, 30 - elapsed)` before each read.
Reads happen only for a PR that would alarm, so a quiet `coordq status` makes none. Worst case is 30 seconds on top of the other `tick_alarm` parts, and only with the switch on.

## Cache and a just-merged PR

`pulls/<n>` is cacheable in `gh_gateway` with `LIST_TTL` = 120 s. A PR merged within 2 minutes of a cached read can read as `live` once more, and the next call after the entry expires drops it. This is the same window `coordq` accepts for its own reads.

## Replay over the live journal, read-only (25 Nov)

Script: `evidence/MO-979/replay.py`. It opens the live journal and `tick.log` for reading only; the only write is the gateway's own usage log and cache. The journal has no row for any PR that is open now, so the "kept" case adds one in-memory hold for the open PR strategy-replay-workbench#2558 at its real head. Nothing is written to the journal.

```text
held_alarm over the journal plus one in-memory hold on the open PR (the journal has no row for any open PR):
without state:
ALARM: shyamsivakumar/sams-llm-wiki#244 held 71.0 h (prompt hold), no merge since
ALARM: shyamsivakumar/strategy-replay-workbench#2558 held 7.0 h (loop code hold), no merge since
with pr_state:
ALARM: shyamsivakumar/strategy-replay-workbench#2558 held 7.0 h (loop code hold), no merge since

idle_alarm as of 24 Nov 02:15 local, journal rows and finished ticks up to then:
without state:
ALARM: 8 finished ticks did nothing; gate FAIL waiting on shyamsivakumar/sams-llm-wiki#254
with pr_state:
  (none)

reads:
  shyamsivakumar/sams-llm-wiki#244 head=bc583010 -> stale
  shyamsivakumar/strategy-replay-workbench#2558 head=0908d67d -> live
  shyamsivakumar/sams-llm-wiki#254 head=763f3538 -> stale
```
