# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `1957da311f05579cc851b9ab904f4033b11634c5`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: board_governor.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' board_governor.py` | passed |  |
| python syntax: coordinator/bin/gate_policy.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/gate_policy.py` | passed |  |
| python syntax: coordinator/bin/proof_file.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/proof_file.py` | passed |  |
| python syntax: coordinator/overnight/lane_driver.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/lane_driver.py` | passed |  |
| python syntax: heavy.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' heavy.py` | passed |  |
| python syntax: scripts/mac_ops_fast_check.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/mac_ops_fast_check.py` | passed |  |
| python syntax: tests/test_check_proof.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_check_proof.py` | passed |  |
| python syntax: tests/test_heavy_host_headroom.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_heavy_host_headroom.py` | passed |  |
| python syntax: tests/test_heavy_ios_admission.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_heavy_ios_admission.py` | passed |  |
| python syntax: tests/test_install_coordinator.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_install_coordinator.py` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-_d0ywdxa -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-_d0ywdxa/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_agent_heavy_wait_pause | `python3 -m unittest tests.test_agent_heavy_wait_pause` | passed |  |
| tests: tests.test_check_proof | `python3 -m unittest tests.test_check_proof` | passed |  |
| tests: tests.test_heavy_host_headroom | `python3 -m unittest tests.test_heavy_host_headroom` | passed |  |
| tests: tests.test_heavy_ios_admission | `python3 -m unittest tests.test_heavy_ios_admission` | passed |  |
| tests: tests.test_heavy_review_slots | `python3 -m unittest tests.test_heavy_review_slots` | passed |  |
| tests: tests.test_install_coordinator | `python3 -m unittest tests.test_install_coordinator` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.
