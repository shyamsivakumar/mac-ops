# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Host: Shyams-MacBook-Pro.local
Checked commit: `0f722440c04dc60117e0cad2b25bb85923218659`
Working tree clean when the checks ran: yes
Run result: passed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| test isolation: no live gh call or log row | `python3 -m unittest; python3 coordinator/overnight/overnight selftest` | passed | gh-usage rows for mac-ops-test 0, skips.log lines 0, unchanged after the run; gh-usage lines in total 0 -> 0; both entry points installed the fake `gh` and `t3mcp` themselves; no call the fake `gh` refused; the isolation tests passed; 699 tests ran (unittest exited 0, selftest exited 0) |
| python syntax: coordinator/evals/hillclimb/arms/plain_agent.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/evals/hillclimb/arms/plain_agent.py` | passed |  |
| python syntax: coordinator/evals/hillclimb/build_labels.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/evals/hillclimb/build_labels.py` | passed |  |
| python syntax: coordinator/evals/hillclimb/burst.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/evals/hillclimb/burst.py` | passed |  |
| python syntax: coordinator/evals/hillclimb/daily3.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/evals/hillclimb/daily3.py` | passed |  |
| python syntax: install_coordinator.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' install_coordinator.py` | passed |  |
| python syntax: tests/test_hillclimb_scripts.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_hillclimb_scripts.py` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/bin/scorecard coordinator/pi/bin/coord-tick` | passed | 76 findings, all in the baseline |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | passed | 1 modules, no issues |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/private/var/folders/4d/l9996sv53p7dl4l5x5y0skhc0000gn/T/mac-ops-test/heavy-queue-tlc-fknj7amj -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /private/var/folders/4d/l9996sv53p7dl4l5x5y0skhc0000gn/T/mac-ops-test/heavy-queue-tlc-fknj7amj/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_hillclimb_scripts | `python3 -m unittest tests.test_hillclimb_scripts` | passed |  |
| tests: tests.test_install_coordinator | `python3 -m unittest tests.test_install_coordinator` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
