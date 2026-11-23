# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Host: Shyams-MacBook-Pro.local
Checked commit: `7a3321cd0fa2afb8880f2a1c9479166bba31c750`
Working tree clean when the checks ran: yes
Run result: failed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| test isolation: no live gh call or log row | `python3 -m unittest; python3 coordinator/overnight/overnight selftest` | passed | gh-usage rows for mac-ops-test 0, skips.log lines 0, unchanged after the run; gh-usage lines in total 0 -> 0; both entry points installed the fake `gh` and `t3mcp` themselves; no call the fake `gh` refused; the isolation tests passed; 702 tests ran (unittest exited 0, selftest exited 0) |
| python syntax: coordinator/evals/hillclimb/arms/plain_agent.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/evals/hillclimb/arms/plain_agent.py` | passed |  |
| python syntax: coordinator/evals/hillclimb/build_labels.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/evals/hillclimb/build_labels.py` | passed |  |
| python syntax: coordinator/evals/hillclimb/burst.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/evals/hillclimb/burst.py` | passed |  |
| python syntax: coordinator/evals/hillclimb/daily3.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/evals/hillclimb/daily3.py` | passed |  |
| python syntax: install_coordinator.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' install_coordinator.py` | passed |  |
| python syntax: tests/test_hillclimb_scripts.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_hillclimb_scripts.py` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/bin/scorecard coordinator/pi/bin/coord-tick` | failed | 1 Ruff findings are not in the baseline; first: coordinator/evals/hillclimb/build_labels.py B904 Within an `except` clause, raise exceptions with `raise ... from err` or `raise ... from None` to distinguish them from errors in exception handling |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | not run | an earlier check failed |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/private/var/folders/4d/l9996sv53p7dl4l5x5y0skhc0000gn/T/mac-ops-test/heavy-queue-tlc-9ke3yzun -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /private/var/folders/4d/l9996sv53p7dl4l5x5y0skhc0000gn/T/mac-ops-test/heavy-queue-tlc-9ke3yzun/states -config HeavyQueue.cfg HeavyQueue.tla` | not run | an earlier check failed |
| heavy help | `python3 heavy.py --help` | not run | an earlier check failed |
| tests: tests.test_hillclimb_scripts | `python3 -m unittest tests.test_hillclimb_scripts` | not run | an earlier check failed |
| tests: tests.test_install_coordinator | `python3 -m unittest tests.test_install_coordinator` | not run | an earlier check failed |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
