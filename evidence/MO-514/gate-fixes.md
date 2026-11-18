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

## How the fixes are proved

The unit tests above run in the repo check whenever the cleaner changes:

```sh
python3 -m unittest tests.test_worktree_cleaner_bootstrap
```

They were run against the cleaner at the head the gate reviewed, `84fd296`:

```
FAIL: test_mode_change_is_real_work
FAIL: test_staged_mode_change_is_real_work
FAIL: test_stale_origin_head_grants_nothing
Ran 11 tests in 1.590s
FAILED (failures=3)
```

and against the current cleaner, where all eleven pass.

The end to end fixture builds real repositories, a local bare remote and stub
GitHub and `t3mcp` CLIs, and covers the worktrees that must be removed and the
worktrees that must be kept:

```sh
python3 verification/worktree-cleaner/check_bootstrap.py
```
