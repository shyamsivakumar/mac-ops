# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `05d3b0af0f70ae328219d2fa3a627374f0806892`
Working tree clean when the checks ran: yes
Run result: passed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: coordinator/bin/journal.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/journal.py` | passed |  |
| python syntax: coordinator/overnight/alarms.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/alarms.py` | passed |  |
| python syntax: coordinator/overnight/lane_driver.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/lane_driver.py` | passed |  |
| python syntax: coordinator/overnight/selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/selftest.py` | passed |  |
| python syntax: scripts/mac_ops_fast_check.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/mac_ops_fast_check.py` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/pi/bin/coord-tick` | passed | 76 findings, all in the baseline |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | passed | 1 modules, no issues |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-wlfjp4py -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-wlfjp4py/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_alarm_panel | `python3 -m unittest tests.test_alarm_panel` | passed |  |
| tests: tests.test_lane_decisions_board | `python3 -m unittest tests.test_lane_decisions_board` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.

## Journal runs

Code head these runs used: `05d3b0af0f70ae328219d2fa3a627374f0806892`. The check above ran on the same head.

### Acceptance 2: concurrency, 8 processes x 500 emits

```
for i in 1..8: COORD_JOURNAL_DIR=$D python3 -c 'for n in range(i*1000, i*1000+500): journal.emit("conc", "coordq", repo="r", item=n, pad="x"*300)' &  (then wait)
files: events-2026-11.jsonl
lines:     4000
parsed: 4000 lines, 0 missing a common key, 4000 distinct item values
```

### Acceptance 3: real paths, COORD_JOURNAL_DIR in a temp dir

A queue dir of its own and a stub t3mcp (two live threads) stand in for the live queue, so no real thread is launched.
```
$ coordq start {"threadId":"t-x","message":"<omitted>"} --title sandbox   # enqueued, then drain: slots, launched
started #1
$ same start again   # duplicate refusal
refused: duplicate message 'sandbox' for t-x: already started as coordq #1
$ coordq start ... --tool t3_thread_bogus   # tool refusal
refused: tool 't3_thread_bogus' is not dispatchable. Accepted tools: t3_thread_launch, t3_thread_send
$ coordq dispatch   # drain again, slot triple unchanged: no slots line
$ coordq status
{"cap": 6, "live": 2, "reserved": {"1": 1795137375.463874}, "queued": 0, "failed": [], "stuck": [], "tickAlarm": ""}
$ wc -l and lines in the journal
       6
{"v":1,"ts":1795137375.3380868,"event":"enqueued","actor":"coordq","repo":null,"ticket":null,"pr":null,"head":null,"thread":"t-x","item":1,"attempt":null,"kind":"other","data":{"tool":"t3_thread_send","taskType":null,"modelSelection":null}}
{"v":1,"ts":1795137375.4636931,"event":"slots","actor":"coordq","repo":null,"ticket":null,"pr":null,"head":null,"thread":null,"item":null,"attempt":null,"kind":null,"data":{"live":2,"reserved":0,"cap":6,"over_cap":false}}
{"v":1,"ts":1795137375.470134,"event":"launched","actor":"coordq","repo":null,"ticket":null,"pr":null,"head":null,"thread":"t-x","item":1,"attempt":null,"kind":"other","data":{"tool":"t3_thread_send","live":2,"reserved":1,"cap":6}}
{"v":1,"ts":1795137375.48283,"event":"slots","actor":"coordq","repo":null,"ticket":null,"pr":null,"head":null,"thread":null,"item":null,"attempt":null,"kind":null,"data":{"live":2,"reserved":1,"cap":6,"over_cap":false}}
{"v":1,"ts":1795137375.539884,"event":"refused","actor":"coordq","repo":null,"ticket":null,"pr":null,"head":null,"thread":"t-x","item":null,"attempt":null,"kind":"other","data":{"tool":"t3_thread_send","reason":"refused: duplicate message 'sandbox' for t-x: already started as coordq #1"}}
{"v":1,"ts":1795137375.591098,"event":"refused","actor":"coordq","repo":null,"ticket":null,"pr":null,"head":null,"thread":"t-x","item":null,"attempt":null,"kind":"other","data":{"tool":"t3_thread_bogus","reason":"refused: tool 't3_thread_bogus' is not dispatchable. Accepted tools: t3_thread_launch, t3_thread_send"}}
```

