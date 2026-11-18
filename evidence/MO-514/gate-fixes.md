# Gate findings and how they are fixed (MO-514)

Every finding the Astra gate reported on PR #545, the fix that answers it, and
the test that fails without the fix.

| # | finding | fix | test |
| --- | --- | --- | --- |
| 1 | the status was read as stripped text, so the leading space of the first porcelain record was lost and its path lost a character: an unstaged edit to `x.specstory/notes` was read as `.specstory/notes` and the worktree could be force-removed | `git status --porcelain=v1 -z`, parsed as NUL separated records that keep their status columns and their paths | `tests/test_worktree_cleaner_bootstrap.py::StatusColumnsTest::test_status_keeps_columns_and_paths` |
| 2 | a rename was classified by its destination only, so a staged rename of a real file into `.specstory/` looked bootstrap only | a rename is bootstrap only when the source and the destination are both bootstrap files | `verification/worktree-cleaner/check_bootstrap.py` (the `renamed` worktree) |
| 3 | any subset of the known rule lines made an `AGENTS.md` a bootstrap file, so one rule added by hand was enough | the added lines must match a whole known rules file, line for line and in order | `...::AgentsBootstrapTest::test_single_rule_is_real_work` |
| 4 | the `AGENTS.md` check compared diff lines and skipped every line starting with `+++`, so a genuine line beginning with `++` disappeared | the check compares file contents, never a diff | `...::AgentsBootstrapTest::test_block_plus_genuine_line_is_real_work`, `...::test_genuine_line_before_block_is_real_work` |
| 5 | the check compared the working copy with `HEAD` and ignored the index, so an `MM AGENTS.md` whose working copy held only `HEAD` plus the block was treated as disposable and its staged edit was discarded | the committed file, the staged file and the working copy must each be the committed file or the committed file plus exactly the rules block | `...::AgentsBootstrapTest::test_staged_genuine_edit_is_real_work` |
| 6 | any single heading between the committed file and the rules block was accepted, so a heading the user wrote could be discarded | no heading is accepted; nothing may sit between the committed file and the block | `...::AgentsBootstrapTest::test_user_heading_between_file_and_block_is_real_work` |
| 7 | the ancestry check accepted `origin/main` or `origin/master`, so a commit unique to `master` could qualify a worktree for removal | only the one default branch of the repository qualifies | `verification/worktree-cleaner/check_bootstrap.py` (the `masteronly` worktree), `...::DefaultBranchTest::test_only_the_default_branch_qualifies` |
| 8 | the `AGENTS.md` check compared contents only, so an executable bit change was invisible and the file looked untouched | the committed, staged and working copy must agree on the type and the executable bit as well as on the contents | `...::AgentsBootstrapTest::test_mode_change_is_real_work`, `...::test_staged_mode_change_is_real_work` |
| 9 | the default branch lookup passed `--repo` to `gh repo view`, which takes the repository as a positional argument, so the lookup always failed and the cleaner fell back to `origin/HEAD`; after a default branch change that ref still points at the old branch | `gh repo view <repository> --json defaultBranchRef`; only a default branch verified by GitHub grants ancestry based eligibility, and a stale `origin/HEAD` is not trusted | `...::DefaultBranchTest::test_stale_origin_head_grants_nothing` |
| 10 | the `AGENTS.md` check compared decoded text, so it stripped the committed trailing newlines and normalised CRLF to LF; a worktree whose committed file ended in two newlines, where the user removed one and appended the rules block, was accepted as the bootstrap and the removed newline or the changed line ending was discarded | the committed, staged and working files are compared as bytes; the committed bytes must stay intact in full and the only permitted change is the rules block appended to them | `...::AgentsBootstrapTest::test_removed_trailing_newline_is_real_work`, `...::test_line_ending_change_is_real_work` |
| 11 | the default branch name filter rejected a valid branch name such as `release/main`, so an otherwise eligible worktree stayed on disk | any name git accepts as a branch name is accepted | `...::DefaultBranchTest::test_valid_branch_names_are_accepted` |
| 12 | the cleanup verified the file and then unlinked it or overwrote it from `HEAD`, so an editor save that landed in between was lost before git looked at the worktree | each bootstrap file is compared with the bytes the scan saw, moved aside with an atomic rename, and compared again; a file that changed in between is put back only when the path is still free, so a save that landed there keeps its own file, and the worktree is kept | `tests/test_worktree_cleaner_bootstrap.py::ClearBootstrapChangesTest::test_a_save_after_the_scan_keeps_the_worktree`, `...::test_a_save_at_a_renamed_source_keeps_the_worktree` |
| 13 | a staged addition has no path in `HEAD`, so restoring it from `HEAD` failed and the worktree was never removed | a file with no path in `HEAD` is removed and dropped from the index, and the index of a tracked file is pointed back at `HEAD` without writing to the file | `...::ClearBootstrapChangesTest::test_a_newly_staged_bootstrap_file_is_cleared` |
| 14 | a bootstrap file that was deleted or renamed had no working-tree file to compare, so the cleanup refused and a finished worktree was never removed; a save that landed on the source of a rename was overwritten with the committed bytes | a path that is already gone has no edit to preserve, so the committed bytes are restored with an exclusive create and a path that came back is kept; the index entry is pointed back at `HEAD` with `--add`, and a file the scan never hashed is kept whenever it still exists | `tests/test_worktree_cleaner_bootstrap.py::ClearBootstrapChangesTest::test_a_bootstrap_rename_is_cleared`, `...::test_a_deleted_bootstrap_file_is_restored`, `...::test_a_save_at_a_renamed_source_keeps_the_worktree` |
| 14 | after the cleaner validated `AGENTS.md`, another process could stage genuine content while the working copy stayed unchanged, and the index reset erased that staged edit | the index is compared with the state the scan saw while the index lock is held, and the reset to `HEAD` happens only when nothing changed | `tests/test_worktree_cleaner_bootstrap.py::ClearBootstrapChangesTest::test_a_staged_edit_after_the_scan_is_never_erased` |
| 15 | when the moved file differed from the expected bytes and the editor had recreated the path, the recovery overwrote the editor's save | the recovery keeps both copies: the recreated path is left alone and the recovered copy is kept beside it | `...::ClearBootstrapChangesTest::test_a_recovery_keeps_both_copies`, `...::test_a_save_that_lands_before_the_restore_is_never_overwritten` |

## How the fixes are proved

The unit tests above run in the repo check whenever the cleaner changes:

```sh
python3 -m unittest tests.test_worktree_cleaner_bootstrap
```

They were run against the cleaner at the head the gate reviewed, `2b43775`:

```
FAIL: test_line_ending_change_is_real_work
FAIL: test_removed_trailing_newline_is_real_work
FAIL: test_valid_branch_names_are_accepted
Ran 14 tests in 1.877s
FAILED (failures=3)
```

and against the current cleaner, where all fourteen pass. The same tests fail
against `84fd296` for the mode, the stale `origin/HEAD` and the branch name
findings (3 failures out of 11 there).

The end to end fixture builds real repositories, a local bare remote and stub
GitHub and `t3mcp` CLIs, and covers the worktrees that must be removed and the
worktrees that must be kept:

```sh
python3 verification/worktree-cleaner/check_bootstrap.py
```
