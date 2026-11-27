# MO-1024 proof

Command: `bash proof.sh <worktree>` (temp COORD_JOURNAL_DIR and decisions path).
It emits 3 gap rows (2 on one topic), runs `curator --dry-run`, then `curator`.

## origin/main (red)

origin/main lacks `coordinator/bin/curator` and `journal.emit_gap`:

```text
fatal: path 'coordinator/bin/curator' exists on disk, but not in 'origin/main'
```

## branch head (green)

```text
--- dry-run
{ "id": "gap-e22545c45a", "kind": "ask",
  "title": "Playbook gap: 2 workers lacked 'no playbook for cloud run deploys'",
  "cause": "2 gap rows on cards 1101, 1102", ... }
--- board after dry-run
{"items":[]}
--- write
raised gap-e22545c45a
--- board after write
['gap-e22545c45a']
```

The one-off topic (card 1103) raises no card (threshold 2).
Dry run leaves the board empty.
