import random
import re

import journal
from gate_bar import GATE_BAR
from gate_policy import JSON_VERDICT_ASK, read_verdict

VOTERS = 3
AGREE = 2
LINE_WINDOW = 5
BAR_SECTION = re.compile(r"\n\n(?=(?:Merge bar|Severity bar|Convergence rule) )")
BLOCKING = ("critical", "major")


def votes(gate_arm):
    return gate_arm == "treatment" and any(
        e["side"] == "gate" and "vote3" in (e.get("names") or [])
        for e in journal.factory_experiments()
    )


def shuffled(message, seed):
    sections = BAR_SECTION.split(GATE_BAR)
    random.Random(seed).shuffle(sections)
    return message.replace(GATE_BAR, "\n\n".join(sections))


def voter_args(args, key):
    ballots = []
    for number in range(1, VOTERS + 1):
        ballot = {**args, "message": shuffled(args["message"], f"{key}:{number}") + "\n" + JSON_VERDICT_ASK}
        if number > 1:
            ballot["clientRequestId"] = (
                "vote:" + key.removeprefix("gate:") + f":{number}"
            )
            ballot["title"] = f"{args['title']} vote {number}"
        ballots.append(ballot)
    return ballots


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


def check_line(reports, tag, head):
    found = [
        re.search(rf"(?m)^{tag}: (PASS|FAIL) {head}\s*$", report) for report in reports
    ]
    if not any(found):
        return None
    passed = sum(1 for match in found if match and match.group(1) == "PASS")
    return f"{tag}: {'PASS' if passed >= AGREE else 'FAIL'} {head}"


def merge_reports(reports, head):
    counted = [(report, *read_verdict(report)) for report in reports]
    counted = [row for row in counted if row[1] in ("PASS", "FAIL")]
    if len(counted) < AGREE:
        return reports[0]
    kept = survivors([findings for _, _, findings in counted])
    unparsed = sum(
        1 for _, outcome, findings in counted if outcome == "FAIL" and not findings
    )
    failed = unparsed >= AGREE or any(f["severity"] in BLOCKING for f in kept)
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
    texts = [report for report, _, _ in counted]
    lines += [
        line
        for line in (
            check_line(texts, "PROVIDES", head),
            check_line(texts, "CHECK", head),
        )
        if line
    ]
    lines.append(f"VERDICT: {'FAIL' if failed else 'PASS'}")
    return "\n".join(lines)
