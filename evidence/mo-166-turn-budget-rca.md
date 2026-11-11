# MO-166 RCA: `check_hub_turn_budget` fails on main

Refs #93. Frozen base: `8bbce09d7702360362e29966cc969cc26ea7ef97` (`main`, identical to
`origin/main`).

Raw command output for everything below: `evidence/mo-166-turn-budget-rca.log`.

## Verdict

The proof broke, not the hub. The first bad commit is
`277741fb7f09e9c28a9b9399d31f415e41f2de2c` (`feat(hub): automate personal-repo merge train`,
MO-159, PR #87). It moved the GitHub-repo resolution of the merge path into
`tool_thread_merge`, and the turn-budget proof never stubbed that seam, so a real
`gh repo view` runs inside the proof's disposable temp home, fails, and turns the dry run
into a refusal.

The naive `git bisect` that points at MO-165 is wrong: `git bisect run` exports
`GIT_DIR`/`GIT_PREFIX` to the test it runs, `gh repo view` then succeeds from any
directory, and every commit "passes". The bisect then blames the commit that was marked
bad by hand.

## Behavior change

None. This ticket is read-only: it adds this evidence file, its raw log, and nothing
else. The proof and `empryo/bin/emp-hub` are unchanged in this branch.

## What fails

`verification/check_hub_turn_budget.py`, one test of seven:

```
$ python3 verification/check_hub_turn_budget.py TurnBudgetProof.test_merge_dry_run_provenance_after_fallback
...
Traceback (most recent call last):
  File ".../verification/check_hub_turn_budget.py", line 348, in test_merge_dry_run_provenance_after_fallback
    self.assertTrue(result["dryRun"])
KeyError: 'dryRun'

Ran 1 test in 0.588s

FAILED (errors=1)
DRY RUN {"merged": false, "refused": "cannot tell which GitHub repo this task belongs to: failed to run git: fatal: not a git repository (or any of the parent directories): .git", "threadId": "emp:f1d371fd-..."}
```

The other six tests in the file pass, and the other three hub proofs pass on the same
tree (`check_hub_auto_merge.py` 29 OK, `check_hub_merge_evidence.py` 7 OK,
`check_hub_single_instance.py` 5 OK). The full file on main: `Ran 7 tests ... FAILED
(errors=1)`.

The refusal is the whole story: the merge tool answers with
`{"merged": false, "refused": ...}` and no `dryRun` key, so the test's first assertion
raises `KeyError` instead of a comparison failure.

## Root cause

1. `empryo/bin/emp-hub:2151` (added by `277741f`) resolves the repo before the merge
   plan runs, to key the per-repo merge lock:

   ```python
   with merge_repo_lock(thread_repo(thread)), merge_guard(thread, automatic):
   ```

   `thread_repo` (`empryo/bin/emp-hub:1650`) is the hub's only repo resolver. It returns
   `thread["pullRequests"][*]["repository"]` when the thread already has one, and
   otherwise runs `gh repo view --json nameWithOwner` in the thread's directory
   (`thread_cwd`, `empryo/bin/emp-hub:298`).
2. Before `277741f`, `thread_repo` was only reachable from `pull_requests_of`
   (`:1661`) and `auto_link_pull_requests` (`:1678`) - both stubbed by the proof.
   `277741f` added a third caller on the merge path, and the proof does not stub it.
3. `verification/check_hub_turn_budget.py:341-345` fakes GitHub by replacing
   `pull_requests_of`, `own_branch`, `gh_json`, `checks_verdict` and `merge_method`.
   `thread_repo` is not among them, so the real `gh` binary runs with
   `cwd=/tmp/hb-XXXX` (the disposable project root, which is not a git checkout). It
   fails, `thread_repo` raises `HubError`, and `tool_thread_merge`'s
   `except HubError` (`:2157`) turns it into a refusal.
4. The proof's docstring says "Only ACP/provider and GitHub I/O are faked". After
   `277741f` that is no longer true for this seam: the recorded subprocess is
   `gh repo view --json nameWithOwner --jq .nameWithOwner cwd=/tmp/hb-XXXX` (probe A in
   log section [F]).

The hub's production behavior is not defective here. `thread_repo` is called twice on
the merge path now (once for the lock, once inside `pull_requests_of`), and both calls
resolve the same repo by the same rule, so the merge plan sees what it saw before. The
only production deltas are one extra `gh repo view` per merge attempt and a
`HubError` from repo resolution now returning as a refusal instead of an RPC error.

## How the commit was found

Two bisects over `2f91640` (last known good) .. `8bbce09` (main), same test command.

**Naive bisect** (`git bisect run python3 verification/check_hub_turn_budget.py ...`)
marks `6b1be70`, `a216db2`, `ca5eb83`, `f74f6ac` (PR #87 itself) and `333f989` as
good, and reports `8bbce09` - the commit marked bad by hand - as the first bad commit.
That answer is an artifact: `f74f6ac` contains the culprit and still "passes".

**Clean bisect** (`git bisect run env -u GIT_DIR -u GIT_WORK_TREE -u GIT_PREFIX python3 ...`):

```
# bad: [f74f6ac] Merge pull request #87 from shyamsivakumar/empryo/mo-159-hub-auto-merges-personal-repo-prs-on-pass-be00ba
# bad: [236a598] fix(hub): update behind branches in all safe merge states
# bad: [277741f] feat(hub): automate personal-repo merge train
# first bad commit: [277741fb7f09e9c28a9b9399d31f415e41f2de2c] feat(hub): automate personal-repo merge train
```

Before/after on the same tree (`277741f^` = `b5b6ff3`): the whole file is
`Ran 7 tests ... OK`; at `277741f` it is `Ran 7 tests ... FAILED (errors=1)`.

Why the naive bisect lies: `git bisect run` runs the test as a child of git, and git
exports `GIT_DIR`, `GIT_EXEC_PATH`, `GIT_PREFIX` and `GIT_TERMINAL_PROMPT` into that
child's environment. `gh repo view` runs `git`, which resolves the repository from
`GIT_DIR` instead of the current directory, so the repo lookup succeeds from
`/tmp/hb-XXXX` and the proof passes at every commit. The same tree, the same test, one
environment apart:

```
$ python3 verification/check_hub_turn_budget.py TurnBudgetProof.test_merge_dry_run_provenance_after_fallback
FAILED (errors=1)                      # plain shell
$ GIT_DIR=<worktree git dir> GIT_WORK_TREE=<worktree> python3 verification/check_hub_turn_budget.py ...
OK                                     # same commit, same tree
```

## Hypotheses and the tests that told them apart

| # | Hypothesis | Test | Result |
|---|---|---|---|
| H1 | MO-165 (`2a3db61`, `333f989`, `8bbce09`) broke the review-gate provenance, so `gate["model"]` is no longer the fallback model | Read the failure: it is a `KeyError: 'dryRun'` at line 348, before any gate assertion, and the returned payload is a refusal. Probe B (log section [F]) then asserts the gate model end to end | Rejected. Probe B shows `reviewGate.model == "subscriptions/gpt-6.1-terra"` for the fallback review and `"subscriptions/claude-opus-5-5"` for the normal review, exactly as the test expects |
| H2 | The merge path resolves the repo outside the proof's fakes, so a real `gh` runs and fails | Probe A records every subprocess the hub starts on the main tree: one `gh repo view --json nameWithOwner --jq .nameWithOwner` with `cwd=/tmp/hb-XXXX` | Confirmed as the cause. Probe B stubs only `hub.thread_repo` and the test passes unchanged on the same tree |
| H3 | The proof is red only because of the ambient environment (a `gh`/`git` artifact), not because of any commit | Same commit, same tree, two environments: plain shell fails, `GIT_DIR`+`GIT_WORK_TREE` exported passes | Confirmed as the reason the naive bisect is useless, and the reason the proof must not depend on ambient git state |
| H4 | `gh` is missing or unauthenticated on this machine | The captured stderr is `failed to run git: fatal: not a git repository`, and the `GIT_DIR` probe (H3) shows the same `gh` succeeding | Rejected: `gh` works; the lookup fails because the directory is not a checkout |

H2 and H3 together are the finding: the leak is real (H2) and the proof's result depends
on the ambient environment (H3). The fix has to remove the leak, which also removes the
environment dependence.

## Blast radius

Only this one test. `check_hub_auto_merge.py` (29), `check_hub_merge_evidence.py` (7)
and `check_hub_single_instance.py` (5) all pass on main. The two other hub proofs that
touch the merge path survive because they stub the seam: `check_hub_auto_merge.py:78`
stubs `h.thread_repo` (it was written with `277741f`, in the same commit) and
`check_hub_merge_evidence.py:79` stubs `h.sh` wholesale.

## Proposed smallest fix (not applied here)

One line in the proof, next to the GitHub fakes it already installs in that test
(`verification/check_hub_turn_budget.py:341`):

```diff
--- a/verification/check_hub_turn_budget.py
+++ b/verification/check_hub_turn_budget.py
@@ -338,6 +338,7 @@
         detail = {"number": 1, "url": "https://github.com/disposable/proof/pull/1", ...}
         task["branch"] = "proof"
         h.pull_requests_of = lambda t: ("disposable/proof", [{"number": 1, "state": "OPEN", "headRefName": "proof", "isCrossRepository": False}])
+        h.thread_repo = lambda t: "disposable/proof"
         h.own_branch = lambda t: "proof"
         h.gh_json = lambda args: dict(detail)
         h.checks_verdict = lambda repo, number: (True, None, {"count": 1, "state": "green"})
```

The `detail` line above is shortened for the note; it is unchanged by the fix. The added
line is the whole change: one stub, in the test that installs the other GitHub fakes.

This is the seam the merge path now uses, and it is the same fake
`check_hub_auto_merge.py:78` installs for the same reason. Probe B (log section [F]) runs
the proof with exactly this stub and no other change: the test passes and every existing
assertion still holds.

Alternatives, if the gate prefers them:

- put the same stub in `boot()` (`verification/check_hub_turn_budget.py:89`) instead, so
  the whole file is immune to ambient git state rather than one test;
- change `empryo/bin/emp-hub` so the merge path reuses the repo `merge_plan` already
  resolves instead of resolving it twice. That is a production change, it is larger, and
  it is not needed: `thread_repo` is deterministic, so the second call returns the same
  answer.

The proof is on the base branch, so editing it needs Shyam's quoted approval of the
exact line. This branch does not edit it; it proposes it.

## Verification (what was run here)

- `python3 verification/check_hub_turn_budget.py TurnBudgetProof.test_merge_dry_run_provenance_after_fallback` on main: `FAILED (errors=1)`, `KeyError: 'dryRun'`.
- The same command with `GIT_DIR`/`GIT_WORK_TREE` exported: `OK`.
- `git bisect` over `2f91640..8bbce09`, naive and clean: naive blames `8bbce09`, clean names `277741f`.
- `277741f^`: whole file `Ran 7 tests ... OK`; `277741f`: `Ran 7 tests ... FAILED (errors=1)`.
- Probe on the main tree: proof as-is fails and records one `gh repo view` subprocess; proof with `hub.thread_repo` stubbed passes.
- `check_hub_auto_merge.py` 29 OK, `check_hub_merge_evidence.py` 7 OK, `check_hub_single_instance.py` 5 OK on main.
- No install, no `emp-hub` service, no production store, no pull request, no provider call.

## Review

No in-session code review was run: this is an evidence-only change and the ticket
sends it to a separate Claude Opus diff-only gate review.

VERDICT: not run (skipped per the ticket; the gate is the separate Claude Opus diff-only review).

## Deployment hold

No install, no hub restart, no drain, no cancellation, no provider call, no installed
binary invoked. The proof loads `empryo/bin/emp-hub` from this tree exactly as it
always does, in-process, on a socket inside a temporary directory. Rollback: nothing to
revert; this branch adds two files under `evidence/`.
