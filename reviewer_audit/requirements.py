"""Map review finding subjects to stable requirement IDs."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RequirementRule:
    requirement_id: str
    pattern: re.Pattern[str]


RULES: tuple[RequirementRule, ...] = (
    RequirementRule(
        "REQ-NATIVE-START-GATE",
        re.compile(
            r"atomic|per-start|per-wake|start.?gate|memory and load gate|"
            r"before each (agent )?start",
            re.IGNORECASE,
        ),
    ),
    RequirementRule(
        "REQ-LIVE-ACCEPTANCE",
        re.compile(
            r"live (safety|acceptance|operational)|not been demonstrated|"
            r"remains unproven|installation.*acceptance",
            re.IGNORECASE,
        ),
    ),
    RequirementRule(
        "REQ-CRITICAL-CURTAIL",
        re.compile(
            r"curtail|running (heavy )?jobs|backstop|critical pressure.*never",
            re.IGNORECASE,
        ),
    ),
    RequirementRule(
        "REQ-SPX-LEVEL-TRACK",
        re.compile(
            r"SPX (index )?level|underlying-based|SPX feed|"
            r"track underlying levels on SPX|live SPX index|SPX index tracking|"
            r"SPX reading|levelTrigger",
            re.IGNORECASE,
        ),
    ),
    RequirementRule(
        "REQ-EXIT-SIZING",
        re.compile(
            r"TP1|partial|take some off|50%|sizing|invented.*size",
            re.IGNORECASE,
        ),
    ),
    RequirementRule(
        "REQ-API-EVIDENCE",
        re.compile(
            r"API evidence|exact API|quote and order|cannot be verified|"
            r"receipt.*prove|API responses are missing|order eligibility",
            re.IGNORECASE,
        ),
    ),
    RequirementRule(
        "REQ-RELEASE-GATE-CREDS",
        re.compile(r"release gate.*credential|private credential", re.IGNORECASE),
    ),
    RequirementRule(
        "REQ-REFUSAL-REGRESSION",
        re.compile(r"refus|valid call|wrong refusal|human.*guru", re.IGNORECASE),
    ),
    RequirementRule(
        "REQ-INDEPENDENT-LABEL",
        re.compile(r"independent|self-written|author.*label", re.IGNORECASE),
    ),
    RequirementRule(
        "REQ-EVIDENCE-LAYER",
        re.compile(
            r"deployed|live account|CI only|local replay|production evidence",
            re.IGNORECASE,
        ),
    ),
)


def requirement_ids_for_subject(subject: str) -> list[str]:
    hits = [rule.requirement_id for rule in RULES if rule.pattern.search(subject)]
    if hits:
        return hits
    slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")[:48]
    return [f"REQ-OTHER-{slug or 'unspecified'}"]


def requirement_ids_for_finding(finding: dict) -> list[str]:
    subject = str(finding.get("subject") or finding.get("text") or "")
    return requirement_ids_for_subject(subject)
