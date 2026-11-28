#!/usr/bin/env python3
"""Add labeled decisions newer than every installed label to the held-out split, then re-lock."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import build_labels as B

SCORE = Path(__file__).resolve().parents[3] / "evals" / "ladder" / "score.py"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--lock", type=Path, help="lock file to rewrite; score.py's default when omitted")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    labels_path, split_path = args.labels / "labels.jsonl", args.labels / "split.json"
    installed = B.prior_rows(str(labels_path))
    since = max((r["ts"] for r in installed.values() if r.get("ts")), key=B.utc)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "hc").mkdir()
        B.OUT = B.TMP = tmp
        B.main(since)
        cases = [json.loads(line) for line in (Path(tmp) / "heldout_cases.jsonl").read_text().splitlines()]
    new = [c for c in cases if c["id"] not in installed]
    print(f"install: {len(new)} new held-out cases newer than {since}")
    if args.dry_run or not new:
        return
    with labels_path.open("a") as fh:
        fh.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in new)
    split = json.loads(split_path.read_text())
    ids = sorted(c["id"] for c in new)
    split["heldout"] += ids
    split["splits"]["HELDOUT"] += ids
    split["counts"]["HELDOUT"] = len(split["heldout"])
    split_path.write_text(json.dumps(split, indent=1))
    lock = ["--lock", str(args.lock)] if args.lock else []
    subprocess.run([sys.executable, str(SCORE), "lock", "--labels", str(args.labels), *lock], check=True)


if __name__ == "__main__":
    main()
