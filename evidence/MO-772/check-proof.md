# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Host: Shyams-M4.local
Checked commit: `b1ae972042522a11bc1280da05c7c98c4c7529bc`
Working tree clean when the checks ran: no
Run result: passed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| test isolation: no live gh call or log row | `python3 -m unittest; python3 coordinator/overnight/overnight selftest` | passed | gh-usage rows for mac-ops-test 0, skips.log lines 0, unchanged after the run; gh-usage lines in total 18895 -> 19037; both entry points installed the fake `gh` themselves; no call the fake `gh` refused; the isolation tests passed; 686 tests ran (unittest exited 1, selftest exited 0) |
| python syntax: evals/harbor/build_tasks.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/build_tasks.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-694/tests/files/tests/test_prompt_paths.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-694/tests/files/tests/test_prompt_paths.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-704/tests/files/tests/test_gate_reviewer_quota.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-704/tests/files/tests/test_gate_reviewer_quota.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-704/tests/files/tests/test_gatekeep_backstop_reviewer.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-704/tests/files/tests/test_gatekeep_backstop_reviewer.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-704/tests/files/tests/test_gatekeep_retry_limit.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-704/tests/files/tests/test_gatekeep_retry_limit.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-704/tests/files/tests/test_reviewer_vendor_split.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-704/tests/files/tests/test_reviewer_vendor_split.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-704/tests/files/tests/test_ticket_text_blockers.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-704/tests/files/tests/test_ticket_text_blockers.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-716/tests/files/tests/test_models_block_provider.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-716/tests/files/tests/test_models_block_provider.py` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-694/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-694/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-694/tests/test.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-694/tests/test.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-704/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-704/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-704/tests/test.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-704/tests/test.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-716/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-716/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-716/tests/test.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-716/tests/test.sh` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/bin/scorecard coordinator/pi/bin/coord-tick` | passed | 76 findings, all in the baseline |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | passed | 1 modules, no issues |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-ba58kujb -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-ba58kujb/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
