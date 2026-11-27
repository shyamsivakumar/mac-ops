# MO-779 runs

Reports in reports/ are the last-message FAIL reports of five real mac-ops gate threads (read-only via t3_thread_read). They are free prose, so findings are the paragraphs that open with Critical or Major. All five carry CHECK: FAIL, so they are shown as they are (must stay FAIL) and again with the CHECK line edited to PASS (marked edited) to exercise the drop paths. Keep threshold is 7: a score under 7 drops the finding. Flip rule: after the dropped findings are removed, the VERDICT becomes PASS only when the remaining report has no case-insensitive whole word critical or major anywhere (headings, prose, tables, JSON). Before scoring, a report is also left unchanged when the whole-word count of critical or major in it exceeds the number of findings found, or when one finding text holds more than one such word. The scoring reply must parse in full as a JSON list (optionally fenced) of exactly N integers 0 to 10, else scoring failed and the report is unchanged. A finding ends at the first CHECK:, PROVIDES:, VERDICT:, Builder check: or Left for later line, and a rewrite that changes any footer line other than VERDICT FAIL to PASS is discarded. Prose such as no major risk or no critical or major finding remains therefore blocks scoring or the flip; that is accepted as fail-safe.

## Before (origin/main)

    $ git show origin/main:coordinator/overnight/lane_driver.py | grep -n "def gate_verdict\|gate_score"
    559:def gate_verdict(repo, number, head, base):
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
    - dropped: Major — scripts/coord_wake_metrics.py:116 and :139. GitHub reconciliation checks mac-ops PRs, but the script collects PR numbers from every repository in the in
    
    
    
    Major — scripts/coord_wake_metrics.py:127–128. When the launcher and event producers go quiet, the clock used to detect stuck rows freezes at the last recorded event. A pending row can remain unreported throughout an outage, however long an operator waits before running the report. Use the report cutoff for historical windows and wall-clock time for live reports.
    
    I applied the standard merge bar because this diff adds read-only reporting and does not change orders, exits, or stop logic. Both findings affect ordinary fleet use. The PR conversation contains no prior gate findings.
    
    GitHub confirmed the requested head and the exact body line `Builder check: PASS 5fa26488da21ce4a78b3572fbf1ee442d20b83d4`. All ten checks in the supplied proof say `passed`, but `ec72b752` is not an ancestor of the head and the trees differ in 489 files. That shared proof is unchanged from the PR base. The PR-specific receipt at evidence/MO-917/check-proof.md:5 names `b13f8cad`, whose tree differs from the reviewed head only in that receipt. I did not rerun the suite.
    
    PROVIDES: PASS 5fa26488da21ce4a78b3572fbf1ee442d20b83d4
    CHECK: PASS 5fa26488da21ce4a78b3572fbf1ee442d20b83d4
    VERDICT: FAIL
    two consecutive Majors, parsed: 2
    two consecutive Majors, first scored low: findings=2 dropped=1 verdict -> FAIL unchanged=False
    two consecutive Majors, both scored low: findings=2 dropped=2 verdict -> PASS unchanged=False
    bulleted Majors, first scored low: findings=2 dropped=1 verdict -> FAIL unchanged=False
    numbered Majors, first scored low: findings=2 dropped=1 verdict -> FAIL unchanged=False
    all-format variants, each alone, scored low flips only when nothing else blocks:
      'Major — a.py:1 x.': findings=1 dropped=1 verdict -> PASS
      '[major] a.py:1 x.': findings=1 dropped=1 verdict -> PASS
      '**Critical**: a.py:1 x.': findings=1 dropped=1 verdict -> PASS
      '- major: a.py:1 x.': findings=1 dropped=1 verdict -> PASS
      '1) MAJOR a.py:1 x.': findings=1 dropped=1 verdict -> PASS
      '`Major` a.py:1 x.': findings=1 dropped=1 verdict -> PASS
      '> Critical - a.py:1 x.': findings=1 dropped=1 verdict -> PASS
      '[Critical] a.py:1 x.': findings=1 dropped=1 verdict -> PASS
      mixed 'Major — a.py:1 x.' + '1) MAJOR a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed 'Major — a.py:1 x.' + '`Major` a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed 'Major — a.py:1 x.' + '> Critical - a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed 'Major — a.py:1 x.' + '[Critical] a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed '[major] a.py:1 x.' + '1) MAJOR a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed '[major] a.py:1 x.' + '`Major` a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed '[major] a.py:1 x.' + '> Critical - a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed '[major] a.py:1 x.' + '[Critical] a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed '**Critical**: a.py:1 x.' + '1) MAJOR a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed '**Critical**: a.py:1 x.' + '`Major` a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed '**Critical**: a.py:1 x.' + '> Critical - a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed '**Critical**: a.py:1 x.' + '[Critical] a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed '- major: a.py:1 x.' + '1) MAJOR a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed '- major: a.py:1 x.' + '`Major` a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed '- major: a.py:1 x.' + '> Critical - a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
      mixed '- major: a.py:1 x.' + '[Critical] a.py:1 x.', first scored low: findings=2 dropped=1 verdict -> FAIL
    mixed Major and [major], one scored low: dropped=1 verdict -> FAIL
    mixed Major and [major], both scored low, minor kept: dropped=2 verdict -> PASS
    json block with a kept critical, one dropped: dropped=0 verdict -> FAIL
    ### Critical: heading plus Major: line, Major scored low: dropped=0 verdict -> FAIL
    table row with Critical plus Major: line, Major scored low: dropped=0 verdict -> FAIL
    prose 'no major risk' left after the only finding is dropped: dropped=0 verdict -> FAIL
    Major line with a ### Critical heading directly under it, Major scored low: dropped=0 verdict -> FAIL
    clean report, every finding dropped, no other severity word: dropped=1 verdict -> PASS
    reply 'Initial score [3]. final score [9]': dropped=0 verdict -> FAIL unchanged=True
    reply with a fenced json list: dropped=1 verdict -> PASS unchanged=False
    reply with a bare fence: dropped=1 verdict -> PASS unchanged=False
    reply with a score of 11: dropped=0 verdict -> FAIL unchanged=True
    reply with a boolean: dropped=0 verdict -> FAIL unchanged=True
    reply with a float: dropped=0 verdict -> FAIL unchanged=True
    reply with trailing prose: dropped=0 verdict -> FAIL unchanged=True
    footer directly after the last finding, scored low: dropped=1 verdict -> PASS unchanged=False
       footer lines kept: ['Builder check: PASS abc', 'CHECK: PASS abc', 'PROVIDES: PASS abc', 'VERDICT: PASS']
    mismatch (2 Major lines in the text, 1 finding in the json block, scored low): dropped=0 unchanged=True verdict=FAIL
    a PASS report is untouched: True

