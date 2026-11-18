# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `dbf9adf06d8bbc92e5ef97a55f7fd43c79a8e8cc`
Working tree clean when the checks ran: yes

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: scripts/mac_ops_fast_check.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/mac_ops_fast_check.py` | passed |  |
| python syntax: scripts/worktree-cleaner/cleaner.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/worktree-cleaner/cleaner.py` | passed |  |
| python syntax: tests/test_worktree_cleaner_bootstrap.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' tests/test_worktree_cleaner_bootstrap.py` | passed |  |
| python syntax: verification/worktree-cleaner/check_bootstrap.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' verification/worktree-cleaner/check_bootstrap.py` | passed |  |
| worktree cleaner bootstrap fixture | `python3 verification/worktree-cleaner/check_bootstrap.py` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-qj8bfui9 -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-qj8bfui9/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |
| tests: tests.test_worktree_cleaner_bootstrap | `python3 -m unittest tests.test_worktree_cleaner_bootstrap` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.
