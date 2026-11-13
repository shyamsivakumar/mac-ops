# MO-205 decisions

Refs #173. Ticket: https://github.com/shyamsivakumar/mac-ops/issues/173
Spec: `~/Code/coordinator/specs/overnight-runner-spec.md` (issue #172), revision 2.
Part: T1 of the spec's rollout plan — the `.overnight/` layout plus the git
ignore.

## What landed

- `coordinator/overnight/README.md`: the overnight module's contract. It
  names the four folders and every file in the spec's section 6 table, and it
  says the board is the list, so there is no `punch-list.md` (revision 2).
- `install_coordinator.py`: the installer creates the layout.
  - `coordinator_dir()` finds the coordinator runtime folder: `--coordinator-dir`
    first, then `MAC_OPS_COORDINATOR_DIR`, then `~/Code/coordinator`.
  - `ensure_overnight_dirs()` creates `.overnight/{run,receipts,inbox,staging}`
    one level at a time, refusing a symlinked level.
  - The module's `README.md` is installed to `.overnight/README.md` through the
    installer's existing transactional write, so it is backed up like every
    other installed file.
  - `gitignore_item()` finds the repository that contains the coordinator
    folder with `git rev-parse --show-toplevel` and adds a `.overnight/` rule
    to that repository's `.gitignore` when git does not already ignore the
    folder (`git check-ignore` is the test, so a nested or global rule
    counts). The write goes through the same backup transaction.
  - `status` and `--dry-run` now report the overnight root, the folders that
    are missing and the files that would be written. `status` counts a
    missing folder as out of sync, so the layout and the files are checked
    together.
  - A coordinator folder that does not exist is reported and left alone: the
    installer creates nothing for it and says how to point at another one.

Not touched: the merge, push and slot-cap rules, the Ascend rules, the launchd
jobs, the coordq queue, and every existing installer behaviour. No existing
test or check was weakened.

## Decisions

### 1. The module is `coordinator/overnight/`, not a bolt-on on the installer

- **When**: revision 1.
- **The decision**: The overnight part has its own folder in the mac-ops
  checkout, `coordinator/overnight/`, next to `coordinator/bin`,
  `coordinator/pi` and `coordinator/mods`. The installer reads the module's
  README from there and writes it into the runtime layout.
- **The gap**: The brief asked for one `coordinator/overnight/` module and
  said to stop and report if the part only fitted as a bolt-on.
- **The reach**: Later parts (intake, arm, the tick's receipt write, the
  morning report) land in the same module folder and reuse the same layout
  contract. The folder names and the README are the only things this part
  needs from the module, and both are data the installer already reads from
  the checkout.
- **Verdict**: sound. The module is a real home, not a wrapper around an
  installer function, and this part fills it.
- **Confidence**: high.

### 2. The runtime folder is found, not hardcoded into the write path

- **When**: revision 1.
- **The decision**: The installer resolves the coordinator folder from
  `--coordinator-dir`, then `MAC_OPS_COORDINATOR_DIR`, then `~/Code/coordinator`,
  and writes `.overnight/` inside it.
- **The gap**: The installer's `plan()` maps fixed checkout files onto fixed
  home paths (`~/.local/bin`, `~/.coordinator`, `~/.config/herdr-app`,
  `~/.pi/agent-coordinator`). The runtime folder is a different kind of
  target: it lives in a checkout that the user owns, and it can move.
- **The reach**: A caller that wants another runtime folder passes one
  argument. The default stays the folder the coordinator already uses on this
  Mac, so the normal install needs no argument. Nothing else in the installer
  changes shape.
- **Verdict**: sound.
- **Confidence**: high.

### 3. `staging/` is scratch, and the board stays the only list

- **When**: revision 1.
- **The decision**: The installer creates `run`, `receipts`, `inbox` and
  `staging`. The README says `staging/` holds work in flight (worktree path,
  branch, builder notes) and is not a queue; the list is the GitHub board.
- **The gap**: The brief names `staging`, but the spec's section 6 table has
  no file in it. The spec's revision 2 also forbids a second queue.
- **The reach**: A later part may stage a diff while a builder works. Nothing
  reads the folder to decide what to work on, so the shift cannot drift into
  keeping its own backlog.
- **Verdict**: sound.
- **Confidence**: medium. The folder's exact purpose is set by the parts that
  come later; if one of them wants a different name, the README changes with
  it.

### 4. The README names the section 6 files and stops there

- **When**: revision 1.
- **The decision**: The README table carries the spec's section 6 rows as they
  are: `run/armed`, `run/deadline`, `run/policy.json`, `run/STOP`,
  `run/shift-log.md`, `receipts/<item>.md`,
  `receipts/morning-YYYY-MM-DD.md`, `inbox/parking-lot.md`,
  `inbox/snag-log.md`. There is no `punch-list.md` row.
- **The gap**: Revision 2 removed the punch list, and the file names come
  from the spec, not from this ticket.
- **The reach**: Later parts write the files the README names, so the README
  is the contract they answer to. If a later part adds a file, the README
  gains a row in the same commit.
- **Verdict**: sound.
- **Confidence**: high.

### 5. The ignore rule goes into the repository that contains the folder

- **When**: revision 1.
- **The decision**: The installer runs `git rev-parse --show-toplevel` on the
  coordinator folder. When a repository contains it, the installer asks git
  whether the folder is already ignored (`git check-ignore`), and adds
  `.overnight/` to that repository's `.gitignore` when the answer is no. When
  no repository contains it, the installer writes nothing for the ignore.
- **The gap**: The spec says the folder is git-ignored, but the coordinator
  runtime folder is not a repository today, and the brief says to ignore it
  in any repository that contains it.
- **The reach**: The rule is idempotent: a second install asks git, gets
  "ignored", and writes nothing. A repository that ignores the folder in
  another way (a nested `.gitignore`, `info/exclude`, the global excludes
  file) keeps its own rule and gets no second one. The installer never
  creates a repository and never edits a `.gitignore` that is already
  correct.
- **Verdict**: sound.
- **Confidence**: high.

### 6. No new unit test file; the real command is the proof
- **When**: revision 1.
- **The decision**: This part adds no test file. The proof is the installer
  run for real, once in a throwaway repository and once on this Mac.
- **The gap**: The spec's revision 2 says no new unit test files, and the
  brief repeats it.
- **The reach**: The existing `tests/test_install_coordinator.py` still
  passes, and it still covers the installer's file plan and backup
  behaviour.
- **Verdict**: sound.
- **Confidence**: high.

## Proof

1. **Live install.** `python3 install_coordinator.py` from the task worktree
   created `/Users/shyamsivakumar/Code/coordinator/.overnight/{run,receipts,
   inbox,staging}` and wrote `README.md` beside them. `ls -a
   ~/Code/coordinator/.overnight` shows the four folders and the README. The
   install wrote 1 file (the README); every other installed file was already
   in sync.
2. **The ignore, in a repository that contains the folder.** A throwaway
   repository under the home directory held a `coordinator/` folder with a
   `.gitignore` that had one existing rule. The install created the four
   folders and the README, added the `.overnight/` rule to the repository's
   `.gitignore`, and left the earlier rule alone. `git check-ignore -v
   coordinator/.overnight/README.md` matched `.gitignore:5:.overnight/`, and
   `git status --short` showed only the `.gitignore` edit — the folder and
   its README never appeared as untracked. The fixture was deleted afterwards.
3. **Idempotence.** A second install of the same fixture wrote 0 files and
   left the `.gitignore` unchanged.
4. **Checks.** `python3 scripts/mac_ops_fast_check.py` → passed. The same
   command through `~/.local/bin/heavy` → passed. The full suite,
   `python3 -m unittest discover -s tests -t .` → 116 tests, OK.
5. **A coordinator folder that is not there.** The installer against a
   coordinator folder that does not exist printed a warning, created nothing
   for it, and wrote 0 files. The same run against a real folder creates the
   four folders and the README.
6. **After the reviewer's fixes.** The fixture was run again: the four
   folders and the README, `git check-ignore` matched the rule, `git status`
   showed only the `.gitignore` edit, and the second install wrote 0 files.
   The live install on this Mac wrote the README again with the revised
   table, and `python3 install_coordinator.py status` reports `in_sync: true`
   with no missing folder.

## The reviewer round

One in-session reviewer round (Claude Opus 5.5) read `git diff
origin/main...HEAD` and returned `VERDICT: PASS` with two minor findings and
four nits. What was done with them:

1. **Minor, fixed.** The README was queued for writing even when the
   coordinator folder did not exist, so an install could leave a half-built
   layout (README, no folders). Both steps now ask the same question: the
   README is written and the folders are created only when the coordinator
   folder is there, and a missing folder is reported with the way to point
   the installer elsewhere.
2. **Minor, fixed.** This section claimed a verdict before the review had
   run. It now records what the review said and what came of it.
3. **Nit, fixed.** The "already ignored" test looked only for an exact
   `.overnight/` line in the top-level `.gitignore`. It now asks git with
   `git check-ignore`, so a nested, `info/exclude` or global rule counts and
   no second rule is added.
4. **Nit, fixed.** A `.gitignore` that is a symlink or cannot be read ended
   both `status` and `install` with an uncaught OS error. The installer now
   leaves that file alone and says so.
5. **Nit, noted.** `status` counts a missing overnight folder as out of
   sync, so the layout and the files are checked together. Nothing else
   reads `in_sync` today; the field is documented in the status output.
6. **Nit, fixed.** The README's file table now keeps the spec's section 6
   row order, and the `run/STOP` row names Shyam (or `overnight.sh stop`) as
   the spec does.

## After the merge

```sh
cd <mac-ops checkout on merged main> && python3 install_coordinator.py
ls -a ~/Code/coordinator/.overnight
```

## Rollback

Revert the commit and run `python3 install_coordinator.py` again. The
`.overnight/` folders are scratch and can be deleted by hand; the README copy
under `.overnight/` is removed by hand, because a reverted source no longer
overwrites it. The `.gitignore` rule is harmless and can stay.

## Known gap, out of scope here

The coordinator runtime folder is not a Git repository today, so the ignore
rule has nothing to attach to on this Mac. The rule is written the moment a
repository contains the folder, which the fixture proof exercises.
