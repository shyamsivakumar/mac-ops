import json
import re
import subprocess
import time

COORDQ = "/Users/shyamsivakumar/.local/bin/coordq"
LEDGER = "/Users/shyamsivakumar/Code/coordinator/loop/lanes-ledger.json"
ASTRA = {"instanceId": "codex", "model": "gpt-6-astra"}
CFG = {}
RECEIPTS = "/Users/shyamsivakumar/Code/coordinator/queue/dispatch-receipts.json"
DRY = False
SNAPSHOT = {}
API_FLOOR = 500
REFRESH_SECONDS = 900


class ApiBudgetExhausted(RuntimeError):
    pass


def api_remaining():
    result = subprocess.run(["gh", "api", "rate_limit"], capture_output=True,
                            text=True, timeout=60)
    if result.returncode:
        raise ApiBudgetExhausted("quota could not be read")
    try:
        resources = json.loads(result.stdout)["resources"]
        return {name: int(resources[name]["remaining"]) for name in ("core", "graphql")}
    except (ValueError, KeyError, TypeError) as exc:
        raise ApiBudgetExhausted("quota response is invalid") from exc


def require_api_budget():
    remaining = api_remaining()
    if min(remaining.values()) < API_FLOOR:
        raise ApiBudgetExhausted(f"optional reads stopped: remaining={remaining}, floor={API_FLOOR}")


def read_json(cmd):
    require_api_budget()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise RuntimeError(f"snapshot read failed: {cmd[:3]} (exit {result.returncode})")
    return json.loads(result.stdout)


def board_snapshot(ledger):
    cached = ledger.get("_board_snapshot")
    now = time.time()
    if isinstance(cached, dict) and 0 <= now - cached.get("refreshed_at", 0) < REFRESH_SECONDS:
        return cached
    snapshot = {"tickets": read_json(["ticket", "list", "--json", "--fresh"]).get("issues", []), "repos": {}}
    fields = "number,state,headRefOid,body,mergeable,isDraft,statusCheckRollup"
    for repo in LANE_REPOS:
        snapshot["repos"][repo] = {
            "prs": read_json(["gh", "pr", "list", "-R", repo, "--state", "open", "--limit", "200", "--json", fields]),
            "issues": read_json(["gh", "issue", "list", "-R", repo, "--state", "open", "--limit", "200", "--json", "number,labels,state"]),
        }
    snapshot["refreshed_at"] = time.time()
    ledger["_board_snapshot"] = snapshot
    return snapshot

ORDER = {
    "shyamsivakumar/mac-ops": [],
    "shyamsivakumar/strategy-replay-workbench": [1082, 1089, 1090, 1071, 1072],
    "shyamsivakumar/fantasy-football-toolkit": [423, 444],
    "shyamsivakumar/catalouge": [117, 121],
    "digitized/Concerning": [59, 57, 76],
}


def run(cmd, timeout=150):
    if cmd[0] == "gh" or (cmd[0] == "ticket" and cmd[1] in ("start", "gate", "list")):
        require_api_budget()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return (p.stdout + p.stderr).strip()


def t3(tool, args):
    try:
        return json.loads(run(["t3mcp", "call", tool, json.dumps(args)]) or "{}")
    except ValueError:
        return {}


def last_reply(thread_id):
    items = t3("t3_thread_read", {"threadId": thread_id, "view": "messages", "limit": 80, "maxCharsPerItem": 12000}).get("items") or []
    msgs = [i.get("text") or "" for i in items if i.get("type") == "assistant_message"]
    return (msgs[-1] if msgs else "").rstrip()


def busy(repo):
    pid = CFG[repo]["projectId"]
    live = t3("t3_thread_list", {"projectId": pid, "statuses": ["preparing", "queued", "starting", "running", "waiting"], "limit": 20}).get("threads") or []
    if live:
        return f"live: {live[0].get('title', '')[:60]}"
    queue = json.loads(run([COORDQ, "list", "--json"]) or "[]") if False else []
    return ""


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


def gate_verdict(repo, number, head):
    key = CFG[repo]["key"]
    threads = t3("t3_thread_list", {"projectId": CFG[repo]["projectId"], "titleContains": f"review #{number} {head[:8]}", "limit": 10}).get("threads") or []
    for t in sorted(threads, key=lambda t: t.get("updatedAt") or "", reverse=True):
        if t.get("status") in ("running", "queued", "starting", "preparing"):
            return "running", t, ""
        reply = last_reply(t["threadId"])
        if reply.endswith("VERDICT: PASS"):
            return "PASS", t, reply
        if reply.endswith("VERDICT: FAIL"):
            return "FAIL", t, reply
        return "none", t, reply
    return "absent", None, ""


