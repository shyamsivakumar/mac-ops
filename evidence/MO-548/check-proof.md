# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `833e45ab58e2fa411ee58adf5111445d1c334eaf`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| python syntax: scripts/worktree-cleaner/cleaner.py | `python3 -c 'import ast,sys;[ast.parse(open(f,'"'"'rb'"'"').read(),f) for f in sys.argv[1:]]' scripts/worktree-cleaner/cleaner.py` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-t5mqurmo -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-t5mqurmo/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Focused offline probe: passed. Mocked GitHub 404 refresh evicts a seeded positive entry; save/reload and subsequent scan remain unverified.

Device, handset and live-service checks: not run, waived by Shyam per brief.
Reviewer round: attempted; T3 rejected gpt-6.2-astra as unavailable. Coordinator exact-head gate pending.
