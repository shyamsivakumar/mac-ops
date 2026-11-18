import sys
from pathlib import Path

# The modules below live next to this file. A caller that loads this file
# by path does not put that directory on the path.
_BIN_DIR = str(Path(__file__).resolve().parent)
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)

from answer_format import ANSWER_FORMAT
from gate_bar import GATE_BAR

# The sentence a prompt pull request ends on: it never merges itself.
PROMPT_NO_MERGE = (
    "This pull request changes prompt, skill or playbook files, and a change like that never "
    "auto-merges (Shyam): do not merge. Stop at the verdict and report it; Shyam merges a passing one himself."
)
PROMPT_CLOSE_NOTHING = " Do not close the issue either: the merge that would close it is Shyam's."


def manual_merge(settings):
    return settings.get("merge") == "manual"


def manual_gate_ending():
    return "Do not merge or close; Shyam merges passed PRs himself."


def build_gate_brief(settings, repo, issue, number, head, publisher, base="main", fast_forward_main=True, ascend_override=None, proof=None, proof_path=None, proof_state=None, prompt=False):
    import proof_file
    ascend = settings.get("ascend", False) or repo.split('/')[0] != "shyamsivakumar" or any(x in repo for x in ("action-underwriting-hub", "ascend-mcp", "data-ops", "/dbt", "/omni"))
    if ascend_override is not None:
        ascend = ascend_override
    # No merge call pins both the base and the head, so the gate does not
    # merge: on a PASS the lane writes one item for Shyam, who merges it.
    lane_ask = ("this repository merges nothing automatically: no merge call pins both the base "
                "and the head, so no race can land content this review did not read. On a PASS the "
                "lane writes one decisions item asking Shyam to merge this head; do not merge and do not close")
    merge = (PROMPT_NO_MERGE if prompt else
             "Ascend repo: do not merge; stop at the verdict." if ascend else
             f"If and only if CHECK and VERDICT are PASS on {head}, {lane_ask}.")
    fast_forward = ""
    close = (PROMPT_CLOSE_NOTHING if prompt else
             " Ascend repo: do not close the issue." if ascend else
             " Close nothing: Shyam merges this head himself, and the ticket is closed after that merge.")
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
Reconfirm the PR head is {head}; otherwise CHECK: FAIL. End `CHECK: PASS {head}` or `CHECK: FAIL {head}`, then exactly `VERDICT: PASS` or `VERDICT: FAIL`.
{manual_gate_ending() if manual_merge(settings) else merge + fast_forward + close + " Never call emp. Never print secrets."}"""
    if not fast_forward_main and not manual_merge(settings):
        message = message.replace(" Never call emp. Never print secrets.", "\nNever call emp. Never print secrets.")
    return message
