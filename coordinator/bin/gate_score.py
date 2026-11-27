import json
import re
import subprocess

import gate_policy
import models
from gate_bar import SEVERITY_BAR

KEEP_AT = 7
LEAD = re.compile(r"^[ \t]*(?:[-*>][ \t]+|\d+[.)][ \t]+)?[*_`]*(?:Critical|Major)\b", re.MULTILINE)
SCORES = re.compile(r"\[[\d,\s]*\]")

ASK = """{bar}

Below are the critical and major findings a reviewer raised on a pull request. Score each from 0 to 10 for how well it meets the severity bar: 10 is likely in real fleet use or hard to undo, 0 is an unlikely case that the bar calls minor.
Reply with only a JSON list of {count} integers, one per finding, in order.

{findings}"""


def prose_findings(report):
    found, open_item = [], False
    for line in report.splitlines():
        if LEAD.match(line):
            found.append([line])
            open_item = True
        elif line.strip() and open_item:
            found[-1].append(line)
        else:
            open_item = False
    return [{"text": "\n".join(lines).strip()} for lines in found]


def findings_of(report):
    return [
        f
        for f in gate_policy.read_verdict(report)[1]
        if f.get("severity") in ("critical", "major")
    ] or prose_findings(report)


def scores_for(findings, call):
    prompt = ASK.format(
        bar=SEVERITY_BAR,
        count=len(findings),
        findings="\n".join(f"{i + 1}. {f['text']}" for i, f in enumerate(findings)),
    )
    try:
        found = SCORES.search(call(prompt) or "")
        scores = json.loads(found.group(0)) if found else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return scores if isinstance(scores, list) and len(scores) == len(findings) else None


def without(report, dropped):
    data = gate_policy.parse_verdict(report)
    if not data:
        for finding in dropped:
            report = report.replace(finding["text"], "", 1)
        return report
    block = json.dumps(
        {**data, "findings": [f for f in data["findings"] if f not in dropped]}
    )
    return gate_policy.JSON_BLOCK.sub(lambda _: "```json\n" + block + "\n```", report)


def score_findings(report, call):
    if gate_policy.read_verdict(report)[0] != "FAIL" or re.search(
        r"(?m)^(CHECK|PROVIDES): FAIL", report
    ):
        return report, []
    findings = findings_of(report)
    if len(LEAD.findall(report)) > len(findings):
        return report, []
    scores = scores_for(findings, call) if findings else None
    if scores is None:
        return report, []
    dropped = [f for i, f in enumerate(findings) if scores[i] < KEEP_AT]
    if not dropped:
        return report, []
    report = without(report, dropped)
    if len(dropped) == len(findings):
        report = re.sub(
            r'("verdict":\s*)"FAIL"',
            r'\1"PASS"',
            re.sub(r"(?m)^VERDICT: FAIL", "VERDICT: PASS", report),
        )
    titles = [f["text"].splitlines()[0][:160] for f in dropped]
    return (
        "Second pass scored these below the merge bar and dropped them:\n"
        + "\n".join(f"- dropped: {t}" for t in titles)
        + "\n\n"
        + report,
        titles,
    )


def pi_call(prompt):
    identities = models.pi_identities()
    blocked = models.blocked_identities()
    spec = next(
        (s for s in models.pi_routes("quick") if identities.get(s) not in blocked), None
    )
    if spec is None:
        return ""
    provider, model = spec.split("/", 1)
    done = subprocess.run(
        [
            "pi",
            "--provider",
            provider,
            "--model",
            model,
            "--no-session",
            "--no-tools",
            "-p",
            prompt,
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return done.stdout if done.returncode == 0 else ""
