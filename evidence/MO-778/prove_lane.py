"""Proof for #778: lane_driver.gate_verdict waits for every voter and never acts on the primary alone.

The receipts file is a temp one, and thread state and replies are fakes, so
nothing reads the live queue or t3.
"""

import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "coordinator" / "bin"))
sys.path.insert(0, str(ROOT / "coordinator" / "overnight"))
spec = importlib.util.spec_from_file_location(
    "lane_driver_mo778", ROOT / "coordinator" / "overnight" / "lane_driver.py"
)
lane = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lane)

REPO, NUMBER, HEAD, BASE = "o/r", 1, "a" * 40, "main"
KEY = f"gate:{REPO}#{NUMBER}:{HEAD}"
VOTE = f"vote:{REPO}#{NUMBER}:{HEAD}"


def reply(outcome, check="PASS", findings=()):
    rows = [
        {
            "id": "F1",
            "severity": s,
            "bar_clause": "n/a",
            "path": p,
            "line": n,
            "text": "t",
            "fixed_when": "n/a",
        }
        for s, p, n in findings
    ]
    block = "```json\n" + json.dumps({"verdict": outcome, "findings": rows}) + "\n```"
    return f"{block}\nsummary\n\nPROVIDES: PASS {HEAD}\nCHECK: {check} {HEAD}\nVERDICT: {outcome}"


def scenario(name, receipts, replies, running=(), replied_hours_ago=0):
    path = Path(tempfile.mkdtemp(prefix="mo778-lane-")) / "receipts.json"
    path.write_text(
        json.dumps({**receipts, **{f"base:{t}": BASE for t in ("T1", "T2", "T3")}})
    )
    lane.RECEIPTS = str(path)
    lane.gate_in_flight = lambda thread: thread in running
    lane.last_reply = lambda thread: replies.get(thread, "")
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - replied_hours_ago * 3600))
    lane.reply_updated_at = lambda thread: stamp
    verdict, _gate, text = lane.gate_verdict(REPO, NUMBER, HEAD, BASE)
    print(
        f"--- {name}\nlane verdict: {verdict}"
        + (f"\n{text}" if text and verdict != "PASS" else "")
    )
    print()


EXPECT3 = {KEY: "T1", "voters:T1": 3}
BOTH = {**EXPECT3, f"{VOTE}:2": "T2", f"{VOTE}:3": "T3"}
PASS = reply("PASS")
scenario("primary done PASS, voters 2 and 3 not launched yet", EXPECT3, {"T1": PASS})
scenario(
    "primary done, voter 2 launched, voter 3 not",
    {**EXPECT3, f"{VOTE}:2": "T2"},
    {"T1": PASS, "T2": PASS},
)
scenario(
    "all launched, voter 3 still running",
    BOTH,
    {"T1": PASS, "T2": PASS},
    running={"T3"},
)
scenario("all three PASS", BOTH, {"T1": PASS, "T2": PASS, "T3": PASS})
scenario(
    "one voter dead (no reply): merge of two",
    BOTH,
    {
        "T1": reply("FAIL", findings=[("major", "a.py", 10)]),
        "T2": reply("FAIL", findings=[("major", "a.py", 12)]),
        "T3": "",
    },
)
scenario(
    "two voters dead: FAIL, not the primary alone",
    BOTH,
    {"T1": PASS, "T2": "", "T3": ""},
)
scenario(
    "one voter CHECK FAIL",
    BOTH,
    {"T1": PASS, "T2": reply("PASS", check="FAIL"), "T3": PASS},
)
scenario(
    "control arm: no voters recorded, primary alone as today", {KEY: "T1"}, {"T1": PASS}
)
FAIL_A = reply("FAIL", findings=[("major", "a.py", 10)])
FAIL_B = reply("FAIL", findings=[("major", "a.py", 12)])
VOTER2_ONLY = {**EXPECT3, f"{VOTE}:2": "T2"}
scenario("primary done 1 h ago, voter 3 never launched: still waiting", VOTER2_ONLY, {"T1": FAIL_A, "T2": FAIL_B}, replied_hours_ago=1)
scenario("primary done 3 h ago, voter 3 never launched: merge of 2", VOTER2_ONLY, {"T1": FAIL_A, "T2": FAIL_B}, replied_hours_ago=3)
scenario("primary done 3 h ago, neither voter launched: FAIL, not the primary alone", EXPECT3, {"T1": PASS}, replied_hours_ago=3)
