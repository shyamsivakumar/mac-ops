#!/usr/bin/env python3
"""Daily 3: put three real decisions to Shyam a day and log the guess first.

Two commands:

  pick    Choose the next three real decisions from the live decision inbox
          (~/Code/coordinator/decisions.json) and, when that is empty, from the
          mined backlog (burst_queue.jsonl). The coordinator's guess is written
          to daily3_guesses.jsonl BEFORE the questions are printed, so the guess
          can never be edited after seeing the answer.

  record  Take Shyam's choice and a one-line reason, append the label to
          labels.jsonl, route it into split.json with the same hash rule the
          rest of the set uses, and re-run `score.py lock`.

An escaped bug (a bug that reached production or a merged PR) is written to
hard_set.jsonl instead, never into DEV / HELDOUT / FINAL.

Nothing here changes a harness prompt or a rule. It only records decisions.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_labels as B  # noqa: E402  (same split rule, same normalisation)

DATA = B.data_dir(HERE)

DECISIONS = Path(os.path.expanduser("~/Code/coordinator/decisions.json"))
GUESSES = DATA / "daily3_guesses.jsonl"
LABELS = DATA / "labels.jsonl"
SPLIT = DATA / "split.json"
BURST = DATA / "burst_queue.jsonl"
HARD = DATA / "hard_set.jsonl"
SCORE_PY = Path(os.environ.get("SCORE_PY", os.path.expanduser("~/Code/mac-ops/evals/ladder/score.py")))


# ------------------------------------------------------------------ helpers


def now():
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def append_jsonl(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def write_jsonl(path, rows):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def norm(s):
    return B.norm(s)


def option_for(text, options):
    """Map a free recommendation to one of the options, or None."""
    if not options:
        return None
    n = norm(text)
    for o in options:
        if norm(o) == n:
            return o
    for o in options:
        no = norm(o)
        if no and (no in n or n in no):
            return o
    return None


def live_items():
    """Open ask cards on the live decision board."""
    if not DECISIONS.exists():
        return []
    try:
        board = json.loads(DECISIONS.read_text())
    except json.JSONDecodeError:
        return []
    out = []
    for it in board.get("items") or []:
        if it.get("kind") != "ask":
            continue
        options = [o.get("label") for o in it.get("options") or [] if o.get("label")]
        if not options:
            continue
        rec = [o.get("label") for o in it.get("options") or [] if o.get("recommended")]
        out.append(
            {
                "id": it["id"],
                "kind": B.classify(it.get("title", ""), options),
                "item_text": (it.get("title") or "")[:300],
                "options": options,
                "recommended": rec[0] if rec else "",
                "recommended_option": rec[0] if rec else None,
                "source": "decisions.json (live inbox)",
                "ts": board.get("updated"),
            }
        )
    return out


def backlog_items():
    """Mined decisions with no recorded answer yet."""
    return [r for r in read_jsonl(BURST) if not (r.get("answer") or "").strip()]


def guess_of(item):
    """The coordinator's guess and where it came from."""
    rec = item.get("recommended_option") or item.get("recommended") or ""
    opt = option_for(rec, item.get("options") or [])
    if item.get("recommended_option"):
        source = "recorded recommended option"
    elif rec:
        source = "recorded recommendation"
    else:
        source = "no recorded recommendation"
    return rec, opt, source


# --------------------------------------------------------------------- pick


def cmd_pick(args):
    asked = {r.get("label_id") for r in read_jsonl(GUESSES)}
    pool = [i for i in live_items() if i["id"] not in asked]
    if len(pool) < args.n:
        pool += [i for i in backlog_items() if i["id"] not in asked and i["id"] not in {p["id"] for p in pool}]
    chosen = pool[: args.n]
    if not chosen:
        print("daily3: nothing to ask; the inbox and the backlog are both empty", file=sys.stderr)
        return 1

    # Write every guess first, and flush to disk, before printing anything.
    ts = now()
    for item in chosen:
        guess, guess_opt, source = guess_of(item)
        append_jsonl(
            GUESSES,
            {
                "ts": ts,
                "label_id": item["id"],
                "kind": item["kind"],
                "item_text": item["item_text"],
                "options": item["options"],
                "guess": guess_opt or guess,
                "guess_source": source,
            },
        )

    # Only now show the questions, with the guess hidden.
    print(f"Daily 3 ({ts}) — guess logged to {GUESSES.name} before this line.\n")
    for n, item in enumerate(chosen, 1):
        print(f"{n}. [{item['kind']}] {item['item_text']}")
        for k, opt in enumerate(item["options"], 1):
            print(f"     {k}) {opt}")
        print()
    print("Answer with: python3 daily3.py record --id <id> --choice '<option>' [--reason '<one line>']")
    print("ids: " + ", ".join(i["id"] for i in chosen))
    return 0


# ------------------------------------------------------------------- record


