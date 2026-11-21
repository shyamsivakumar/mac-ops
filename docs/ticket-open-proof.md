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
