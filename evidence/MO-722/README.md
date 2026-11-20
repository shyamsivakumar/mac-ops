# MO-722 evidence

## Who wrote the 2026-11-18 `"by": "provider_block"` entry

The writer is `record_block(selection, reason, failed=None, now=None, by="provider_block")`
in `coordinator/bin/provider_block.py`. Commit `40d1f5c0` (#555, 2026-11-18 11:25 -0800)
added it with the record shape `{"reason", "since", "until", "by"}`. Commit `3b910bf7`
and the merge `5bff8dd2` (#556, 11:56) called it from coordq's launch-failure branch
and from gatekeep's dead-gate retry through `provider_block.block_run`. The revert
`48ab07aa` (12:18) removed it again.

That module is not on `origin/main` (`0dfc6efd`). It lives only on the unmerged
branches `t3/provider-block-reset-time` and `t3/gate-reviewer-fallback`. The entry was
most likely written by a coordq run built from one of those branches during the window
above (inferred: the entry's shape matches `record_block`, and the file's history is not kept).

Searches, read only:

- This repo, `~/Code/coordinator` and `~/.local/bin`: no current file calls
  `record_block` or writes `"by": "provider_block"`. The only other hits are
  `evidence/MO-709/replay.py` and `evidence/MO-1134/replay.py`, which write that string
  into a temp copy of the file as a reader fixture and check the live file's hash is
  unchanged.
- `~/Code/coordinator/queue/providers-blocked.json` no longer holds that entry. It now
  holds t1j's manual `openai-api:gpt-6.2-astra` entry from 2026-11-20 and four manual
  entries.

Reuse: not reused. The writer is not in this repo's main, and `models.block_provider`
(MO-709) is the store writer main already has. It writes `expires_at`, keeps a manual
or longer block, and takes the same lock the readers use. This change calls it.