def start(args, prio, ledger, lkey):
    if lkey in ledger:
        return f"already done {lkey}"
    if DRY:
        return f"DRY {lkey}"
    out = run([COORDQ, "start", json.dumps(args), "--priority", str(prio)]).splitlines()[-1]
    ledger[lkey] = out
    return out


def send(thread_id, message, title, ledger, lkey):
    if lkey in ledger:
        return f"already done {lkey}"
    if DRY:
        return f"DRY {lkey}"
    out = run([COORDQ, "start", json.dumps({"threadId": thread_id, "message": message}),
               "--tool", "t3_thread_send", "--priority", "800", "--title", title]).splitlines()[-1]
    ledger[lkey] = out
    return out


SOL = {"instanceId": "codex", "model": "gpt-6.1-sol"}
LANE_REPOS = ["shyamsivakumar/mac-ops", "shyamsivakumar/strategy-replay-workbench", "shyamsivakumar/fantasy-football-toolkit",
              "shyamsivakumar/catalouge", "digitized/Concerning"]
NEVER_START = {("shyamsivakumar/strategy-replay-workbench", 468)}


def park(repo, number, issue, head, reply, ledger):
    lkey = f"park:{repo}#{number}"
    if lkey in ledger:
        return f"#{number}: parked, re-cut on the way"
    if DRY:
        return f"DRY park #{number}"
    if issue:
        run(["gh", "issue", "edit", str(issue), "-R", repo, "--remove-label", "stage:todo", "--add-label", "stage:backlog"])
        run(["gh", "issue", "comment", str(issue), "-R", repo, "--body",
             f"Parked by the lane (specs/lane.md section 6): PR #{number} failed its gate after two fix rounds (head {head[:8]}). Sol re-cuts it into smaller tickets."])
    msg = (f"Type: design · gpt-6.1-sol (re-cut a parked ticket; coordinator specs/lane.md is at /Users/shyamsivakumar/Code/coordinator/specs/lane.md)\n\n"
           f"Ticket {repo}#{issue} with PR #{number} failed its gate after two fix rounds. Read the issue, the PR diff (`gh pr diff {number} -R {repo}`) and the last gate report below. "
           "Re-cut the remaining work into the smallest ordered tickets that each fit a 5-minute builder turn, using the 12-section template in ~/.coordinator/tickets.json, "
           "with Requires/Provides lines, chained with --add-blocked-by, labels stage:todo,type:<type>,priority:<same>; reuse the PR branch as the base if most of it is right and say so in the first ticket. "
           f"Then comment on #{issue} with the new tickets and close it as not planned. Device and live testing are waived. Start nothing, change no code, 10 minutes.\n\nLast gate report:\n" + reply[-5000:])
    args = {"projectId": CFG[repo]["projectId"], "title": f"{CFG[repo]['key']} re-cut #{issue} (PR #{number})", "modelSelection": SOL,
            "runtimeMode": "full-access", "workspaceStrategy": {"type": "root"}, "message": msg}
    out = run([COORDQ, "start", json.dumps(args), "--priority", "900"]).splitlines()[-1]
    ledger[lkey] = out
    return f"#{number}: parked, re-cut {out}"


