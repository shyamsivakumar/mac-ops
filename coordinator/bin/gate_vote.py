import random
import re
import time
from datetime import datetime

from gate_policy import JSON_VERDICT_ASK, read_verdict

VOTERS = 3
AGREE = 2
LINE_WINDOW = 5
VOTER_WAIT_HOURS = 2
BLOCKING = ("critical", "major")


def voter_args(args, key, paths):
    ballots = []
    for number in range(1, VOTERS + 1):
        order = random.Random(f"{key}:{number}").sample(paths, len(paths))
        ordered = "\nReview the changed files in this order: " + ", ".join(order) if order else ""
        ballot = {**args, "message": args["message"] + ordered + "\n" + JSON_VERDICT_ASK}
        if number > 1:
            ballot["clientRequestId"] = "vote:" + key.removeprefix("gate:") + f":{number}"
            ballot["title"] = f"{args['title']} vote {number}"
        ballots.append(ballot)
    return ballots


def replied_epoch(replied_at):
    if not replied_at:
        return None
    return datetime.fromisoformat(replied_at.replace("Z", "+00:00")).timestamp()


def overdue(since):
    return time.time() - since >= VOTER_WAIT_HOURS * 3600


def vote_threads(receipts, key):
    prefix = "vote:" + key.removeprefix("gate:") + ":"
    return [
        thread for name, thread in sorted(receipts.items()) if name.startswith(prefix)
    ]


def same(a, b):
    if a["severity"] != b["severity"] or a["path"] != b["path"]:
        return False
    if a["line"] is None or b["line"] is None:
        return a["line"] is b["line"]
    return abs(a["line"] - b["line"]) <= LINE_WINDOW


def survivors(finding_lists):
    kept = []
    for findings in finding_lists:
        for finding in findings:
            if any(same(finding, other) for other in kept):
                continue
            backers = sum(
                any(same(finding, other) for other in theirs)
                for theirs in finding_lists
            )
            if backers >= AGREE:
                kept.append(finding)
    return kept


def own_line(report, tag, head):
    match = re.search(rf"(?m)^{tag}: (PASS|FAIL) {head}\s*$", report)
    return match.group(1) if match else None


def counts(report, outcome, head):
    return outcome in ("PASS", "FAIL") and None not in (
        own_line(report, "CHECK", head),
        own_line(report, "PROVIDES", head),
    )


def merge_reports(reports, head):
    counted = [(report, *read_verdict(report)) for report in reports]
    counted = [row for row in counted if counts(row[0], row[1], head)]
    if len(counted) < AGREE:
        return f"Merged gate review of {len(reports)} reports on {head}: only {len(counted)} carried a verdict with its own CHECK and PROVIDES lines for this head.\nVERDICT: FAIL"
    kept = survivors([findings for _, _, findings in counted])
    unparsed = sum(
        1 for _, outcome, findings in counted if outcome == "FAIL" and not findings
    )
    mechanical = {
        tag: "FAIL" if any(own_line(r, tag, head) == "FAIL" for r, _, _ in counted) else "PASS"
        for tag in ("PROVIDES", "CHECK")
    }
    failed = (
        unparsed >= AGREE
        or "FAIL" in mechanical.values()
        or any(f["severity"] in BLOCKING for f in kept)
    )
    lines = [
        f"Merged gate review of {len(counted)} reports on {head}: a finding stays when {AGREE} agree on file, line within {LINE_WINDOW} and severity."
    ]
    for f in kept:
        where = f["path"] + (f":{f['line']}" if f["line"] is not None else "")
        lines.append(f"[{f['severity']}] {where} {f['text']}".rstrip())
    if unparsed >= AGREE:
        lines.append(
            f"{unparsed} reports ended FAIL without a finding line the merge could read."
        )
    lines += [f"{tag}: {mechanical[tag]} {head}" for tag in ("PROVIDES", "CHECK")]
    lines.append(f"VERDICT: {'FAIL' if failed else 'PASS'}")
    return "\n".join(lines)
