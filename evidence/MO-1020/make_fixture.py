"""Build a fixture journal, dispatch receipts and thread store under the directory given as argv[1].

Arm "control" passes 1 of 2 first gates, uses 2000 tokens a ticket, merges in 2 h.
Arm "treatment" passes 2 of 2, uses 1000 tokens a ticket, merges in 1 h.
Treatment therefore dominates control. Pass --split to give treatment a higher
cost so that neither arm dominates. Pass --no-cost to omit the receipts.
"""

import json
import os
import sqlite3
import sys

root = sys.argv[1]
split = "--split" in sys.argv
no_cost = "--no-cost" in sys.argv
journal, queue = os.path.join(root, "journal"), os.path.join(root, "queue")
os.makedirs(journal)
os.makedirs(queue)
base = 1_700_000_000
treatment_tokens = 5000 if split else 1000
tickets = [
    ("control", 1, "FAIL", 7200, 2000),
    ("control", 2, "PASS", 7200, 2000),
    ("treatment", 3, "PASS", 3600, treatment_tokens),
    ("treatment", 4, "PASS", 3600, treatment_tokens),
]
rows, receipts = [], {}
db = sqlite3.connect(os.path.join(root, "state.sqlite"))
db.execute(
    "create table orchestration_v2_projection_provider_threads (thread_id text, driver text, payload_json text)"
)
for index, (arm, number, verdict, wait, tokens) in enumerate(tickets):
    start = base + index * 100000
    common = {
        "v": 1,
        "actor": "fixture",
        "repo": "demo",
        "ticket": number,
        "head": None,
        "thread": None,
        "item": None,
        "attempt": None,
        "kind": None,
    }
    rows.append(
        {
            **common,
            "ts": start,
            "event": "assigned",
            "pr": None,
            "arm": arm,
            "data": {"experiment": "exp-a"},
        }
    )
    rows.append(
        {
            **common,
            "ts": start + 60,
            "event": "gate_verdict",
            "pr": 100 + number,
            "arm": arm,
            "data": {"verdict": verdict},
        }
    )
    rows.append(
        {
            **common,
            "ts": start + wait,
            "event": "merged",
            "pr": 100 + number,
            "arm": arm,
            "data": {},
        }
    )
    session = os.path.join(root, f"session-{number}.jsonl")
    with open(session, "w") as handle:
        handle.write(
            json.dumps(
                {
                    "message": {
                        "role": "assistant",
                        "usage": {"input": tokens, "output": 0},
                    }
                }
            )
            + "\n"
        )
    receipts[f"ticket:demo#{number}:a1"] = f"thread-{number}"
    db.execute(
        "insert into orchestration_v2_projection_provider_threads values (?, 'pi', ?)",
        (f"thread-{number}", json.dumps({"nativeThreadRef": {"nativeId": session}})),
    )
db.commit()
with open(os.path.join(journal, "events-2023-11.jsonl"), "w") as handle:
    handle.writelines(json.dumps(row) + "\n" for row in rows)
if not no_cost:
    with open(os.path.join(queue, "dispatch-receipts.json"), "w") as handle:
        json.dump(receipts, handle)
