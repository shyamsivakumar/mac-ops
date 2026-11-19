# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `357d8861a5f0f00dc4544997f9e7977f14969a36`
Working tree clean when the checks ran: no
Run result: failed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: scripts/bot1_rollback_dry_run.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/bot1_rollback_dry_run.py` | passed |  |
| python syntax: tests/test_bot1_rollback_dry_run.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_bot1_rollback_dry_run.py` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/pi/bin/coord-tick` | passed | 86 findings, all in the baseline |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-ire0fkfz -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-ire0fkfz/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_bot1_rollback_dry_run | `python3 -m unittest tests.test_bot1_rollback_dry_run` | failed | Command '['/Applications/Xcode.app/Contents/Developer/usr/bin/python3', '-m', 'unittest', 'tests.test_bot1_rollback_dry_run']' returned non-zero exit status 1. |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.

Device, handset and live-service testing: waived by Shyam on 2026-11-14; not run.
