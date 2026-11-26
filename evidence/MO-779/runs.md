# MO-779 runs

Reports in reports/ are the last-message FAIL reports of five real mac-ops gate threads (read-only via t3_thread_read). They are free prose, so findings are the paragraphs that open with Critical or Major. All five carry CHECK: FAIL, so they are shown as they are (must stay FAIL) and again with the CHECK line edited to PASS (marked edited) to exercise the drop paths. Keep threshold is 7: a score under 7 drops the finding.

## Before (origin/main)

    $ git show origin/main:coordinator/overnight/lane_driver.py | grep -n "def gate_verdict\|gate_score"
    555:def gate_verdict(repo, number, head, base):
    $ git cat-file -e origin/main:coordinator/bin/gate_score.py; echo $?
    128

A FAIL reply returns FAIL in every arm; nothing scores it.

## After: score_findings with a fake call (python3 -I evidence/MO-779/proof.py fake)

    fail1.txt CHECK FAIL, all low: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail1.txt CHECK PASS (edited), all at 6: findings=1 dropped=1 verdict FAIL -> PASS remaining_majors=0 complete_pass=True unchanged=False
       dropped: Major — PR #909 moved to 4f832559c2c449f3609297bd4cb364995916e673. Both the PR metadata and the remote head confirm it. The body still contains the exact line `
    fail1.txt CHECK PASS (edited), all at 7: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail1.txt CHECK PASS (edited), first low, rest kept: findings=1 dropped=1 verdict FAIL -> PASS remaining_majors=0 complete_pass=True unchanged=False
       dropped: Major — PR #909 moved to 4f832559c2c449f3609297bd4cb364995916e673. Both the PR metadata and the remote head confirm it. The body still contains the exact line `
    fail1.txt CHECK PASS (edited), unparseable: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail1.txt CHECK PASS (edited), wrong length: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail1.txt CHECK PASS (edited), call raises: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail2.txt CHECK FAIL, all low: findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    fail2.txt CHECK PASS (edited), all at 6: findings=2 dropped=2 verdict FAIL -> PASS remaining_majors=0 complete_pass=True unchanged=False
       dropped: Major — scripts/coord_wake_metrics.py:116 and :139. GitHub reconciliation checks mac-ops PRs, but the script collects PR numbers from every repository in the in
       dropped: Major — scripts/coord_wake_metrics.py:127–128. When the launcher and event producers go quiet, the clock used to detect stuck rows freezes at the last recorded 
    fail2.txt CHECK PASS (edited), all at 7: findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    fail2.txt CHECK PASS (edited), first low, rest kept: findings=2 dropped=1 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=False
       dropped: Major — scripts/coord_wake_metrics.py:116 and :139. GitHub reconciliation checks mac-ops PRs, but the script collects PR numbers from every repository in the in
    fail2.txt CHECK PASS (edited), unparseable: findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    fail2.txt CHECK PASS (edited), wrong length: findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    fail2.txt CHECK PASS (edited), call raises: findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    fail3.txt CHECK FAIL, all low: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail3.txt CHECK PASS (edited), all at 6: findings=1 dropped=1 verdict FAIL -> PASS remaining_majors=0 complete_pass=True unchanged=False
       dropped: Major — [PR #919](https://github.com/shyamsivakumar/mac-ops/pull/919) now points to `717c2b5ff81dd8eb23d9be979720e391b8d0c9b8`. GitHub and the remote Git ref ag
    fail3.txt CHECK PASS (edited), all at 7: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail3.txt CHECK PASS (edited), first low, rest kept: findings=1 dropped=1 verdict FAIL -> PASS remaining_majors=0 complete_pass=True unchanged=False
       dropped: Major — [PR #919](https://github.com/shyamsivakumar/mac-ops/pull/919) now points to `717c2b5ff81dd8eb23d9be979720e391b8d0c9b8`. GitHub and the remote Git ref ag
    fail3.txt CHECK PASS (edited), unparseable: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail3.txt CHECK PASS (edited), wrong length: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail3.txt CHECK PASS (edited), call raises: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail4.txt CHECK FAIL, all low: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail4.txt CHECK PASS (edited), all at 6: findings=1 dropped=1 verdict FAIL -> PASS remaining_majors=0 complete_pass=True unchanged=False
       dropped: Major — coordinator/bin/ticket:1927. Every valid partial PR reviewed through `ticket gate` receives the full-ticket Provides instructions. The command passes `F
    fail4.txt CHECK PASS (edited), all at 7: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail4.txt CHECK PASS (edited), first low, rest kept: findings=1 dropped=1 verdict FAIL -> PASS remaining_majors=0 complete_pass=True unchanged=False
       dropped: Major — coordinator/bin/ticket:1927. Every valid partial PR reviewed through `ticket gate` receives the full-ticket Provides instructions. The command passes `F
    fail4.txt CHECK PASS (edited), unparseable: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail4.txt CHECK PASS (edited), wrong length: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail4.txt CHECK PASS (edited), call raises: findings=1 dropped=0 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=True
    fail5.txt CHECK FAIL, all low: findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    fail5.txt CHECK PASS (edited), all at 6: findings=2 dropped=2 verdict FAIL -> PASS remaining_majors=0 complete_pass=True unchanged=False
       dropped: Major — `reviewer_audit/manifest.json:714`. The PR description confirms that `metrics.py` raises when `read_task` receives the new task IDs. Every metrics run t
       dropped: Major — `reviewer_audit/manifest.json:713`. The PR description also confirms that every normal `reviewer_audit freeze` rebuild drops all 26 additions because it
    fail5.txt CHECK PASS (edited), all at 7: findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    fail5.txt CHECK PASS (edited), first low, rest kept: findings=2 dropped=1 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=False
       dropped: Major — `reviewer_audit/manifest.json:714`. The PR description confirms that `metrics.py` raises when `read_task` receives the new task IDs. Every metrics run t
    fail5.txt CHECK PASS (edited), unparseable: findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    fail5.txt CHECK PASS (edited), wrong length: findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    fail5.txt CHECK PASS (edited), call raises: findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    fail2 partial drop report body: findings=2 dropped=1 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=False
       dropped: Major — scripts/coord_wake_metrics.py:116 and :139. GitHub reconciliation checks mac-ops PRs, but the script collects PR numbers from every repository in the in
    Second pass scored these below the merge bar and dropped them:
    - Major — scripts/coord_wake_metrics.py:116 and :139. GitHub reconciliation checks mac-ops PRs, but the script collects PR numbers from every repository in the in
    
    
    
    Major — scripts/coord_wake_metrics.py:127–128. When the launcher and event producers go quiet, the clock used to detect stuck rows freezes at the last recorded event. A pending row can remain unreported throughout an outage, however long an operator waits before running the report. Use the report cutoff for historical windows and wall-clock time for live reports.
    
    I applied the standard merge bar because this diff adds read-only reporting and does not change orders, exits, or stop logic. Both findings affect ordinary fleet use. The PR conversation contains no prior gate findings.
    
    GitHub confirmed the requested head and the exact body line `Builder check: PASS 5fa26488da21ce4a78b3572fbf1ee442d20b83d4`. All ten checks in the supplied proof say `passed`, but `ec72b752` is not an ancestor of the head and the trees differ in 489 files. That shared proof is unchanged from the PR base. The PR-specific receipt at evidence/MO-917/check-proof.md:5 names `b13f8cad`, whose tree differs from the reviewed head only in that receipt. I did not rerun the suite.
    
    PROVIDES: PASS 5fa26488da21ce4a78b3572fbf1ee442d20b83d4
    CHECK: PASS 5fa26488da21ce4a78b3572fbf1ee442d20b83d4
    VERDICT: FAIL
    a PASS report is untouched: True

## After: one real cheap-model call (python3 -I evidence/MO-779/proof.py real)

Model: morph/morph-dsv41flash, the first available entry of models.pi_routes('quick'), run through pi. An attempt can return an empty answer (a pi/morph flake); the report is then left unchanged, which is the fail-safe. Three runs follow.

    model spec: morph/morph-dsv41flash
    fail2 CHECK PASS edited (real cheap model): findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    raw model answer: '[8, 8]\n'

    model spec: morph/morph-dsv41flash
    fail2 CHECK PASS edited (real cheap model): findings=2 dropped=1 verdict FAIL -> FAIL remaining_majors=1 complete_pass=False unchanged=False
       dropped: Major — scripts/coord_wake_metrics.py:116 and :139. GitHub reconciliation checks mac-ops PRs, but the script collects PR numbers from every repository in the in
    raw model answer: '[6, 8]\n'

    model spec: morph/morph-dsv41flash
    fail2 CHECK PASS edited (real cheap model): findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    raw model answer: '[8, 9]\n'

A score of 7 or more keeps the finding.

## After: lane gate_verdict in and out of the arm (python3 -I evidence/MO-779/proof.py lane)

pi_call, last_reply, the receipts file and the journal dir are replaced by temp stand-ins; nothing is sent. The arm comes from the real journal.assigned_arm and journal.treatment_names (#997); only factory_experiments and assigned_arm are stubbed.

    no experiment (assigned_arm None): verdict=FAIL ledger_keys=[]
    control arm: verdict=FAIL ledger_keys=[]
    treatment arm: verdict=FAIL ledger_keys=[]
    treatment, CHECK PASS (edited), low scores: verdict=PASS ledger_keys=['journal-score2:thread1', 'score2:thread1']
    treatment, model returns garbage: verdict=FAIL ledger_keys=['score2:thread1']
    journal rows: [('gate_score_dropped', ['Major — scripts/coord_wake_metrics.py:116 and :139. GitHub reconciliation checks mac-ops PRs, but the script collects PR numbers from every repository in the in', 'Major — scripts/coord_wake_metrics.py:127–128. When the launcher and event producers go quiet, the clock used to detect stuck rows freezes at the last recorded '])]