def act_on_pr(repo, number, ledger):
    pr = next((p for p in SNAPSHOT["repos"][repo]["prs"] if p["number"] == number), {})
    if pr.get("state") != "OPEN":
        return None
    head, body = pr["headRefOid"], pr.get("body") or ""
    issue, builder = builder_thread(repo, body)
    if issue:
        issue_record = next((i for i in SNAPSHOT["repos"][repo]["issues"] if i["number"] == int(issue)), None)
        if issue_record is None:
            return None
        if any(label["name"] in ("stage:backlog", "stage:hold") for label in issue_record["labels"]):
            return None
    agent_ok = any("agent-check" in (c.get("context") or c.get("name") or "") and (c.get("state") or c.get("conclusion")) == "SUCCESS"
                   for c in pr.get("statusCheckRollup") or [])
    check_ok = f"Builder check: PASS {head}" in body or agent_ok
    if pr.get("mergeable") == "CONFLICTING" or not check_ok:
        why = "it conflicts with main" if pr.get("mergeable") == "CONFLICTING" else f"it has no passing check on head {head}"
        if not builder:
            return f"skip #{number}: {why}, no builder thread"
        msg = (f"Coordinator: PR #{number} cannot be gated because {why}. Update the branch from origin/main if needed, run the repo check "
               "(mac-ops: `python3 scripts/mac_ops_fast_check.py`; SRW: rely on srw/agent-check, do not run scripts/check.sh), push, set "
               "`Builder check: PASS <full new head sha>` on its own line in the PR body, and report the head. 20 minutes at most; every command under `timeout 300`.")
        return f"#{number} fix-check: " + send(builder, msg, f"{CFG[repo]['key']}#{number} check", ledger, f"check:{repo}#{number}:{head}")
    verdict, gate, reply = gate_verdict(repo, number, head)
    if verdict == "running":
        return f"#{number}: gate running"
    if verdict == "PASS":
        return f"skip #{number}: gate PASS but still open (merge refused or digitized); for Shyam"
    if verdict == "FAIL" and sum(1 for k in ledger if k.startswith(f"fix:{repo}#{number}:")) >= 2:
        return "skip " + park(repo, number, issue, head, reply, ledger)
    if verdict == "FAIL" and f"fix:{repo}#{number}:{head}" in ledger and builder:
        status = (t3("t3_thread_read", {"threadId": builder, "limit": 1}).get("thread") or {}).get("status")
        if status in ("completed", "interrupted", "failed"):
            return "skip " + park(repo, number, issue, head, reply, ledger)
    if verdict == "FAIL":
        if not builder:
            return f"skip #{number}: FAIL, no builder thread"
        msg = (f"The gate on PR #{number} at {head} returned VERDICT: FAIL. Fix every critical and major finding below, push, set "
               "`Builder check: PASS <full new head sha>` on its own line in the PR body, and report the new head. 20 minutes at most.\n\n"
               + ("Device, handset and live-service testing is waived (Shyam 2026-11-14: \"no testing is needed lets just finish backlog building everything\"). Do not run device or live cases; state in the receipt that they were waived, not failed. Findings that only ask for device or live results are resolved by that statement.\n\n") + reply[-6000:])
        return f"#{number} fix: " + send(builder, msg, f"{CFG[repo]['key']}#{number} gate findings", ledger, f"fix:{repo}#{number}:{head}")
    if True:
        return None
    brief = run(["ticket", "gate", f"{repo}#{number}", "--print-brief"])
    if head not in brief:
        return f"#{number}: no gate brief ({brief[-120:]})"
    key = CFG[repo]["key"]
    args = {"projectId": CFG[repo]["projectId"], "title": f"{key}-{issue} review #{number} {head[:8]} (Astra)", "modelSelection": ASTRA,
            "runtimeMode": "full-access", "workspaceStrategy": {"type": "root"}, "clientRequestId": f"gate:{repo}#{number}:{head}:lane",
            "message": brief}
    tag = "regate" if verdict == "none" else "gate"
    if verdict == "none" and sum(1 for k in ledger if (k.startswith(f"gate:{repo}#{number}:") or k.startswith(f"regate:{repo}#{number}:"))) >= 3:
        return "skip " + park(repo, number, issue, head, reply, ledger)
    return f"#{number} {tag}: " + start(args, 5000, ledger, f"{tag}:{repo}#{number}:{head}")


PATHS = {"shyamsivakumar/mac-ops": "mac-ops", "shyamsivakumar/strategy-replay-workbench": "strategy-replay-workbench",
         "shyamsivakumar/fantasy-football-toolkit": "fantasy-football-toolkit", "shyamsivakumar/catalouge": "catalouge",
         "digitized/Concerning": "concerning"}


