# MO-1055 runs

## Red on origin/main

On origin/main, `grep -q verdict_block_missing coordinator/bin/gate_score.py`
finds nothing (count 0).
The proof exits 1 with `gate_score.py has no missing-block guard`.

## Green on the branch (`evidence/MO-1055/proof.sh`)

<!-- markdownlint-disable MD013 -->

```text
block scored, dropped: 1
prose unchanged: True dropped: 0 findings_of: None
1 block ballot + 2 prose: Merged gate review of 3 reports on abc123: only 1 carried a JSON verdict block with its own CHECK and PROVIDES lines for this head.
2 block ballots + 1 prose: Merged gate review of 2 reports on abc123: a finding stays when 2 agree on file, line within 5 and severity.
```

<!-- markdownlint-enable MD013 -->

A prose-only reply is returned unchanged. When `findings_of` is None,
`lane_driver.second_pass` journals `verdict_block_missing` once per thread.
