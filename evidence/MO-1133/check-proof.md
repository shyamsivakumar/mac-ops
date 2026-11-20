# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `2653c248248b4ca83bf07486fca792b687db7a33`
Working tree clean when the checks ran: yes
Run result: passed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| test isolation: no live gh call or log row | `python3 -m unittest; python3 coordinator/overnight/overnight selftest` | passed | gh-usage rows for mac-ops-test 0, skips.log lines 0, unchanged after the run; gh-usage lines in total 14360 -> 14418; both entry points installed the fake `gh` themselves; no call the fake `gh` refused; the isolation tests passed; 679 tests ran (unittest exited 1, selftest exited 0) |
| python syntax: coordinator/bin/hourly_selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/hourly_selftest.py` | passed |  |
| python syntax: coordinator/overnight/selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/selftest.py` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/bin/scorecard coordinator/pi/bin/coord-tick` | passed | 76 findings, all in the baseline |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | passed | 1 modules, no issues |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-xfjbyp7_ -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-xfjbyp7_/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
