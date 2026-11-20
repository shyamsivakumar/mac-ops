"""The per-PR findings ledger: what the gate found, what is still open.

A gate reply lists each critical or major as a `FINDING F<n>` block. The
ledger keeps those blocks under the queue directory, one file per pull
request, so the next gate brief and the builder's fix message carry the
same open findings in full, with the same ids.
"""

import fcntl
import json
import os
import re
import tempfile
from contextlib import contextmanager

FIELDS = {
    "severity": "severity",
    "where": "where",
    "bar": "bar",
    "text": "text",
    "trigger": "trigger",
    "fixed when": "fixed_when",
}
HEADER = re.compile(r"^\W*FINDING\s+(F\d+)\b", re.IGNORECASE)
FIELD = re.compile(
    r"^\W*(severity|where|bar|text|trigger|fixed when)\s*:\s*(.*)$", re.IGNORECASE
)
ANSWER = re.compile(r"^\W*(F\d+)\s+(fixed|open)\b\W*(.*)$", re.IGNORECASE)
LEGACY = re.compile(r"^\W*(critical|major)\b", re.IGNORECASE)
LEGACY_NONE = re.compile(
    r"^\W*(critical|major)( or (critical|major))?( findings?)?\W*(none|0)\b",
    re.IGNORECASE,
)
LEGACY_WHERE = re.compile(r"[\w./-]+\.\w+:\d+")
MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
FINAL_LINE = re.compile(
    r"^\W*(CHECK|PROVIDES|VERDICT|Open critical or major findings)\b"
)
UNPARSED_CHARS = 1500


def format_instruction(next_id):
    return (
        "Write each critical or major as a block (a critical or major with no block does not count):\n"
        "FINDING F<n>\nseverity: critical|major\nwhere: file:line\nbar: <the bar clause it breaks, such as M1>\n"
        "text: the full finding\ntrigger: who or what triggers it, how often, and your evidence\n"
        "fixed when: a test the builder can run or read to show it is fixed\n"
        f'Number new findings from F{next_id}. Minors go under "Left for later", with no block.'
    )


def queue_dir():
    return os.environ.get("COORDQ_DIR") or os.path.expanduser("~/Code/coordinator/queue")


def ledger_path(repo, number, base=None):
    return os.path.join(
        base or queue_dir(), "findings", f"{repo.replace('/', '_')}#{number}.json"
    )


def empty(repo, number):
    return {"repo": repo, "pr": number, "next": 1, "findings": {}, "reviews": {}}


def load(repo, number, base=None):
    try:
        with open(ledger_path(repo, number, base)) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return empty(repo, number)
    return (
        data if isinstance(data, dict) and "findings" in data else empty(repo, number)
    )


