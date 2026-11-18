# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `bde79b8182f5f7c3404e283576c430bfad0039c7`
Working tree clean when the checks ran: yes

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: coordinator/bin/gh_gateway.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/bin/gh_gateway.py` | passed |  |
| python syntax: coordinator/overnight/lane_driver.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/lane_driver.py` | passed |  |
| python syntax: coordinator/overnight/overnight | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/overnight` | passed |  |
| python syntax: coordinator/overnight/selftest.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' coordinator/overnight/selftest.py` | passed |  |
| python syntax: evidence/MO-1088/prove-gh-gateway.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evidence/MO-1088/prove-gh-gateway.py` | passed |  |
| python syntax: evidence/MO-548/prove-cleaner-cache.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evidence/MO-548/prove-cleaner-cache.py` | passed |  |
| python syntax: evidence/MO-548/prove-overnight-reads.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evidence/MO-548/prove-overnight-reads.py` | passed |  |
| python syntax: evidence/MO-548/prove-ticket-fresh.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' evidence/MO-548/prove-ticket-fresh.py` | passed |  |
| python syntax: scripts/gh-usage-report.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/gh-usage-report.py` | passed |  |
| python syntax: scripts/worktree-cleaner/cleaner.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/worktree-cleaner/cleaner.py` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-ud3e5mq8 -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-ud3e5mq8/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.
