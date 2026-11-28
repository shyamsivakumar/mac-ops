# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Host: Shyams-M4.local
Checked commit: `222948972917ec2b336270d4c1eca104bbe61e92`
Working tree clean when the checks ran: no
Run result: passed

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| installed selftest | `installed_selftest(ROOT)` | passed | exit 0, 38 PASS |
| test isolation: no live gh call or log row | `python3 -m unittest; python3 coordinator/overnight/overnight selftest` | passed | gh-usage rows for mac-ops-test 0, skips.log lines 0, unchanged after the run; gh-usage lines in total 25548 -> 25623; both entry points installed the fake `gh` and `t3mcp` themselves; no call the fake `gh` refused; the isolation tests passed; 740 tests ran (unittest exited 0, selftest exited 0) |
| python syntax: runtime/agents/deny-merge-guard.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' runtime/agents/deny-merge-guard.py` | passed |  |
| python syntax: tests/test_install_deny_rules.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_install_deny_rules.py` | passed |  |
| ruff F,B | `uvx ruff@0.14.0 check --select F,B --output-format json --extend-exclude 'evals/harbor/tasks/*/tests/files' . coordinator/overnight/overnight coordinator/bin/coord-watch coordinator/bin/scorecard coordinator/pi/bin/coord-tick` | passed | 75 findings, all in the baseline |
| mypy | `uvx mypy@1.18.2 --strict --follow-imports=silent --ignore-missing-imports --python-version 3.9 board_resources.py` | passed | 1 modules, no issues |
| finding rules | `check_finding_rules(changed files)` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/mac-ops-test/heavy-queue-tlc-ct9tqq2w -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /private/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/mac-ops-test/heavy-queue-tlc-ct9tqq2w/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_install_deny_rules | `python3 -m unittest tests.test_install_deny_rules` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`. A tool that is not on this machine
is recorded as `not run` too, and leaves the run incomplete: the run is
then not a pass.
