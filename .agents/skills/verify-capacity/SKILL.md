---
name: verify-capacity
description: Verify bounded no-growth and resource-ceiling properties after changing Mac load controller decisions.
---

# Capacity safety verification

Run from the mac-ops checkout:

```sh
heavy python3 verify_capacity.py --mutation-check
```

The check explores the actual `board_governor.decision` and `_capacity_decision` implementations across slot counts 0 to 16, 2/14/32 cores, 12/48/128 GiB, six load fractions, and three pressure levels. It also replaces required input fields with malformed or missing readings and runs healthy sequences. Above-floor growth on bad readings must never occur. A fresh noncritical sample restores the baseline of two, bounded by the hardware ceiling. Healthy growth above that baseline is at most one slot, and the decision must obey its computed ceiling. Compressor, swap-use and swapout growth must each veto growth independently.

The mutation checks alter the actual decision source at the critical-pressure branch and the active heavy controller host-veto branch to add one slot. The verifier must reject both mutations. No repository source is changed. A passing unmutated result and detected mutation are required together.

Coverage: `board_governor.py:decision` and `_capacity_decision`, `board_governor.json`, and `verify_capacity.py` at the first MO-2 migration commit. Before advancing the coverage record to a later revision, read those files and confirm the checker still reaches the live decision. Use `git log --format=%H -- verify_capacity.py` to identify the recorded source commit.

Python has no installed source verifier here. The check uses generated inputs against the real function, with finite bounds. It does not prove arbitrary Python inputs, OS scheduling, process identity races, launchd behavior, installed board enforcement, or real load response. Use historical replay and native process acceptance for those layers. A failure is a finding until a source or checker mismatch is demonstrated. Do not weaken the property to make it pass.
