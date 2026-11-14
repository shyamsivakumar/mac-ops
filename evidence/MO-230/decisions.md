# MO-230 decisions

Run id: `ticket:shyamsivakumar/mac-ops#212:a2`. Refs #212.

## What landed

The live count in `coordinator/bin/coordq` no longer counts the in-session
review sub-agents that a running task starts.

- `coordinator/bin/coordq`: `live()` calls `t3_thread_list` with
  `"includeSubagents": False`.
- `evidence/MO-230/decisions.md`: this file.

The one-line call change landed in commit `8bb45dec8164e62bb1953d59c87ffb333e7a86d5`
("Count task threads only in the coordq live total (Refs #212)", PR #214).
Attempt 2 of this run re-verified it, ran the gate, and recorded the proof.

Nothing else changed. The cap value stays 6, the queue order in `drain()` is
untouched, no existing test or check was edited or weakened, and no test file
was added: the standing rule forbids one, so the proof below is the real
`coordq status` and `t3mcp call t3_thread_list` output taken while a sub-agent
was running.

## Why

`live()` called `t3_thread_list` with no `includeSubagents` flag, so the count
included the review sub-agent a builder starts ("Act as the review sub-agent
..."). Each builder with a reviewer took two of the six slots, so only three or
four tasks ran at once. Shyam asked on 2026-11-13 12:33 PT: "and why only 3/6".

`wait_until_counted()` reads its count through `live()`, and `drain()` and the
status output do the same, so the single call site covers all three.

## Proof

Taken at 2026-11-13 13:22 PT, while the in-session sub-agent "MO-230 proof
sleeper" was running. The sleeper is a child of this task thread, so it is a
sub-agent row in `t3_thread_list` and not a task thread.

`coordq status`:

```
{"cap": 6, "live": 6, "queued": 20, "failed": [], "stuck": []}
```

`t3mcp call t3_thread_list '{"allProjects":true,"limit":1,"statuses":["running","starting","preparing","queued"],"includeSubagents":false}'`:

```
total = 6
```

`t3mcp call t3_thread_list '{"allProjects":true,"limit":50,"statuses":["running","starting","preparing","queued"]}'`
(the same call without the flag, so sub-agents are included):

```
total = 7
  running | task     | MO-230 · coordq cap counts task threads, not their revi
  running | SUBAGENT | MO-230 proof sleeper
  running | task     | FFBT-35 · Inventory approved current-news and development so
  running | task     | MO-1000 · Dispatcher refills empty slots from the board
  running | task     | FFBT-23 · Observe authoritative snake-draft capability
  running | task     | FFBT-24 · Verify request-driven Fantrax live evidence
  running | task     | STS-2 · Learn by heart button on a saved verse
```

`coordq status` live (6) equals the `includeSubagents: false` total (6) while a
sub-agent is running. The old count would have read 7.

## Gate

The Opus gate reviewer read the diff of `8bb45de` and returned:

```
VERDICT: PASS
```

Its findings: the diff is exactly the intended call change (2 insertions, 1
deletion, one file), `cap()` and the queue order in `drain()` are untouched, no
test was weakened, `t3_thread_list` appears only once in `coordq` so `live()`,
`wait_until_counted()`, `drain()` and the status output all exclude sub-agent
threads, and `live()` still returns an integer on success and `None` on
failure, so the cap logic is unchanged.

It noted one consequence that is correct as designed: `wait_until_counted()`
waits for the count to rise, so a dispatch that creates a sub-agent thread
rather than a task thread waits out its 10 attempts instead of returning
early. Normal launches create task threads, which do raise the count.

## Check

`~/.local/bin/heavy --review python3 scripts/mac_ops_fast_check.py` ends with:

```
fast-check: passed; selected checks are not the full suite
```
