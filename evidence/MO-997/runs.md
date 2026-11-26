# MO-997 runs

A builder-side experiment in factory.json names the switches it controls in `names`. `severity_bar` shows the builder the bar. `proof_required` makes a green proof required before the gate.
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
  arm=None: bar_visible=False proof_required(unset)=False proof_required(proofRequired=True)=True
  arm=control: bar_visible=False proof_required(unset)=False proof_required(proofRequired=True)=True
  arm=treatment: bar_visible=False proof_required(unset)=False proof_required(proofRequired=True)=True
  caller with no arm: True False
builder experiment naming severity_bar only
  arm=None: bar_visible=False proof_required(unset)=False proof_required(proofRequired=True)=True
  arm=control: bar_visible=False proof_required(unset)=False proof_required(proofRequired=True)=True
  arm=treatment: bar_visible=True proof_required(unset)=False proof_required(proofRequired=True)=True
builder experiment naming proof_required only
  arm=None: bar_visible=False proof_required(unset)=False proof_required(proofRequired=True)=True
  arm=control: bar_visible=False proof_required(unset)=False proof_required(proofRequired=True)=True
  arm=treatment: bar_visible=False proof_required(unset)=True proof_required(proofRequired=True)=True
builder experiment naming both
  arm=control: bar_visible=False proof_required(unset)=False proof_required(proofRequired=True)=True
  arm=treatment: bar_visible=True proof_required(unset)=True proof_required(proofRequired=True)=True
gate-side experiment naming proof_required
  arm=treatment: bar_visible=False proof_required(unset)=False proof_required(proofRequired=True)=True
real cmd_start --dry-run --print-brief path, gh and queue stubbed, journal.emit raises if called
  experiment split=100: assigned arm=treatment, bar in brief=True
  experiment split=0: assigned arm=control, bar in brief=False
  no experiment: bar in brief = False
  no experiment, COORD_ARM=treatment: bar in brief = False
coordq scope_gate (the gatekeep proof rule), real journal assigned row, temp dirs, dry run, gh read stubbed
  ticket 5 treatment, proof experiment, proofRequired unset: scope_gate returned True, gh reads before returning: 1
  ticket 6 control, proof experiment, proofRequired unset: scope_gate returned True, gh reads before returning: 0
  ticket 5 treatment, bar-only experiment, proofRequired unset: scope_gate returned True, gh reads before returning: 0
  ticket 5 treatment, no experiment, proofRequired unset: scope_gate returned True, gh reads before returning: 0
  ticket 6 control, proof experiment, proofRequired=True: scope_gate returned True, gh reads before returning: 1
```

Reading the output:

- With no experiment, every brief and every proof decision is as on origin/main. `proof_required` called with no arm (every existing caller) returns what it did before. `COORD_ARM=treatment` with no experiment registered adds no bar.
- `severity_bar`: only the treatment arm of a builder-side experiment naming it sees the bar. Control, no arm, other names and a gate-side experiment do not.
- `proof_required`: the treatment arm of a builder-side experiment naming it requires a green proof even when `proofRequired` is unset. Control, no arm, an experiment naming only `severity_bar`, and a gate-side experiment give the configured value. A configured `proofRequired: true` stays on for every arm.
- The `cmd_start` run shows the arm from the cluster stamp reaches the brief: split 100 gives treatment and the bar appears, split 0 gives control and it does not.
- The `scope_gate` run reads the arm from a real journal `assigned` row. With `proofRequired` unset, the treatment ticket goes on to the scope read (proof required) and the control ticket returns with no read. A configured `proofRequired` still reads for control.
