# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Host: Shyams-M4.local
Checked commit: `0c7e462c3726cb1068480d3a7bc8acf19290020f`
Working tree clean when the checks ran: yes
Run result: passed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| installed selftest | `installed_selftest(ROOT)` | passed | exit 0, 38 PASS |
| test isolation: no live gh call or log row | `python3 -m unittest; python3 coordinator/overnight/overnight selftest` | passed | gh-usage rows for mac-ops-test 0, skips.log lines 0, unchanged after the run; gh-usage lines in total 18551 -> 18718; both entry points installed the fake `gh` and `t3mcp` themselves; no call the fake `gh` refused; the isolation tests passed; 742 tests ran (unittest exited 0, selftest exited 0) |
| python syntax: tests/test_ticket_section_headings.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_ticket_section_headings.py` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/bin/scorecard coordinator/pi/bin/coord-tick` | passed | 75 findings, all in the baseline |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | passed | 1 modules, no issues |
| finding rules | `check_finding_rules(changed files)` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/mac-ops-test/heavy-queue-tlc-5tfc212i -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/mac-ops-test/heavy-queue-tlc-5tfc212i/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_answer_format | `python3 -m unittest tests.test_answer_format` | passed |  |
| tests: tests.test_close_check | `python3 -m unittest tests.test_close_check` | passed |  |
| tests: tests.test_prompt_paths | `python3 -m unittest tests.test_prompt_paths` | passed |  |
| tests: tests.test_ticket_gate_live | `python3 -m unittest tests.test_ticket_gate_live` | passed |  |
| tests: tests.test_ticket_section_headings | `python3 -m unittest tests.test_ticket_section_headings` | passed |  |
| tests: tests.test_ticket_text_blockers | `python3 -m unittest tests.test_ticket_text_blockers` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
