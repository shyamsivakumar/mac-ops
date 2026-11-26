# MO-991 runs

## Ticket proof command

On origin/main (snapshot of origin/main coordinator/):

```text
Traceback (most recent call last):
  File "<string>", line 1, in <module>
AssertionError: no stop rule
exit 1
```

On the head:

```text
exit 0
```

## Selftest case consolidation-guard (extended with partial cases)

On origin/main code with the extended selftest:

```text
AssertionError: expected True, got False
exit 1
```

On the head:

```text
consolidation_guard PASS
exit 0
```

## Table (python3 evidence/MO-991/probe.py, fakes only, temp COORDQ_DIR, COORD_JOURNAL_DIR and decisions board)

Every gate row also asserts that `ticket gate` by hand reaches the same value through the shared `partial_state`. Gate rows (partial: None is no marker, False is a marker without a valid claim, True is a valid claim; a marker of any kind closes nothing, in every brief): the line is `present`, `absent` or `fenced` (inside a code block); the left section is `listed`, `empty` or `none`; `lane` is a lane repo, `reviewer` a reviewer-merge repo. A size of 301 is the recut band: gatekeep queues no gate there, so the marker is ignored, as for a fix round that pushes 280 to 310.

cmd_close rows are the counts of: issue close, issue comment, label edit, journal partial_merged. The size does not matter to cmd_close, so the marker on a 40-line PR keeps the issue open too.

```text
gate brief: line, left, size, mode -> partial (None no marker, False marker only, True valid claim), partial text, gh issue close in brief
present  listed  199 lane     -> partial=False partial_text=False issue_close=False
present  listed  199 reviewer -> partial=False partial_text=False issue_close=False
present  listed  200 lane     -> partial=True  partial_text=True  issue_close=False
present  listed  200 reviewer -> partial=True  partial_text=True  issue_close=False
present  listed  300 lane     -> partial=True  partial_text=True  issue_close=False
present  listed  300 reviewer -> partial=True  partial_text=True  issue_close=False
present  listed  301 lane     -> partial=False partial_text=False issue_close=False
present  listed  301 reviewer -> partial=False partial_text=False issue_close=False
present  empty   199 lane     -> partial=False partial_text=False issue_close=False
present  empty   199 reviewer -> partial=False partial_text=False issue_close=False
present  empty   200 lane     -> partial=False partial_text=False issue_close=False
present  empty   200 reviewer -> partial=False partial_text=False issue_close=False
present  empty   300 lane     -> partial=False partial_text=False issue_close=False
present  empty   300 reviewer -> partial=False partial_text=False issue_close=False
present  empty   301 lane     -> partial=False partial_text=False issue_close=False
present  empty   301 reviewer -> partial=False partial_text=False issue_close=False
present  none    199 lane     -> partial=False partial_text=False issue_close=False
present  none    199 reviewer -> partial=False partial_text=False issue_close=False
present  none    200 lane     -> partial=False partial_text=False issue_close=False
present  none    200 reviewer -> partial=False partial_text=False issue_close=False
present  none    300 lane     -> partial=False partial_text=False issue_close=False
present  none    300 reviewer -> partial=False partial_text=False issue_close=False
present  none    301 lane     -> partial=False partial_text=False issue_close=False
present  none    301 reviewer -> partial=False partial_text=False issue_close=False
absent   listed  200 lane     -> partial=None  partial_text=False issue_close=False
absent   listed  200 reviewer -> partial=None  partial_text=False issue_close=True
fenced   listed  199 lane     -> partial=None  partial_text=False issue_close=False
fenced   listed  199 reviewer -> partial=None  partial_text=False issue_close=True
fenced   listed  200 lane     -> partial=None  partial_text=False issue_close=False
fenced   listed  200 reviewer -> partial=None  partial_text=False issue_close=True
fenced   listed  300 lane     -> partial=None  partial_text=False issue_close=False
fenced   listed  300 reviewer -> partial=None  partial_text=False issue_close=True
fenced   listed  301 lane     -> partial=None  partial_text=False issue_close=False
fenced   listed  301 reviewer -> partial=None  partial_text=False issue_close=True
cmd_close: line, left -> issue close, comment, label edit, journal partial_merged (calls)
recorded shyamsivakumar/mac-ops#7: #8 is partial
present  listed  -> (0, 1, 1, 1)
recorded shyamsivakumar/mac-ops#7: #8 is partial
present  empty   -> (0, 1, 1, 1)
recorded shyamsivakumar/mac-ops#7: #8 is partial
present  none    -> (0, 1, 1, 1)
closed shyamsivakumar/mac-ops#7 via mmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmm
fenced   listed  -> (1, 0, 0, 0)
closed shyamsivakumar/mac-ops#7 via mmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmm
absent   none    -> (1, 0, 0, 0)
recorded shyamsivakumar/mac-ops#7: #8 is partial
shyamsivakumar/mac-ops#7 already has the partial record for #8; nothing to do
shyamsivakumar/mac-ops#7 already has the partial record for #8; nothing to do
repeated cmd_close x3 (present, listed) -> (0, 1, 1, 1)
closed by a Closes keyword at merge, no record yet -> recorded shyamsivakumar/mac-ops#7: #8 is partial
shyamsivakumar/mac-ops#7 already has the partial record for #8; nothing to do
[['issue', 'reopen'], ['issue', 'edit'], ['issue', 'comment'], ['journal', 'partial_merged']] (second call recorded nothing)
shyamsivakumar/mac-ops#7 was closed as NOT_PLANNED, not by a merge keyword; left closed
recorded shyamsivakumar/mac-ops#7: #8 is partial
closed as not planned -> [['issue', 'edit'], ['issue', 'comment'], ['journal', 'partial_merged']] (no reopen)
marker spellings -> ['- x', 'x', '']
recorded shyamsivakumar/mac-ops#7: #8 is partial
stage:todo ticket -> [['issue', 'edit'], ['issue', 'comment']] [{'name': 'stage:backlog'}]
decisions items on the board: ['partial-mac-ops-7-8']
```
