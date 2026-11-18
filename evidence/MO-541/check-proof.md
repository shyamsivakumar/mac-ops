# Check proof

Command: `python3 scripts/mac_ops_fast_check.py`
Checked commit: `54733d91df245d9f473f5400582311f4996498b6`
Working tree clean when the checks ran: yes

| Check | Command | Result | Detail |
| --- | --- | --- | --- |
| lane selection | `python3 scripts/mac_ops_fast_check.py --lane-selection` | passed |  |
| overnight selftest | `python3 coordinator/overnight/overnight selftest` | passed |  |
| TLC heavy queue model | `/opt/homebrew/opt/openjdk@17/bin/java -Xmx128m -Djava.io.tmpdir=/var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-nne0l4ep -cp /Users/shyamsivakumar/Code/llmwiki/runtime/tla/tla2tools.jar tlc2.TLC -workers 1 -noGenerateSpecTE -metadir /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/heavy-queue-tlc-nne0l4ep/states -config HeavyQueue.cfg HeavyQueue.tla` | passed |  |
| heavy help | `python3 heavy.py --help` | passed |  |

A result is `passed`, `failed` or `not run`. A failed check stopped the run,
so every check after it is `not run`.

Scope repair: merged current origin/main without force push. The PR merge-base diff now contains only four cockpit JavaScript files and this receipt. MO-539 prompt, test and receipt files have no PR diff.

| Additional check | Command | Result |
| --- | --- | --- |
| Full local suite | `python3 -m unittest discover -s tests` | failed: 7 failures, 390 tests |
| JavaScript syntax | `node --check` on each of the four changed cockpit files | passed |
| Whitespace | `git diff --check` | passed |
| Scope review | `git diff origin/main...HEAD` | passed: one in-session review, no critical or major findings |
| Device, handset, live-service, live-board | No command run | not run: waived by Shyam 2026-11-14 |

No checks or tests were weakened. Selected check success does not mean full-suite success. Cleanup review found no in-scope cleanup; this repair adds no code comments. Coordinator Astra gate remains required on the new head.

Gate repair: restored evidence/MO-540/check-proof.md and evidence/check-proof.md byte for byte from origin/main so neither is deleted by this PR. The root proof belongs to main and is not the MO-541 receipt.

Fresh selected check: `python3 scripts/mac_ops_fast_check.py --proof /tmp/mo541-check-current.md` passed. Full suite rerun: `python3 -m unittest discover -s tests` (result recorded below). One in-session scope review confirmed no changes to coordinator/bin/ticket or coordinator/bin/gate_policy.py. No critical or major scope findings remain. Deslop and comment diff review: this repair changes receipts only, with no code comments added.

Full suite rerun result: failed; see /tmp/mo541-full-current.log. Existing tests and checks were not weakened.
