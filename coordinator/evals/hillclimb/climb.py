#!/usr/bin/env python3
"""Keep or revert one hill-climb change (MO-1199 c).

Scores the candidate arm against the incumbent on the locked split through
score.py and prints KEEP when the lift is above zero and beats the noise,
else REVERT. Exit 0 for KEEP, 1 for REVERT. Every decision is appended to
climb_log.jsonl in the data dir. FINAL is never touched here.

    python3 climb.py [--data DIR] --arm NAME --arm-cmd "ARGV" \
        --baseline NAME [--baseline-cmd "ARGV"] [--repeats 5]
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_labels as B  # noqa: E402

DATA = B.data_dir(HERE)

SCORE_PY = Path(os.environ.get("SCORE_PY", os.path.expanduser("~/Code/mac-ops/evals/ladder/score.py")))


def decide(result):
    return "KEEP" if result["lift"] > 0 and result["beats_noise"] else "REVERT"


def score(args):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "result.json"
        cmd = [sys.executable, str(SCORE_PY), "locked", "--labels", str(DATA), "--lock", str(DATA / "score.lock"),
               "--arm", args.arm, "--baseline", args.baseline, "--repeats", str(args.repeats), "--json", str(out)]
        for role in ("arm", "baseline"):
            if getattr(args, f"{role}_cmd"):
                cmd += [f"--{role}-cmd", getattr(args, f"{role}_cmd")]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            sys.exit(f"climb: score.py exited {proc.returncode}: {proc.stderr.strip()}")
        return json.loads(out.read_text())


def main(argv=None):
    parser = argparse.ArgumentParser(prog="climb.py", description=__doc__)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--arm-cmd")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--baseline-cmd")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args(argv)
    result = score(args)
    verdict = decide(result)
    row = {"ts": datetime.now(timezone.utc).isoformat(), "arm": args.arm, "baseline": args.baseline, "verdict": verdict,
           "lift": result["lift"], "paired_se": result["paired_se"], "n": result["n"], "repeats": args.repeats}
    with (DATA / "climb_log.jsonl").open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    print(f"{verdict} lift {result['lift']:.2f} se {result['paired_se']:.2f} n {result['n']}")
    return 0 if verdict == "KEEP" else 1


if __name__ == "__main__":
    sys.exit(main())
