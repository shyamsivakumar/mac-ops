from contextlib import contextmanager
import shlex
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

for _dir in (Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent / "bin"):
    if (_dir / "models.py").is_file() and str(_dir) not in sys.path:
        sys.path.insert(0, str(_dir))

import alarms
import models as model_list
import stall

# The GitHub call path and the prompt paths live next to the coordq and ticket
# binaries: one cache, one floor and one usage log for every caller, and the
# lane reads the same prompt list the gate brief does (Refs #543).
_BIN_DIR = str(Path(__file__).resolve().parents[1] / "bin")
if _BIN_DIR not in sys.path:
    sys.path.insert(0, _BIN_DIR)
import gh_gateway
import gate_policy
from gate_policy import LANE_REPOS, MERGE_REPOS, complete_pass, merge_mode
import prompt_paths

# The lane driver loads inside the overnight command, so it names itself on
# its own calls. A process-wide name would charge every later overnight call
# to the lane driver and spoil the per-caller ranking.
LANE_CALLER = "lane_driver"

COORDQ = "/Users/shyamsivakumar/.local/bin/coordq"
LEDGER = "/Users/shyamsivakumar/Code/coordinator/loop/lanes-ledger.json"
CFG = {}
RECEIPTS = "/Users/shyamsivakumar/Code/coordinator/queue/dispatch-receipts.json"
# The decisions board the lane raises one item on. The path comes from the
# environment, so a test or a dry run writes its item to a scratch file
# and never to the board Shyam reads.
DECISIONS_PATH = os.environ.get(
    "COORDINATOR_DECISIONS", "/Users/shyamsivakumar/Code/coordinator/decisions.json")
# The failed gate reviews one pull request gets before it goes to Shyam.
# The convergence rule (Shyam, 2026-11-18): after 3 review rounds without
# PASS the pull request is re-cut into smaller pull requests or brought to
# Shyam, and it is not reviewed a 4th time as it is. So the 3rd failed
# review raises one decisions item instead of a fix round.
GATE_ROUND_CAP = 3
DRY = False
SNAPSHOT = {}
# Where each lane repository is checked out. The path is the shared root
# of the repository: work there moves the branch everyone installs from.
PATHS = {"shyamsivakumar/mac-ops": "mac-ops", "shyamsivakumar/strategy-replay-workbench": "strategy-replay-workbench",
         "shyamsivakumar/fantasy-football-toolkit": "fantasy-football-toolkit", "shyamsivakumar/catalouge": "catalogue",
         "shyamsivakumar/tunerise": "tunerise", "shyamsivakumar/openscan": "openscan", "shyamsivakumar/CineJar": "CineJar",
         "digitized/Concerning": "concerning", "shyamsivakumar/sams-llm-wiki": "llmwiki",
         "shyamsivakumar/scripture-scroll": "scripture-scroll", "shyamsivakumar/scrapers": "scrapers",
         "shyamsivakumar/recoup": "recoup"}
MERGE_WAIT_PASSES = 5
# The calls left in reserve before an optional read is skipped. The lane
# driver, gatekeep and the overnight shift share this one floor.
API_FLOOR = gh_gateway.floor()
BOARD_REFRESH_PASSES = 5
# The stall events of the last pass: an item that was reported as stalled
# and a board that stopped moving. The shift writes the records for them.
STALL_EVENTS = []
# The stall state of the shift: how long every item has been idle. The
# shift loads it before the pass and saves it after the pass, so the pass
# itself keeps no file of its own.
STALL_STATE = {}


# The quota, its floor and its refusal are the shared helper's, so the
# lane driver stops on the same number as every other caller.
ApiBudgetExhausted = gh_gateway.ApiBudgetExhausted


def api_remaining():
    return gh_gateway.api_remaining()


def require_api_budget():
    """Stop an optional read below the shared floor.

    The quota read is this module's `api_remaining`, so a caller that
    already read the quota in this pass is not made to read it again."""
    remaining = api_remaining()
    if min(remaining.values()) < API_FLOOR:
        raise ApiBudgetExhausted(
            f"optional reads stopped: remaining={remaining}, floor={API_FLOOR}")
    return remaining


def read_json(cmd):
    require_api_budget()
    result = gh_gateway.run(cmd, timeout=300, caller_name=LANE_CALLER)
    if result.returncode:
        raise RuntimeError(f"snapshot read failed: {cmd[:3]} (exit {result.returncode})")
    return json.loads(result.stdout)


def board_snapshot(ledger, force=False):
    cached = ledger.get("_board_snapshot")
    current_pass = ledger.get("_pass", 0) + 1
    ledger["_pass"] = current_pass
    if isinstance(cached, dict) and any(
        "headRefName" not in pr or "baseRefName" not in pr
        for data in cached.get("repos", {}).values() for pr in data.get("prs", [])
    ):
        force = True
    if not force and isinstance(cached, dict) and 0 <= current_pass - cached.get("refreshed_pass", -BOARD_REFRESH_PASSES) < BOARD_REFRESH_PASSES:
        return cached
    snapshot = {"tickets": read_json(["ticket", "list", "--json", "--fresh"]).get("issues", []), "repos": {}}
    fields = "number,state,headRefOid,headRefName,baseRefName,body,mergeable,isDraft,statusCheckRollup,changedFiles"
    for repo in LANE_REPOS:
        snapshot["repos"][repo] = {
            "prs": read_json(["gh", "pr", "list", "-R", repo, "--state", "open", "--limit", "200", "--json", fields]),
            "issues": read_json(["gh", "issue", "list", "-R", repo, "--state", "open", "--limit", "200", "--json", "number,title,labels,state"]),
        }
    snapshot["refreshed_at"] = time.time()
    snapshot["refreshed_pass"] = current_pass
    ledger["_board_snapshot"] = snapshot
    return snapshot

ORDER = {
    "shyamsivakumar/mac-ops": [],
    "shyamsivakumar/strategy-replay-workbench": [1082, 1089, 1090, 1071, 1072],
    "shyamsivakumar/fantasy-football-toolkit": [423, 444],
    "shyamsivakumar/catalouge": [117, 121],
}


def run(cmd, timeout=150):
    if cmd[0] == "gh" or (cmd[0] == "ticket" and cmd[1] in ("start", "gate", "list")):
        require_api_budget()
    p = gh_gateway.run(cmd, timeout=timeout, caller_name=LANE_CALLER)
    output = (p.stdout + p.stderr).strip()
    refusal = ("--dry-run" in cmd and cmd[:2] == ["ticket", "start"]
               and p.returncode == 2 and output.startswith("refused: ")
               and len(output.splitlines()) == 1)
    already_closed = (cmd[:2] == ["ticket", "close"] and p.returncode == 1
                      and len(cmd) > 2 and re.fullmatch(
                          rf"(?:gh failed \(error\): )?(?:[!✓] )?Issue {re.escape(cmd[2])} is already closed\.?",
                          output) is not None)
    if p.returncode and not (refusal or already_closed):
        raise subprocess.CalledProcessError(p.returncode, cmd, output=p.stdout, stderr=p.stderr)
    return output



@contextmanager
def item_boundary(repo, item, ledger):
    try:
        yield
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        ledger["_item_failures"] = ledger.get("_item_failures", 0) + 1
        output = (exc.output or b"")
        stderr = (exc.stderr or b"")
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        first = output.splitlines() + stderr.splitlines()
        code = getattr(exc, "returncode", "timeout")
        command = shlex.join(exc.cmd) if isinstance(exc.cmd, (list, tuple)) else str(exc.cmd)
        print(f"ITEM ERROR repo={repo} item={item} command={command!r} exit={code} output={(first[0] if first else '')!r}")


def t3(tool, args):
    try:
        return json.loads(run(["t3mcp", "call", tool, json.dumps(args)]) or "{}")
    except ValueError:
        return {}


def settle_dead_run(thread_id):
    try:
        t3("t3_thread_organize", {"threadId": thread_id, "action": "settle"})
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        parts = [getattr(exc, "output", None), getattr(exc, "stderr", None)]
        reason = " ".join(part.decode(errors="replace") if isinstance(part, bytes) else part
                          for part in parts if part) or str(exc)
        print(f"DEAD {thread_id}: settle failed: {' '.join(reason.split())}; left for the next pass")
        return False
    return True


def last_reply(thread_id):
    items = t3("t3_thread_read", {"threadId": thread_id, "view": "messages", "limit": 80, "maxCharsPerItem": 12000}).get("items") or []
    msgs = [i.get("text") or i.get("message") or "" for i in items
            if i.get("type") in {"assistant_message", "error", "run_error", "provider_error"}]
    return (msgs[-1] if msgs else "").rstrip()


def busy(repo):
    pid = CFG[repo]["projectId"]
    live = t3("t3_thread_list", {"projectId": pid, "statuses": ["preparing", "queued", "starting", "running", "waiting"], "limit": 20}).get("threads") or []
    if live:
        return f"live: {live[0].get('title', '')[:60]}"
    queue = json.loads(run([COORDQ, "list", "--json"]) or "[]") if False else []
    return ""


def pr_item(repo, pr):
    """Return the stall key of one pull request and the ticket it names.

    A pull request that names a ticket is that ticket's work, so the key is
    the ticket's. A pull request that names none is a record of its own, so
    its key says so."""
    body = pr.get("body") or ""
    refs = re.findall(r"\bRefs #(\d+)", body)
    if refs:
        return f"{repo}#{refs[0]}", refs[0]
    return f"{repo}!pr{pr.get('number')}", ""


def issue_record(snapshot, repo, number):
    issues = ((snapshot.get("repos") or {}).get(repo) or {}).get("issues") or []
    return next((i for i in issues if i["number"] == int(number)), None)


def issue_held(record):
    return any(label["name"] in ("stage:backlog", "stage:hold") for label in record["labels"])


def ticket_held(snapshot, repo, number):
    record = issue_record(snapshot, repo, number) if number else None
    return record is not None and issue_held(record)


def stall_receipts():
    """Return the queue's dispatch receipts, or none when they cannot be read.

    A receipt is a new attempt on an item, so the receipt count is part of
    the item's marker."""
    try:
        with open(RECEIPTS) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def receipt_attempt(repo, number, receipts):
    """Return the newest dispatch receipt of one ticket, or an empty string.

    The attempts are compared as numbers: `a10` is newer than `a9`."""
    if not number:
        return ""
    prefix = f"ticket:{repo}#{number}:a"
    best = 0
    for key in receipts:
        if key.startswith(prefix) and key[len(prefix):].isdigit():
            best = max(best, int(key[len(prefix):]))
    return str(best) if best else ""


def stall_markers(snapshot, receipts):
    """Return the marker of every item the shift works.

    An item's marker is its commit and its newest dispatch receipt, so a
    new commit or a new receipt is progress and nothing else is.

    An item is measured when it has a commit or a receipt: an item the
    shift never started has neither, so it is not a stalled item, it is an
    item the shift still has to start."""
    markers = {}
    for repo in LANE_REPOS:
        data = (snapshot.get("repos") or {}).get(repo) or {}
        for pr in data.get("prs") or []:
            if pr.get("isDraft"):
                # The shift does not work a draft, so it does not measure
                # one either.
                continue
            key, issue = pr_item(repo, pr)
            if ticket_held(snapshot, repo, issue):
                continue
            attempt = receipt_attempt(repo, issue, receipts)
            if not pr.get("headRefOid") and not attempt:
                continue
            markers[key] = {
                "marker": stall.marker(pr.get("headRefOid"), attempt),
                "repo": repo,
                "number": issue or pr.get("number"),
                "key": "",
                "title": "",
                "url": "",
            }
    for ticket in snapshot.get("tickets") or []:
        repo = ticket.get("repo") or ""
        number = ticket.get("number")
        if repo not in LANE_REPOS or not number:
            continue
        if (ticket.get("stage") or "") not in ("todo", "started"):
            continue
        if ticket_held(snapshot, repo, number):
            continue
        key = f"{repo}#{number}"
        entry = markers.get(key)
        attempt = receipt_attempt(repo, number, receipts)
        if entry is None:
            if not attempt:
                continue
            markers[key] = {
                "marker": stall.marker("", attempt),
                "repo": repo,
                "number": number,
                "key": ticket.get("key") or "",
                "title": ticket.get("title") or "",
                "url": ticket.get("url") or "",
            }
            continue
        entry["key"] = ticket.get("key") or entry.get("key") or ""
        entry["title"] = ticket.get("title") or entry.get("title") or ""
        entry["url"] = ticket.get("url") or entry.get("url") or ""
    return markers


