# `ticket open` runs the proof on main

For a repo with `"proofOnOpen": true` in `tickets.json`, `ticket open` runs the
ticket's `Proof command:` on `origin/main` in a throwaway checkout (through
`proof_run.py`) and opens the ticket only when the proof is red for the
intended reason. The repo's checkout comes from `repos.<repo>.checkout`, and
`--repo-dir` overrides it. Other repos skip the run and record `"proof":
"unchecked"` in the `ticket_opened` row.

A behavior ticket names the failure it expects under the proof command:

```
Proof command: python3 scripts/check_x.py
Expected red signature: AttributeError: .*repo_dir
```

The signature is a regex matched against the proof's output. The outcomes:

- Red with a matching signature: the ticket opens, `proof` is `red`.
- The proof passes on main: refused, `proof passes on main: nothing to build`.
- The proof fails with another error, or times out at 120 seconds: refused with the
  output tail.
- No signature line: refused.
- `Proof command: none (prose)` (docs and config tickets): no run, `proof` is `prose`.

`--dry-run` runs the proof and prints the state; it writes nothing.

## Gatekeep refuses a head without a green proof only when asked

Gatekeep always runs the proof once per head for a `proofOnOpen` repo and
puts the record in the gate brief. It refuses to queue the gate for a red or
unresolved head only when `"proofRequired": true` is set for the repo in
`tickets.json` (or `COORD_PROOF_REQUIRED` is set). The refusal prints
`no proof record`, raises one board card and journals `gate_skipped` with
`reason=no_proof`. Prose and legacy tickets always gate.
