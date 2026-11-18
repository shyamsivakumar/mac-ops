# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `608a8bc5a75cee2bf5308d34e107608e01301fed`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: coordinator/bin/answer_format.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/answer_format.py` | passed |  |
| python syntax: coordinator/bin/gate_policy.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/gate_policy.py` | passed |  |
| python syntax: tests/test_answer_format.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_answer_format.py` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-xkipsb57 -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-xkipsb57/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_answer_format | `python3 -m unittest tests.test_answer_format` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Scope: only cockpit option selection, answer logging and choice guard changes remain against origin/main. Builder fallback, provider health and overnight dispatch changes were removed.

Device, handset, live-service and live-board checks: not run, waived by Shyam on 2026-11-14.
Full suite: failed, 7 failures across 390 tests in the pre-receipt run; all failures are in test_gatekeep_backstop_reviewer. No tests or checks were weakened.
JavaScript syntax: passed, `node --check coordinator/mods/cockpit/main.js`.
Prior individual Sonnet findings were unavailable and remain unverified.
