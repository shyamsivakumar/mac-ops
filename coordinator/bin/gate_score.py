"""The gate second pass: a cheap model scores each critical or major finding against the severity bar.

Findings scored below `KEEP_AT` are removed from the report; with none left the
VERDICT reads PASS. A FAIL CHECK or PROVIDES line, or any failure to score,
leaves the report as it was.
"""

import json
import re
import subprocess

import gate_policy
import models
from gate_bar import SEVERITY_BAR

KEEP_AT = 7
LEAD = re.compile(r"(Critical|Major)\b")
SCORES = re.compile(r"\[[\d,\s]*\]")

ASK = """{bar}

Below are the critical and major findings a reviewer raised on a pull request. Score each from 0 to 10 for how well it meets the severity bar: 10 is likely in real fleet use or hard to undo, 0 is an unlikely case that the bar calls minor.
Reply with only a JSON list of {count} integers, one per finding, in order.

{findings}"""


def findings_of(report):
    return [
        f
        for f in gate_policy.read_verdict(report)[1]
        if f.get("severity") in ("critical", "major")
    ] or [
        {"text": p.strip()}
        for p in re.split(r"\n\s*\n", report)
        if LEAD.match(p.strip())
    ]


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
    """Return (report, dropped titles). A report with a FAIL CHECK or PROVIDES line is returned as it was."""
    if gate_policy.read_verdict(report)[0] != "FAIL" or re.search(
        r"(?m)^(CHECK|PROVIDES): FAIL", report
    ):
        return report, []
    findings = findings_of(report)
    scores = scores_for(findings, call) if findings else None
    if scores is None:
        return report, []
    dropped = [f for f, s in zip(findings, scores, strict=True) if s < KEEP_AT]
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
        + "\n".join(f"- {t}" for t in titles)
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