def board_items(snapshot):
    """Return how many items the board holds.

    The board counts every item the shift may work, measured or not: a
    board with work in it and nothing moving is a stalled board."""
    return len(board_keys(snapshot))


def board_keys(snapshot):
    """Return the keys of the items the board holds.

    A pull request and the ticket it names are the same item, so a pull
    request is keyed by its ticket. A ticket the shift has not started is
    on the board too: the board is the list, and the shift does not keep
    a list of its own. A draft is not on the board for the shift: the
    shift does not work a draft, so it does not count one either."""
    keys = set()
    for repo in LANE_REPOS:
        data = (snapshot.get("repos") or {}).get(repo) or {}
        for pr in data.get("prs") or []:
            if pr.get("isDraft"):
                continue
            key, issue = pr_item(repo, pr)
            if not ticket_held(snapshot, repo, issue):
                keys.add(key)
    for ticket in snapshot.get("tickets") or []:
        repo = ticket.get("repo") or ""
        number = ticket.get("number")
        if repo not in LANE_REPOS or not number:
            continue
        if (ticket.get("stage") or "") not in ("todo", "started"):
            continue
        if ticket_held(snapshot, repo, number):
            continue
        keys.add(f"{repo}#{number}")
    return keys


def builder_thread(repo, body):
    refs = re.findall(r"\bRefs #(\d+)", body)
    receipts = json.load(open(RECEIPTS))
    for ref in refs:
        prefix = f"ticket:{repo}#{ref}:a"
        best = max(((int(k[len(prefix):]), v) for k, v in receipts.items()
                    if k.startswith(prefix) and k[len(prefix):].isdigit()), default=None)
        if best:
            return ref, best[1]
    return (refs[0] if refs else None), None


def pr_action(pr, builder, verdict="absent", gate_live=False, builder_live=False):
    head = pr.get("headRefOid") or ""
    body = pr.get("body") or ""
    checks = pr.get("statusCheckRollup") or []
    failed = any((c.get("conclusion") or c.get("state") or "").upper()
                 in {"FAIL", "FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"} for c in checks)
    agent_ok = any("agent-check" in (c.get("context") or c.get("name") or "")
                   and (c.get("conclusion") or c.get("state") or "").upper() == "SUCCESS" for c in checks)
    check_ok = bool(head and re.search(rf"(?m)^Builder check: PASS {re.escape(head)}\s*$", body)) or agent_ok
    if pr.get("isDraft"):
        state, action = "draft", "finish"
    elif pr.get("mergeable") == "CONFLICTING":
        state, action = "conflict", "rebase"
    elif not re.search(r"\bRefs #\d+", body):
        state, action = "no-ticket-link", "link"
    elif failed or not check_ok:
        state, action = ("check-failed" if failed else "check-missing"), "check"
    elif gate_live or verdict == "running":
        return "gate-running", "none"
    elif verdict == "none":
        return "gate-no-verdict", "regate"
    elif verdict == "PASS":
        state, action = "gate-pass-unmerged", "fix"
    elif verdict == "FAIL":
        state, action = "gate-fail", "fix"
    else:
        return "ready-for-gate", "gate"
    if builder_live:
        return state, "none"
    return (state, action) if builder else ("needs-you", "needs-you")


def gate_in_flight(thread_id):
    status = (t3("t3_thread_read", {"threadId": thread_id, "limit": 1}).get("thread") or {}).get("status")
    return status in ("running", "queued", "starting", "preparing")


def gate_verdict(repo, number, head, base):
    receipts = json.load(open(RECEIPTS)) if os.path.exists(RECEIPTS) else {}
    key = f"gate:{repo}#{number}:{head}"
    current = receipts.get(key)
    if not current:
        return "absent", None, ""
    gate = {"threadId": current}
    if gate_in_flight(current):
        return "running", gate, ""
    reply = last_reply(current)
    if reply.endswith("VERDICT: FAIL"):
        return "FAIL", gate, reply
    if not complete_pass(reply, head) and not (
            complete_pass(reply, head, provides=False)
            and prompt_pull(repo, number, None, base, head) == prompt_paths.HOLD):
        return "none", gate, reply
    if receipts.get(f"base:{current}") != base:
        return "absent", None, ""
    earlier = sorted({v for k, v in receipts.items() if k.startswith(key + ":") and v != current
                      and receipts.get(f"base:{v}") == base})
    for thread in earlier:
        if gate_in_flight(thread):
            return "running", {"threadId": thread}, ""
    if any(last_reply(thread).endswith("VERDICT: FAIL") for thread in earlier):
        return "SPLIT", gate, reply
    return "PASS", gate, reply


def gate_split_decision(repo, number, head):
    key = CFG[repo]["key"]
    item = {"id": f"lane-gate-split-{key}-{number}", "group": "Coordinator", "kind": "action",
            "title": (f"{key}-{number} has a gate PASS and a gate FAIL on head {head[:8]}. "
                      "Nothing merged: read both reports and merge it or send it back."),
            "why": ("Two gates reviewed the same head and disagreed, so the lane does not merge on the "
                    "PASS. If the FAIL is wrong, merge it yourself pinned to this head.")}
    if DRY:
        return f"DRY #{number}: gate PASS and FAIL on one head, one decisions item"
    publish_decision(item)
    return f"#{number}: gate PASS and FAIL on head {head[:8]}, no merge, decisions item raised"


def duplicate_refusal(exc):
    """True when coordq refused a start because the queue already holds it.

    The queue is the record of what it holds: an item waiting there, or a
    message a thread is still working, is the same message. A refusal is a
    skip, not a failure: the pass tried to say something twice.
    """
    parts = [getattr(exc, "output", "") or "", getattr(exc, "stderr", "") or ""]
    return any("refused: duplicate message" in part for part in parts if isinstance(part, str))


def start(args, prio, ledger, lkey):
    if lkey in ledger:
        return f"already done {lkey}"
    if DRY:
        return f"DRY {lkey}"
    try:
        out = run([COORDQ, "start", json.dumps(args), "--priority", str(prio)]).splitlines()[-1]
    except subprocess.CalledProcessError as exc:
        if duplicate_refusal(exc):
            return f"skip {lkey}: the queue already holds this message"
        raise
    ledger[lkey] = out
    return out


def pr_action_skip(repo, number):
    pr = read_json(["gh", "pr", "view", str(number), "-R", repo,
                    "--json", "number,state,headRefName,baseRefName,headRefOid,body,changedFiles"])
    branches = [pr.get(field) for field in ("headRefName", "baseRefName")]
    if any(not isinstance(branch, str) or not branch for branch in branches):
        return pr, f"skip #{number}: missing PR branch names"
    if any(branch.startswith("herdr/") for branch in branches):
        return pr, f"skip #{number}: herdr branch, Shyam merges"
    if pr.get("state") in ("MERGED", "CLOSED"):
        return pr, f"skip #{number}: PR is merged or closed"
    if pr.get("state") != "OPEN":
        return pr, f"skip #{number}: PR state could not be read"
    return pr, None


def repo_root(repo):
    """Return the shared checkout of a repository, or none when unknown."""
    folder = PATHS.get(repo)
    return "/Users/shyamsivakumar/Code/" + folder if folder else None


def root_workspace(thread):
    """Say whether a thread works in the root checkout of a repository.

    A thread without a worktree works in the project root. A worktree
    that is the root checkout of a repository is that repository's shared
    checkout: the root checkout keeps the common git directory of the
    repository, while a linked worktree keeps its own. Pull request work
    in a shared checkout moves the branch everyone installs from, so it
    never belongs there.
    """
    path = thread.get("worktreePath")
    if not path:
        return True
    try:
        listing = run(["git", "-C", path, "rev-parse", "--git-dir", "--git-common-dir"], timeout=60)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        # A path that cannot be read cannot be shown to be a worktree of
        # its own, so pull request work does not go there.
        return True
    lines = listing.splitlines()
    if len(lines) != 2:
        return True
    return os.path.realpath(os.path.join(path, lines[0])) == os.path.realpath(os.path.join(path, lines[1]))


def branch_on_origin(repo, branch):
    """Say whether a branch is on origin, so a worktree can start there.

    A worktree that cannot start at its base ref would fall back to the
    shared root of the repository, so a branch that is not on origin is
    not a safe base for pull request work.
    """
    root = repo_root(repo)
    if not root or not os.path.isdir(root):
        return False
    try:
        listing = run(["git", "-C", root, "ls-remote", "--heads", "origin", branch], timeout=60)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    return bool(listing.strip())


def send(thread_id, message, title, ledger, lkey, repo=None, priority=800, pr_number=None, worktree_only=False):
    """Send work to a thread, or start a fresh one when it cannot take it.

    With `worktree_only` the work belongs in a worktree of its own: a
    thread that works in a shared checkout of a repository never takes
    it, and the work starts a fresh worktree instead. That is the
    fix-check path's rule; the other paths keep their own routing.
    """
    repo = repo or next((r for r in CFG if r in lkey), None)
    pr = None
    if pr_number is not None:
        pr, skip = pr_action_skip(repo, pr_number)
        if skip:
            return skip
    if lkey in ledger:
        return f"already done {lkey}"
    thread = t3("t3_thread_read", {"threadId": thread_id, "limit": 1}).get("thread") or {}
    fixer = model_list.first_available("fix")
    if fixer is None:
        return f"skip {lkey}: every fix model is blocked"
    for attached in thread.get("pullRequests") or []:
        if attached.get("repository") == repo and attached.get("number"):
            _, skip = pr_action_skip(repo, attached["number"])
            if skip:
                return skip
    sendable = (thread.get("status") in {"completed", "interrupted", "failed", "running", "waiting", "queued", "starting", "preparing"}
                and not thread.get("archived") and thread.get("sendable") is not False
                and thread.get("canSend") is not False)
    reroute = "unreachable"
    thread_model = {"instanceId": thread.get("providerInstanceId"), "model": thread.get("model")}
    if not model_list.same_selection(thread_model, fixer["selection"]):
        if thread.get("status") in {"running", "waiting", "queued", "starting", "preparing"}:
            return (f"skip {lkey}: thread is {thread.get('status')} on "
                    f"{model_list.identity(thread_model) or 'an unknown model'}, "
                    f"not the first available fix model; held until it is idle")
        if thread.get("status") in {"completed", "interrupted", "failed"}:
            sendable = False
            reroute = "model is not first available"
    if sendable and worktree_only and root_workspace(thread):
        # Pull request work in a shared checkout of the repository moves
        # the branch everyone installs from, so it starts a fresh
        # worktree instead of the thread that works there.
        sendable = False
        reroute = "root workspace"
    if sendable:
        workspace = None
        args = {"threadId": thread_id, "message": message}
        options = ["--tool", "t3_thread_send", "--priority", str(priority), "--title", title]
    else:
        repo = repo or next((r for r in CFG if r in lkey), None)
        if not repo:
            raise ValueError(f"No repository for {lkey}")
        if reroute == "model is not first available" and not root_workspace(thread):
            workspace = {"type": "existing_worktree", "worktreePath": thread["worktreePath"]}
        else:
            if pr is None:
                return f"skip {lkey}: no verified PR branch for relaunch"
            if worktree_only and not branch_on_origin(repo, pr["headRefName"]):
                return f"skip {lkey}: branch {pr['headRefName']} is not on origin, no safe worktree"
            workspace = {"type": "worktree", "baseRef": "origin/" + pr["headRefName"], "startFromOrigin": True}
        # The client request names the work this launch starts, so the queue
        # refuses a second launch for the same work while this one runs.
        args = {"projectId": CFG[repo]["projectId"], "title": title,
                "taskType": "fix", "modelSelection": fixer["selection"], "runtimeMode": "full-access",
                "workspaceStrategy": workspace, "message": message,
                "clientRequestId": lkey}
        options = ["--priority", str(priority)]
    if DRY:
        return f"DRY {lkey}: {json.dumps(workspace) if workspace else 'send existing thread'}"
    try:
        receipt = run([COORDQ, "start", json.dumps(args), *options]).strip()
    except subprocess.CalledProcessError as exc:
        if duplicate_refusal(exc):
            return f"skip {lkey}: the queue already holds this message"
        raise
    if not receipt:
        raise RuntimeError(f"Empty dispatch receipt for {lkey}")
    out = receipt.splitlines()[-1]
    ledger[lkey] = out
    if not sendable:
        print(f"SEND REROUTE {thread_id}: {out}")
        return f"fresh ({thread_id} {reroute}): {out}"
    return out


