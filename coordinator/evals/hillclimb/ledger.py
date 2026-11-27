#!/usr/bin/env python3
"""Preference ledger: one labeled row per decision card Shyam answered or ignored.

Reads labels.jsonl (written by daily3 record and build_labels) and the decision
events that `coordq decision sync/answered` journal. A card with a label takes
the label (accept when his answer matched the recommendation, reject when it
did not). A card without one takes its journal outcome (acted or ignored).
Read-only on both inputs; writes preferences.jsonl only.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "bin"))
import daily3  # noqa: E402
import journal  # noqa: E402

OUTCOMES = {"decision_answered": "acted", "decision_expired": "ignored"}
VERDICTS = {True: "accept", False: "reject"}


def label_rows(labels):
    for row in labels:
        if row.get("agree") in VERDICTS and row.get("id"):
            yield row["id"], {
                "kind": row.get("kind", "other"),
                "label": VERDICTS[row["agree"]],
                "recommended": row.get("recommended"),
                "answer": row.get("answer"),
                "reason": row.get("reason", ""),
                "source": "labels.jsonl",
            }


def journal_rows(events):
    for event in events:
        if event.get("event") in OUTCOMES and event.get("item"):
            yield event["item"], {
                "kind": event.get("kind") or "other",
                "label": OUTCOMES[event["event"]],
                "source": "journal",
            }


def build(labels, events):
    rows = dict(journal_rows(events))
    rows.update(label_rows(labels))
    return [{"id": item, **row} for item, row in sorted(rows.items())]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=HERE / "preferences.jsonl")
    parser.add_argument("--labels", type=Path, default=daily3.LABELS)
    parser.add_argument("--dry-run", action="store_true", help="print the rows, write nothing")
    args = parser.parse_args(argv)
    rows = build(daily3.read_jsonl(args.labels), journal_events())
    if args.dry_run:
        print(json.dumps(summary(rows)))
        return 0
    daily3.write_jsonl(args.out, rows)
    print(f"ledger: {len(rows)} rows -> {args.out} {json.dumps(summary(rows))}")
    return 0


def journal_events():
    events = []
    for path in sorted(Path(journal.journal_dir()).glob("events-*.jsonl")):
        events.extend(daily3.read_jsonl(path))
    return events


def summary(rows):
    counts = {}
    for row in rows:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    return counts


if __name__ == "__main__":
    sys.exit(main())
