import importlib.util
import json
import sys
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("daily3", Path(sys.argv[1]))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

tmp = Path(tempfile.mkdtemp(prefix="mo1035-"))
d.LABELS, d.HARD, d.BURST = (
    tmp / "labels.jsonl",
    tmp / "hard.jsonl",
    tmp / "burst.jsonl",
)
d.GUESSES, d.SPLIT = tmp / "guesses.jsonl", tmp / "split.json"
d.DECISIONS = tmp / "decisions.json"
d.relock = lambda: True
d.SPLIT.write_text(json.dumps({"splits": {"DEV": [], "HELDOUT": [], "FINAL": []}}))
d.GUESSES.write_text(
    "".join(
        json.dumps(
            {
                "label_id": i,
                "kind": "other",
                "item_text": "q",
                "options": ["a", "b"],
                "guess": "a",
            }
        )
        + "\n"
        for i in ("t1", "t2", "t3", "t4")
    )
)


def run(label_id, *extra):
    argv = ["record", "--id", label_id, "--choice", "a", *extra]
    try:
        rc = d.main(argv)
    except SystemExit as e:
        rc = f"SystemExit({e.code})"
    rows = {r["id"]: r for r in d.read_jsonl(d.LABELS)}
    row = rows.get(label_id)
    stored = repr(row["reason"]) if row else "no row"
    print(f"{label_id} {[e[:20] for e in extra]} -> rc={rc} reason_in_row={stored}")


run("t1", "--reason", "Because the retry is cheap")
run("t2")
run("t3", "--reason", "x" * 201)
run("t4", "--reason", "line one\nline two")