Read-only ticket command, journal dir empty afterwards:
```
$ COORD_JOURNAL_DIR=$T ticket show shyamsivakumar/mac-ops#688 | head -3
{
 "repo": "shyamsivakumar/mac-ops",
 "number": 688,
journal files written:        0
```

Emits that need a real launch, a real gate or a real merge are not run here. By file and line at this head:

- `coordinator/bin/coordq:105` `    journal.emit("refused", "coordq", thread=args.get("threadId"), tool=tool, reason=message,`
- `coordinator/bin/coordq:114` `    journal.emit(event, "coordq", **row)`
- `coordinator/bin/coordq:123` `    journal.emit("slots", "coordq", live=triple[0], reserved=triple[1], cap=triple[2],`
- `coordinator/bin/coordq:635` `            journal.emit("thread_ended", "coordq", item=int(key.split(":")[0]), thread=thread,`
- `coordinator/bin/coordq:663` `                journal_item("dropped", item, tries=item["attempts"], error=item.get("last_error"))`
- `coordinator/bin/coordq:672` `            journal_item("refused", item, reason=tool_refusal(tool))`
- `coordinator/bin/coordq:797` `            journal_item("launched", item, thread=started_thread(queue, item, reservation) or None,`
- `coordinator/bin/coordq:818` `            journal_item("launch_failed", item, tries=item["attempts"], error=out[:200])`
- `coordinator/bin/coordq:889` `        refuse_start(f"refused: {tool_refusal(tool)}", args, tool)`
- `coordinator/bin/coordq:897` `            refuse_start(refusal, requested, tool)`
- `coordinator/bin/coordq:904` `                refuse_start(f"refused: {e}", args, tool)`
- `coordinator/bin/coordq:919` `                refuse_start(f"refused: the action key {key} is already "`
- `coordinator/bin/coordq:932` `            refuse_start(f"refused: duplicate message {title!r} for {target or 'a new thread'}: "`
- `coordinator/bin/coordq:946` `                refuse_start(f"refused: a gate for this head is already recorded as "`
- `coordinator/bin/coordq:950` `        journal.emit("enqueued", "coordq", item=item["id"], thread=args.get("threadId"), tool=tool,`
- `coordinator/bin/coordq:1902` `                journal.emit("gate_queued", "gatekeep", item=item["id"],`
- `coordinator/bin/ticket:512` `    journal.emit("ticket_opened", "ticket", repo=repo, ticket=int(url.rsplit("/", 1)[1]), key=key, labels=labels)`
- `coordinator/bin/ticket:1379` `    journal.emit("ticket_started", "ticket", builder=t["builderAlias"], reviewer=t["reviewerAlias"],`
- `coordinator/bin/ticket:1789` `        journal.emit("close_failed", "ticket", repo=repo, ticket=number, pr=a.pr, head=a.head,`
- `coordinator/bin/ticket:1794` `    journal.emit("ticket_closed", "ticket", repo=repo, ticket=number, pr=a.pr, head=a.head,`
- `coordinator/bin/ticket:1820` `    journal.emit("ticket_abandoned", "ticket", repo=repo, ticket=n)`
- `coordinator/overnight/lane_driver.py:410` `        journal.emit(event, "lane", repo=repo, pr=number, head=head, **fields)`
- `coordinator/overnight/lane_driver.py:416` `        journal_event(event, repo, number, head, **fields)`
- `coordinator/overnight/lane_driver.py:420` `    journal_once("gate_verdict", repo, number, head, ledger,`
- `coordinator/overnight/lane_driver.py:635` `        journal.emit("fix_sent", "lane", thread=thread_id, model=fixer["selection"]["model"],`
- `coordinator/overnight/lane_driver.py:709` `        journal_event("round_cap", repo, number, head, reviews=count)`
- `coordinator/overnight/lane_driver.py:1050` `        journal_event("merge_held", repo, number, head,`
- `coordinator/overnight/lane_driver.py:1067` `        journal_event("merge_held", repo, number, head, reason="base moved")`
- `coordinator/overnight/lane_driver.py:1110` `            journal_once("merge_held", repo, number, head, ledger,`
- `coordinator/overnight/lane_driver.py:1118` `        journal_once("merge_held", repo, number, head, ledger,`
- `coordinator/overnight/lane_driver.py:1132` `    journal_event("merged", repo, number, head, thread=gate["threadId"], base=base)`
- `coordinator/overnight/lane_driver.py:1200` `        journal_event("merged_outside_lane", repo, number, head,`
- `coordinator/overnight/lane_driver.py:1232` `        journal_verdict(repo, number, head, verdict, gate, ledger)`
- `coordinator/overnight/lane_driver.py:1234` `            journal_once("merge_held", repo, number, head, ledger,`
- `coordinator/overnight/lane_driver.py:1317` `        journal_verdict(repo, number, head, verdict, gate, ledger)`
- `coordinator/overnight/lane_driver.py:1319` `        journal_once("merge_held", repo, number, head, ledger,`
- `coordinator/overnight/alarms.py:368` `        journal.emit(event[0], "alarms", alarm=alarm_id, board=str(path), group=event[1])`
- `coordinator/overnight/alarms.py:384` `    journal_alarm(path, alarm_id, event)`
- `coordinator/overnight/alarms.py:416` `        journal_alarm(path, alarm_id, event)`

