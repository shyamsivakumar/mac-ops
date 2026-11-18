# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `eacc37ecdf6593af7ec7a9cb7b983e33a4ddc5c0`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-9hj2eeci -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-9hj2eeci/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

PASS: `node --input-type=module` isolated mergeOne probe exercised queueing and pre-validation eligibility snapshots for needs and ready cards.
PASS: `git diff --check`.
Device, handset and live-service cases: WAIVED by Shyam; not run, not failed.
No-comments diff review: no added or touched comments. Deslop review: direct expression is the smallest fix; no further cleanup.
