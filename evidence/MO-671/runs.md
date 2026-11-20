# Runs

Command: `COORDQ_DIR=<temp dir> heavy python3 <replay script>`.
The script runs the gate-pipeline eval of
`coordinator/overnight/selftest.py`, recording the lane's `gate_verdict`.

Result: the eval passed. The verdict the lane read for each case, in case order:

```text
checked-head: absent
pass: PASS
prompt-pass: PASS
fail: FAIL
no-verdict: none
second-no-verdict: none
pass-then-no-verdict-attempt: PASS
fail-then-no-verdict-attempt: none
```

The case `pass-then-no-verdict-attempt` has a complete PASS on the head
and a later attempt with no verdict. The lane reads PASS and merges
(actions merge, provides, ff), as the case asserts.

Full overnight selftest with a temp `COORDQ_DIR`: 27 of 27 evals print PASS (`evidence/MO-671/selftest.out`).

## Retargeted head

The `gate-pipeline` eval has two retarget replays.

- `gatekeep_retarget`: a head gated on `main` (receipt `base:gate` = main) whose pull request now targets `other`. Gatekeep queues exactly one gate with `clientRequestId` `gate:<repo>#20:<head>:other`, and a second run queues nothing more. On the previous head the same replay queued the plain key, which the launch treats as the same request, and the eval failed: expected the `:other` key, got the plain key.
- `retargeted-regated-pass`: the new gate's receipt carries `base:gate` = other, the pull request targets `other`, and the lane reads PASS and merges (actions merge, provides, ff). `retargeted-after-pass` (old base PASS) still launches nothing.