NEVER_START = {("shyamsivakumar/strategy-replay-workbench", 468)}


def park(repo, number, issue, head, reply, ledger):
    lkey = f"park:{repo}#{number}"
    if lkey in ledger:
        return f"#{number}: parked, re-cut on the way"
    if DRY:
        return f"DRY park #{number}"
    recutter = model_list.first_available("build")
    if recutter is None:
        return f"#{number}: park waits, every builder is blocked"
    if issue:
        run(["gh", "issue", "edit", str(issue), "-R", repo, "--remove-label", "stage:todo", "--add-label", "stage:backlog"])
        run(["gh", "issue", "comment", str(issue), "-R", repo, "--body",
             f"Parked by the lane (specs/lane.md section 6): PR #{number} failed its gate after two fix rounds (head {head[:8]}). A builder re-cuts it into smaller tickets."])
    msg = (f"Type: design · {recutter['id']} (re-cut a parked ticket; coordinator specs/lane.md is at /Users/shyamsivakumar/Code/coordinator/specs/lane.md)\n\n"
           f"Ticket {repo}#{issue} with PR #{number} failed its gate after two fix rounds. Read the issue, the PR diff (`gh pr diff {number} -R {repo}`) and the last gate report below. "
           "Re-cut the remaining work into at most 2 ordered tickets that each fit a 5-minute builder turn. Consolidate any further work into those tickets; never create a third ticket. Use the 12-section template in ~/.coordinator/tickets.json, "
           "with Requires/Provides lines, chained with --add-blocked-by, labels stage:todo,type:<type>,priority:<same>; reuse the PR branch as the base if most of it is right and say so in the first ticket. "
           f"Then comment on #{issue} with the new tickets and close it as not planned. Open every new ticket with `ticket open --repo {repo} --title \"<title>\" --body-file <file> --label stage:todo,type:<type>,priority:<n>`; the tool mints the key, so never type the key yourself and never use `gh issue create`. Device and live testing are waived. Start nothing, change no code, 10 minutes.\n\nLast gate report:\n" + reply[-5000:])
    args = {"projectId": CFG[repo]["projectId"], "title": f"{CFG[repo]['key']} re-cut #{issue} (PR #{number})", "taskType": "design", "modelSelection": recutter["selection"],
            "runtimeMode": "full-access", "workspaceStrategy": {"type": "root"}, "message": msg}
    out = run([COORDQ, "start", json.dumps(args), "--priority", "900"]).splitlines()[-1]
    ledger[lkey] = out
    return f"#{number}: parked, re-cut {out}"


MAC_OPS_REPO = "shyamsivakumar/mac-ops"
SRW_REPO = "shyamsivakumar/strategy-replay-workbench"


def fix_rounds_sent(repo, number, ledger):
    """The fix rounds the ledger already holds for one pull request.

    A fix round is the answer to one failed review, so the fix rounds
    the ledger holds are the failed reviews the pull request already
    had. The count starts from them, so a pull request that two earlier
    lane sessions already sent two fix rounds to is not answered with a
    third one: that would be the 4th review the rule refuses.
    """
    prefix = f"fix:{repo}#{number}:"
    return sum(1 for key in ledger if key.startswith(prefix))


def failed_reviews(repo, number, ledger):
    """The failed gate reviews of one pull request, and the head of the last.

    The count is per pull request, not per head: a pull request that
    failed its gate, was fixed and failed again has had two reviews. The
    head is kept with the count, so one failed review is never counted
    twice when a later pass sees it again.
    """
    state = ledger.get(f"rounds:{repo}#{number}") or {}
    count = max(int(state.get("count", 0)), fix_rounds_sent(repo, number, ledger))
    return count, state.get("head")


def record_failed_review(repo, number, head, ledger):
    """Count the failed gate review in hand, and return the count."""
    count, last = failed_reviews(repo, number, ledger)
    if last == head or f"fix:{repo}#{number}:{head}" in ledger:
        return count
    count += 1
    ledger[f"rounds:{repo}#{number}"] = {"count": count, "head": head}
    return count


OPEN_FINDINGS_NONE = "Open critical or major findings: none"
OPEN_FINDINGS_INSTRUCTION = (
    "This is the last review round. The second-to-last line of your report must be exactly "
    f"`{OPEN_FINDINGS_NONE}` or `Open critical or major findings: <n>` (the count of critical "
    "and major findings still open), after your CHECK line and followed by the final VERDICT line.")


def no_open_findings(reply, head):
    """True when a FAIL report fails only for the round cap.

    The report needs `CHECK: PASS <head>` and no `CHECK: FAIL` line, the none
    line as the last non-blank line before `VERDICT: FAIL`, and nothing but
    trailing whitespace stripped from any line.
    """
    lines = [line.rstrip() for line in reply.splitlines() if line.strip()]
    return (len(lines) >= 2 and lines[-1] == "VERDICT: FAIL" and lines[-2] == OPEN_FINDINGS_NONE
            and f"CHECK: PASS {head}" in lines
            and not any(line.startswith("CHECK: FAIL") for line in lines))


def gate_round_item(repo, number, head):
    """The one decisions item a pull request with no review rounds left raises."""
    return {
        "id": f"lane-gate-rounds-{repo.replace('/', '-')}-{number}",
        "group": "Coordinator",
        "kind": "ask",
        "title": (f"Shyam, PR #{number} in {repo} failed {GATE_ROUND_CAP} gate rounds without PASS. "
                  "Re-cut it into smaller pull requests, or take it over yourself."),
        "cause": f"{repo}#{number} head {head[:8]}: {GATE_ROUND_CAP} review rounds without PASS",
        "why": ("The gate failed three review rounds without PASS, so the lane stopped sending fix "
                "rounds: this pull request is not reviewed a 4th time as it is. It is re-cut into "
                "smaller pull requests, or Shyam takes it over."),
        "options": [
            {"label": "Re-cut it into smaller pull requests",
             "detail": "The coordinator re-cuts the remaining work into at most two ordered tickets.",
             "recommended": True},
            {"label": "Take it over",
             "detail": "Shyam reads the pull request and the last gate report and decides what happens to it.",
             "recommended": False},
        ],
    }


def card_on_board(alarm_id):
    """True when the decisions item is on the board it belongs to.

    The item id is fixed per pull request, so the board is the only place
    that says whether the card is still there. A board that cannot be read
    reads as no card, so a missing card is raised again instead of being
    trusted to a ledger key.
    """
    _, board = alarms.read_board(alarms.board_for(DECISIONS_PATH, alarm_id))
    return any(isinstance(entry, dict) and entry.get("id") == alarm_id
               for entry in (board or {"items": []})["items"])


def gate_round_decision(repo, number, head, ledger):
    """Raise the one decisions item for a pull request that used its rounds.

    The board holds one item per pull request: the item has a fixed id,
    so a later pass over the same pull request finds it already raised
    instead of raising a second one. The ledger key alone is not proof
    that the card is there: a card that was withdrawn or never written is
    raised again, so the ledger and the board cannot disagree.
    """
    lkey = f"rounds-decision:{repo}#{number}"
    item = gate_round_item(repo, number, head)
    if lkey in ledger:
        if DRY:
            return f"DRY #{number}: no fix round, the decisions item is on the board"
        if alarms.migrate_stale(DECISIONS_PATH, item["id"]) != "wrote":
            return f"#{number}: the decisions item could not be published"
        if card_on_board(item["id"]):
            return f"#{number}: no fix round, the decisions item is on the board"
        if alarms.route_update(DECISIONS_PATH, item["id"], "raise", item) != "wrote":
            return f"#{number}: the decisions item could not be published"
        return f"#{number}: no fix round, the decisions item was raised again"
    if DRY:
        return f"DRY #{number}: no fix round, one decisions item"
    if alarms.route_update(DECISIONS_PATH, item["id"], "raise", item) != "wrote":
        return f"#{number}: the decisions item could not be published"
    ledger[lkey] = item["id"]
    return (f"#{number}: no fix round after {GATE_ROUND_CAP} failed reviews, "
            "one decisions item is on the board")


def gate_rounds_used(repo, number, ledger):
    """True when a pull request has used the reviews the rule gives it.

    A pull request that used them is re-cut into smaller pull requests
    or taken over by Shyam, so the lane sends it no 4th review of it as
    it is. The check is asked before every review, not only after a
    failed one: a new head with no verdict yet would otherwise be
    reviewed again.
    """
    count, _ = failed_reviews(repo, number, ledger)
    return count >= GATE_ROUND_CAP


def clear_gate_round_decision(repo, number, ledger):
    """Take the decisions item of a pull request off the board when it passes.

    Returns False when the item is still on the board. The ledger key
    stays, so the next pass retries the removal.
    """
    lkey = f"rounds-decision:{repo}#{number}"
    if lkey not in ledger:
        return True
    item = gate_round_item(repo, number, "")
    if not DRY and alarms.route_update(DECISIONS_PATH, item["id"], "remove") != "wrote":
        return False
    ledger.pop(lkey, None)
    return True


def check_step(repo, proof_path):
    """The step a builder takes to put a passing check on its head.

    Only mac-ops writes a proof file, so only mac-ops is told to commit
    one. The other repositories publish their own check.
    """
    if repo == MAC_OPS_REPO:
        return (f"run the repo check (`python3 scripts/mac_ops_fast_check.py --proof {proof_path}`), "
                f"commit the proof file `{proof_path}` it writes")
    if repo == SRW_REPO:
        return "rely on srw/agent-check (do not run scripts/check.sh)"
    return "run the repo's full local check"


def pr_paths(repo, number, changed_files=None):
    """The paths a pull request changed, or None when GitHub cannot say.

    Both names of a renamed file count. Moving `prompts/reviewer.md` to
    `archive/reviewer.md` removed prompt text, so a read that looked at the
    new name alone would let that pull request merge. A list shorter than
    the pull request's own changed-file count may have left the one prompt
    file out (the files endpoint stops at 3,000), so it is no list at all.
    """
    output = run(["gh", "api", "--paginate", "--slurp",
                  f"repos/{repo}/pulls/{number}/files?per_page=100"])
    try:
        pages = json.loads(output or "[]")
    except ValueError:
        return None
    entries = prompt_paths.page_entries(pages)
    if entries is None:
        return None
    if not prompt_paths.list_is_complete(entries, changed_files):
        return None
    return prompt_paths.entries_paths(entries)


def pr_changed_count(repo, number):
    """The pull request's own changed-file count, or None when unreadable.

    The count is what tells a complete file list from a capped one, so a list
    read without it is deferred rather than trusted.
    """
    output = run(["gh", "api", f"repos/{repo}/pulls/{number}"])
    try:
        pull = json.loads(output or "{}")
    except ValueError:
        return None
    count = pull.get("changed_files") if isinstance(pull, dict) else None
    return count if isinstance(count, int) else None


def api_json(endpoint):
    """One `gh api` read of an endpoint, parsed as JSON."""
    return json.loads(run(["gh", "api", endpoint]) or "{}")


def prompt_pull(repo, number, changed_files=None, base=None, head=None, attempts=2):
    """HOLD, CLEAR or UNKNOWN for the paths a pull request changed.

    The merge base and the head are pinned by the caller, so their trees are
    read first: a file list is read by pull-request number and describes
    whatever head GitHub holds at that moment, so a code-only revision could
    clear a prompt-changing head that is restored before the merge. An
    unreadable tree diff is retried, then UNKNOWN: the lane defers a passing
    pull request it cannot read instead of merging it blind.

    A caller with no pinned pair has only the file list, and a list that is
    unreadable or short is UNKNOWN.
    """
    if base and head:
        return prompt_paths.scan_diff(api_json, repo, base, head, attempts)
    try:
        count = changed_files if isinstance(changed_files, int) else pr_changed_count(repo, number)
    except (RuntimeError, ValueError, subprocess.SubprocessError):
        return prompt_paths.UNKNOWN
    for _ in range(max(1, attempts)):
        try:
            paths = pr_paths(repo, number, count)
        except (RuntimeError, ValueError, subprocess.SubprocessError):
            # A `gh` read that failed is retried, never guessed at.
            continue
        state = prompt_paths.prompt_scan(paths)
        if state != prompt_paths.UNKNOWN:
            return state
    return prompt_paths.UNKNOWN


def publish_decision(item):
    """Put one item on Shyam's decisions board, under the board's lock."""
    return alarms.route_update(DECISIONS_PATH, item["id"], "raise", item)


