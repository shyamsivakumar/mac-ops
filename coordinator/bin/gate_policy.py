import json
import re
import sys
from pathlib import Path

# The modules below live next to this file. A caller that loads this file
# by path does not put that directory on the path.
_BIN_DIR = str(Path(__file__).resolve().parent)
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

from answer_format import ANSWER_FORMAT
import gate_findings
from gate_bar import GATE_BAR, REVIEW_BAR, TRADING_BAR

LANE_REPOS = ["shyamsivakumar/mac-ops", "shyamsivakumar/strategy-replay-workbench", "shyamsivakumar/fantasy-football-toolkit",
              "shyamsivakumar/catalouge"]
PERSONAL_OWNER = "shyamsivakumar"
ASCEND_PARTS = ("action-underwriting-hub", "ascend-mcp", "data-ops", "/dbt", "/omni")


def merge_repos():
    for candidate in (Path(_BIN_DIR).parent / "config" / "tickets.json", Path.home() / ".coordinator" / "tickets.json"):
        if candidate.exists():
            return list(json.loads(candidate.read_text())["repos"])
    raise FileNotFoundError("tickets.json not found next to the module or in ~/.coordinator")


MERGE_REPOS = merge_repos()

# The sentence a prompt pull request ends on: it never merges itself.
PROMPT_NO_MERGE = (
    "This pull request changes prompt, skill or playbook files, and a change like that never "
    "auto-merges (Shyam): do not merge. Stop at the verdict and report it; Shyam merges a passing one himself."
)


def complete_pass(reply, head, provides=True):
    """True when a gate reply carries every line `ticket close` requires on this head."""
    lines = [line.rstrip() for line in reply.splitlines()]
    return (bool(lines) and lines[-1] == "VERDICT: PASS" and f"CHECK: PASS {head}" in lines
            and (not provides or f"PROVIDES: PASS {head}" in lines))


GATE_ROUND_CAP = 3
TRADING_REPOS = ("shyamsivakumar/strategy-replay-workbench",)
OPEN_FINDINGS_NONE = "Open critical or major findings: none"
ROUND_CAP_RULE = (f"After {GATE_ROUND_CAP} rounds without PASS the PR is re-cut into smaller PRs or brought to Shyam: "
                  "open findings go to the round-cap decision, and there is no 4th review.")


def reply_of(thread):
    """The last assistant message of a `t3_thread_read` result."""
    texts = [item.get("text") or "" for item in (thread.get("items") or []) if item.get("type") == "assistant_message"]
    return texts[-1] if texts else ""


def round_context(repo, number, head, ledger, receipts, read_thread, base=None):
    """The review round of a head, the head reviewed before it and the open findings.

    The lane's ledger holds the failed reviews and the head of the last. The
    gate thread that reviewed that head is read by `read_thread(thread_id)`,
    which returns a `t3_thread_read` result, and its findings go into the
    findings ledger once.
    """
    state = ledger.get(f"rounds:{repo}#{number}") or {}
    prefix = f"fix:{repo}#{number}:"
    fixed = [key[len(prefix):] for key in ledger if key.startswith(prefix)]
    failed = max(int(state.get("count", 0)), len(fixed))
    previous = state.get("head") or (fixed[-1] if fixed else None)
    if not failed or not previous:
        return {"round": 1, "previous": None, "open": "", "next": 1}
    thread = receipts.get(f"gate:{repo}#{number}:{previous}")
    if thread and not gate_findings.reviewed(repo, number, previous, base):
        gate_findings.record(repo, number, previous, failed, reply_of(read_thread(thread)), base=base)
    findings = gate_findings.load(repo, number, base)
    context = {"open": gate_findings.brief_section(findings, previous), "next": findings["next"]}
    if previous == head:
        return {"round": min(failed, GATE_ROUND_CAP), "previous": None, **context}
    return {"round": min(failed + 1, GATE_ROUND_CAP), "previous": previous, **context}


def round_brief(context, head, base="main"):
    context = context or {"round": 1, "previous": None, "open": "", "next": 1}
    number, previous = context["round"], context["previous"]
    if number == 1 or not previous:
        text = "List every critical and major, not only the first."
        if context["open"]:
            text += "\n" + context["open"]
    else:
        text = (f"Previous reviewed head {previous}, this head {head}. Round diff: `git diff {previous}..{head}`. "
                f"If `git merge-base --is-ancestor {previous} {head}` fails the branch was rebased: say so and use "
                f"`git range-diff origin/{base}..{previous} origin/{base}..{head}`. "
                "New blockers come only from the round diff; the full PR diff is context. A major blocks only when it is an open "
                "prior finding, sits in lines changed since the previous reviewed head, or is a regression the repair caused "
                "(state the causal path). Every other new finding is minor.\n" + context["open"])
    text += "\n" + gate_findings.format_instruction(context["next"]) + "\n" + ROUND_CAP_RULE
    if number == GATE_ROUND_CAP:
        text += " This is the last round."
    return text


PROMPT_CLOSE_NOTHING = " Do not close the issue either: the merge that would close it is Shyam's."


def brief_base(message, head):
    found = re.search(rf"git diff origin/(\S+?)\.\.\.{re.escape(head)}", message)
    return found.group(1) if found else None


