# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `1cbbe744b270d7eb379f870200cc1f8ba947a69f`
Working tree clean when the checks ran: no
Run result: passed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: board_resources.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' board_resources.py` | passed |  |
| python syntax: coordinator/bin/gate_bar.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/gate_bar.py` | passed |  |
| python syntax: coordinator/bin/gate_policy.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/gate_policy.py` | passed |  |
| python syntax: coordinator/bin/hourly_selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/hourly_selftest.py` | passed |  |
| python syntax: coordinator/bin/prompt_paths.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/prompt_paths.py` | passed |  |
| python syntax: coordinator/overnight/lane_driver.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/lane_driver.py` | passed |  |
| python syntax: coordinator/overnight/selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/selftest.py` | passed |  |
| python syntax: evidence/MO-543/proof.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evidence/MO-543/proof.py` | passed |  |
| python syntax: scripts/mac_ops_fast_check.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/mac_ops_fast_check.py` | passed |  |
| python syntax: tests/test_check_proof.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_check_proof.py` | passed |  |
| python syntax: tests/test_gate_bar_convergence.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_gate_bar_convergence.py` | passed |  |
| python syntax: tests/test_lane_decisions_board.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_lane_decisions_board.py` | passed |  |
| python syntax: tests/test_prompt_paths.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_prompt_paths.py` | passed |  |
| shell syntax: evals/harbor/install.sh | `/bin/sh -n evals/harbor/install.sh` | passed |  |
| shell syntax: evals/harbor/run-example.sh | `/bin/sh -n evals/harbor/run-example.sh` | passed |  |
| shell syntax: evals/harbor/tasks/example/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/example/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/example/tests/test.sh | `/bin/sh -n evals/harbor/tasks/example/tests/test.sh` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/pi/bin/coord-tick` | passed | 77 findings, all in the baseline |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | passed | 1 modules, no issues |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-3y5tu9iq -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-3y5tu9iq/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_answer_format | `python3 -m unittest tests.test_answer_format` | passed |  |
| tests: tests.test_check_proof | `python3 -m unittest tests.test_check_proof` | passed |  |
| tests: tests.test_gate_bar_convergence | `python3 -m unittest tests.test_gate_bar_convergence` | passed |  |
| tests: tests.test_heavy_host_headroom | `python3 -m unittest tests.test_heavy_host_headroom` | passed |  |
| tests: tests.test_lane_decisions_board | `python3 -m unittest tests.test_lane_decisions_board` | passed |  |
| tests: tests.test_prompt_paths | `python3 -m unittest tests.test_prompt_paths` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
