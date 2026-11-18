# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `6b49b574b50d01eba04ea16d9752e352a2237bd4`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | failed | Command '['/Applications/Xcode.app/Contents/Developer/usr/bin/python3', 'coordinator/overnight/overnight', 'selftest']' returned non-zero exit status 1. |
| python syntax: coordinator/overnight/lane_driver.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/lane_driver.py` | not run | an earlier check failed |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-h30a4bgk -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-h30a4bgk/states -config HeavyQueue.cfg HeavyQueue.tla` | not run | an earlier check failed |
| heavy help | `python3 heavy.py --help` | not run | an earlier check failed |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Literal option repair: preserve original option strings and normalize only recommendation matching.

Additional checks: `node --input-type=module` literal src/**/*.js assertion probe passed; `node --check coordinator/mods/cockpit/asks.js` passed; `git diff --check` passed.

Device, handset, live-service and live-board checks: not run, waived by Shyam 2026-11-14. Full suite not rerun; prior seven failures remain unresolved. Required repository check failed in overnight selftest with undefined thread_builder. No checks weakened. Deslop assessment: no additional cleanup warranted. Comment diff review: no comments added.
