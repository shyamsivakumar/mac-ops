# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `a8a9761650ae1eb88b7db3c5a58353e985cd42a1`
Working tree clean when the checks ran: yes
Run result: failed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | failed | Command '['/Applications/Xcode.app/Contents/Developer/usr/bin/python3', 'coordinator/overnight/overnight', 'selftest']' returned non-zero exit status 1. |
| test isolation: no live gh call or log row | `python3 -m unittest; python3 coordinator/overnight/overnight selftest` | not run | an earlier check failed |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/bin/scorecard coordinator/pi/bin/coord-tick` | not run | an earlier check failed |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | not run | an earlier check failed |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-08zfwtx1 -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-08zfwtx1/states -config HeavyQueue.cfg HeavyQueue.tla` | not run | an earlier check failed |
| heavy help | `python3 heavy.py --help` | not run | an earlier check failed |
| tests: tests.test_answer_format | `python3 -m unittest tests.test_answer_format` | not run | an earlier check failed |
| tests: tests.test_close_check | `python3 -m unittest tests.test_close_check` | not run | an earlier check failed |
| tests: tests.test_prompt_paths | `python3 -m unittest tests.test_prompt_paths` | not run | an earlier check failed |
| tests: tests.test_ticket_gate_live | `python3 -m unittest tests.test_ticket_gate_live` | not run | an earlier check failed |
| tests: tests.test_ticket_section_headings | `python3 -m unittest tests.test_ticket_section_headings` | not run | an earlier check failed |
| tests: tests.test_ticket_text_blockers | `python3 -m unittest tests.test_ticket_text_blockers` | not run | an earlier check failed |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
