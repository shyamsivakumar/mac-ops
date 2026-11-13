# MO-208 decisions

Run id: `ticket:shyamsivakumar/mac-ops#176:a1`. Refs #176.
Ticket: https://github.com/shyamsivakumar/mac-ops/issues/176
Spec: the overnight runner spec (issue #172), revision 2.
Part: T3a of the spec's rollout plan - intake reads the board and the open
pull requests.

## What landed

- `coordinator/overnight/overnight`: the overnight module's command line, a
  read-only Python program with one subcommand.
  - `overnight intake --dry-run` reads `ticket list --fresh --json` for the
    tickets and `gh pr list` for each allowed repository, turns them into
    intake records and prints the record count per repository.
  - The allow list is the board config (`tickets.json`), the same file the
    ticket CLI reads. The Ascend repositories are not in it, and no Ascend
    rule is written here.
  - A pull request that a board ticket names (`Refs #n`, `Fixes #n`,
    `Closes #n` or `Resolves #n` in the body or title, or the repository key
    and number in the branch name) is part of that ticket's record. A pull
    request no ticket names is a record of its own. One work item is one
    record, so the shift cannot pick the same item twice.
  - The command writes nothing, keeps no list of its own and holds the
    records in memory for the run. `overnight intake` without `--dry-run`
    refuses with a clear line, because this part has no write path.
- `install_coordinator.py`: the installer copies the command to
  `~/.local/bin/overnight`, next to `ticket`, `coordq` and `coord-tick`.
- `coordinator/overnight/README.md`: the module contract now names the
  command and what it does.

Not touched: the merge, push and slot-cap rules, the Ascend rules, the
coordq queue, the launchd jobs, the tick, and every existing installer
behaviour. No existing test or check was weakened.

## Decisions

### 1. The module gets its own command, not a subcommand of `ticket`

- **When**: revision 1.
- **The decision**: The overnight module's command line is
  `coordinator/overnight/overnight`, installed as `~/.local/bin/overnight`.
  It does not add a subcommand to the `ticket` CLI.
- **The gap**: The ticket CLI already reads the board, so adding
  `ticket intake` looked like the smaller change.
- **The reach**: The spec's later parts (arm, the tick's work, the morning
  report) are shift commands, not ticket commands. Keeping them in the
  overnight module leaves the `ticket` CLI as the board's reader and the
  `overnight` command as the shift's.
- **Verdict**: sound.
- **Confidence**: high.

### 2. The allow list is the board config, not a second list in the module

- **When**: revision 1.
- **The decision**: Intake reads `tickets.json`, the file the ticket CLI
  reads, and takes its `repos` block as the allowed repositories. There is
  no allow list in the module and none on disk.
- **The gap**: The spec names an allow list as a policy input (section 15,
  question 4), and revision 2 says the shift keeps no second queue.
- **The reach**: The board config is already the coordinator's list of the
  repositories it works on, so the shift and the day board agree by
  construction. The spec's Ascend repositories are not in that list, so the
  intake cannot offer Ascend work. A later part (T4) can narrow the list
  when it writes the policy snapshot; that part, not this one, owns the
  policy.
- **Verdict**: sound.
- **Confidence**: medium. Shyam's answer to the spec's question 4 may name
  three repositories for v1 instead of the fifteen the board config holds.
  That answer changes the config, not this code.

### 3. One record per work item, not one record per ticket and one per pull request

- **When**: revision 1.
- **The decision**: A ticket with an open pull request is one record that
  carries the pull request. A pull request that no board ticket names is a
  record of its own.
- **The gap**: The board and the pull requests are two lists, and a naive
  read would produce two records for one piece of work.
- **The reach**: The later parts order the work (T3c) and the tick works it
  (T5). With one record per item, an item with an open pull request cannot
  be started twice, and the "pull requests already open" ordering rule
  reads the record's `pr` field.
- **Verdict**: sound.
- **Confidence**: medium. The link is a keyword in the body or title, or
  the repository key and number in the branch name. A pull request that
  names its ticket in some other way stays a record of its own, which is
  the safe direction: it shows up for a human to look at.

### 4. A stale board is reported, not hidden

- **When**: revision 1.
- **The decision**: `ticket list --fresh --json` can answer with a stale
  cache when GitHub is unreachable. Intake prints that on stderr and says
  "stale" in its header, and keeps the records it has.
- **The gap**: The ticket CLI falls back to its cache by itself; nothing
  downstream knows the list is old.
- **The reach**: The morning report counts records, so a count taken from a
  stale board is a count of the wrong thing. Saying so on stderr and in
  the header keeps the reader honest, and the shift can decide later what
  a stale board means.
- **Verdict**: sound.
- **Confidence**: high.

### 5. `--dry-run` is required in this part

- **When**: revision 1.
- **The decision**: `overnight intake` without `--dry-run` prints one line
  and exits 2. The command reads only.
- **The gap**: The spec's intake step writes a one-line summary to the shift
  log. That write belongs to the part that owns the shift log.
- **The reach**: Nobody can read a bare `overnight intake` as "the shift
  started". When a later part adds the write path, `--dry-run` stays the
  read-only mode.
- **Verdict**: sound.
- **Confidence**: high.

### 6. No new unit test file; the real command is the proof

- **When**: revision 1.
- **The decision**: This part adds no test file. The proof is the command
  run for real against today's board, and the installer run for real.
- **The gap**: The spec's revision 2 says no new unit test files, and the
  brief repeats it.
- **The reach**: The existing `tests/test_install_coordinator.py` still
  passes and still covers the installer's file plan and backup behaviour.
- **Verdict**: sound.
- **Confidence**: high.

## Proof

1. **The real command.** `overnight intake --dry-run` on this Mac's board
   printed the record count per repository for all fifteen allowed
   repositories (see the transcript in this file's proof log). It read
   `ticket list --fresh --json` and `gh pr list` per repository, wrote
   nothing, and changed no queue.
2. **The link.** On the strategy-replay-workbench board, six pull requests
   named a board ticket and became part of that ticket's record; the pull
   requests that named nothing stayed records of their own.
3. **The installer.** `python3 install_coordinator.py --dry-run` lists
   `~/.local/bin/overnight` and the `.overnight/README.md` copy as the
   files it would write, and creates no folder. The real install wrote the
   command to `~/.local/bin/overnight`, and a second install wrote 0 files.
4. **Checks.** `python3 scripts/mac_ops_fast_check.py` passed. The full
   suite, `python3 -m unittest discover -s tests -t .`, through
   `~/.local/bin/heavy` ran 116 tests and passed.

## The reviewer round

One in-session reviewer round (Opus) read `git diff origin/main...HEAD` and
returned `VERDICT: PASS`. What was done with its findings is recorded here.

## After the merge

```sh
cd <mac-ops checkout on merged main> && python3 install_coordinator.py
overnight intake --dry-run
```

## Rollback

Revert the commit and run `python3 install_coordinator.py` again. The
installed `~/.local/bin/overnight` is left in place by the installer's
backup transaction; removing it by hand is safe.

## Known gap, out of scope here

`gh pr list` is asked for at most 100 open pull requests per repository. A
repository with more open pull requests than that would be under-counted,
and the count would not say so. No repository on the board is close to
that today.
