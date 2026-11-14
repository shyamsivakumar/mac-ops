# Refs #322

Rule 5 of the approved one-lane-per-repo spec replaces wrap-up escalation.
The controller source was copied from ~/Code/coordinator/loop/turn_cap.py into
this repository for review. No live file or installed rules were changed.

## Dry run
An in-process fake T3 response supplied a running run at each age.
No T3 mutation, GitHub comment, state write or live install occurred.

| Age | Output |
| --- | --- |
| 9 minutes | No action |
| 11 minutes | cap mis-sized |
| 21 minutes | cap mis-sized; interrupt; cap stopped; gh issue comment |
The comment body is "Run passed 20 minutes; park for re-cut".
Dry-run state stayed unchanged.

## Review round
Self-review against rule 5: no critical, major or minor findings.
The interrupt names the observed runId, so a replacement run cannot be stopped.
Persistent run IDs suppress repeated interrupts and comments on later passes.
Missing or ambiguous ticket identity raises an error rather than guessing.
No wrap-up send or second final interrupt remains.
Comment cleanup: no new code comments. Deslop review: removed unused legacy state defaults.

## Limits
No live installation, real interrupt or issue comment was exercised.
The caller must expose ticket identity in the run or thread metadata.
An interruption between an external action and saving its receipt can duplicate
that action on restart. A failed comment is reported; if the run has already
stopped, the running-thread scan will not retry it.
Post-install observations belong to the coordinator, not this build.

## Historical durations
The original brief reports 31 of 164 runs over 10 minutes, with longest durations
324, 275, 246, 188, 134 and 111 minutes. These are supplied figures, not a fresh
measurement. The re-scoped brief drops the next-20-runs installation requirement.
