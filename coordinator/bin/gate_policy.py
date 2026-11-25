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
from gate_bar import GATE_BAR

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

NO_LATER_MERGE = " This thread never merges this pull request later, whoever asks, and reports the request instead."


def verdict(report):
    lines = [line for line in report.splitlines() if line.strip()]
    match = lines and re.match(r"VERDICT:\s*(PASS|FAIL)\b", re.sub(r"[*`_]", "", lines[-1]))
    return match.group(1) if match else None


def complete_pass(reply, head, provides=True):
    """True when a gate reply carries every line `ticket close` requires on this head."""
    lines = [line.rstrip() for line in reply.splitlines()]
    return (bool(lines) and verdict(reply) == "PASS" and f"CHECK: PASS {head}" in lines
            and (not provides or f"PROVIDES: PASS {head}" in lines))


JSON_VERDICT_ASK = """Machine-readable verdict. Before the final CHECK and VERDICT lines, post exactly one fenced json block, and only one:

```json
{"verdict": "PASS", "findings": [{"id": "F1", "severity": "major", "bar_clause": "the bar line this finding breaks", "path": "file/that/changed.py", "line": 42, "text": "what is wrong, in one sentence", "fixed_when": "the check that proves it is fixed"}]}
```

- "verdict" is "PASS" or "FAIL" and must match the VERDICT line.
- "findings" holds one entry per finding, in the order you list them in prose. Use an empty list when there are none.
- Every entry carries all seven keys: id, severity, bar_clause, path, line, text, fixed_when. Use "n/a" for path and null for line when a finding has no file.
- Follow the block with a one-line prose summary of the verdict.
- The VERDICT line stays last, after the json block and the summary."""


JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


def valid_finding(entry):
    return (isinstance(entry, dict) and all(isinstance(entry.get(k), str) for k in ("severity", "path", "text"))
            and "line" in entry
            and (entry["line"] is None or (isinstance(entry["line"], int) and not isinstance(entry["line"], bool))))


def parse_verdict(report):
    for block in reversed(JSON_BLOCK.findall(report)):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("verdict") in ("PASS", "FAIL") and isinstance(data.get("findings"), list) \
                and all(valid_finding(f) for f in data["findings"]):
            return data
    return None


def read_verdict(report):
    data = parse_verdict(report)
    outcome = verdict(report)
    if data:
        return (data["verdict"] if outcome in (None, data["verdict"]) else "CONFLICT", data["findings"])
    findings = [{"severity": s, "path": p, "line": int(l), "text": t.strip()}
                for s, p, l, t in re.findall(r"\[(critical|major|minor)\]\s+(\S+?):(\d+)(.*)", report)]
    return (outcome, findings)


def report_for_builder(report):
    data = parse_verdict(report)
    if data is None:
        return report
    lines = [f"[{f.get('severity', '')}] {f.get('path', '')}:{f.get('line', '')} {f.get('text', '')} (fixed when: {f.get('fixed_when', '')})"
             for f in data["findings"]]
    return report + "\n\nFindings from the verdict block:\n" + "\n".join(lines)


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
    return "Do not merge or close; Shyam merges passed PRs himself." + NO_LATER_MERGE


def build_gate_brief(settings, repo, issue, number, head, publisher, base="main", fast_forward_main=True, ascend_override=None, proof=None, proof_path=None, proof_state=None, prompt=False, json_verdict=False):
    import proof_file
    mode = merge_mode(repo, settings, ascend_override)
    merge = (PROMPT_NO_MERGE + NO_LATER_MERGE if prompt else
             "Ascend repo: do not merge; stop at the verdict." if mode == "ascend" else
             f"If and only if CHECK and VERDICT are PASS on {head}, run `gh pr merge {number} -R {repo} --squash --match-head-commit {head}`; report the merge commit or refusal.")
    provides_ask = (f"Verify every Provides claim from the ticket on head {head}. A ticket with no Provides section has "
                    f"no claims, so it passes this check trivially. Include the exact line `PROVIDES: PASS {head}` before "
                    f"the final CHECK and VERDICT lines whenever every claim holds, and `PROVIDES: FAIL {head}` with "
                    f"`VERDICT: FAIL` when one does not. A PASS reply without the PROVIDES line is read as no verdict.")
    lane = mode == "lane" and not prompt
    if lane:
        merge = "Do not merge, close the issue or fast-forward main: the lane does all three on your verdict." + NO_LATER_MERGE
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
    message = f"""{label} {'review only' if prompt else 'review and merge'} · #{number} {head}
Type: review gate · finish in 4 minutes. Task: {task}
Read the {source} and diff only: `git fetch origin && git diff origin/{base}...{head}`. Check out nothing. Do NOT rerun the suite.
{check}
{proof_text}
Re-read prior gate findings and say whether each is resolved.
Tag findings critical, major, minor with file:line. Runtime changes outside the task, unrelated test weakening, circular proof and workflow files are major; secrets are critical.
{GATE_BAR}
{ANSWER_FORMAT}
Reconfirm the PR head is {head}; otherwise CHECK: FAIL. End `CHECK: PASS {head}` or `CHECK: FAIL {head}`, then exactly `VERDICT: PASS` or `VERDICT: FAIL`, as plain text with no markdown and no sentence after them.
{manual_gate_ending() if mode == "manual" else merge + fast_forward + close} {provides_ask} Never call emp. Never print secrets."""
    if not fast_forward_main and mode != "manual":
        message = message.replace(" Never call emp. Never print secrets.", "\nNever call emp. Never print secrets.")
    if json_verdict:
        message += "\n" + JSON_VERDICT_ASK
    return message