def drift_ff(ledger):
    for repo, name in PATHS.items():
        if repo not in LANE_REPOS:
            continue
        d = "/Users/shyamsivakumar/Code/" + name
        out = run(["git", "-C", d, "rev-parse", "main", "origin/main"], timeout=60)
        ids = out.split()
        if len(ids) != 2 or ids[0] == ids[1]:
            continue
        lkey = f"ff:{repo}:{ids[1]}"
        if lkey in ledger or DRY:
            print(f"{CFG[repo]['key']:5} main behind ({ids[0][:8]} vs {ids[1][:8]})" + (" DRY" if DRY else " queued"))
            if lkey in ledger:
                continue
            ledger[lkey] = "pending"
            continue
        msg = open("/Users/shyamsivakumar/Code/coordinator/loop/ff-chore.md").read().replace(
            "Three repositories have a local main that trails their origin/main, so new tickets can branch from stale code:",
            "This repository's local main trails origin/main, so tools read stale code:").replace(
            "- /Users/shyamsivakumar/Code/strategy-replay-workbench: local ceb1c509, origin c9daf467\n- /Users/shyamsivakumar/Code/fantasy-football-toolkit: local 6d4611d5, origin 764832d1\n- /Users/shyamsivakumar/Code/concerning: local 30b1c55, origin b6206ab\n",
            f"- {d}: local {ids[0][:9]}, origin {ids[1][:9]}\n").replace(
            "For each checkout in order:", "For this checkout:").replace(
            "Report one line per repo: the two commit ids before, the single commit id after (or \"left alone, not fast-forwardable\").",
            "Report the two commit ids before and the single commit id after (or \"left alone, not fast-forwardable\").")
        args = {"projectId": "f093cc9b-5332-48eb-a719-2187eb8cbabc", "title": f"Chore · level local main ({CFG[repo]['key']})",
                "modelSelection": {"instanceId": "router", "model": "task/chore"}, "runtimeMode": "full-access",
                "workspaceStrategy": {"type": "root"}, "message": msg}
        out2 = run([COORDQ, "start", json.dumps(args), "--priority", "700"]).splitlines()[-1]
        ledger[lkey] = out2
        print(f"{CFG[repo]['key']:5} ff chore: {out2}")


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
        if "refused" in dry.splitlines()[-1] if dry else True:
            ledger[f"refused:{ref}"] = now.isoformat()
            continue
        if DRY:
            return f"DRY start {t['key']} #{t['number']}"
        out = run(["ticket", "start", ref], timeout=200).splitlines()[-1]
        ledger[f"start:{ref}:{len(ledger)}"] = out
        return f"start {t['key']} #{t['number']}: {out[:60]}"
    return unstick(repo, ledger)


def unstick(repo, ledger):
    issues = SNAPSHOT["repos"][repo]["issues"]
    referenced = {int(x) for pr in SNAPSHOT["repos"][repo]["prs"]
                  for x in re.findall(r"\bRefs #(\d+)", pr.get("body") or "")}
    orphans = [i["number"] for i in issues if not any(l["name"].startswith("stage:") for l in i["labels"])
               and i["number"] not in referenced]
    if not orphans:
        return "nothing ready"
    receipts = json.load(open(RECEIPTS))
    for n in orphans:
        prefix = f"ticket:{repo}#{n}:a"
        best = max(((int(k[len(prefix):]), v) for k, v in receipts.items()
                    if k.startswith(prefix) and k[len(prefix):].isdigit()), default=None)
        if not best:
            continue
        v = ledger.get(f"cont:{best[1]}")
        if isinstance(v, list) and (__import__("datetime").datetime.now(__import__("datetime").timezone.utc) - __import__("datetime").datetime.fromisoformat(v[0])).total_seconds() < 1800:
            continue
        if not t3("t3_thread_read", {"threadId": best[1], "limit": 1}).get("thread"):
            if DRY:
                return f"DRY start #{n}"
            out = run(["ticket", "start", f"{repo}#{n}"], timeout=200)
            ledger[f"relaunch:{repo}#{n}"] = out
            return f"start #{n}: {out}"
        if DRY:
            return f"DRY continue #{n}"
        msg = open("/Users/shyamsivakumar/Code/coordinator/loop/continue-brief.md").read().replace("{issue}", str(n))
        out = run([COORDQ, "start", json.dumps({"threadId": best[1], "message": msg}), "--tool", "t3_thread_send",
                   "--priority", "900", "--title", f"{CFG[repo]['key']}#{n} continue"]).splitlines()[-1]
        ledger[f"cont:{best[1]}"] = [__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), out]
        return f"continue #{n}: {out}"
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    def marked(k):
        v = ledger.get(k)
        if isinstance(v, list) and (now - __import__("datetime").datetime.fromisoformat(v[0])).total_seconds() < 1800:
            return True
        return False
    orphans = [n for n in orphans if not marked(f"unstick:{repo}#{n}")]
    if not orphans:
        return "nothing ready"
    batch = orphans[:7]
    if DRY:
        return f"DRY unstick {batch}"
    lst = ", ".join(f"#{n}" for n in batch)
    msg = open("/Users/shyamsivakumar/Code/coordinator/loop/unstick-brief.md").read().replace("{repo}", repo).replace("{list}", lst)
    args = {"projectId": CFG[repo]["projectId"], "title": f"{CFG[repo]['key']} unstick {lst}"[:80], "modelSelection": SOL,
            "runtimeMode": "full-access", "workspaceStrategy": {"type": "root"}, "message": msg}
    out = run([COORDQ, "start", json.dumps(args), "--priority", "950"]).splitlines()[-1]
    stamp = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    for n in batch:
        ledger[f"unstick:{repo}#{n}"] = [stamp, out]
    return f"unstick {lst}: {out}"


