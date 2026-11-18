# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `dd8b038064a0a5c17946408a3a8b3f34097d2c9e`
Working tree clean when the checks ran: yes

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: coordinator/bin/answer_format.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/answer_format.py` | passed |  |
| python syntax: coordinator/bin/gate_policy.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/gate_policy.py` | passed |  |
| python syntax: tests/test_answer_format.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_answer_format.py` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-pf1h1wz7 -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-pf1h1wz7/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_answer_format | `python3 -m unittest tests.test_answer_format` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Scope review: the diff against origin/main contains only five cockpit JavaScript files and this receipt. Builder fallback, provider-health and overnight dispatch files have no diff.
In-session review: no critical or major finding in the remaining scope; choose suppresses duplicate pending sends and clears its guard in finally. No cleanup or comment changes were needed.
JavaScript syntax: passed, node --check coordinator/mods/cockpit/main.js.
Diff whitespace: passed, git diff --check.
Full suite: failed, python3 -m unittest discover -s tests; 390 tests, seven failures. No tests or checks were weakened.
Device, handset, live-service and live-board checks: not run, waived by Shyam on 2026-11-14.
Individual prior Sonnet findings were unavailable and remain unverified.
