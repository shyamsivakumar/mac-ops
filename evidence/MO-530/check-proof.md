# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `a959471b1f1d4d42d156bbef962c69b51c661ed8`
Working tree clean when the checks ran: yes

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: coordinator/overnight/lane_driver.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/lane_driver.py` | passed |  |
| python syntax: coordinator/overnight/selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/selftest.py` | passed |  |
| python syntax: evidence/MO-530/probes.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evidence/MO-530/probes.py` | passed |  |
| python syntax: runtime/agents/deny-merge-guard.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' runtime/agents/deny-merge-guard.py` | passed |  |
| python syntax: scripts/install_deny_rules.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/install_deny_rules.py` | passed |  |
| python syntax: tests/test_install_deny_rules.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_install_deny_rules.py` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-fhyhxgsh -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-fhyhxgsh/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_install_deny_rules | `python3 -m unittest tests.test_install_deny_rules` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.