@contextmanager
def locked(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def save(path, ledger):
    descriptor, temporary = tempfile.mkstemp(
        dir=os.path.dirname(path), prefix=".findings-"
    )
    with os.fdopen(descriptor, "w") as handle:
        json.dump(ledger, handle, indent=1)
    os.replace(temporary, path)


def clean(text):
    return " ".join(MARKDOWN_LINK.sub(r"\1", text).replace("**", "").split())


def parse_blocks(reply):
    blocks, current, key = [], None, None
    for line in reply.splitlines():
        header = HEADER.match(line)
        field = FIELD.match(line)
        if header:
            current = {"id": header.group(1).upper()}
            blocks.append(current)
            key = None
        elif current is not None and field:
            key = FIELDS[field.group(1).lower()]
            current[key] = clean(field.group(2))
        elif (
            current is not None
            and key
            and line.strip()
            and not FINAL_LINE.match(line)
            and not ANSWER.match(line)
        ):
            current[key] = f"{current[key]} {clean(line)}".strip()
        else:
            current, key = None, None
    return blocks


def parse_legacy(reply):
    """Findings from a reply written before the block format: a paragraph that opens with Critical or Major."""
    found, paragraph = [], []
    for line in reply.splitlines() + [""]:
        stripped = line.strip().lstrip("-*0123456789.) ")
        if paragraph and (not line.strip() or LEGACY.match(stripped)):
            found.append(clean(" ".join(paragraph)))
            paragraph = []
        if LEGACY.match(stripped) and not LEGACY_NONE.match(stripped):
            paragraph = [stripped]
        elif paragraph and line.strip():
            paragraph.append(line.strip())
    blocks = []
    for text in found:
        where = LEGACY_WHERE.search(text)
        blocks.append(
            {
                "severity": LEGACY.match(text).group(1).lower(),
                "where": where.group(0) if where else "",
                "text": text,
                "legacy": True,
            }
        )
    return blocks


def parse_answers(reply):
    answers = {}
    for line in reply.splitlines():
        match = ANSWER.match(line)
        if match:
            answers[match.group(1).upper()] = {
                "status": match.group(2).lower(),
                "evidence": clean(match.group(3)),
            }
    return answers


def apply_reply(ledger, head, round_number, reply):
    blocks = parse_blocks(reply)
    answers = parse_answers(reply)
    legacy = not blocks and not answers
    if legacy:
        blocks = parse_legacy(reply)
    if legacy and blocks:
        for known in ledger["findings"].values():
            if known.get("legacy") and known.get("status") == "open":
                known["status"] = "superseded"
    for block in blocks:
        if "id" not in block:
            block["id"] = f"F{ledger['next']}"
        number = int(block["id"][1:])
        ledger["next"] = max(ledger["next"], number + 1)
        known = ledger["findings"].setdefault(block["id"], {"opened": head})
        known.update({key: value for key, value in block.items() if value})
        known["severity"] = (
            known.get("severity")
            if known.get("severity") in ("critical", "major")
            else "major"
        )
        known["status"] = "open"
    for finding_id, answer in answers.items():
        known = ledger["findings"].get(finding_id)
        if known and finding_id not in {block["id"] for block in blocks}:
            known["status"] = answer["status"]
            known["evidence"] = answer["evidence"]
    unparsed = None
    if not blocks and not answers and reply.rstrip().endswith("VERDICT: FAIL"):
        unparsed = reply.strip()[-UNPARSED_CHARS:]
    ledger["reviews"][head] = {
        "round": round_number,
        "legacy": legacy and bool(blocks),
        "unparsed": unparsed,
    }


def record(repo, number, head, round_number, reply, write=True, base=None):
    """Merge the findings of the gate reply for one head into the ledger, once per head, and return it."""
    path = ledger_path(repo, number, base)
    with locked(path):
        ledger = load(repo, number, base)
        if head in ledger["reviews"]:
            return ledger
        apply_reply(ledger, head, round_number, reply)
        if write:
            save(path, ledger)
    return ledger


def reviewed(repo, number, head, base=None):
    return head in load(repo, number, base)["reviews"]


def open_findings(ledger):
    return [
        dict(item, id=finding_id)
        for finding_id, item in ledger["findings"].items()
        if item.get("status") == "open"
    ]


def detail(item):
    lines = [
        f"{item['id']} {item.get('severity', 'major')} at {item.get('where') or 'no file:line given'}"
        + (f", bar {item['bar']}" if item.get("bar") else "")
        + f": {item.get('text', '')}"
    ]
    if item.get("trigger"):
        lines.append(f"  trigger: {item['trigger']}")
    if item.get("fixed_when"):
        lines.append(f"  fixed when: {item['fixed_when']}")
    return lines


def brief_section(ledger, head):
    """The open findings of earlier rounds, in full, as the gate brief carries them."""
    items = open_findings(ledger)
    if not items:
        last = (ledger["reviews"].get(head) or {}).get("unparsed")
        last = last or next(
            (
                r["unparsed"]
                for r in reversed(list(ledger["reviews"].values()))
                if r.get("unparsed")
            ),
            None,
        )
        if last:
            return (
                "No finding block could be read from the previous gate reply. Its last lines:\n"
                + last
            )
        return "No open findings from earlier rounds."
    lines = [
        "Open findings from earlier rounds. Answer each with `F<n> fixed: <evidence>` or `F<n> open: <evidence>`:"
    ]
    for item in items:
        lines.extend(detail(item))
    return "\n".join(lines)


def checklist(ledger):
    """The open findings as the builder's checklist, with the gate's ids."""
    items = open_findings(ledger)
    lines = []
    for item in items:
        first, *rest = detail(item)
        lines.append(f"- [ ] {first}")
        lines.extend(f"  {line.strip()}" for line in rest)
    return "\n".join(lines)
