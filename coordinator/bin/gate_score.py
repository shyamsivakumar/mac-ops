"""The gate second pass: a cheap model scores each critical or major finding against the severity bar.

A FAIL report whose every critical or major finding scores below `KEEP_AT` is
rewritten to PASS. Any failure to score leaves the report as it was.
"""

import json
import re
import subprocess

import gate_policy
import models
from gate_bar import SEVERITY_BAR

KEEP_AT = 5
LEAD = re.compile(r"(Critical|Major)\b")
SCORES = re.compile(r"\[[\d,\s]*\]")

ASK = """{bar}

Below are the critical and major findings a reviewer raised on a pull request. Score each from 0 to 10 for how well it meets the severity bar: 10 is likely in real fleet use or hard to undo, 0 is an unlikely case that the bar calls minor.
Reply with only a JSON list of {count} integers, one per finding, in order.

{findings}"""


def findings_of(report):
    parsed = [
        f["text"]
        for f in gate_policy.read_verdict(report)[1]
        if f.get("severity") in ("critical", "major")
    ]
    return parsed or [
        p.strip() for p in re.split(r"\n\s*\n", report) if LEAD.match(p.strip())
    ]


def scores_for(findings, call):
    prompt = ASK.format(
        bar=SEVERITY_BAR,
        count=len(findings),
        findings="\n".join(f"{i + 1}. {t}" for i, t in enumerate(findings)),
    )
    try:
        found = SCORES.search(call(prompt) or "")
        scores = json.loads(found.group(0)) if found else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return scores if isinstance(scores, list) and len(scores) == len(findings) else None


def score_findings(report, call):
    """Return (report, dropped titles); the report is rewritten only when every critical or major finding scores below the bar."""
    findings = (
        findings_of(report) if gate_policy.read_verdict(report)[0] == "FAIL" else []
    )
    scores = scores_for(findings, call) if findings else None
    if scores is None or any(s >= KEEP_AT for s in scores):
        return report, []
    titles = [f.splitlines()[0][:160] for f in findings]
    passed = re.sub(
        r'("verdict":\s*)"FAIL"',
        r'\1"PASS"',
        re.sub(r"(?m)^(CHECK|PROVIDES|VERDICT): FAIL", r"\1: PASS", report),
    )
    note = (
        "Second pass scored these below the merge bar and dropped them:\n"
        + "\n".join(f"- {t}" for t in titles)
    )
    return f"{note}\n\n{passed}", titles


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
