# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `475e42c7a11ff91b9eae23cdba26256060726a08`
Working tree clean when the checks ran: yes
Run result: failed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: session_traces/__main__.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' session_traces/__main__.py` | passed |  |
| python syntax: session_traces/cost_report.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' session_traces/cost_report.py` | passed |  |
| python syntax: tests/test_cost_report.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_cost_report.py` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/pi/bin/coord-tick` | failed | 1 Ruff findings are not in the baseline; first: session_traces/__main__.py F821 Undefined name `state_root` |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-nfwt2ffl -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-nfwt2ffl/states -config HeavyQueue.cfg HeavyQueue.tla` | not run | an earlier check failed |
| heavy help | `python3 heavy.py --help` | not run | an earlier check failed |
| tests: tests.test_cost_report | `python3 -m unittest tests.test_cost_report` | not run | an earlier check failed |
| tests: tests.test_session_traces | `python3 -m unittest tests.test_session_traces` | not run | an earlier check failed |
| tests: tests.test_session_traces_fallback | `python3 -m unittest tests.test_session_traces_fallback` | not run | an earlier check failed |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
