# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `1c1b9b0c0d901aa8c90cab56df6dcd78971efabe`
Working tree clean when the checks ran: no

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-n3ckti7e -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-n3ckti7e/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Node syntax: passed (`node --check coordinator/mods/cockpit/main.js`).
Focused extracted tellEach probe: passed for Rebase, Retry and Note with refresh during send, and rejected sends logging no act.
Device, handset and live-service testing: waived by Shyam, not failed.
In-session reviewer round: inspected eligibility capture, success-only logging and failure path; no critical or major findings. Deslop and no-comments diff review: no additional edits needed.
Provenance: checks ran on the modified source based on 1c1b9b0c0d901aa8c90cab56df6dcd78971efabe. The final commit adds this receipt; post-commit verification is recorded in the PR body.
