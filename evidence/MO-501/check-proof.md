# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `825e90d56442b72d5b1c166f279f4c552f20325a`
Working tree clean when the checks ran: yes

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `/Applications/Xcode.app/Contents/Developer/usr/bin/python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `/Applications/Xcode.app/Contents/Developer/usr/bin/python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: coordinator/bin/coordq | `/Applications/Xcode.app/Contents/Developer/usr/bin/python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/coordq` | passed |  |
| python syntax: coordinator/bin/gate_policy.py | `/Applications/Xcode.app/Contents/Developer/usr/bin/python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/gate_policy.py` | passed |  |
| python syntax: coordinator/bin/proof_file.py | `/Applications/Xcode.app/Contents/Developer/usr/bin/python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/proof_file.py` | passed |  |
| python syntax: coordinator/bin/ticket | `/Applications/Xcode.app/Contents/Developer/usr/bin/python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/ticket` | passed |  |
| python syntax: coordinator/overnight/lane_driver.py | `/Applications/Xcode.app/Contents/Developer/usr/bin/python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/lane_driver.py` | passed |  |
| python syntax: scripts/mac_ops_fast_check.py | `/Applications/Xcode.app/Contents/Developer/usr/bin/python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/mac_ops_fast_check.py` | passed |  |
| python syntax: tests/test_check_proof.py | `/Applications/Xcode.app/Contents/Developer/usr/bin/python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_check_proof.py` | passed |  |
| TLC heavy queue model | `java tlc2.TLC -workers 1 -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `/Applications/Xcode.app/Contents/Developer/usr/bin/python3 heavy.py --help` | passed |  |
| tests: tests.test_check_proof | `/Applications/Xcode.app/Contents/Developer/usr/bin/python3 -m unittest tests.test_check_proof` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.
