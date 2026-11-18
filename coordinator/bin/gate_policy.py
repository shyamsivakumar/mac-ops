import sys
from pathlib import Path

# The modules below live next to this file. A caller that loads this file
# by path does not put that directory on the path.
_BIN_DIR = str(Path(__file__).resolve().parent)
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

from gate_bar import GATE_BAR


def manual_merge(settings):
    return settings.get("merge") == "manual"


def manual_gate_ending():
    return "Do not merge or close; Shyam merges passed PRs himself."


def build_gate_brief(settings, repo, issue, number, head, publisher, base="main", fast_forward_main=True, ascend_override=None, proof=None, proof_path=None):
    import proof_file
    ascend = settings.get("ascend", False) or repo.split('/')[0] != "shyamsivakumar" or any(x in repo for x in ("action-underwriting-hub", "ascend-mcp", "data-ops", "/dbt", "/omni"))
    if ascend_override is not None:
        ascend = ascend_override
    merge = ("Ascend repo: do not merge; stop at the verdict." if ascend else
             f"If and only if CHECK and VERDICT are PASS on {head}, run `gh pr merge {number} -R {repo} --squash --match-head-commit {head}`; report the merge commit or refusal.")
    fast_forward = ("" if ascend or not fast_forward_main else
                    " Only when that merge produced a merge commit, fast-forward this repository's local main to origin/main and never force: "
                    "find the worktree that has main checked out in `git worktree list` and run `git fetch origin` then "
                    "`git merge --ff-only origin/main` there; when no worktree has main checked out, run `git fetch origin main:main`. "
                    "Report `git rev-parse main origin/main` (one hash twice) or the exact refusal. Fast-forward no other repository.")
    close = (" Ascend repo: do not close the issue." if ascend else
             f" Only when that merge produced a merge commit, verify every Provides claim from the ticket on that merge commit and report the commit SHA, evidence and result for each claim. If any Provides claim is false, missing or unverified, close nothing and report the refusal. Only after every Provides claim passes on the merge commit, close the ticket: run `gh issue close {issue} -R {repo} --comment \"VERDICT: PASS. Merged via #{number} (<merge commit sha>).\"` with <merge commit sha> the merge commit you reported, or read it with `gh pr view {number} -R {repo} --json mergeCommit --jq .mergeCommit.oid` when the merge output did not give it. On VERDICT: FAIL, or when the merge did not happen, close nothing.")
    if issue is None:
        close = " No ticket is associated with this PR; close no issue."
    check = (f"Confirm srw/agent-check success on {head} using gh api repos/{repo}/commits/{head}/statuses."
             if publisher else f"Confirm the exact PR-body line `Builder check: PASS {head}`.")
    task = f"https://github.com/{repo}/issues/{issue}" if issue is not None else f"https://github.com/{repo}/pull/{number}"
    label = f"{settings['key']}-{issue}" if issue is not None else f"{settings['key']} PR"
    source = "ticket" if issue is not None else "PR description"
    proof_text = proof_file.section(proof, proof_path)
    message = f"""{label} review and merge · #{number} {head}
Type: review gate · finish in 4 minutes. Task: {task}
Read the {source} and diff only: `git fetch origin && git diff origin/{base}...{head}`. Check out nothing. Do NOT rerun the suite.
{check}
{proof_text}
Re-read prior gate findings and say whether each is resolved.
Tag findings critical, major, minor with file:line. Runtime changes outside the task, unrelated test weakening, circular proof and workflow files are major; secrets are critical.
{GATE_BAR}
Reconfirm the PR head is {head}; otherwise CHECK: FAIL. End `CHECK: PASS {head}` or `CHECK: FAIL {head}`, then exactly `VERDICT: PASS` or `VERDICT: FAIL`.
{manual_gate_ending() if manual_merge(settings) else merge + fast_forward + close + " Never call emp. Never print secrets."}"""
    if not fast_forward_main and not manual_merge(settings):
        message = message.replace(" Never call emp. Never print secrets.", "\nNever call emp. Never print secrets.")
    return message