def find_item(label_id):
    for item in live_items() + backlog_items():
        if item["id"] == label_id:
            return item
    for g in reversed(read_jsonl(GUESSES)):
        if g.get("label_id") == label_id:
            return {
                "id": label_id,
                "kind": g.get("kind", "other"),
                "item_text": g.get("item_text", ""),
                "options": g.get("options") or [],
                "recommended": g.get("guess", ""),
                "recommended_option": g.get("guess") if g.get("guess") in (g.get("options") or []) else None,
                "source": "daily3_guesses.jsonl",
                "ts": g.get("ts"),
            }
    return None


def find_guess(label_id):
    for g in reversed(read_jsonl(GUESSES)):
        if g.get("label_id") == label_id:
            return g
    return None


def relock():
    if not SCORE_PY.exists():
        print(f"daily3: score.py not found at {SCORE_PY}; run the lock by hand", file=sys.stderr)
        return False
    done = subprocess.run(
        [sys.executable, str(SCORE_PY), "lock", "--labels", str(DATA)],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        print(f"daily3: lock failed: {done.stderr.strip()}", file=sys.stderr)
        return False
    return True


MAX_REASON = 200


def cmd_record(args):
    reason = (args.reason or "").strip()
    if len(reason) > MAX_REASON or "\n" in reason or "\r" in reason:
        print(f"daily3: --reason must be one line of at most {MAX_REASON} characters", file=sys.stderr)
        return 2
    item = find_item(args.id)
    if item is None:
        print(f"daily3: no item with id {args.id!r} in the inbox, backlog or guess log", file=sys.stderr)
        return 2

    options = item.get("options") or []
    choice = args.choice.strip()
    picked = option_for(choice, options)
    if options and picked is None and not args.allow_free_text:
        print(f"daily3: {choice!r} is not one of the options: {options}", file=sys.stderr)
        return 2
    answer = picked or choice

    guess_row = find_guess(args.id)
    if guess_row:
        recommended = guess_row.get("guess") or ""
        recommended_option = recommended if recommended in options else option_for(recommended, options)
        guess_source = guess_row.get("guess_source", "daily3_guesses.jsonl")
    else:
        recommended, recommended_option, guess_source = guess_of(item)

    agree = B.agreement(recommended_option or recommended, answer, options)
    label = {
        "id": args.id,
        "kind": item.get("kind", "other"),
        "item_text": item.get("item_text", "")[:300],
        "options": options,
        "answer": answer,
        "recommended": recommended,
        "recommended_option": recommended_option,
        "agree": agree,
        "ts": now(),
        "source": f"daily3 record <- {item.get('source', 'unknown')} (guess: {guess_source})",
        "reason": reason,
    }

    if args.escaped_bug:
        append_jsonl(HARD, label)
        queue = read_jsonl(BURST)
        if any(r.get("id") == args.id for r in queue):
            write_jsonl(BURST, [r for r in queue if r.get("id") != args.id])
        print(f"daily3: escaped bug {args.id} written to {HARD.name} (not scored)")
        return 0

    existing = {r["id"] for r in read_jsonl(LABELS)}
    if args.id in existing:
        print(f"daily3: {args.id} is already labelled; not adding it twice", file=sys.stderr)
        return 2
    append_jsonl(LABELS, label)

    split = json.loads(SPLIT.read_text())
    bucket = B.split_of(args.id)
    if args.id not in split["splits"][bucket]:
        split["splits"][bucket].append(args.id)
    split["counts"] = {k: len(v) for k, v in split["splits"].items()}
    split["final"] = split["splits"]["FINAL"]
    split["dev"] = split["splits"]["DEV"]
    split["heldout"] = split["splits"]["HELDOUT"]
    SPLIT.write_text(json.dumps(split, indent=1) + "\n")

    # An answered backlog item leaves the queue.
    queue = read_jsonl(BURST)
    if any(r.get("id") == args.id for r in queue):
        write_jsonl(BURST, [r for r in queue if r.get("id") != args.id])

    locked = relock()
    print(f"daily3: {args.id} -> {bucket} (agree={agree}); lock {'re-run' if locked else 'NOT re-run'}")
    return 0


# ---------------------------------------------------------------------- cli


def main(argv=None):
    parser = argparse.ArgumentParser(prog="daily3.py", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("pick", help="choose and print the next three decisions")
    p.add_argument("-n", type=int, default=3)
    p.set_defaults(func=cmd_pick)

    r = sub.add_parser("record", help="record Shyam's answer as a label")
    r.add_argument("--id", required=True)
    r.add_argument("--choice", required=True)
    r.add_argument("--reason", default="")
    r.add_argument("--escaped-bug", action="store_true", help="route to hard_set.jsonl, never a split")
    r.add_argument("--allow-free-text", action="store_true")
    r.set_defaults(func=cmd_record)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
