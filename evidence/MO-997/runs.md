# MO-997 runs

A builder-side factory.json experiment names the bar with
`"names": ["severity_bar"]`.
Only the treatment arm of that experiment changes anything.

## Ticket proof command

`HOME=/nonexistent` is dropped because this builder's sandbox refuses commands
that set HOME. The check reads no HOME path.

Before (origin/main):

```text
reads 1 False
AssertionError: bar_visible ignores the arm
exit 1
```

After (this branch):

```text
reads 1 True
exit 0
```

## Real functions, temp journal and queue dirs, no live start

A one-off script (not committed) runs the real `bar_visible`, `proof_required`,
`cmd_start --dry-run --print-brief` and `scope_gate`. It patches
`factory_experiments` and puts `COORD_JOURNAL_DIR` and `COORDQ_DIR` in temp dirs.
`journal.emit` raises during the cmd_start runs. `default_branch`, `fetch_issue`
and the other gh readers are stubbed, so nothing is written or queued.

<!-- markdownlint-disable MD013 -->

```text
no experiment
  arm=None: bar_visible=False proof_required(proofRequired=True)=True
  arm=control: bar_visible=False proof_required(proofRequired=True)=True
  arm=treatment: bar_visible=False proof_required(proofRequired=True)=True
  caller with no arm: True False
builder experiment naming severity_bar
  arm=None: bar_visible=False proof_required(proofRequired=True)=True
  arm=control: bar_visible=False proof_required(proofRequired=True)=True
  arm=treatment: bar_visible=True proof_required(proofRequired=True)=False
builder experiment not naming the bar
  arm=treatment: bar_visible=False proof_required(proofRequired=True)=True
gate-side experiment naming the bar
  arm=treatment: bar_visible=False proof_required(proofRequired=True)=True
real cmd_start --dry-run --print-brief path, gh and queue stubbed, journal.emit raises if called
  experiment split=100: assigned arm=treatment, bar in brief=True
  experiment split=0: assigned arm=control, bar in brief=False
  no experiment: bar in brief = False
  no experiment, COORD_ARM=treatment: bar in brief = False
coordq scope_gate (the gatekeep proof rule), real journal assigned row, temp dirs, dry run, gh read stubbed
  ticket 5 journaled treatment, severity-bar experiment: scope_gate returned True, gh reads before returning: 0
  ticket 6 journaled control, severity-bar experiment: scope_gate returned True, gh reads before returning: 1
  ticket 5 journaled treatment, no experiment: scope_gate returned True, gh reads before returning: 1
```

<!-- markdownlint-enable MD013 -->

Reading the output:

- With no experiment, all briefs and proof decisions match origin/main.
  `proof_required` with no arm (every existing caller) returns what it did before.
  `COORD_ARM=treatment` with no registered experiment adds no bar.
- With a registered builder-side experiment naming the bar, only the treatment
  arm sees the bar and has the proof rule relaxed. Control, no arm, an experiment
  not naming the bar, and a gate-side experiment all stay unchanged.
- The `cmd_start` run shows the cluster stamp's arm reaches the brief. Split 100
  gives treatment and the bar appears. Split 0 gives control and it does not.
- The `scope_gate` run reads the arm from a real journal `assigned` row. The
  treatment ticket returns before any GitHub read. The control ticket goes on to
  the scope read as today.