def prompt_merge_item(repo, number, head):
    """The one item Shyam answers to merge a prompt pull request that passed."""
    key = CFG[repo]["key"]
    return {"id": f"prompt-merge-{key}-{number}", "group": "Coordinator", "kind": "action",
            "title": (f"{key}-{number} passed its gate in {repo}. It changes prompt, skill or playbook "
                      f"text, so it waits for you: merge it or close it."),
            "why": (f"Prompt text never auto-merges (your rule), so the lane stopped at the verdict on "
                    f"head {head[:8]} and merged nothing. Merge with "
                    f"`gh pr merge {number} -R {repo} --squash --match-head-commit {head}`.")}


def withdraw_decision(item_id):
    """Take one item off Shyam's board, once the pull request is settled."""
    return alarms.route_update(DECISIONS_PATH, item_id, "remove", None)


def pull_settled(repo, number):
    """True only when the pull request itself says it is merged or closed.

    The open list the snapshot holds stops at 200 pull requests, so an older
    open request can fall outside it; absence from that list is not proof
    that Shyam settled it. Only the pull request's own state answers that,
    and a read that fails answers nothing: the card stays until the state is
    known rather than disappearing while its pull request is still open.
    """
    try:
        state = json.loads(run(["gh", "pr", "view", str(number), "-R", repo,
                                "--json", "state,mergedAt"]))
    except (subprocess.SubprocessError, RuntimeError, ValueError):
        return False
    if not isinstance(state, dict):
        return False
    return state.get("state") in ("MERGED", "CLOSED") or bool(state.get("mergedAt"))


def reconcile_prompt_items(snapshot):
    """Take merge asks off the board for pull requests Shyam settled.

    A prompt pull request Shyam merged or closed between two passes is not in
    the snapshot any more, so no per-pull-request action ever reaches its
    item: the board would keep asking for work that is done. The items are
    read once here and the stale ones are removed by the key and number their
    id carries. A request that left the capped open list without being
    settled is still open, so each candidate's own state is read before its
    card goes. Return how many were removed.
    """
    boards = []
    for path in (Path(DECISIONS_PATH), alarms.board_for(DECISIONS_PATH, "prompt-merge-MO-0")):
        try:
            boards.append(alarms.read_board(path)[1])
        except OSError:
            continue
    items = {str(i.get("id")): i for b in boards if isinstance(b, dict)
             for i in b.get("items") or [] if isinstance(i, dict)}.values()
    repos_by_key = {CFG[repo]["key"]: repo for repo in CFG if repo in LANE_REPOS}
    open_prs = {(repo, pull["number"]) for repo, data in snapshot["repos"].items()
                for pull in data["prs"]}
    removed = 0
    for item in items:
        match = re.fullmatch(r"prompt-merge-([A-Za-z0-9]+)-(\d+)", str(item.get("id") or ""))
        if not match or match.group(1) not in repos_by_key:
            continue
        repo, number = repos_by_key[match.group(1)], int(match.group(2))
        if (repo, number) in open_prs:
            continue
        if DRY:
            continue
        # Absent from the capped list is not settled: confirm it on the pull
        # request, and leave the card when the state cannot be read.
        if not pull_settled(repo, number):
            continue
        if withdraw_decision(item["id"]) == "wrote":
            removed += 1
    return removed


def prompt_pass(repo, number, head, prompt):
    """What the lane does with a passing pull request's path state.

    A prompt, skill or playbook change never auto-merges (Shyam): the lane
    stops at the verdict and asks him once. A dry run writes nothing at all,
    and an unknown list defers to the next run rather than merging blind.
    None means the merge may go ahead.
    """
    if prompt == prompt_paths.UNKNOWN:
        return (f"skip #{number}: gate PASS, the changed-file list could not be read on "
                f"head {head[:8]}, next run retries")
    if prompt != prompt_paths.HOLD:
        return None
    if DRY:
        return f"DRY hold #{number} {head}"
    if publish_decision(prompt_merge_item(repo, number, head)) != "wrote":
        return f"skip #{number}: prompt change, the decisions item could not be written"
    return f"skip #{number}: gate PASS, prompt change, Shyam merges"


def base_moved_item(repo, number, head, landed, base):
    """The item Shyam answers when a merge landed on a base nobody reviewed.

    The merge API pins no base, so the guard reads the base again after the
    merge; a merge that landed elsewhere is not silently reported as a merge
    on the reviewed base. The item is what makes that reach Shyam instead of
    a log line nobody reads.
    """
    key = CFG[repo]["key"]
    return {"id": f"base-moved-{key}-{number}", "group": "Coordinator", "kind": "action",
            "title": (f"{key}-{number} merged into `{landed}`, not the reviewed `{base}`: "
                      f"read head {head[:8]} and decide whether to keep it."),
            "why": ("The merge call pins the head only, so a retarget inside the last moment before "
                    "it cannot be refused by the merge. Nothing was closed and main was not "
                    "fast-forwarded. Inspect the merged diff for prompt files before keeping it.")}


def merge_on_reviewed_base(repo, number, head, base):
    """Merge one pull request only when its base is still the reviewed one.

    `--match-head-commit` pins the head, and nothing in the merge call pins
    the base: a retarget leaves the head where it is. Two things guard the
    interval around the merge. The base and head are read once immediately
    before it, and a pull request that moved merges nothing. The base is read
    once more after it: a merge cannot pin its base, so a retarget that slipped
    into that interval would otherwise be reported as a merge on the reviewed
    base. A merge that landed on another base is reported as one that is not
    the reviewed review's, and the caller closes nothing and fast-forwards
    nothing, so the outcome Shyam reads is never "merged as reviewed" for a
    base nobody reviewed.
    Return (merged, note): merged means the merge was issued onto the reviewed
    base; note is the line the pass prints.

    The residue this cannot remove, and why it is accepted:

    The merge call pins the head and squashes, and the pull request carries the
    base. So a retarget landing between the read above and the merge below is
    merged into the new base, and the read after it reports that instead of
    claiming a merge on the reviewed base. No GitHub merge call pins a base and
    a head together: the `merges` endpoint names the base but cannot squash and
    takes a head commit, and pushing the squash by hand bypasses the pull
    request merge and is refused where direct pushes are restricted. Six
    designs along those lines were built, each losing one of the properties
    this rule needs, which is why the ticket's own merge is the one kept.

    Who reaches the window: retargeting a pull request needs write access to
    the repository, so on a private repository it is the owner racing his own
    two calls, not an outsider. The prompt rule itself is unaffected: the
    classification decides on the pull request's own diff, and anything the
    pull request introduces against the base this review read still holds.
    """
    current = json.loads(run(["gh", "pr", "view", str(number), "-R", repo,
                              "--json", "baseRefName,headRefOid"])) or {}
    if current.get("baseRefName") != base or current.get("headRefOid") != head:
        return False, (f"skip #{number}: gate PASS, but the pull request moved (base {base} -> "
                       f"{current.get('baseRefName')}, head {head[:8]} -> "
                       f"{str(current.get('headRefOid'))[:8]}); nothing merged, the next pass reviews it")
    try:
        run(["gh", "pr", "merge", str(number), "-R", repo, "--squash", "--match-head-commit", head])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        after = json.loads(run(["gh", "pr", "view", str(number), "-R", repo, "--json", "state"])) or {}
        if after.get("state") != "MERGED":
            raise
    landed = json.loads(run(["gh", "pr", "view", str(number), "-R", repo,
                             "--json", "baseRefName"])) or {}
    if landed.get("baseRefName") != base:
        # The pull request cannot be retargeted once it is merged, so the base
        # it names now is the base the merge landed on. The item puts that in
        # front of Shyam; the pass itself claims no merge.
        published = publish_decision(base_moved_item(repo, number, head,
                                                     landed.get("baseRefName"), base))
        return False, (f"critical #{number}: the merge landed on base "
                       f"{landed.get('baseRefName')}, not the reviewed {base}; nothing closed, "
                       f"nothing fast-forwarded, Shyam has the item ({published})")
    return True, f"#{number}: merged {head}"
def message_title(repo, number, action, head):
    """The title of one message about one head of one pull request.

    The queue names a message by its title and its target, so the head is in
    the title: two heads of one pull request are two messages to the same
    builder thread, and the second must not be read as a copy of the first.
    The whole head is in the title, because two heads can share a short
    prefix and their messages are still two messages. Two passes over one
    head keep one title, so they still queue once.
    """
    return f"{CFG[repo]['key']}#{number} {action} {head}"


def superseded_by(repo, number, issue):
    """True when a newer open pull request names the same ticket.

    A pull request the board replaced with a newer one for the same ticket
    is superseded: its findings belong to the newer work, and a message to
    it is a message nobody reads.
    """
    for other in SNAPSHOT["repos"][repo]["prs"]:
        if other["number"] <= number or other.get("isDraft"):
            continue
        if re.search(rf"\bRefs #{issue}\b", other.get("body") or ""):
            return True
    return False


def merge_passed_pr(repo, number, head, pr, issue, gate, ledger):
    # A prompt, skill or playbook change never auto-merges (Refs #543):
    # the hold comes first, so a prompt PR is written to the board before
    # anything else looks at the merge.
    held = prompt_pass(repo, number, head,
                       prompt_pull(repo, number, pr.get("changedFiles"),
                                   pr.get("baseRefName") or "main", head))
    if held:
        return held
    # Main's gate-round bookkeeping: the round's decisions item must leave
    # the board before the merge, or the merge waits.
    if not clear_gate_round_decision(repo, number, ledger):
        return f"#{number}: gate PASS, the decisions item could not be taken off the board, no merge until it is"
    if merge_mode(repo, CFG[repo]) in ("manual", "ascend"):
        return manual_merge_ask(repo, number, head)
    base = pr.get("baseRefName") or "main"
    if DRY:
        return f"DRY merge #{number} {head}"
    # A retarget moves the pull request onto another base without moving
    # its head, and the same head can then introduce prompt text it did
    # not introduce against the base this pass classified. The base and
    # head are read again inside the merge step, as close to the merge as
    # the merge can be guarded: a pull request that moved merges nothing.
    merged, note = merge_on_reviewed_base(repo, number, head, base)
    if not merged:
        return note
    close_after_merge(repo, number, head, issue, gate, ledger)
    return note


def manual_merge_ask(repo, number, head):
    key = CFG[repo]["key"]
    item = {"id": f"manual-merge-{key}-{number}", "group": "Coordinator", "kind": "action",
            "title": f"{key}-{number} passed its gate in {repo}. This repository merges by hand: merge it or send it back.",
            "why": f"Nothing merged. Merge with `gh pr merge {number} -R {repo} --squash --match-head-commit {head}`."}
    if not DRY:
        publish_decision(item)
    return f"#{number}: gate PASS, manual merge, decisions item raised"


def after_merge(repo, number, head, issue, gate):
    if issue:
        ref = f"{repo}#{issue}"
        output = run(["ticket", "close", ref, "--pr", str(number), "--head", head,
                      "--gate-thread", gate["threadId"]])
        if "is already closed" in output:
            print(f"already-closed:{ref}: {output}")
    fast_forward_main(repo)


def close_failed_item(repo, number, head, issue):
    key = CFG[repo]["key"]
    return {"id": f"lane-close-failed-{key}-{number}", "group": "Coordinator", "kind": "action",
            "title": (f"{key}-{number} is merged at head {head[:8]} but closing {key}-{issue} failed: "
                      "check why and close the ticket yourself."),
            "why": "The lane tried the close once and does not retry it every pass."}


def close_after_merge(repo, number, head, issue, gate, ledger):
    lkey = f"after-merge:{repo}#{number}:{head}"
    try:
        after_merge(repo, number, head, issue, gate)
    except subprocess.CalledProcessError:
        ledger[lkey] = "close failed"
        publish_decision(close_failed_item(repo, number, head, issue))
        return
    ledger[lkey] = "closed"


def merged_without_gate_item(repo, number, head):
    key = CFG[repo]["key"]
    return {"id": f"lane-merged-unreviewed-{key}-{number}", "group": "Coordinator", "kind": "action",
            "title": (f"{key}-{number} is merged at head {head[:8]} with no recorded gate PASS, "
                      "so its ticket stays open: check the merge and close the ticket yourself."),
            "why": "The lane closes a ticket only after a merge whose head the recorded gate attempt passed."}


