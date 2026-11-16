# MO-1007 delivery

Refs #346. Base: 9ff5e2b on fetched origin/main.

The launcher defaults COORD_WAKE to 1 and preserves an explicit 0.
The extension default prompt now matches the ticket exactly. COORD_TICK_PROMPT,
COORD_WAKE_MIN, /wake off, idle and pending-message guards remain unchanged.
The guard remains unchanged: coord-watch is not denied by checkBash; all existing
deletion, secrets, protected-path and installation restrictions still apply.
No automatic ticket start or separate scheduler was added.

Verification: `python3 scripts/mac_ops_fast_check.py` passed; `git diff --check`
passed. One in-session read-only review of the complete source diff found no
defects. Comment review retained the concise override documentation; cleanup
review found no additional in-scope changes needed. No rule breaks introduced.

Coordinator continuation waives the prior missing native dependency stop,
full-suite, fake-provider, device and live-service testing. No live activation
or provider calls performed. Runtime wake capture and live behavior remain
unverified. Provides wake-backlog can be claimed on main only after merge.

Reproduce static review with `git show -- coordinator/pi/bin/coord-pi
coordinator/pi/extensions/coordinator.ts` and the fast check above.

Left for later: coordinator Opus gate, merge and confirmation on origin/main;
README.md still describes the old off default (outside the scoped source edits).