WATCH = {"tick": ("/Users/shyamsivakumar/Library/Logs/coordinator/tick.log", 65),
         "gatekeep": ("/Users/shyamsivakumar/Code/coordinator/queue/gatekeep.log", 120),
         "dispatch": ("/Users/shyamsivakumar/Code/coordinator/queue/dispatch.log", 10)}


def watchdog():
    import os, time, datetime as dt
    stale = []
    for name, (path, minutes) in WATCH.items():
        try:
            age = (time.time() - os.path.getmtime(path)) / 60
        except OSError:
            age = 9999
        if age > minutes:
            stale.append(f"{name} silent {age:.0f} min (limit {minutes})")
    p = "/Users/shyamsivakumar/Code/coordinator/decisions.json"
    d = json.load(open(p))
    d["items"] = [i for i in d["items"] if i.get("id") != "factory-watchdog"]
    if stale:
        print("WATCHDOG " + "; ".join(stale))
        d["items"].append({"id": "factory-watchdog", "group": "Coordinator", "kind": "action",
                           "title": "Factory job silent: " + "; ".join(stale),
                           "why": "A coordinator job stopped writing its log. The coordinator is routing a fix; nothing for you unless this stays up."})
    d["updated"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump(d, open(p + ".tmp", "w"), indent=1)
    os.replace(p + ".tmp", p)


def run_pass(ledger):
    global SNAPSHOT
    watchdog()
    drift_ff(ledger)
    SNAPSHOT = board_snapshot(ledger)
    tickets = SNAPSHOT["tickets"]
    for repo in LANE_REPOS:
        prs = list(ORDER.get(repo, []))
        others = SNAPSHOT["repos"][repo]["prs"]
        prs += sorted(p["number"] for p in others if p["number"] not in prs and not p["isDraft"])
        b = busy(repo)
        if b:
            print(f"{CFG[repo]['key']:5} busy ({b}); PR actions still run")
        done = False
        for number in prs:
            result = act_on_pr(repo, number, ledger)
            if result is None:
                continue
            print(f"{CFG[repo]['key']:5} {result}")
            if result.startswith("skip "):
                continue
            done = True
        if done and not DRY and not b:
            u = unstick(repo, ledger)
            if not u.startswith("nothing ready"):
                print(f"{CFG[repo]['key']:5} {u}")
        if repo == "shyamsivakumar/strategy-replay-workbench" and not done:
            response = t3("t3_thread_list", {"projectId": CFG[repo]["projectId"],
                          "statuses": ["preparing", "queued", "starting", "running", "waiting"], "limit": 20})
            live = response.get("threads") if isinstance(response, dict) else None
            if not isinstance(live, list) or any(not isinstance(t, dict) or not isinstance(t.get("title"), str) for t in live):
                print(f"{CFG[repo]['key']:5} refused: invalid thread-list response")
                continue
            excluded = {group_of(t.get("title") or "") for t in live}
            if len(live) < 3:
                print(f"{CFG[repo]['key']:5} " + start_next(repo, tickets, ledger, excluded))
        elif not done and not b:
            print(f"{CFG[repo]['key']:5} " + start_next(repo, tickets, ledger))


def main():
    global CFG
    with open("/Users/shyamsivakumar/.coordinator/tickets.json") as handle:
        CFG = json.load(handle)["repos"]
    try:
        ledger = json.load(open(LEDGER))
    except (OSError, ValueError):
        ledger = {}
    before = None
    try:
        before = api_remaining()
        run_pass(ledger)
    except ApiBudgetExhausted as exc:
        print(f"API BUDGET {exc}")
    finally:
        try:
            after = api_remaining()
            used = {name: max(0, before[name] - after[name]) for name in after} if before else None
            print(f"API USAGE used={used} remaining={after} floor={API_FLOOR}")
        except ApiBudgetExhausted as exc:
            print(f"API USAGE unavailable: {exc}")
        if not DRY:
            with open(LEDGER, "w") as handle:
                json.dump(ledger, handle, indent=1)