## After: one real cheap-model call (python3 -I evidence/MO-779/proof.py real)

Model: morph/morph-dsv41flash, the first available entry of models.pi_routes('quick'), run through pi. An attempt can return an empty answer (a pi/morph flake); the report is then left unchanged, which is the fail-safe. Three runs follow.

    model spec: morph/morph-dsv41flash
    fail2 CHECK PASS edited (real cheap model): findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    raw model answer: '[7, 9]\n'

    model spec: morph/morph-dsv41flash
    fail2 CHECK PASS edited (real cheap model): findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    raw model answer: ''

    model spec: morph/morph-dsv41flash
    fail2 CHECK PASS edited (real cheap model): findings=2 dropped=0 verdict FAIL -> FAIL remaining_majors=2 complete_pass=False unchanged=True
    raw model answer: '[9, 7]\n'

A score of 7 or more keeps the finding.

## After: lane gate_verdict in and out of the arm (python3 -I evidence/MO-779/proof.py lane)

pi_call, last_reply, the receipts file and the journal dir are replaced by temp stand-ins; nothing is sent. Arms are stamped per ticket: journal.assigned_arm is stubbed with a per-ticket table (ticket 42 treatment, ticket 7 control) and the real journal.treatment_names reads a stubbed factory_experiments. The ticket comes from the PR body Refs line.

    PR 7, ticket 42 (treatment): verdict=PASS model_calls=1 ledger_keys=['journal-score2:t7', 'score2:t7']
    PR 42, ticket 7 (control; PR number equals the treated ticket): verdict=FAIL model_calls=1 ledger_keys=[]
    PR 50, no Refs (not in the arm): verdict=FAIL model_calls=1 ledger_keys=[]
    PR 7, treatment, CHECK: FAIL report, low scores: verdict=FAIL
    PR 7, model returns empty, tick 1: verdict=FAIL model_calls=1 score2='failed'
    PR 7, model returns empty, tick 2: verdict=FAIL model_calls=1 score2='failed'
    PR 7, model returns empty, tick 3: verdict=FAIL model_calls=1 score2='failed'
    PR 7, model call raises, tick 1: verdict=FAIL model_calls=1 score2='failed'
    PR 7, model call raises, tick 2: verdict=FAIL model_calls=1 score2='failed'
    journal rows: [('gate_score_dropped', 7, 2)]
