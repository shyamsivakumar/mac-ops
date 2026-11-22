# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Host: Shyams-M4.local
Checked commit: `6af78439274bb209cd1a39bdffb2e2c4ed819633`
Working tree clean when the checks ran: yes
Run result: passed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| test isolation: no live gh call or log row | `python3 -m unittest; python3 coordinator/overnight/overnight selftest` | passed | gh-usage rows for mac-ops-test 0, skips.log lines 0, unchanged after the run; gh-usage lines in total 19210 -> 19347; both entry points installed the fake `gh` and `t3mcp` themselves; no call the fake `gh` refused; the isolation tests passed; 694 tests ran (unittest exited 0, selftest exited 0) |
| python syntax: coordinator/bin/scorecard | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/scorecard` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/bin/scorecard coordinator/pi/bin/coord-tick` | passed | 76 findings, all in the baseline |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | passed | 1 modules, no issues |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/mac-ops-test/heavy-queue-tlc-bpwpxr6m -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/mac-ops-test/heavy-queue-tlc-bpwpxr6m/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
## Scorecard dollars distribution on 2026-11-21 (real journal, receipts, T3 database, pi rates; read-only)

Command, both runs: `python3 coordinator/bin/scorecard --date 2026-11-21 --no-github --out-dir <tmp>`

Before, scorecard at `74214bca` (the gate head):

```
  ticket_dollars: {"dollars":{"total":null,"median":null,"p90":null,"tickets":0},"list_dollars":{"total":null,"median":null,"p90":null,"tickets":0},"tokens":{"total":1041390986,"median":11532119,"p90":44944772,"tickets":47},"unpriced_threads":152}
```

After, scorecard at `6af78439`:

```
  ticket_dollars: {"dollars":{"total":0.0,"median":0.0,"p90":0.0,"tickets":47},"list_dollars":{"total":null,"median":null,"p90":null,"tickets":0},"tokens":{"total":1041390986,"median":11532119,"p90":44944772,"tickets":47},"unpriced_threads":152}
```

Billed tickets go from 0 to 47 and the total from null to 0.0: the 47 tickets
with observed usage on a flat plan now count as billed at zero instead of
being dropped. `list_dollars`, `tokens` and `unpriced_threads` are unchanged.

Mixed-plan check, `ticket_costs` over all 738 receipt tickets (journal rows
empty), after the fix: `{"dollars": {"total": 151.4, "median": 0.08, "p90": 0.6,
"tickets": 475}, ...}`. Zero-dollar tickets are now inside the median and p90
instead of being excluded.
