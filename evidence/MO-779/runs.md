# MO-779 runs

Reports in reports/ are the last-message FAIL reports of five real mac-ops gate threads (read-only via t3_thread_read). They are free prose, so findings are the paragraphs that open with Critical or Major.

## Before (origin/main)

    $ git show origin/main:coordinator/overnight/lane_driver.py | grep -n "def gate_verdict\|gate_score"
    555:def gate_verdict(repo, number, head, base):
    $ git cat-file -e origin/main:coordinator/bin/gate_score.py; echo $?
    128

A FAIL reply returns FAIL in every arm; nothing scores it.

## After: score_findings with a fake call (python3 -I evidence/MO-779/proof.py fake)

    fail1.txt all low: findings=1 dropped=1 verdict FAIL -> PASS complete_pass=True unchanged=False
       dropped: Major — PR #909 moved to 4f832559c2c449f3609297bd4cb364995916e673. Both the PR metadata and the remote head confirm it. The body still contains the exact line `
    fail1.txt one kept: findings=1 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail1.txt unparseable: findings=1 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail1.txt wrong length: findings=1 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail1.txt call raises: findings=1 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail2.txt all low: findings=2 dropped=2 verdict FAIL -> PASS complete_pass=True unchanged=False
       dropped: Major — scripts/coord_wake_metrics.py:116 and :139. GitHub reconciliation checks mac-ops PRs, but the script collects PR numbers from every repository in the in
       dropped: Major — scripts/coord_wake_metrics.py:127–128. When the launcher and event producers go quiet, the clock used to detect stuck rows freezes at the last recorded 
    fail2.txt one kept: findings=2 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail2.txt unparseable: findings=2 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail2.txt wrong length: findings=2 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail2.txt call raises: findings=2 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail3.txt all low: findings=1 dropped=1 verdict FAIL -> PASS complete_pass=True unchanged=False
       dropped: Major — [PR #919](https://github.com/shyamsivakumar/mac-ops/pull/919) now points to `717c2b5ff81dd8eb23d9be979720e391b8d0c9b8`. GitHub and the remote Git ref ag
    fail3.txt one kept: findings=1 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail3.txt unparseable: findings=1 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail3.txt wrong length: findings=1 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail3.txt call raises: findings=1 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail4.txt all low: findings=1 dropped=1 verdict FAIL -> PASS complete_pass=True unchanged=False
       dropped: Major — coordinator/bin/ticket:1927. Every valid partial PR reviewed through `ticket gate` receives the full-ticket Provides instructions. The command passes `F
    fail4.txt one kept: findings=1 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail4.txt unparseable: findings=1 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail4.txt wrong length: findings=1 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail4.txt call raises: findings=1 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail5.txt all low: findings=2 dropped=2 verdict FAIL -> PASS complete_pass=True unchanged=False
       dropped: Major — `reviewer_audit/manifest.json:714`. The PR description confirms that `metrics.py` raises when `read_task` receives the new task IDs. Every metrics run t
       dropped: Major — `reviewer_audit/manifest.json:713`. The PR description also confirms that every normal `reviewer_audit freeze` rebuild drops all 26 additions because it
    fail5.txt one kept: findings=2 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail5.txt unparseable: findings=2 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail5.txt wrong length: findings=2 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    fail5.txt call raises: findings=2 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    a PASS report is untouched: True

## After: one real cheap-model call (python3 -I evidence/MO-779/proof.py real)

Model: morph/morph-dsv41flash, the first available entry of models.pi_routes('quick'), run through pi. An attempt can return an empty answer (a pi/morph flake); the report is then left unchanged, which is the fail-safe. Three runs follow.

    model spec: morph/morph-dsv41flash
    fail2 (real cheap model): findings=2 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    raw model answer: ''

    model spec: morph/morph-dsv41flash
    fail2 (real cheap model): findings=2 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    raw model answer: '[7, 8]\n'

    model spec: morph/morph-dsv41flash
    fail2 (real cheap model): findings=2 dropped=0 verdict FAIL -> FAIL complete_pass=False unchanged=True
    raw model answer: ''

A score at or above 5 keeps the finding, so a real score of 8 or 5 keeps the FAIL.

## After: lane gate_verdict in and out of the arm (python3 -I evidence/MO-779/proof.py lane)

pi_call, last_reply, the receipts file and the journal dir are replaced by temp stand-ins; nothing is sent. journal.treatment_names comes from #997 (PR #1005); the proof injects an equivalent when main lacks it.

    no experiment (assigned_arm None): verdict=FAIL ledger_keys=[]
    control arm: verdict=FAIL ledger_keys=[]
    treatment arm: verdict=PASS ledger_keys=['journal-score2:thread1', 'score2:thread1']
    treatment, model returns garbage: verdict=FAIL ledger_keys=['score2:thread1']
    journal rows: [('gate_score_dropped', ['Major — scripts/coord_wake_metrics.py:116 and :139. GitHub reconciliation checks mac-ops PRs, but the script collects PR numbers from every repository in the in', 'Major — scripts/coord_wake_metrics.py:127–128. When the launcher and event producers go quiet, the clock used to detect stuck rows freezes at the last recorded '])]
