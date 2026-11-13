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
    to that repository's `.gitignore` when the rule is missing. The write goes
    through the same backup transaction.
  - `status` and `--dry-run` now report the overnight root, the folders that
    are missing and the files that would be written.

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
  coordinator folder. When a repository contains it, the installer adds
  `.overnight/` to that repository's `.gitignore` if no such line is there
  already. When no repository contains it, the installer writes nothing for
  the ignore.
- **The gap**: The spec says the folder is git-ignored, but the coordinator
  runtime folder is not a repository today, and the brief says to ignore it
  in any repository that contains it.
- **The reach**: The rule is idempotent: a second install finds the line and
  writes nothing. The installer never creates a repository and never edits a
  `.gitignore` that is already correct.
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

## The reviewer round

One in-session reviewer round (Opus) read `git diff origin/main...HEAD` and
returned `VERDICT: PASS`. What was done with its findings is recorded below.

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
