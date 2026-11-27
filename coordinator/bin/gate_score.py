import json
import re
import subprocess

import gate_policy
import models
from gate_bar import SEVERITY_BAR

KEEP_AT = 7
LEAD = re.compile(
    r"^[\s>*_`\[(\-]*(?:\d+[.)][\s>*_`\[(\-]*)?(?:critical|major)\b",
    re.MULTILINE | re.IGNORECASE,
)
BLOCKING_WORD = re.compile(r"\b(?:critical|major)\b", re.IGNORECASE)
FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
FOOTER = re.compile(r"^(?:CHECK|PROVIDES|VERDICT):.*$", re.MULTILINE)
ENDS = re.compile(
    r"^\s*(?:CHECK:|PROVIDES:|VERDICT:|Builder check:|#{0,6}\s*Left for later\b)",
    re.IGNORECASE,
)

ASK = """{bar}

Below are the critical and major findings a reviewer raised on a pull request. Score each from 0 to 10 for how well it meets the severity bar: 10 is likely in real fleet use or hard to undo, 0 is an unlikely case that the bar calls minor.
Reply with only a JSON list of {count} integers, one per finding, in order.

{findings}"""


def prose_findings(report):
    found, open_item = [], False
    for line in report.splitlines():
        if ENDS.match(line):
            open_item = False
        elif LEAD.match(line):
            found.append([line])
            open_item = True
        elif line.strip() and open_item:
            found[-1].append(line)
        else:
            open_item = False
    return [{"text": "\n".join(lines).strip()} for lines in found]


def blocking(finding):
    return str(finding.get("severity")).lower() in ("critical", "major")


def findings_of(report):
    data = gate_policy.parse_verdict(report)
    if data:
        return [f for f in data["findings"] if blocking(f)]
    return prose_findings(report)


def scores_for(findings, call):
    prompt = ASK.format(
        bar=SEVERITY_BAR,
        count=len(findings),
        findings="\n".join(f"{i + 1}. {f['text']}" for i, f in enumerate(findings)),
    )
    try:
        text = (call(prompt) or "").strip()
        fenced = FENCE.match(text)
        scores = json.loads(fenced.group(1) if fenced else text)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    valid = (
        isinstance(scores, list)
        and len(scores) == len(findings)
        and all(type(n) is int and 0 <= n <= 10 for n in scores)
    )
    return scores if valid else None


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
    if len(BLOCKING_WORD.findall(report)) > len(findings) or any(
        len(BLOCKING_WORD.findall(f["text"])) > 1 for f in findings
    ):
        return report, []
    scores = scores_for(findings, call) if findings else None
    if scores is None:
        return report, []
    dropped = [f for i, f in enumerate(findings) if scores[i] < KEEP_AT]
    if not dropped:
        return report, []
    original, kept = report, FOOTER.findall(report)
    report = without(report, dropped)
    if not BLOCKING_WORD.search(report):
        kept = [line.replace("VERDICT: FAIL", "VERDICT: PASS") for line in kept]
        report = re.sub(
            r'("verdict":\s*)"FAIL"',
            r'\1"PASS"',
            re.sub(r"(?m)^VERDICT: FAIL", "VERDICT: PASS", report),
        )
    if FOOTER.findall(report) != kept:
        return original, []
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