def merge_mode(repo, settings, ascend=None):
    if ascend is None:
        ascend = (settings.get("ascend", False) or repo.split("/")[0] != PERSONAL_OWNER
                  or any(part in repo for part in ASCEND_PARTS))
    if settings.get("merge") == "manual":
        return "manual"
    if ascend:
        return "ascend"
    return "lane" if repo in MERGE_REPOS else "reviewer"


def brief_merger(message):
    return "reviewer-merges" if "gh pr merge" in message else "lane-merges"


def manual_gate_ending():
    return "Do not merge or close; Shyam merges passed PRs himself."


def build_gate_brief(settings, repo, issue, number, head, publisher, base="main", fast_forward_main=True, ascend_override=None, proof=None, proof_path=None, proof_state=None, prompt=False, round_info=None):
    import proof_file
    mode = merge_mode(repo, settings, ascend_override)
    merge = (PROMPT_NO_MERGE if prompt else
             "Ascend repo: do not merge; stop at the verdict." if mode == "ascend" else
             f"If and only if CHECK and VERDICT are PASS on {head}, run `gh pr merge {number} -R {repo} --squash --match-head-commit {head}`; report the merge commit or refusal.")
    provides_ask = (f"Verify each Provides claim on head {head} (none: pass). `PROVIDES: FAIL {head}` forces `VERDICT: FAIL`; "
                    f"a PASS reply without the PROVIDES line is read as no verdict.")
    lane = mode == "lane" and not prompt
    if lane:
        merge = "Do not merge, close the issue or fast-forward main: the lane does all three on your verdict."
    fast_forward = ("" if mode == "ascend" or lane or not fast_forward_main else
                    " Only when that merge produced a merge commit, fast-forward this repository's local main to origin/main and never force: "
                    "find the worktree that has main checked out in `git worktree list` and run `git fetch origin` then "
                    "`git merge --ff-only origin/main` there; when no worktree has main checked out, run `git fetch origin main:main`. "
                    "Report `git rev-parse main origin/main` (one hash twice) or the exact refusal. Fast-forward no other repository.")
    close = ("" if lane else
             PROMPT_CLOSE_NOTHING if prompt else
             " Ascend repo: do not close the issue." if mode == "ascend" else
             f" Only when that merge produced a merge commit, verify every Provides claim from the ticket on that merge commit and report the commit SHA, evidence and result for each claim. If any Provides claim is false, missing or unverified, close nothing and report the refusal. "
             f"Before the close, run the close checklist: `python3 coordinator/bin/close_check.py --repo {repo} --pr {number}"
             + (f" --issue {issue}" if issue is not None else "") + "` (the coordinator's mac-ops checkout holds it). "
             "If it ends `RESULT: FAIL`, send the work back to the builder with the failing item it names, close nothing, and report the refusal. "
             f"Only after every Provides claim passes on the merge commit and the checklist passes, close the ticket: run `gh issue close {issue} -R {repo} --comment \"VERDICT: PASS. Merged via #{number} (<merge commit sha>).\"` with <merge commit sha> the merge commit you reported, or read it with `gh pr view {number} -R {repo} --json mergeCommit --jq .mergeCommit.oid` when the merge output did not give it. On VERDICT: FAIL, or when the merge did not happen, close nothing.")
    if issue is None:
        close = " No ticket is associated with this PR; close no issue."
    check = (f"Confirm srw/agent-check success on {head} using gh api repos/{repo}/commits/{head}/statuses."
             if publisher else f"Confirm the exact PR-body line `Builder check: PASS {head}`.")
    task = f"https://github.com/{repo}/issues/{issue}" if issue is not None else f"https://github.com/{repo}/pull/{number}"
    label = f"{settings['key']}-{issue}" if issue is not None else f"{settings['key']} PR"
    source = "ticket" if issue is not None else "PR description"
    proof_text = proof_file.section(proof_state or (proof_file.FOUND if proof else proof_file.MISSING),
                                    proof, proof_path)
    round_number = (round_info or {}).get("round", 1)
    later = round_number > 1 and (round_info or {}).get("previous")
    scope = (f"Context only, not a source of new blockers: `git fetch origin && git diff origin/{base}...{head}`." if later else
             f"Read the {source} and the diff only: `git fetch origin && git diff origin/{base}...{head}`.")
    trading = f"\n{TRADING_BAR}" if repo in TRADING_REPOS else ""
    message = f"""{label} {'review only' if prompt else 'review and merge'} · #{number} {head} · round {round_number} of {GATE_ROUND_CAP}
{REVIEW_BAR}
{round_brief(round_info, head, base)}
Task: {task}. {scope} Do not switch branches or rerun the suite.
{check}
{proof_text}
{GATE_BAR}{trading}
{ANSWER_FORMAT}
End with these lines in order: `PROVIDES: PASS {head}` or `PROVIDES: FAIL {head}`, `CHECK: PASS {head}` or `CHECK: FAIL {head}`, `{OPEN_FINDINGS_NONE}` or `Open critical or major findings: <n>`, then exactly `VERDICT: PASS` or `VERDICT: FAIL`.
{manual_gate_ending() if mode == "manual" else merge + fast_forward + close} {provides_ask} Never call emp. Never print secrets."""
    if not fast_forward_main and mode != "manual":
        message = message.replace(" Never call emp. Never print secrets.", "\nNever call emp. Never print secrets.")
    return message