def settle_merged_prs(repo, ledger):
    merged = json.loads(run(["gh", "pr", "list", "-R", repo, "--state", "merged", "--limit", "10",
                             "--json", "number,headRefOid,body,mergedAt,baseRefName"]) or "[]")
    since = ledger.setdefault("settle-since", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    for pr in merged:
        if (pr.get("mergedAt") or "") < since:
            continue
        number, head = pr["number"], pr["headRefOid"]
        lkey = f"after-merge:{repo}#{number}:{head}"
        found = re.search(r"\bRefs #(\d+)", pr.get("body") or "")
        if lkey in ledger or not found or issue_record(SNAPSHOT, repo, found.group(1)) is None:
            continue
        if DRY:
            print(f"DRY after-merge #{number}")
            continue
        verdict, gate, _ = gate_verdict(repo, number, head, pr["baseRefName"])
        if verdict == "PASS":
            close_after_merge(repo, number, head, found.group(1), gate, ledger)
            print(f"{CFG[repo]['key']:5} #{number}: merged earlier, ticket closed and main fast-forwarded")
        else:
            publish_decision(merged_without_gate_item(repo, number, head))
            ledger[lkey] = "item raised"


def merge_wait_item(repo, number, head, passes):
    key = CFG[repo]["key"]
    return {"id": f"merge-pass-stuck-{key}-{number}", "group": "Coordinator", "kind": "action",
            "title": f"{key}-{number} has a gate PASS on head {head[:8]} and is still unmerged after {passes} passes: check why and merge it.",
            "why": "The merge pass tried each pass and the merge was refused or failed."}


def merge_candidates(repo, ledger):
    receipts = stall_receipts()
    for key, thread in sorted(receipts.items()):
        found = re.fullmatch(r"gate:(.+)#(\d+):([0-9a-f]{40})", key)
        if (found and found[1] == repo and receipts.get(f"brief:{thread}") == "lane-merges"
                and f"merge-pass:{key[5:]}:{thread}" not in ledger):
            yield int(found[2]), found[3], thread, receipts.get(f"base:{thread}")


def merge_pass(repo, ledger):
    for number, head, thread, base in merge_candidates(repo, ledger):
        verdict, gate, _ = gate_verdict(repo, number, head, base)
        settled = f"merge-pass:{repo}#{number}:{head}:{thread}"
        if verdict in ("running", "none", "absent"):
            continue
        if verdict == "SPLIT":
            print(f"{CFG[repo]['key']:5} {gate_split_decision(repo, number, head)}")
        if verdict in ("FAIL", "SPLIT"):
            ledger[settled] = verdict
            continue
        pr, skip = pr_action_skip(repo, number)
        if skip:
            ledger[settled] = skip
            continue
        if gate_verdict(repo, number, head, pr["baseRefName"])[0] != "PASS":
            continue
        found = re.search(r"\bRefs #(\d+)", pr.get("body") or "")
        wait = f"merge-wait:{repo}#{number}:{head}"
        ledger[wait] = ledger.get(wait, 0) + 1
        if ledger[wait] >= MERGE_WAIT_PASSES:
            publish_decision(merge_wait_item(repo, number, head, ledger[wait]))
        note = merge_passed_pr(repo, number, head, pr, found[1] if found else None, gate, ledger)
        print(f"{CFG[repo]['key']:5} {note}")
        if not note.endswith("no merge until it is"):
            ledger[settled] = note
            if ledger.pop(wait) >= MERGE_WAIT_PASSES:
                withdraw_decision(merge_wait_item(repo, number, head, 0)["id"])


def restrict_merge_repos(allowed):
    global MERGE_REPOS
    MERGE_REPOS = [repo for repo in MERGE_REPOS if allowed is None or repo in allowed]


def merge_passes(ledger):
    for repo in MERGE_REPOS:
        if repo not in gate_policy.LANE_REPOS:
            with item_boundary(repo, "merge-pass", ledger):
                merge_pass(repo, ledger)


def act_on_pr(repo, number, ledger):
    if repo not in LANE_REPOS:
        return None
    pr = next((p for p in SNAPSHOT["repos"][repo]["prs"] if p["number"] == number), {})
    if pr.get("state") != "OPEN":
        return None
    current_pr, skip = pr_action_skip(repo, number)
    if skip:
        if current_pr.get("state") in ("MERGED", "CLOSED") and not DRY:
            # The pull request says it is settled, so its merge ask is
            # answered by whoever settled it. A state that did not come back
            # says nothing, so the card stays: an unread state is not a
            # closed pull request.
            withdraw_decision(f"prompt-merge-{CFG[repo]['key']}-{number}")
        return skip
    pr = {**pr, **current_pr}
    state = json.loads(run(["gh", "pr", "view", str(number), "-R", repo,
                            "--json", "state,mergedAt"]))
    if state.get("state") != "OPEN" or state.get("mergedAt"):
        return f"skip #{number}: PR is merged or closed"
    head, body = pr["headRefOid"], pr.get("body") or ""
    issue, builder = builder_thread(repo, body)
    if (issue and superseded_by(repo, number, int(issue))
            and gate_verdict(repo, number, head, pr.get("baseRefName") or "main")[0] != "PASS"):
        return f"skip #{number}: superseded by a newer pull request for #{issue}"
    proof_path = f"evidence/{CFG[repo]['key']}-{issue}/check-proof.md" if issue else "evidence/check-proof.md"
    if issue:
        record = issue_record(SNAPSHOT, repo, issue)
        if record is None or issue_held(record):
            return None
    agent_ok = any("agent-check" in (c.get("context") or c.get("name") or "") and (c.get("state") or c.get("conclusion")) == "SUCCESS"
                   for c in pr.get("statusCheckRollup") or [])
    check_ok = f"Builder check: PASS {head}" in body or agent_ok
    if pr.get("mergeable") == "CONFLICTING" or not check_ok:
        why = "it conflicts with main" if pr.get("mergeable") == "CONFLICTING" else f"it has no passing check on head {head}"
        if not builder:
            return f"skip #{number}: {why}, no builder thread"
        msg = (f"Coordinator: PR #{number} cannot be gated because {why}. Update the branch from origin/main if needed, "
               f"{check_step(repo, proof_path)}, push, set "
               "`Builder check: PASS <full new head sha>` on its own line in the PR body, and report the head. 20 minutes at most; every command under `timeout 300`.")
        return f"#{number} fix-check: " + send(builder, msg, message_title(repo, number, "check", head), ledger, f"check:{repo}#{number}:{head}", pr_number=number, worktree_only=True)
    base = pr.get("baseRefName") or "main"
    verdict, gate, reply = gate_verdict(repo, number, head, base)
    if verdict == "running":
        return f"#{number}: gate running"
    if verdict == "SPLIT":
        return gate_split_decision(repo, number, head)
    if verdict == "PASS":
        return merge_passed_pr(repo, number, head, pr, issue, gate, ledger)
    if verdict == "FAIL":
        # The failed review in hand is one after the reviews the pull
        # request already had. The convergence rule gives it three
        # reviews: the first review and the two fix rounds it can answer.
        # The cap is asked before the same-head retry, so a pull request
        # at the cap is never sent "Continue fixing".
        reviews = record_failed_review(repo, number, head, ledger)
        if reviews >= GATE_ROUND_CAP:
            if no_open_findings(reply, head):
                return merge_passed_pr(repo, number, head, pr, issue, gate, ledger)
            return gate_round_decision(repo, number, head, ledger)
    if verdict == "FAIL" and f"fix:{repo}#{number}:{head}" in ledger and builder:
        status = (t3("t3_thread_read", {"threadId": builder, "limit": 1}).get("thread") or {}).get("status")
        if status in ("completed", "interrupted", "failed"):
            return f"#{number} continue: " + send(
                builder, "Continue fixing the gate findings for this head. Push the fixes and report the new head.",
                message_title(repo, number, "continue", head), ledger, f"continue:{repo}#{number}:{head}", pr_number=number)
        # The findings for this head are already with the builder, which is
        # still working them. A second copy is the padding the queue had.
        return f"skip #{number}: gate findings for this head are already with the builder ({status})"
    if verdict == "FAIL":
        if not builder:
            return f"skip #{number}: FAIL, no builder thread"
        msg = (f"The gate on PR #{number} at {head} returned VERDICT: FAIL. Fix every critical and major finding below, "
               f"{check_step(repo, proof_path)}, push, set "
               "`Builder check: PASS <full new head sha>` on its own line in the PR body, and report the new head. 20 minutes at most.\n\n"
               + ("Device, handset and live-service testing is waived (Shyam 2026-11-14: \"no testing is needed lets just finish backlog building everything\"). Do not run device or live cases; state in the receipt that they were waived, not failed. Findings that only ask for device or live results are resolved by that statement.\n\n") + reply[-6000:])
        return f"#{number} fix: " + send(builder, msg, message_title(repo, number, "gate findings", head), ledger, f"fix:{repo}#{number}:{head}", pr_number=number)
    if gate_rounds_used(repo, number, ledger):
        # The pull request has used the three reviews the rule gives it.
        # It is re-cut into smaller pull requests, or Shyam takes it
        # over, and it is not reviewed a 4th time as it is.
        return gate_round_decision(repo, number, head, ledger)
    tag = "regate" if verdict == "none" else "gate"
    reviewers = json.loads(run(["ticket", "gate", f"{repo}#{number}", "--print-model"]))
    if not reviewers:
        return f"#{number}: no gate reviewer is available"
    model = reviewers[0]["selection"]
    if verdict == "none" and f"regate:{repo}#{number}:{head}:{base}" in ledger:
        if "quota" in reply.lower() and "exhaust" in reply.lower() and len(reviewers) > 1:
            tag, model = "fallbackgate", reviewers[1]["selection"]
        else:
            ledger[f"needs-you:{repo}#{number}:{head}"] = "gate ended without verdict after retry"
            return f"#{number}: needs-you, gate ended without verdict after retry"
    brief = run(["ticket", "gate", f"{repo}#{number}", "--print-brief"])
    if head not in brief:
        return f"#{number}: no gate brief ({brief[-120:]})"
    if failed_reviews(repo, number, ledger)[0] >= GATE_ROUND_CAP - 1:
        brief += f"\n{OPEN_FINDINGS_INSTRUCTION}\n"
    key = CFG[repo]["key"]
    args = {"projectId": CFG[repo]["projectId"], "title": f"{key}-{issue} review #{number} {head[:8]} ({model['model']})", "taskType": "review", "modelSelection": model,
            "runtimeMode": "full-access", "workspaceStrategy": {"type": "root"}, "clientRequestId": f"gate:{repo}#{number}:{head}:{tag}:{base}:lane",
            "message": brief}
    return f"#{number} {tag}: " + start(args, 5000, ledger, f"{tag}:{repo}#{number}:{head}:{base}")


def fast_forward_main(repo):
    if repo not in PATHS or not os.path.isdir("/Users/shyamsivakumar/Code/" + PATHS[repo]):
        print(f"{CFG[repo]['key']:5} no local checkout for {repo}; main not fast-forwarded")
        return
    canonical = "/Users/shyamsivakumar/Code/" + PATHS[repo]
    listing = run(["git", "-C", canonical, "worktree", "list", "--porcelain", "-z"])
    records = [record.split("\0") for record in listing.split("\0\0") if record]
    if not records or any(not record[0].startswith("worktree ") for record in records):
        raise RuntimeError("invalid worktree listing; main update refused")
    main_paths = [record[0][len("worktree "):] for record in records if "branch refs/heads/main" in record]
    if len(main_paths) > 1:
        raise RuntimeError("multiple main worktrees; main update refused")
    if main_paths:
        path = main_paths[0]
        if run(["git", "-C", path, "symbolic-ref", "--quiet", "HEAD"]) != "refs/heads/main":
            raise RuntimeError("main worktree branch changed; main update refused")
        run(["git", "-C", path, "pull", "--ff-only", "origin", "main"])
    else:
        run(["git", "-C", canonical, "fetch", "origin", "main:main"])


def drift_ff(ledger):
    for repo, name in PATHS.items():
        with item_boundary(repo, "main-refresh", ledger):
            if repo not in LANE_REPOS:
                continue
            d = "/Users/shyamsivakumar/Code/" + name
            if not os.path.isdir(d):
                print(f"{CFG[repo]['key']:5} checkout absent: {d}; skipping")
                continue
            run(["git", "-C", d, "fetch", "origin", "main"], timeout=120)
            out = run(["git", "-C", d, "rev-parse", "main", "origin/main"], timeout=60)
            ids = out.split()
            if len(ids) != 2 or ids[0] == ids[1]:
                continue
            try:
                run(["git", "-C", d, "merge-base", "--is-ancestor", ids[0], ids[1]], timeout=60)
            except subprocess.CalledProcessError as exc:
                if exc.returncode != 1:
                    raise
                print(f"{CFG[repo]['key']:5} left alone, not fast-forwardable ({ids[0]} vs {ids[1]})")
                continue
            if DRY:
                print(f"{CFG[repo]['key']:5} main behind ({ids[0][:8]} vs {ids[1][:8]}) DRY")
                continue
            fast_forward_main(repo)
            print(f"{CFG[repo]['key']:5} main fast-forwarded ({ids[0][:8]} -> {ids[1][:8]})")


def group_of(title):
    title = title.lower()
    if "census" in title:
        return "census"
    if any(word in title for word in ("dashboard", "design", "document", "critique", "mock")):
        return "docs"
    return "bot"


def start_next(repo, tickets, ledger, excl=frozenset()):
    ready = sorted((t for t in tickets if t["repo"] == repo and t.get("stage") == "todo" and not t.get("problems")
                    and group_of(t.get("title") or "") not in excl),
                   key=lambda t: (t.get("priority") or 9, t["number"]))
    import datetime as _dt
    now = _dt.datetime.now(_dt.timezone.utc)
    tries = 0
    for t in ready:
        with item_boundary(repo, t["number"], ledger):
            if (repo, t["number"]) in NEVER_START:
                continue
            ref = f"{repo}#{t['number']}"
            r = ledger.get(f"refused:{ref}")
            if isinstance(r, str) and (now - _dt.datetime.fromisoformat(r)).total_seconds() < 1800:
                continue
            if tries >= 3:
                break
            tries += 1
            dry = run(["ticket", "start", ref, "--dry-run"], timeout=200)
            if dry.startswith("refused: "):
                ledger[f"refused:{ref}"] = now.isoformat()
                print(f"refused:{ref}: {dry}")
                continue
            if DRY:
                return f"DRY start {t['key']} #{t['number']}"
            out = run(["ticket", "start", ref], timeout=200).splitlines()[-1]
            ledger[f"start:{ref}:{len(ledger)}"] = out
            return f"start {t['key']} #{t['number']}: {out[:60]}"
    return unstick(repo, ledger, excl)


def unstick(repo, ledger, excl=frozenset()):
    issues = SNAPSHOT["repos"][repo]["issues"]
    referenced = {int(x) for pr in SNAPSHOT["repos"][repo]["prs"]
                  for x in re.findall(r"\bRefs #(\d+)", pr.get("body") or "")}
    orphans = [i["number"] for i in issues if not any(l["name"].startswith("stage:") for l in i["labels"])
               and i["number"] not in referenced
               and (repo, i["number"]) not in NEVER_START
               and (not excl or (isinstance(i.get("title"), str) and i["title"]
                                 and group_of(i["title"]) not in excl))]
    if not orphans:
        return "nothing ready"
    receipts = json.load(open(RECEIPTS))
    failures_before = ledger.get("_item_failures", 0)
    started = set()
    for n in orphans:
        with item_boundary(repo, n, ledger):
            prefix = f"ticket:{repo}#{n}:a"
            best = max(((int(k[len(prefix):]), v) for k, v in receipts.items()
                        if k.startswith(prefix) and k[len(prefix):].isdigit()), default=None)
            if not best:
                continue
            started.add(n)
            v = ledger.get(f"cont:{best[1]}")
            if isinstance(v, list) and (__import__("datetime").datetime.now(__import__("datetime").timezone.utc) - __import__("datetime").datetime.fromisoformat(v[0])).total_seconds() < 1800:
                continue
            if not t3("t3_thread_read", {"threadId": best[1], "limit": 1}).get("thread"):
                if DRY:
                    return f"DRY start #{n}"
                out = run(["ticket", "start", f"{repo}#{n}"], timeout=200)
                ledger[f"relaunch:{repo}#{n}"] = out
                print(f"SEND REROUTE {best[1]}: {out}")
                return f"start #{n}: {out}"
            if DRY:
                return f"DRY continue #{n}"
            msg = open("/Users/shyamsivakumar/Code/coordinator/loop/continue-brief.md").read().replace("{issue}", str(n))
            out = send(best[1], msg, f"{CFG[repo]['key']}#{n} continue",
                       {}, f"continue:{repo}#{n}:{best[1]}", repo=repo, priority=900)
            ledger[f"cont:{best[1]}"] = [__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), out]
            return f"continue #{n}: {out}"
    if ledger.get("_item_failures", 0) > failures_before:
        return "continue failed"
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    def marked(k):
        v = ledger.get(k)
        if isinstance(v, list) and (now - __import__("datetime").datetime.fromisoformat(v[0])).total_seconds() < 1800:
            return True
        return False
    # A receipt is the proof a builder was started. A ticket with no receipt
    # was never started, so nothing finished and there is nothing to re-cut:
    # the batch takes only the started tickets.
    orphans = [n for n in orphans if n in started and not marked(f"unstick:{repo}#{n}")]
    if not orphans:
        return "nothing ready"
    batch = orphans[:7]
    if DRY:
        return f"DRY unstick {batch}"
    lst = ", ".join(f"#{n}" for n in batch)
    unsticker = model_list.first_available("build")
    if unsticker is None:
        return "unstick waits, every builder is blocked"
    msg = open("/Users/shyamsivakumar/Code/coordinator/loop/unstick-brief.md").read().replace("{repo}", repo).replace("{list}", lst)
    args = {"projectId": CFG[repo]["projectId"], "title": f"{CFG[repo]['key']} unstick {lst}"[:80], "taskType": "chore", "modelSelection": unsticker["selection"],
            "runtimeMode": "full-access", "workspaceStrategy": {"type": "root"}, "message": msg}
    out = run([COORDQ, "start", json.dumps(args), "--priority", "950"]).splitlines()[-1]
    stamp = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    for n in batch:
        ledger[f"unstick:{repo}#{n}"] = [stamp, out]
    return f"unstick {lst}: {out}"


