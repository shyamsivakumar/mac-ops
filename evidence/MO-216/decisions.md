# MO-216 · Overnight T7b: Route every overnight write through redaction

Ticket: https://github.com/shyamsivakumar/mac-ops/issues/184
Spec: overnight runner spec part T7b (spec issue #172, copy in
`~/Code/coordinator/specs/overnight-runner-spec.md`).

## What was built

The one redaction function of the module (`redact`, with the one pattern
list `SECRET_PATTERNS`) now covers every writer the module has, including
the one that was left out: the console.

```
overnight redact --file fixture.txt      # unchanged, the redaction itself
```

New in this part: `emit(text, err=False)`. Every line the module prints
goes through it, and it calls `redact` on the whole text before it
prints.

## The gap this part closes

T7a (MO-215) routed the *file* writers: `write_record` and
`append_record` redact, and they are the only two places the module
writes a file (`grep -n "write_text\|open(" coordinator/overnight/overnight`
finds the two helpers and three read-only opens).

The console was still an open writer. Launchd writes everything the
module prints to the job's own log
(`~/Library/Logs/coordinator/overnight.log`, the `StandardOutPath` of
`coordinator/launchd/dev.coordinator.overnight.plist`), and a printed
line carries foreign text: a pull request title, a ticket title, a
command's own output tail, a gate thread's report, a receipt body. The
spec's rule (section 5, rule 4) covers logs, not only records under
`.overnight/`, so the job log was the one place a secret could land
unredacted.

## The decisions

1. **One function, one list, one place.** `redact` and `SECRET_PATTERNS`
   are unchanged. `emit` calls the same function, so the console and the
   records cannot drift apart.
2. **Every print in the module goes through `emit`.** The change is
   mechanical: every `print(...)` became `emit(...)`, and
   `file=sys.stderr` became `err=True`. The module has one `print` left,
   the one inside `emit` itself. A writer added later cannot print a
   secret by accident: the rule is in the one place every line goes
   through.
3. **The whole text is redacted at once, not line by line.** A secret
   that spans lines (a PEM private key block) is one match for the
   pattern list, so redacting a fragment at a time would leave the body
   of the key in the log.
4. **The redacted console output stays valid.** The board's JSON is
   printed through `emit` as well. A redaction is a replacement inside a
   string, so the JSON the tick reads is still JSON.
5. **The records are unchanged.** `write_record` and `append_record` were
   already redacting; this part does not touch them, and the receipt
   writer's own comparison (the receipt on disk against the body it would
   write) still holds.
6. **Nothing else changes.** No merge rule, no push rule, no slot cap,
   no Ascend rule, no approval dialog handling, no second queue. The
   redaction is a regular expression pass over a string.

## The proof

The real commands, on a fixture whose board, queue and threads are
stubbed (`evidence/MO-216/proof-harness.sh`, transcript in
`evidence/MO-216/proof.log`). The fixture carries a fake key in a thread
report (the gate's own findings) and in a pull request title.

Run 1, the old module (origin/main) prints the key:

```
old: the fake key in the console output: 1
```

Run 2, the new module prints the same board:

```
new: the fake key in the console output: 0
new: redactions in the console output: 1
```

The same line, old and new:

```
old (origin/main): "title":"Fixture pull request GITHUB_TOKEN=ghp_EXAMPLEEXAMPLEEXAMPLEEXAMPLE"
new (this branch): "title":"Fixture pull request GITHUB_TOKEN=[REDACTED:github token] builder check does not name this head"
```

Run 3, a dry shift with the fake key in the thread report. The shift
writes the receipts, the shift log and the morning report under the
fixture root:

```
$ python3 coordinator/overnight/overnight shift --root "$FIX"
shift exit: 0
$ python3 coordinator/overnight/overnight report --root "$FIX" --date 2026-11-14
report exit: 0
```

Run 4, the grep:

```
$ grep -r "ghp_EXAMPLEEXAMPLEEXAMPLEEXAMPLE" "$FIX"
grep exit=1 (1 means no match)
```

No file under the fixture root holds the fake key: not the receipts, not
the shift log, not the morning report, not the policy snapshot.

Run 5, the shift's own console output, which is what launchd writes to
the job log:

```
the fake key in the shift's own console output: 0
redactions in the shift's own console output: 15
```

Run 6, the receipt the shift wrote, with the title it read:

```
# MO-999

- Item: Fixture pull request GITHUB_TOKEN=[REDACTED:github token]
- Repo: shyamsivakumar/mac-ops
- Ticket: MO-999 (#123)
- State: stuck
- PR: https://github.com/shyamsivakumar/mac-ops/pull/123
- Checks: `gh pr checks 123 -R shyamsivakumar/mac-ops` exit 0
- Gate: FAIL
- Files: 1
- Builder thread: t-mo216-builder
- Time used: 90 min
- Observed: 0 s
- Stopped because: the gate did not pass
- Next: the builder fixes the gate findings and the gate runs again
```

The gate's verdict is FAIL because the stubbed thread report ends with
`VERDICT: FAIL`, so the thread was really read.

## The checks

- `python3 scripts/mac_ops_fast_check.py` -> passed.
- `~/.local/bin/heavy python3 scripts/mac_ops_fast_check.py` -> passed
  (exit 0; the full local check per `README.md`, "Check a task").

No new unit test files were written, per the ticket. The proof is the
real command and the real grep.
