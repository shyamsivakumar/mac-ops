# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `327914312803c0ffbdd2eaef5012037107d89336`
Working tree clean when the checks ran: yes
Run result: passed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| test isolation: no live gh call or log row | `python3 -m unittest; python3 coordinator/overnight/overnight selftest` | passed | gh-usage rows for mac-ops-test 0, skips.log lines 0, unchanged after the run; gh-usage lines in total 1955 -> 2185; both entry points installed the fake `gh` themselves; no call the fake `gh` refused; the isolation tests passed; 675 tests ran (unittest exited 1, selftest exited 0) |
| python syntax: coordinator/bin/hourly_selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/hourly_selftest.py` | passed |  |
| python syntax: coordinator/overnight/selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/selftest.py` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/bin/scorecard coordinator/pi/bin/coord-tick` | passed | 76 findings, all in the baseline |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | passed | 1 modules, no issues |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-2ajn0wd8 -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-2ajn0wd8/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_answer_format | `python3 -m unittest tests.test_answer_format` | passed |  |
| tests: tests.test_coordq_action_key | `python3 -m unittest tests.test_coordq_action_key` | passed |  |
| tests: tests.test_coordq_capacity | `python3 -m unittest tests.test_coordq_capacity` | passed |  |
| tests: tests.test_coordq_message_dedupe | `python3 -m unittest tests.test_coordq_message_dedupe` | passed |  |
| tests: tests.test_gate_fast_forward | `python3 -m unittest tests.test_gate_fast_forward` | passed |  |
| tests: tests.test_gatekeep_backstop_reviewer | `python3 -m unittest tests.test_gatekeep_backstop_reviewer` | passed |  |
| tests: tests.test_gatekeep_retry_limit | `python3 -m unittest tests.test_gatekeep_retry_limit` | passed |  |
| tests: tests.test_lane_duplicate_suppression | `python3 -m unittest tests.test_lane_duplicate_suppression` | passed |  |
| tests: tests.test_prompt_paths | `python3 -m unittest tests.test_prompt_paths` | passed |  |
| tests: tests.test_reviewer_vendor_split | `python3 -m unittest tests.test_reviewer_vendor_split` | passed |  |
| tests: tests.test_tick_external_call_bounds | `python3 -m unittest tests.test_tick_external_call_bounds` | passed |  |
| tests: tests.test_ticket_gate_live | `python3 -m unittest tests.test_ticket_gate_live` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
