# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Host: Shyams-MacBook-Pro.local
Checked commit: `129f2f9d1ffb4c1282fa50bb2a23402d6361f5f4`
Working tree clean when the checks ran: yes
Run result: failed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | failed | Command '['/opt/homebrew/opt/python@3.14/bin/python3.14', 'coordinator/overnight/overnight', 'selftest']' returned non-zero exit status 1. |
| test isolation: no live gh call or log row | `python3 -m unittest; python3 coordinator/overnight/overnight selftest` | not run | an earlier check failed |
| python syntax: coordinator/overnight/selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/selftest.py` | not run | an earlier check failed |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/bin/scorecard coordinator/pi/bin/coord-tick` | not run | an earlier check failed |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | not run | an earlier check failed |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/private/var/folders/4d/l9996sv53p7dl4l5x5y0skhc0000gn/T/mac-ops-test/heavy-queue-tlc-oxvy78ng -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /private/var/folders/4d/l9996sv53p7dl4l5x5y0skhc0000gn/T/mac-ops-test/heavy-queue-tlc-oxvy78ng/states -config HeavyQueue.cfg HeavyQueue.tla` | not run | an earlier check failed |
| heavy help | `python3 heavy.py --help` | not run | an earlier check failed |
| tests: tests.test_answer_format | `python3 -m unittest tests.test_answer_format` | not run | an earlier check failed |
| tests: tests.test_coordq_action_key | `python3 -m unittest tests.test_coordq_action_key` | not run | an earlier check failed |
| tests: tests.test_coordq_capacity | `python3 -m unittest tests.test_coordq_capacity` | not run | an earlier check failed |
| tests: tests.test_coordq_message_dedupe | `python3 -m unittest tests.test_coordq_message_dedupe` | not run | an earlier check failed |
| tests: tests.test_gate_fast_forward | `python3 -m unittest tests.test_gate_fast_forward` | not run | an earlier check failed |
| tests: tests.test_gatekeep_backstop_reviewer | `python3 -m unittest tests.test_gatekeep_backstop_reviewer` | not run | an earlier check failed |
| tests: tests.test_gatekeep_retry_limit | `python3 -m unittest tests.test_gatekeep_retry_limit` | not run | an earlier check failed |
| tests: tests.test_lane_duplicate_suppression | `python3 -m unittest tests.test_lane_duplicate_suppression` | not run | an earlier check failed |
| tests: tests.test_prompt_paths | `python3 -m unittest tests.test_prompt_paths` | not run | an earlier check failed |
| tests: tests.test_reviewer_vendor_split | `python3 -m unittest tests.test_reviewer_vendor_split` | not run | an earlier check failed |
| tests: tests.test_tick_external_call_bounds | `python3 -m unittest tests.test_tick_external_call_bounds` | not run | an earlier check failed |
| tests: tests.test_ticket_gate_live | `python3 -m unittest tests.test_ticket_gate_live` | not run | an earlier check failed |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
