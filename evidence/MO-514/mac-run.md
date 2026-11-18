# Mac run evidence (MO-514)

The worktree cleaner on this Mac, at the head of PR #545.

## Dry run

`python3 scripts/worktree-cleaner/cleaner.py --dry-run --no-report`

- repositories scanned: 71
- worktrees scanned: 238
- categories: safe 0, needs a look 112, in use or protected 55, prune 0
- eligible (would be removed): 0
- excluded repositories: 32
- held: 238
- candidates with bootstrap files only: 0

Reasons per worktree:

| reason | worktrees |
| --- | --- |
| worktree outside the scan scope | 84 |
| worktree dirty | 79 |
| pull request not closed for the head | 52 |
| live T3 thread | 39 |
| remote commit unverified | 20 |
| pull request open | 16 |
| detached worktree not proven 24 hours old | 16 |
| process has its working directory inside | 13 |
| worktree missing or prunable | 10 |
| status unknown | 1 |
| main checkout | 71 |

No worktree on this Mac currently holds only agent bootstrap files, so the
bootstrap rule changes no count here. Every worktree that needs a look
holds real files, so it stays.

## Real run

`python3 scripts/worktree-cleaner/cleaner.py --apply --no-report`

- removed: 4
- categories after the run: safe 0, needs a look 109, in use or protected 50, removed 4
- eligible after the run: 0
- held after the run: 230

The append-only log `worktree-cleaner.log` recorded one `removal_attempted`
and one `removed` entry per worktree, each with the repo, the path, the
branch and the head:

| path | branch | head | on the default branch |
| --- | --- | --- | --- |
| `~/.t3/worktrees/fantasy-football-toolkit/t3-3973622e-531f491fa46dd6f7` | `t3/league-intelligence-workspace-6` | `974e10970ab80262b5d05732fc6e7d643d22f5d9` | yes |
| `/private/tmp/macops-main` | detached | `13c79aedc6fa611f3eb171fb3904f72ffd3828f4` | no, removed by the 24 hour rule |
| `~/.t3/worktrees/mac-ops/t3-e7e8696e-f284ea12ebd41fa7` | `t3/heavy-m1-memory-headroom-per-host` | `13c79aedc6fa611f3eb171fb3904f72ffd3828f4` | yes |
| `~/Code/mac-ops/.claude/worktrees/agent-a95ad4d3bad0d5625` | `remove-empryo` | `758710924a397ab59a1418a6a816ad1e76f82090` | yes |

## GitHub confirmation for every removed head

`gh api repos/<repo>/commits/<head>` returned the same head for each of the
three distinct commits, so every removed worktree was already on GitHub:

```
974e10970ab80262b5d05732fc6e7d643d22f5d9  974e10970ab80262b5d05732fc6e7d643d22f5d9
13c79aedc6fa611f3eb171fb3904f72ffd3828f4  13c79aedc6fa611f3eb171fb3904f72ffd3828f4
758710924a397ab59a1418a6a816ad1e76f82090  758710924a397ab59a1418a6a816ad1e76f82090
```

Every branch of the removed worktrees still exists locally, and no remote
ref changed.

## The removal log on this Mac

The installed cleaner writes the same record to
`~/.local/state/mac-ops/worktree-cleaner.log`. A recent entry from it:

```json
{"branch": "t3/reconcile-release-docs-m1", "event": "removed", "head": "0133d324c60a1b9e71cc05d72155f0062d9da3cb", "path": "/Users/shyamsivakumar/.t3/worktrees/tunerise/t3-ded6acbb-0f4627a17f56af87", "pull_request": "https://github.com/shyamsivakumar/tunerise/pull/26", "reason": "clean, remote commit verified, no live T3 thread, and closed PR or detached idle for 24 hours", "removed_at": "2026-11-18T06:44:21.921435+00:00", "repo": "/Users/shyamsivakumar/Code/tunerise"}
```

Device, handset and live-service testing was waived by Shyam on 2026-11-14
("no testing is needed"), so no device or live-service case was run for this
change. The runs above are the local cleaner on this Mac.
