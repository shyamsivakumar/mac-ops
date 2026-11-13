# MO-208 decisions

Run id: `ticket:shyamsivakumar/mac-ops#176:a1`. Refs #176.
Ticket: https://github.com/shyamsivakumar/mac-ops/issues/176
Spec: the overnight runner spec (issue #172), revision 2.
Part: T3a of the spec's rollout plan - intake reads the board and the open
pull requests.

Note on the pull requests: PR #203 merged the first version of this part
while the reviewer round was still running. The review fixes came after
that merge, so they ride in a follow-up pull request on the same branch
line. Both carry `Refs #176`.

## What landed

- `coordinator/overnight/overnight`: the overnight module's command line, a
  read-only Python program with one subcommand.
  - `overnight intake --dry-run` reads `ticket list --fresh --json` for the
    tickets and `gh pr list` for each allowed repository, turns them into
    intake records and prints the record count per repository.
  - The allow list is the board config (`tickets.json`), the same file the
    ticket CLI reads. The Ascend repositories are not in it, and no Ascend
    rule is written here.
  - A pull request that a board ticket names is part of that ticket's
    record. A pull request no board ticket names is a record of its own. One
    work item is one record, so the shift cannot pick the same item twice.
    A keyword reference (`Refs #n`, `Fixes #n`, `Closes #n`, `Resolves #n`
    in the body or title) names a GitHub issue number. A branch name
    carries a ticket key (`mo-208`), whose number is a different counter,
    so a branch is looked up by key and never by issue number.
  - The command writes no record, keeps no list of its own and holds the
    records in memory for the run. `overnight intake` without `--dry-run`
    refuses with a clear line, because this part has no write path.
  - A repository whose pull requests cannot be read, or whose pull request
    list is cut off at the limit, shows `ERR` in its cells, and the total
    reads UNVERIFIED. A board ticket in a repository the allow list does
    not name is counted and marked "not allowed".
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
  carries the pull requests. A pull request that no board ticket names is a
  record of its own.
- **The gap**: The board and the pull requests are two lists, and a naive
  read would produce two records for one piece of work.
- **The reach**: The later parts order the work (T3c) and the tick works it
  (T5). With one record per item, an item with an open pull request cannot
  be started twice, and the "pull requests already open" ordering rule
  reads the record's `prs` field.
- **Verdict**: sound, after the reviewer round. The first version linked a
  branch name by its number as a GitHub issue number, which was wrong: the
  board key number and the issue number are different counters. A branch is
  now looked up by board key.
- **Confidence**: high for the rule, medium for the link. The link is a
  keyword in the body or title, or the repository key and number in the
  branch name. A pull request that names its ticket in some other way, or
  names a ticket the board does not show, stays a record of its own, which
  is the safe direction: it shows up for a human to look at.

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
   repositories, with the command and its exit code at the top of
   `evidence/MO-208/intake-dry-run.log`. It read `ticket list --fresh
   --json` and `gh pr list` per repository, wrote no record, changed no
   queue, and left the ticket CLI's own cache as the only file it touched.
2. **The link, after the reviewer's fix.** Four strategy-replay-workbench
   pull requests are part of a board ticket's record: #855 to SRW-1038
   (issue #853), #976 to SRW-1100 (#975), #895 to SRW-685 (#468) and #878 to
   SRW-1016 (#843). A pull request that names a ticket the board does not
   show (for example #987, whose body says "Refs #940" while #940 has left
   the backlog and todo stages) stays a record of its own, and so does one
   that names nothing.
3. **The branch key is a key, not an issue number.** The pull request
   `work/ffbt-9-agentic-ci` (#412) has a branch that carries the ticket key
   FFBT-9. It stays a record of its own, because no board ticket has that
   key. Before the fix it resolved to issue #9, which is a different
   ticket.
4. **The installer.** `python3 install_coordinator.py --dry-run` lists
   `~/.local/bin/overnight` and the `.overnight/README.md` copy as the
   files it would write, and creates no folder. The real install wrote the
   command to `~/.local/bin/overnight`, and a second install wrote 0 files.
5. **Checks.** `python3 scripts/mac_ops_fast_check.py` passed. The full
   suite, `python3 -m unittest discover -s tests -t .`, through
   `~/.local/bin/heavy` ran 116 tests and passed.

## The reviewer round

One in-session reviewer round (Opus 5.5) read the diff of the first version
of this part (`git diff origin/main...HEAD` at that point) and returned
`VERDICT: PASS` with one major finding, five minor findings and six nits.
What was done with them:

1. **Major, fixed.** The branch fallback took the number from a ticket key
   and looked it up as a GitHub issue number. The board key number and the
   issue number are different counters (MO-208 is issue #176, SRW-1100 is
   issue #975), so the branch is now looked up by key in the board's own
   keys, and never by issue number. The keyword path still looks up the
   issue number, which is what a keyword names. The docstring and decision
   3 now say that the branch is the fallback and the keyword the first
   signal.
2. **Minor, fixed.** A repository whose pull requests cannot be read, or
   whose pull request list reaches the limit, now shows `ERR` in its pull
   request, linked and record cells, the total reads UNVERIFIED, and the
   reason is on stderr. Before, stdout showed zero for that repository.
3. **Minor, fixed.** The pull request limit is now detected: a repository
   that reaches `PR_LIMIT` is reported, its counts are not claimed, and the
   total reads UNVERIFIED.
4. **Minor, fixed.** The whole intake now runs inside one deadline
   (`--deadline`, 540 seconds by default), and every command gets what is
   left of it. The worst case was 300 seconds plus 15 times 60 seconds,
   which is past the ten-minute turn cap.
5. **Minor, fixed.** A board ticket in a repository the allow list does not
   name is counted and printed, marked "not allowed", so the printed total
   and the board count cannot disagree silently. This happens when the
   module's config and the ticket CLI's config differ.
6. **Minor, fixed.** The proof claimed six linked pull requests. It is
   four, and the proof now says four and explains the off-board case.
7. **Minor, fixed.** This section claimed a verdict before the review had
   run. It now records what the review said and what came of it.
8. **Nit, fixed.** The dead `raise AssertionError("unreachable")` lines
   after every `die()` are gone; `die()` is `NoReturn`. The
   `except SystemExit` around the pull request reads is now a `RepoError`
   that names the repository.
9. **Nit, fixed.** The README and the module docstring said "writes
   nothing". They now say the ticket CLI refreshes its own cache when it
   reads the board, and that the cache is the ticket CLI's, not a queue of
   the shift's.
10. **Nit, fixed.** A ticket record now carries a list of pull requests
    (`prs`), so two pull requests that name the same ticket both sit on
    that ticket's record instead of one of them standing alone.
11. **Nit, fixed.** The proof log starts with the command and its exit
    code, as the spec's evidence rule asks.
12. **Nit, noted.** The branch build is installed on the live Mac. The
    command only reads, and the rollback note already says the installed
    file can be removed by hand.

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
repository with more open pull requests than that has its counts reported
as UNVERIFIED rather than counted, so the shift never trusts a short
count. No repository on the board is close to that today.

The linking is a keyword in the body or title, or the repository key and
number in the branch name. A pull request that names its ticket in some
other way stays a record of its own. The later parts (T3b, T3c) may tighten
this once they decide what a work item is.

---

# MO-208 decisions, attempt 2

Run id: `ticket:shyamsivakumar/mac-ops#176:a2`. Refs #176.
Same part: T3a of the spec's rollout plan. Attempt 1 delivered the part
(PR #203, then the reviewer fixes in PR #205). The ticket stayed open, so
this attempt re-reads the merged code against the brief, proves it by
running the real command, and fixes what the re-read found.

## What the re-read found

The merged code does what the brief asks. The dry run on today's board
prints the record count per repository, reads the board through
`ticket list --fresh --json` and the pull requests through `gh pr list`,
and writes nothing. Three defects came out of reading it again.

### 1. A pull request whose body names a ticket the board does not show was never linked

The keyword reference decided the link on its own. A pull request whose
body says `Refs #999`, where issue 999 has left the board, was never
linked to anything, even when its branch carried the key of a ticket that
is on the board (`t3/aa-10-second-fix`). It became a record of its own.

That is the harm decision 3 exists to prevent: the ticket and its pull
request were two work items, and the shift could have worked the same
piece of work twice.

**Fixed.** The keyword decides when it names a ticket the board shows.
When it names one the board does not show, the branch is still read. A
pull request that names neither is still a record of its own.

**Proof.** A fixture run of the real command, with the ticket and `gh`
commands replaced by stubs, before and after:

| | linked | records |
| --- | --- | --- |
| merged main | 2 | 5 |
| this attempt | 3 | 4 |

The fixture holds four pull requests: one whose body says `Refs #10` (the
issue is on the board), one whose body says `Refs #999` (that issue is not
on the board) and whose branch carries the key of a ticket that is, one
whose branch carries a key and no keyword, and one that names nothing.
The first three join their ticket; the last stays a record of its own.

### 2. The total counted records from repositories outside the allow list

The total added the records of the repositories the allow list does not
name, and then said "across 15 repositories", the number of allowed
repositories. When the board holds a ticket in a repository the allow list
does not name, the printed total and the printed repository count
disagreed.

**Fixed.** The total counts the allowed repositories that read cleanly.
The records outside the allow list are printed on their own line, with
their own count.

**Proof.** The real command with a fixture board config that leaves
`strategy-replay-workbench` out of the allow list:

```
shyamsivakumar/strategy-replay-workbench            56   n/a     n/a       56  (not allowed)

Total: 80 records across 14 repositories
56 more records in 1 repository, outside the allow list, counted above and marked 'not allowed'.
```

Before, the same run printed "Total: 136 records across 14 repositories".

### 3. A board ticket without a key carried a null key into its record

23 of the 117 board tickets have no key today. Their records carried
`null` where the other records carried an empty string, so a later part
that reads `record["key"]` had to handle both.

**Fixed.** The record carries an empty string, like the other fields.

## The reviewer round

One in-session reviewer round read `git diff origin/main...HEAD` for this
attempt. What it said and what came of it is in the section below, once
the round has run.

## Checks

`python3 scripts/mac_ops_fast_check.py` passed. The full suite,
`python3 -m unittest discover -s tests -t .`, through `~/.local/bin/heavy`
is recorded in the pull request body next to the `Builder check:` line.

## Rollback

Revert the commit and run `python3 install_coordinator.py` again. The
installed `~/.local/bin/overnight` is left in place by the installer's
backup transaction; removing it by hand is safe.
