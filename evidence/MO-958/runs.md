# MO-958 runs

## Ticket proof on origin/main (red)
```
AttributeError: module 'cq' has no attribute 'scope_issue'
exit 1
```

## close-evidence eval (drives cmd_gatekeep over gate_candidates, stubbed GitHub) on origin/main code (red)
```
KeyError: 'issue'
exit 1
```

## Ticket proof on the branch (green)
```
exit 0
```

## close-evidence eval on the branch
```
in place OK
close-evidence OK
rc=0
```

Cases driven through cmd_gatekeep over gate_candidates: a PR with no receipt and Refs #951 (out of scope: no gate, one card, one scope_checked row; in scope: gated), the same two with a receipt (unchanged), and a PR naming no ticket (gated, no scope read). proof_gate runs only on the receipt path, as today.

Also found by the eval: gh_json returns a list of rows, so the ticket read in scope_gate (dict .get) would have raised in production. It now reads the first row.

## Live read-only attempt
```
gh_gateway.ApiBudgetExhausted: optional reads stopped: remaining={'core': 58, 'graphql': 0}, floor=1500
```
The gateway's API floor stopped the optional read (core 58, floor 1500). The floor was not bypassed, so no live candidate is shown.
