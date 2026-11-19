# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `25cad64a997d79a5311f19c0d9afa51796c0b7dc`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: coordinator/bin/models.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/models.py` | passed |  |
| python syntax: tests/test_gatekeep_retry_limit.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_gatekeep_retry_limit.py` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-6th076e2 -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-6th076e2/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_gatekeep_retry_limit | `python3 -m unittest tests.test_gatekeep_retry_limit` | failed | Command '['/Applications/Xcode.app/Contents/Developer/usr/bin/python3', '-m', 'unittest', 'tests.test_gatekeep_retry_limit']' returned non-zero exit status 1. |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.