# Every watched job: its log, the silence limit in minutes and its launchd
# label. The label names the plist under coordinator/launchd, which stays the
# source of truth for which jobs exist.
WATCH = {"tick": ("/Users/shyamsivakumar/Library/Logs/coordinator/tick.log", 65, "dev.coordinator.tick"),
         "gatekeep": ("/Users/shyamsivakumar/Code/coordinator/queue/gatekeep.log", 120, "dev.coordinator.gatekeep"),
         "dispatch": ("/Users/shyamsivakumar/Code/coordinator/queue/dispatch.log", 10, "dev.coordinator.dispatch"),
         "lanes": ("/Users/shyamsivakumar/Library/Logs/coordinator/lanes.log", 10, "dev.coordinator.lanes")}


def exit_status(text):
    """Return the exit status of the last run: a code, or None when unknown.

    launchd prints a plain code (`0`), a code with its name
    (`78: EX_CONFIG`) and, for a job that never ran, `(never exited)`.
    Anything that is not a number keeps the status unknown.
    """
    if text is None:
        return None
    match = re.match(r"\s*(-?\d+)", text)
    return int(match.group(1)) if match else None


def signal_status(text):
    """Return the signal that ended the last run, or 0 when there was none.

    launchd prints the number (`9`) and often the name with it
    (`Killed: 9`). The number is the signal, so the name is read past. A
    field without a number says nothing, and that is not a signal.
    """
    if text is None:
        return 0
    numbers = re.findall(r"\d+", text)
    return int(numbers[-1]) if numbers else 0


def launchd_state(label):
    """Return the launchd state of one job, or None when launchd cannot say.

    A job that launchd no longer holds has no state: `launchctl print` fails
    for it with "Could not find service". That is the difference between a
    stopped job and a job that is loaded and idle, which is the difference
    the watchdog has to see. Any other failure of launchctl is a failure to
    read, not evidence that the job stopped, so it returns None.
    """
    try:
        result = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        said = result.stdout + result.stderr
        if "Could not find service" in said:
            return {"loaded": False}
        return None
    text = result.stdout

    def field(pattern):
        match = re.search(pattern, text, re.MULTILINE)
        return match.group(1) if match else None

    return {"loaded": True,
            "runs": int(field(r"^\truns = (\d+)$") or 0),
            "exit_code": exit_status(field(r"^\tlast exit code = (.+)$")),
            "signal": signal_status(field(r"^\tlast terminating signal = (.+)$")),
            "running": field(r"^\tstate = (.+)$") == "running",
            "pid": int(field(r"^\tpid = (\d+)$") or 0)}