### Acceptance 4: parse_request_id on real ids from dispatch-receipts.json

```
ticket:shyamsivakumar/strategy-replay-workbench#902:a1
  -> {"repo": "shyamsivakumar/strategy-replay-workbench", "ticket": 902, "pr": null, "head": null, "attempt": 1, "kind": "build", "data": {}}
gate:shyamsivakumar/mac-ops#150:366d395bf5628ade62bd5ccf5c0324a78ca11c06
  -> {"repo": "shyamsivakumar/mac-ops", "ticket": null, "pr": 150, "head": "366d395bf5628ade62bd5ccf5c0324a78ca11c06", "attempt": null, "kind": "gate", "data": {}}
gate:digitized/Concerning#59:121dbc981e50b56ed3d1acf4cae323633fad5fd6:lane
  -> {"repo": "digitized/Concerning", "ticket": null, "pr": 59, "head": "121dbc981e50b56ed3d1acf4cae323633fad5fd6", "attempt": null, "kind": "gate", "data": {"suffix": "lane"}}
fix:shyamsivakumar/mac-ops#545:496a1d732adcf32d23146e3d94bc417580ec41b1
  -> {"repo": "shyamsivakumar/mac-ops", "ticket": null, "pr": 545, "head": "496a1d732adcf32d23146e3d94bc417580ec41b1", "attempt": null, "kind": "fix", "data": {}}
continue:shyamsivakumar/mac-ops#545:496a1d732adcf32d23146e3d94bc417580ec41b1
  -> {"repo": "shyamsivakumar/mac-ops", "ticket": null, "pr": 545, "head": "496a1d732adcf32d23146e3d94bc417580ec41b1", "attempt": null, "kind": "continue", "data": {}}
crit:one-lane:Sol
  -> {"repo": null, "ticket": null, "pr": null, "head": null, "attempt": null, "kind": "other", "data": {"request": "crit:one-lane:Sol"}}
```

### Existing tests that load coordq and ticket, run for the reason the fast check does not select them

The fast check selects tests by changed .py file, and coordq and ticket have no .py suffix. The twelve test modules that load them ran on 163bced (the code before the last commit, which changed only the selftest and the check script) and on da70cd7d (`git archive`): both give 298 tests, 13 failures, 3 errors, the same 16 names. The failures are in origin/main, not in this diff.
