#!/usr/bin/env python3
"""Mine past decisions that have no recorded answer and queue them for Shyam.

Reads the same sources build_labels.py reads (coordinator pi session logs and the
decisions-board snapshots) and keeps only decisions that:

  * carry a recorded recommendation (so the coordinator has a real guess), and
  * have no recorded answer (a board answer, or a typed reply that names an
    option), and
  * are not already a label, and
  * are one of the thin kinds: merge, money, access, size_exception.

Nothing is invented. An item with no recorded answer stays in burst_queue.jsonl
until Shyam answers it through `daily3.py record`.

Writes only burst_queue.jsonl under this directory.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_labels as B  # noqa: E402

THIN = ("merge", "money", "access", "size_exception")
OUT = HERE / "burst_queue.jsonl"
LABELS = HERE / "labels.jsonl"
DECISIONS = Path.home() / "Code/coordinator/decisions.json"

STOP = {
    "the", "a", "an", "it", "is", "to", "and", "or", "of", "for", "in", "on", "that", "this",
    "so", "we", "i", "you", "me", "my", "be", "as", "at", "by", "with", "then", "now", "if",
    "not", "no", "yes", "do", "does", "should", "can", "will", "would", "could", "have", "shyam",
}


def nz(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def toks(s):
    return set(nz(s).split()) - STOP


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def overlap(a, b):
    """Overlap coefficient: how much of the smaller set the larger covers."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def signature(text):
    """Distinctive ids: PR numbers and ticket ids. Two cards with different
    numbers are different decisions even when the template is identical."""
    return set(re.findall(r"\b\d{3,}\b", text or "")) | set(
        re.findall(r"\b[A-Za-z]{2,}-\d+\b", text or "")
    )


def same_decision(a_text, b_text, threshold):
    sa, sb = signature(a_text), signature(b_text)
    if sa and sb and not (sa & sb):
        return False
    return overlap(toks(a_text), toks(b_text)) >= threshold


def clean_options(options, recommended):
    """Reject a typed ask whose parsed options are broken."""
    if not options:
        return False
    if [nz(o) for o in options] == ["yes", "no"]:
        # A yes/no parse of an A/B/C question is wrong.
        return not re.fullmatch(r"[A-Ca-c]", (recommended or "").strip())
    # A bare single word is a fragment of a longer alternative, not an option.
    return all(len(o.strip()) >= 4 and len(o.split()) >= 2 for o in options)


def main():
    recs = B.load_messages()
    panel = B.load_panel(recs)
    board = B.load_board(recs)
    typed = B.load_typed(recs)
    board_ids = {b["id"] for b in board}

    labels = [json.loads(l) for l in LABELS.read_text().splitlines() if l.strip()]

    live_ids = set()
    if DECISIONS.exists():
        try:
            live_ids = {it["id"] for it in (json.loads(DECISIONS.read_text()).get("items") or [])}
        except json.JSONDecodeError:
            pass

    def already_labelled(text):
        # A paraphrase of a labelled decision is still that decision. Overlap
        # coefficient catches a short restatement of a longer card; the id
        # signature keeps two different PRs apart.
        return any(same_decision(text, l.get("item_text", ""), 0.55) for l in labels)

    cands = []

    # 1. Board cards raised with a recommendation but never answered on the board.
    for iid, rows in panel.items():
        if iid in board_ids or iid in live_ids:
            continue
        row = rows[-1]
        if not row["rec"] or not row["options"]:
            continue
        kind = B.classify(row["title"], row["options"])
        if kind not in THIN or already_labelled(row["title"]):
            continue
        cands.append(
            {
                "id": iid,
                "kind": kind,
                "item_text": row["title"][:300],
                "options": row["options"],
                "recommended": row["rec"][0],
                "recommended_option": row["rec"][0],
                "answer": "",
                "agree": None,
                "ts": row["ts"],
                "source": f"{row['f']}:{row['i']} (decisions board item, no board answer)",
                "reason": "",
            }
        )

    # 2. Typed asks whose reply was a follow-up, not an answer.
    for n, t in enumerate(typed):
        if n in B.TYPED_KEEP:
            continue
        options = B.options_for_question(t["q"])
        kind = B.classify(t["q"], options)
        if kind not in THIN:
            continue
        if B.pick_option(t["ans"], options) is not None:
            continue  # it was answered
        if not clean_options(options, t["rec"]):
            continue  # the parsed options are broken; do not ask a malformed card
        if already_labelled(t["q"]):
            continue
        iid = "typed-" + re.sub(r"[^a-z0-9]+", "-", t["q"].lower())[:60].strip("-")
        if iid in live_ids:
            continue
        cands.append(
            {
                "id": iid,
                "kind": kind,
                "item_text": t["q"][:300],
                "options": options,
                "recommended": t["rec"],
                "recommended_option": B.pick_option(t["rec"], options),
                "answer": "",
                "agree": None,
                "ts": t["ansts"],
                "source": f"{t['f']}:{t['i']} (ask with Recommended; reply was a follow-up)",
                "reason": "",
            }
        )

    # Dedupe by near-identical text, keeping the first (board card before typed).
    # A typed yes/no restatement of a board card is dropped at a lower threshold,
    # because the board card carries the real options.
    out = []
    for c in cands:
        typed = c["id"].startswith("typed-")
        if any(same_decision(c["item_text"], o["item_text"], 0.7 if typed else 0.6) for o in out):
            continue
        out.append(c)

    out.sort(key=lambda r: (THIN.index(r["kind"]), r.get("ts") or "", r["id"]))
    with OUT.open("w") as fh:
        for row in out:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    counts = {k: sum(1 for r in out if r["kind"] == k) for k in THIN}
    print(f"burst_queue.jsonl: {len(out)} items {counts}")

    # Print the first ten as ready-to-ask items, with the guess hidden.
    print("\nFirst 10 ready to ask (guess hidden):\n")
    for n, row in enumerate(out[:10], 1):
        print(f"{n}. [{row['kind']}] {row['item_text']}")
        for k, opt in enumerate(row["options"], 1):
            print(f"     {k}) {opt}")
        print(f"     id: {row['id']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
