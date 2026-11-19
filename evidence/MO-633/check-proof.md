# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `4851c32400fb42fb35aadcd8bc0e22b7de0138dd`
Working tree clean when the checks ran: yes
Run result: passed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: evals/harbor/build_tasks.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/build_tasks.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-223/tests/files/tests/test_ticket_text_blockers.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-223/tests/files/tests/test_ticket_text_blockers.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-273/tests/files/tests/test_ticket_gate_live.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-273/tests/files/tests/test_ticket_gate_live.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-312/tests/files/tests/test_gatekeep_retry_limit.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-312/tests/files/tests/test_gatekeep_retry_limit.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-315/tests/files/tests/test_ticket_text_blockers.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-315/tests/files/tests/test_ticket_text_blockers.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-340/tests/files/tests/test_gate_reviewer_quota.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-340/tests/files/tests/test_gate_reviewer_quota.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-486/tests/files/tests/test_tick_external_call_bounds.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-486/tests/files/tests/test_tick_external_call_bounds.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-608/tests/files/tests/test_heavy_review_slots.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-608/tests/files/tests/test_heavy_review_slots.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-618/tests/files/tests/test_prompt_paths.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-618/tests/files/tests/test_prompt_paths.py` | passed |  |
| python syntax: evals/harbor/tasks/mac-ops-619/tests/files/tests/test_prompt_paths.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evals/harbor/tasks/mac-ops-619/tests/files/tests/test_prompt_paths.py` | passed |  |
| python syntax: scripts/mac_ops_fast_check.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/mac_ops_fast_check.py` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-223/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-223/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-223/tests/test.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-223/tests/test.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-273/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-273/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-273/tests/test.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-273/tests/test.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-312/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-312/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-312/tests/test.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-312/tests/test.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-315/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-315/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-315/tests/test.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-315/tests/test.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-340/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-340/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-340/tests/test.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-340/tests/test.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-486/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-486/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-486/tests/test.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-486/tests/test.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-608/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-608/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-608/tests/test.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-608/tests/test.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-618/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-618/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-618/tests/test.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-618/tests/test.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-619/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-619/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/mac-ops-619/tests/test.sh | `/bin/sh -n evals/harbor/tasks/mac-ops-619/tests/test.sh` | passed |  |
| shell syntax: evals/harbor/tasks/srw-1324/solution/solve.sh | `/bin/sh -n evals/harbor/tasks/srw-1324/solution/solve.sh` | passed |  |
| shell syntax: evals/harbor/tasks/srw-1324/tests/test.sh | `/bin/sh -n evals/harbor/tasks/srw-1324/tests/test.sh` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/pi/bin/coord-tick` | passed | 77 findings, all in the baseline |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | passed | 1 modules, no issues |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-xtcq57mn -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-xtcq57mn/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