def process_seconds(pid):
    """Return how long a process has been running, or None when it cannot say.

    macOS ps has no `etimes`, so the elapsed time is read as `etime`, which
    prints `[[dd-]hh:]mm:ss`.
    """
    try:
        result = subprocess.run(["ps", "-o", "etime=", "-p", str(pid)],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    text = result.stdout.strip()
    days = 0
    if "-" in text:
        head, _, text = text.partition("-")
        try:
            days = int(head)
        except ValueError:
            return None
    parts = text.split(":")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if len(numbers) == 3:
        hours, minutes, seconds = numbers
    elif len(numbers) == 2:
        hours, minutes, seconds = 0, numbers[0], numbers[1]
    else:
        return None
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def log_age(path):
    """Return the age of a log in minutes, or None when the log is missing."""
    try:
        return (time.time() - os.path.getmtime(path)) / 60
    except OSError:
        return None


def silence_alarm(name, minutes, age):
    """Return the alarm for a job whose only evidence is the age of its log."""
    if age is None or age > minutes:
        silence = "no log" if age is None else f"{age:.0f} min"
        return f"{name} silent {silence} (limit {minutes})"
    return None


def watchdog_signal(name, minutes, label, age, state):
    """Return the signal and the alarm for one watched job.

    The signal names the evidence used. The alarm is None when the job is
    healthy. A job that launchd holds and that ends clean is alive even when
    its log is quiet, because a job with nothing to write writes nothing. A
    job that launchd no longer holds, or that fails, or that runs past its
    limit, is not alive. When launchd cannot say how the job ended, the age
    of the log is the only evidence left, so the old silence rule applies and
    a real alarm is never silenced.

    A job that is running now is judged by the run in flight alone. A job
    that is idle now is judged by what its last run left behind.
    """
    if state is None:
        return "log-age", silence_alarm(name, minutes, age)
    if not state["loaded"]:
        return "launchd", f"{name} stopped (launchd job {label} is not loaded)"
    if state["running"]:
        # The run in flight decides. What an earlier run left behind, an
        # exit code or a signal, says nothing about the run that is going
        # on now, so a job that started a moment ago after a failure does
        # not raise an alarm. Only a run that overruns its limit is a
        # problem now.
        elapsed = process_seconds(state["pid"]) if state["pid"] else None
        if elapsed is None:
            # The job is running but nobody can say for how long, so the
            # log age is the only evidence left.
            return "log-age", silence_alarm(name, minutes, age)
        if elapsed > minutes * 60:
            return "launchd", f"{name} stuck (running {elapsed // 60} min, limit {minutes})"
        return "launchd", None
    # The job is idle now, so what its last run left behind is the evidence.
    if state["signal"]:
        return "launchd", f"{name} killed (last terminating signal {state['signal']})"
    if state["exit_code"]:
        return "launchd", f"{name} failing (last exit code {state['exit_code']})"
    if state["exit_code"] is None:
        # launchd does not say how the last run ended, so the log age is
        # the only evidence left.
        return "log-age", silence_alarm(name, minutes, age)
    return "launchd", None


def watchdog():
    import datetime as dt
    stale = []
    for name, (path, minutes, label) in WATCH.items():
        age = log_age(path)
        state = launchd_state(label)
        signal, alarm = watchdog_signal(name, minutes, label, age, state)
        detail = "log_age=missing" if age is None else f"log_age={age:.0f} min"
        if state is None:
            detail += " launchd=unavailable"
        elif not state["loaded"]:
            detail += " launchd=not-loaded runs=0 exit=0"
        else:
            detail += (f" launchd=loaded runs={state['runs']} exit={state['exit_code']}"
                       f" signal={state['signal']}"
                       f" running={'yes' if state['running'] else 'no'}")
        print(f"WATCH {name}: signal={signal} limit={minutes} min {detail}"
              + (f" alarm={alarm}" if alarm else ""))
        if alarm:
            stale.append(alarm)
    p = DECISIONS_PATH
    if stale:
        cause = "; ".join(stale)

        def publish(action):
            """Read the board, change it, and write it, under the board lock.

            The board lock is taken first; when it cannot be taken the
            write falls back to a compare-and-swap, so the alarm is still
            published and two publishers still cannot erase one another's
            alarm. A board that cannot be read or written returns
            "failed", so the tick says the alarm is nowhere."""
            item = None
            if action in ("raise", "unchecked"):
                item = {"id": "factory-watchdog", "group": "Coordinator", "kind": "action",
                        "title": "Factory job stopped or failing: " + cause,
                        "cause": alarms.cause_of(cause),
                        "why": "A coordinator job is stopped or failing. The coordinator is routing a fix; nothing for you unless this stays up."}
            if alarms.board_update(p, "factory-watchdog",
                                   "raise" if item else "remove", item) != "wrote":
                return "failed"
            if action == "quiet":
                # The alarm was acknowledged, so the same cause stays
                # quiet for four hours. The tick still says what it did
                # not raise, and the board holds no item for it.
                print("WATCHDOG quiet: " + cause)
            else:
                print("WATCHDOG " + cause)
                if action == "unchecked":
                    # The key could not be written, so the answer to this
                    # alarm cannot be recorded. The alarm is published
                    # anyway: a storage failure must not hide a real
                    # failure from Shyam.
                    print("WATCHDOG the alarm key could not be written; the answer to this alarm cannot be recorded")

        # The decision and the publication happen under the state lock, so
        # an answer that lands between them cannot be missed.
        action = alarms.decide_and_publish("factory-watchdog", cause, publish)
        if action == "failed":
            # The board could not be written, so the alarm is nowhere.
            print("WATCHDOG the alarm could not be published; the board file could not be written")
        return

    def publish_healthy():
        """Take the watchdog's item off the board.

        The board lock is taken first, and a lock that cannot be taken
        falls back to a compare-and-swap, so a stale alarm does not stay
        on the board because a lock file cannot be opened."""
        if alarms.board_update(p, "factory-watchdog", "remove") != "wrote":
            print("WATCHDOG could not take the alarm off the board; the board file could not be written")

    # The alarm is not true any more, so the same cause can alarm again
    # the next time it is true. An acknowledgement that is still running
    # keeps the key quiet. The board is cleaned under the board lock,
    # even when the mute state cannot be locked or read, so a broken
    # mute storage does not leave a stale alarm on the board.
    if not alarms.forget_and_save("factory-watchdog", publish_healthy):
        print("WATCHDOG could not write the mute state; the alarm is not muted")


def zero_merge(snapshot):
    import datetime as dt
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(minutes=60)
    recent = False
    open_prs = any(data["prs"] for data in snapshot["repos"].values())
    if open_prs:
        for repo in snapshot["repos"]:
            rows = read_json(["gh", "pr", "list", "-R", repo, "--state", "merged",
                              "--search", "merged:>=" + cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
                              "--limit", "1", "--json", "mergedAt"])
            if not isinstance(rows, list):
                raise ValueError("invalid merged PR response")
            for row in rows:
                stamp = dt.datetime.fromisoformat(row["mergedAt"].replace("Z", "+00:00"))
                if cutoff <= stamp <= now:
                    recent = True
    path = DECISIONS_PATH
    # The key names the repos that have open pull requests and no merge:
    # that is the cause. A stall on one repo and a stall on another are
    # different causes, so answering the first does not silence the
    # second. The title stays one title, for the board.
    waiting = sorted(repo for repo, data in snapshot["repos"].items() if data["prs"])
    title = "No merge in 60 minutes with open PRs"
    cause = title + ": " + (", ".join(waiting) if waiting else "none")
    item = None
    if open_prs and not recent:
        item = {"id": "factory-zero-merge", "group": "Coordinator",
                "kind": "action", "title": title,
                "cause": alarms.cause_of(cause),
                "why": "The coordinator must inspect blocked PRs and restore merge progress: "
                       + ", ".join(waiting)}
    # The alarm is muted for four hours once it is acknowledged, like the
    # watchdog's and the stall's (Refs #496): one place decides, and the
    # board is written under its lock.
    action = alarms.decide_and_publish(
        "factory-zero-merge", cause or "",
        lambda decided: None if alarms.route_update(
            path, "factory-zero-merge",
            "raise" if decided in ("raise", "unchecked") and item else "remove",
            item) == "wrote" else "failed")
    if action == "failed":
        # The board could not be written, so the alarm is nowhere. The
        # tick has to say so, or a real failure reaches nobody.
        raise RuntimeError("the merge alert could not be published: the board file could not be written")
    # A healthy tick has no alarm, so it says nothing about one: the log
    # names an alarm only when there is an alarm to name.
    if item is None:
        return
    if action == "quiet":
        print("ZERO-MERGE quiet: " + cause)
    elif action in ("raise", "unchecked"):
        print("ZERO-MERGE " + cause)


def item_failure_summary(ledger):
    failures = ledger.get("_item_failures", 0)
    print(f"ITEM SUMMARY failures={failures}")
    return failures


def dead_run_model(thread, limit_failure):
    """The build entry a dead run relaunches on, or None when every builder is blocked.

    The configured build order decides, whatever the thread ran on. A run
    that died on a usage limit names its own builder as out, so the
    relaunch skips it."""
    blocked = model_list.blocked_identities()
    if limit_failure:
        own = {"instanceId": thread.get("providerInstanceId"), "model": thread.get("model")}
        blocked = blocked | model_list.selection_identities(own)
    chosen = model_list.first_available("build", None, blocked)
    return chosen["selection"] if chosen else None


def dead_reference(repo, number):
    """Return the issue or pull request one number names, or none.

    A number that names nothing returns none, so a stale `#12` in a title
    does not stop the pass. A read that fails raises: a thread is never
    settled or flagged on a state the driver could not see."""
    require_api_budget()
    result = gh_gateway.run(["gh", "api", f"repos/{repo}/issues/{number}"],
                            timeout=120, caller_name=LANE_CALLER)
    if result.returncode:
        output = result.stdout + result.stderr
        if "HTTP 404" in output or "Not Found" in output:
            return None
        first = output.strip().splitlines()
        raise RuntimeError(
            f"{repo}#{number}: {first[0] if first else result.returncode}")
    data = json.loads(result.stdout)
    pull = data.get("pull_request") if isinstance(data, dict) else None
    return {"kind": "pr" if isinstance(pull, dict) else "issue",
            "state": str((data or {}).get("state") or "").lower(),
            "merged": bool(isinstance(pull, dict) and pull.get("merged_at"))}


DEAD_PR_PAGE = 50


def dead_ticket_prs(repo, number):
    """Return the pull requests whose body names one ticket, and whether that list was cut short.

    A ticket key names an issue, and the pull requests that name it say
    whether the work landed. A full page is not a complete list: a ticket
    with more than a page of pull requests has an open one the read did not
    return, so the caller cannot settle on it."""
    require_api_budget()
    result = gh_gateway.run(["gh", "pr", "list", "-R", repo, "--state", "all",
                             "--limit", str(DEAD_PR_PAGE), "--search", f"#{number} in:body",
                             "--json", "number,state,mergedAt,body"], timeout=120,
                            fresh=True, caller_name=LANE_CALLER)
    if result.returncode:
        first = (result.stdout + result.stderr).strip().splitlines()
        raise RuntimeError(
            f"{repo}#{number} pull requests: {first[0] if first else result.returncode}")
    rows = [row for row in json.loads(result.stdout or "[]") if isinstance(row, dict)]
    return ([row for row in rows if re.search(rf"#{number}\b", row.get("body") or "")],
            len(rows) >= DEAD_PR_PAGE)


def dead_ticket_numbers(repo, token):
    """Return the issues whose title names one ticket key.

    A ticket key (`MO-1058`) is the ticket tool's name for an issue, not the
    issue number, so the issue is found by its key in the title. Closed
    issues count: finished work is what settles a thread."""
    require_api_budget()
    result = gh_gateway.run(["gh", "issue", "list", "-R", repo, "--state", "all",
                             "--limit", "10", "--search", f"{token} in:title",
                             "--json", "number,title"], timeout=120,
                            fresh=True, caller_name=LANE_CALLER)
    if result.returncode:
        first = (result.stdout + result.stderr).strip().splitlines()
        raise RuntimeError(f"{repo} {token}: {first[0] if first else result.returncode}")
    rows = json.loads(result.stdout or "[]")
    return [int(row["number"]) for row in rows if isinstance(row, dict)
            and re.search(rf"\b{re.escape(token)}\b", row.get("title") or "", re.I)]


def dead_reference_outcome(repo, number):
    """Return (settle, note) for one number a dead thread names.

    A pull request that is merged or closed settles the thread, and an open
    pull request is unfinished work that keeps it. An issue is settled only
    after the pull requests that name it are read: an issue can close before
    its pull request lands, and an open pull request is unfinished work even
    then. A list that was cut short settles nothing: the unseen pull request
    could be the open one."""
    found = dead_reference(repo, number)
    if not found:
        return False, ""
    if found["kind"] == "pr":
        if found["state"] == "closed":
            return True, f"PR {repo}#{number} {'merged' if found['merged'] else 'closed'}"
        return False, f"PR {repo}#{number} is open"
    linked, truncated = dead_ticket_prs(repo, number)
    open_note, landed_note = "", ""
    for pr in linked:
        state = str(pr.get("state") or "").upper()
        if state == "OPEN":
            open_note = open_note or f"PR {repo}#{pr.get('number')} is open"
        elif state in {"MERGED", "CLOSED"}:
            landed_note = landed_note or (
                f"PR {repo}#{pr.get('number')} {'merged' if state == 'MERGED' or pr.get('mergedAt') else 'closed'}")
    if open_note:
        return False, open_note
    if truncated:
        return False, (f"issue {repo}#{number} names more pull requests than one read returns, "
                       "so an unseen open one cannot be ruled out")
    if found["state"] == "closed":
        return True, f"issue {repo}#{number} closed"
    if landed_note:
        return True, landed_note
    return False, f"issue {repo}#{number} is open"


def dead_run_outcome(repo, title, thread):
    """Return (settle, note) for a dead thread that has no ticket receipt.

    The thread's work is named by its linked pull requests and its title: a
    pull request number (`#12`) or a ticket key (`MO-1058`, which maps to a
    repository through the ticket config). The thread settles only when all
    of that work has finished."""
    references = [(repo, pr.get("number")) for pr in thread.get("pullRequests") or []
                  if pr.get("repository") == repo and pr.get("number")]
    references += [(repo, int(number)) for number in re.findall(r"#(\d+)\b", title)]
    keys = {str(cfg.get("key") or "").lower(): name for name, cfg in CFG.items()
            if isinstance(cfg, dict) and cfg.get("key")}
    for key, number in re.findall(r"\b([A-Za-z][A-Za-z0-9]{1,7})-(\d+)\b", title):
        if key.lower() in keys:
            references += [(keys[key.lower()], found)
                           for found in dead_ticket_numbers(keys[key.lower()], f"{key.upper()}-{number}")]
    settled_note, open_note = "", ""
    for ref_repo, number in dict.fromkeys(references):
        settle, note = dead_reference_outcome(ref_repo, number)
        if settle:
            settled_note = settled_note or note
        else:
            open_note = open_note or note
    if open_note:
        return False, open_note
    if settled_note:
        return True, settled_note
    return False, "no pull request or ticket in the title"


def recover_dead_runs(ledger):
    receipts = stall_receipts()
    for repo in LANE_REPOS:
        project_id = CFG[repo]["projectId"]
        threads = []
        cursor = None
        while True:
            args = {"projectId": project_id, "statuses": ["failed", "interrupted"], "settled": False, "limit": 100}
            if cursor is not None:
                args["cursor"] = cursor
            page = t3("t3_thread_list", args)
            if not isinstance(page, dict) or not isinstance(page.get("threads"), list):
                print(f"DEAD {repo}: refused, invalid thread list")
                threads = None
                break
            threads.extend(page["threads"])
            cursor = page.get("nextCursor")
            if cursor is None:
                break
        if threads is None:
            continue
        for thread in threads:
            if not isinstance(thread, dict):
                print(f"DEAD {repo}: refused, invalid thread record")
                continue
            thread_id = thread.get("threadId")
            if not thread_id or thread.get("settled"):
                continue
            title = thread.get("title") or ""
            if "ascend" in title.lower():
                print(f"DEAD {thread_id}: coordinator needed, Ascend excluded")
                continue
            receipt_key = next((key for key, value in receipts.items() if value == thread_id and key.startswith(f"ticket:{repo}#")), "")
            if not receipt_key:
                # A thread with no receipt is settled once its work has
                # finished, and otherwise flagged for the coordinator once.
                # The ledger note is the driver's record of that one report.
                if ledger.get(f"dead-run:{thread_id}"):
                    continue
                try:
                    settle, note = dead_run_outcome(repo, title, thread)
                except ApiBudgetExhausted:
                    raise
                except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                    print(f"DEAD {thread_id}: coordinator needed, state unread ({exc}); left for the next pass")
                    continue
                day = time.strftime("%Y-%m-%d")
                if not settle:
                    print(f"DEAD {thread_id}: coordinator needed, {note}; flagged once (model {thread.get('model')})")
                    ledger[f"dead-run:{thread_id}"] = f"flagged {day}: {note}"
                    continue
                print(f"DEAD {thread_id}: settle, {note} (model {thread.get('model')})")
                if DRY or settle_dead_run(thread_id):
                    ledger[f"dead-run:{thread_id}"] = f"settled {day}: {note}"
                continue
            work_match = re.match(rf"ticket:{re.escape(repo)}#(\d+)(?::a\d+)?$", receipt_key)
            if not work_match:
                print(f"DEAD {thread_id}: coordinator needed, invalid ticket receipt")
                continue
            ticket = int(work_match.group(1))
            work_key = receipt_key.rsplit(":a", 1)[0]
            full_thread = t3("t3_thread_read", {"threadId": thread_id, "limit": 1}).get("thread") or thread
            reply = last_reply(thread_id)
            moved = False
            if ticket:
                issue = read_json(["gh", "issue", "view", str(ticket), "-R", repo, "--json", "state"])
                moved = issue.get("state") == "CLOSED"
            unknown_open_pr = False
            protected_pr = False
            for pr in thread.get("pullRequests") or []:
                if pr.get("repository") != repo or not pr.get("number"):
                    continue
                current_pr = read_json(["gh", "pr", "view", str(pr["number"]), "-R", repo, "--json", "state,headRefOid,headRefName,baseRefName"])
                _, skip = pr_action_skip(repo, pr["number"])
                if skip:
                    print(skip)
                    protected_pr = True
                if current_pr.get("state") in {"CLOSED", "MERGED"}:
                    moved = True
                recorded_head = pr.get("headRefOid") or pr.get("headSha")
                if not recorded_head:
                    heads = re.findall(r"\b(?:head|commit)(?:\s+sha)?\s*[:= ]\s*([0-9a-f]{7,40})\b", reply, re.I)
                    recorded_head = heads[-1] if heads else None
                current_head = current_pr.get("headRefOid")
                if recorded_head and current_head and not current_head.startswith(recorded_head):
                    moved = True
                if current_pr.get("state") == "OPEN" and not recorded_head:
                    unknown_open_pr = True
            if protected_pr:
                continue
            attempt = re.search(r":a(\d+)$", receipt_key)
            live = []
            cursor = None
            while True:
                args = {"projectId": project_id, "statuses": ["preparing", "queued", "starting", "running", "waiting"], "limit": 100}
                if cursor is not None:
                    args["cursor"] = cursor
                page = t3("t3_thread_list", args)
                if not isinstance(page, dict) or not isinstance(page.get("threads"), list):
                    live = None
                    break
                live.extend(page["threads"])
                cursor = page.get("nextCursor")
                if cursor is None:
                    break
            if live is None:
                print(f"DEAD {thread_id}: coordinator needed, invalid live-thread list")
                continue
            newer_threads = {value for key, value in receipts.items() if attempt and key.startswith(receipt_key.rsplit(":a", 1)[0] + ":a") and re.search(r":a(\d+)$", key) and int(re.search(r":a(\d+)$", key).group(1)) > int(attempt.group(1))}
            if any(t.get("threadId") in newer_threads for t in live if isinstance(t, dict)):
                moved = True
            if moved:
                print(f"DEAD {thread_id}: settle, work moved on")
                if not DRY:
                    settle_dead_run(thread_id)
                continue
            failure = reply.lower()
            limit_failure = any(term in failure for term in ("rate limit", "spend limit", "quota", "individual spend"))
            day = time.strftime("%Y-%m-%d")
            count_key = f"dead-relaunch:{day}:{work_key}"
            count = int(ledger.get(count_key, 0))
            if ledger.get(f"dead-relaunch-thread:{thread_id}"):
                print(f"DEAD {thread_id}: settle, relaunch already queued")
                if not DRY:
                    settle_dead_run(thread_id)
                continue
            model = dead_run_model(full_thread, limit_failure)
            if model is None:
                print(f"DEAD {thread_id}: coordinator needed, every builder is blocked")
                continue
            if count >= 2:
                print(f"DEAD {thread_id}: coordinator needed, daily relaunch limit reached")
                continue
            path = full_thread.get("worktreePath")
            if not path:
                print(f"DEAD {thread_id}: coordinator needed, no worktree")
                continue
            if unknown_open_pr:
                print(f"DEAD {thread_id}: coordinator needed, open PR head cannot be compared")
                continue
            worktrees = run(["git", "-C", "/Users/shyamsivakumar/Code/" + PATHS[repo],
                             "worktree", "list", "--porcelain"])
            if not any(line == f"worktree {path}" for line in worktrees.splitlines()):
                print(f"DEAD {thread_id}: coordinator needed, worktree is unavailable")
                continue
            ticket_url = f"https://github.com/{repo}/issues/{ticket}"
            message = (f"Continue {repo}#{ticket} ({ticket_url}) in this existing worktree. The prior thread {thread_id} stopped. "
                       "Read the ticket and current diff, preserve completed work, finish the acceptance checks, and report the exact remaining blocker. "
                       "Do not create a new ticket or move the work to another checkout.")
            next_attempt = max((int(match.group(1)) for key in receipts
                                if key.startswith(work_key + ":a")
                                and (match := re.search(r":a(\d+)$", key))), default=0) + 1
            args = {"projectId": project_id, "clientRequestId": f"{work_key}:a{next_attempt}",
                    "title": f"Continue {repo}#{ticket}: {title}", "taskType": "worker", "modelSelection": model,
                    "runtimeMode": "full-access", "workspaceStrategy": {"type": "existing_worktree", "worktreePath": path}, "message": message}
            print(f"DEAD {thread_id}: relaunch {model['model']}")
            if not DRY:
                result = run([COORDQ, "start", json.dumps(args), "--priority", "800"]).strip()
                if not result:
                    raise RuntimeError(f"Empty dead-run dispatch receipt for {thread_id}")
                ledger[count_key] = count + 1
                ledger[f"dead-relaunch-thread:{thread_id}"] = result.splitlines()[-1]
                settle_dead_run(thread_id)


def run_pass(ledger):
    global SNAPSHOT, STALL_STATE
    ledger.pop("_item_failures", None)
    watchdog()
    drift_ff(ledger)
    SNAPSHOT = board_snapshot(ledger)
    if not isinstance(STALL_STATE, dict):
        STALL_STATE = {}
    state = STALL_STATE
    receipts = stall_receipts()
    markers = stall_markers(SNAPSHOT, receipts)
    swept = False
    if stall.board_pending(state) or any(
        stall.pending(state, key, item["marker"]) for key, item in markers.items()
    ):
        # The board the shift holds is cached for several passes, and a
        # stale head is not evidence that an item stopped moving. A tick
        # that could report a stall or stall the board reads the board
        # again first.
        SNAPSHOT = board_snapshot(ledger, force=True)
        receipts = stall_receipts()
        markers = stall_markers(SNAPSHOT, receipts)
        swept = True
    busy_by_repo = {}
    for repo in LANE_REPOS:
        with item_boundary(repo, "busy", ledger):
            busy_by_repo[repo] = busy(repo)
    fresh = stall.arrived(state, board_keys(SNAPSHOT))
    progressed = any(
        stall.moved(state, key, item["marker"]) for key, item in markers.items()
    ) or bool(fresh)
    board_event = stall.board(
        state, progressed or any(busy_by_repo.values()), board_items(SNAPSHOT)
    )
    for key, item in sorted(markers.items()):
        event = stall.observe(state, key, item["marker"])
        if not event:
            continue
        event.update(item)
        print(
            f"STALL {key}: no new commit or receipt for {event['idle']} ticks; "
            "reported, the shift keeps working it"
        )
        STALL_EVENTS.append(event)
    stall.prune(state, set(markers))
    if board_event:
        print(
            f"STALL board: no board progress for {board_event['idle']} ticks; "
            "the board is swept again"
        )
        STALL_EVENTS.append(board_event)
        if not swept:
            SNAPSHOT = board_snapshot(ledger, force=True)
    tickets = SNAPSHOT["tickets"]
    recover_dead_runs(ledger)
    for repo in LANE_REPOS:
        if repo not in busy_by_repo:
            continue
        with item_boundary(repo, "lane", ledger):
            prs = list(ORDER.get(repo, []))
            others = SNAPSHOT["repos"][repo]["prs"]
            prs += sorted(p["number"] for p in others if p["number"] not in prs and not p["isDraft"])
            with item_boundary(repo, "after-merge", ledger):
                settle_merged_prs(repo, ledger)
            b = busy_by_repo[repo]
            if b:
                print(f"{CFG[repo]['key']:5} busy ({b}); PR actions still run")
            done = False
            for number in prs:
                with item_boundary(repo, number, ledger):
                    result = act_on_pr(repo, number, ledger)
                    if result is None:
                        continue
                    print(f"{CFG[repo]['key']:5} {result}")
                    if result.startswith("skip "):
                        continue
                    done = True
            if repo != "shyamsivakumar/strategy-replay-workbench" and done and not DRY and not b:
                u = unstick(repo, ledger)
                if not u.startswith("nothing ready"):
                    print(f"{CFG[repo]['key']:5} {u}")
            if repo == "shyamsivakumar/strategy-replay-workbench":
                response = t3("t3_thread_list", {"projectId": CFG[repo]["projectId"],
                              "statuses": ["preparing", "queued", "starting", "running", "waiting"], "limit": 20})
                live = response.get("threads") if isinstance(response, dict) else None
                if not isinstance(live, list) or any(not isinstance(t, dict) or not isinstance(t.get("title"), str) for t in live):
                    print(f"{CFG[repo]['key']:5} refused: invalid thread-list response")
                    continue
                excluded = {group_of(t.get("title") or "") for t in live}
                if len(live) < 3:
                    if done:
                        if not DRY:
                            print(f"{CFG[repo]['key']:5} " + unstick(repo, ledger, excluded))
                    else:
                        print(f"{CFG[repo]['key']:5} " + start_next(repo, tickets, ledger, excluded))
            elif not done and not b:
                print(f"{CFG[repo]['key']:5} " + start_next(repo, tickets, ledger))

    merge_passes(ledger)

    if item_failure_summary(ledger):
        raise RuntimeError(f"lane pass completed with {ledger['_item_failures']} item failures")


def load_ledger():
    try:
        with open(LEDGER) as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        sys.exit(f"lane: REFUSED: the ledger {LEDGER} is unreadable ({exc}); it was left as is")


def save_ledger(ledger):
    temporary = f"{LEDGER}.{os.getpid()}.tmp"
    try:
        with open(temporary, "w") as handle:
            json.dump(ledger, handle, indent=1)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, LEDGER)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def main():
    global CFG
    STALL_EVENTS.clear()
    ledger = load_ledger()
    with open("/Users/shyamsivakumar/.coordinator/tickets.json") as handle:
        CFG = json.load(handle)["repos"]
    before = None
    try:
        before = api_remaining()
        run_pass(ledger)
        if not DRY:
            zero_merge(SNAPSHOT)
            stale = reconcile_prompt_items(SNAPSHOT)
            if stale:
                print(f"BOARD removed {stale} settled merge ask(s)")
    except ApiBudgetExhausted as exc:
        print(f"API BUDGET {exc}")
        if ledger.get("_item_failures", 0):
            item_failure_summary(ledger)
            raise RuntimeError(f"lane pass completed with {ledger['_item_failures']} item failures") from exc
    finally:
        try:
            after = api_remaining()
            used = {name: max(0, before[name] - after[name]) for name in after} if before else None
            print(f"API USAGE used={used} remaining={after} floor={API_FLOOR}")
        except ApiBudgetExhausted as exc:
            print(f"API USAGE unavailable: {exc}")
        if not DRY:
            save_ledger(ledger)
