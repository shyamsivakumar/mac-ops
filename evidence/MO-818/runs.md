# MO-1189 (#818) runs

## Proof command (adapted)

The ticket's command prints `os.path.dirname(e[g.ROOT_VAR])`. It is run as written, with `TMPDIR=$HOME`, against a copy of
origin/main's `gh_isolation.py` for "before" and against the branch for "after". Both are Python-only reads, no suite runs.

    before (origin/main, TMPDIR=$HOME):                /Users/shyamsivakumar
    after  (branch,      TMPDIR=$HOME):                /private/tmp/mac-ops-test
    after  (branch,      TMPDIR=$HOME/Code):           /private/tmp/mac-ops-test

The roots the runs made were removed by their `atexit` hook, and `ls -d ~/mac-ops-test-*` shows the same 7 folders before and
after the branch runs, so the branch writes nothing to the home folder.

## Expiry

Scratch base with four roots (a stand-in `TMPDIR`, nothing under `~`), then `gh_isolation.environment()` once:

| Root | Owner pid | Age | Result |
| --- | --- | --- | --- |
| old-dead | 999999 (gone) | 2026-11-01 | removed |
| old-nopid | no `owner.pid` | folder 2026-11-01 | removed |
| old-live | this shell (alive) | 2026-11-01 | kept |
| young-dead | 999999 (gone) | now | kept |
| outside-old (sibling of the base, old) | n/a | 2026-11-01 | untouched |

Only children of `<temp>/mac-ops-test/` are visited.

## The `pr view 169` refusal

Not reproduced, and the sender was not found in the repo. Facts gathered:

- The refused text `pr view 169 --json state,reviewDecision,author,comments,reviews,headRefOid,mergeCommit,statusCheckRollup` is in no
  source file, test or fixture of the repo (searched for `reviewDecision`, `mergeCommit,statusCheckRollup`, `169`, every `pr view`
  caller). It has no `-R`, which every repo caller passes, so it is not a repo `gh` call.
- `169` is the ticket number in the live receipt key `ticket:shyamsivakumar/mac-ops#169:a1` in `~/Code/coordinator/queue/dispatch-receipts.json`.
  The number came from live state, not from a test fixture.
- Both failing runs predate a fix that stops a suite reading live state: #737/#738 (09:37) ran before #750 (13:23, the selftest read the live
  `queue.json`); #792's first run was on 31a9db68 (16:22), three minutes before #817 (16:25) put a fake `t3mcp` in the isolation, so
  that run's `coordq` calls reached the real T3 server. Rerunning with an empty `COORDQ_DIR` passed (MO-514 runs.md).
- This ticket's per-run root does not change shared state: the fast check already made a fresh root and an empty `COORDQ_DIR` per run.

The cause is UNCERTAIN. The fast check on this head is the one run that shows whether it still happens.

## Leftover folders in the home folder (not deleted by code)

- /Users/shyamsivakumar/mac-ops-test-_c26c6cu
- /Users/shyamsivakumar/mac-ops-test-442974ei
- /Users/shyamsivakumar/mac-ops-test-4ymvzxcv
- /Users/shyamsivakumar/mac-ops-test-7320vjav
- /Users/shyamsivakumar/mac-ops-test-bcur8952
- /Users/shyamsivakumar/mac-ops-test-muke92_z
- /Users/shyamsivakumar/mac-ops-test-yn7xrvf5

## Expiry cannot escape the isolation base (gate fix)

Run in a temp sandbox on the fixed code (`python3 -I proof.py`):

```
1 symlink base: target kept = True | root under real tmp = True
2 child symlink skipped, outside kept = True
3 old no owner.pid kept = True
4 old dead pid removed = True
```

## A pre-existing 0755 base is repaired (coordinator follow-up)

```
0755 base now mode 0o700 | used as parent = True | expiry ran (dead removed) = True
symlink still rejected = True
```
