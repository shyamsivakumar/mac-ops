#!/bin/bash
ROOT=$1
W=$(mktemp -d)
export COORDQ_DIR=$W/q COORD_JOURNAL_DIR=$W/j T3_STATE_DB=$W/t3.sqlite COORDQ_T3MCP=$W/t3mcp HOME=$W/home
mkdir -p "$COORDQ_DIR" "$COORD_JOURNAL_DIR" "$HOME"
echo '{"cap": 6, "spendCapTokens": 1000, "stallMinutes": 30}' >"$COORDQ_DIR"/config.json
echo '{"message":{"role":"assistant","usage":{"input":5000,"output":0}}}' >"$W"/over.jsonl
echo '{"message":{"role":"assistant","usage":{"input":10,"output":0}}}' >"$W"/under.jsonl
echo '{"message":{"role":"assistant","usage":{"input":10,"output":0}}}' >"$W"/stalled.jsonl
cat >"$W"/setup.py <<PY
import sqlite3, json
c = sqlite3.connect("$W/t3.sqlite")
c.execute("create table orchestration_v2_projection_provider_threads(thread_id text, driver text, payload_json text)")
for t in ("over", "under", "stalled"):
    c.execute("insert into orchestration_v2_projection_provider_threads values(?,?,?)",
              ("th-" + t, "pi", json.dumps({"nativeThreadRef": {"nativeId": "$W/" + t + ".jsonl"}})))
c.commit()
json.dump({"ticket:o/r#1:a1": "th-over", "ticket:o/r#2:a1": "th-under", "ticket:o/r#3:a1": "th-stalled"},
          open("$COORDQ_DIR/dispatch-receipts.json", "w"))
PY
python3 "$W"/setup.py
cat >"$W"/t3mcp <<'SH'
#!/usr/bin/env python3
import sys, json, datetime
tool = sys.argv[2]
args = json.loads(sys.stdin.read() or "{}")
open(__file__ + ".calls", "a").write(tool + " " + json.dumps(args) + "\n")
now = datetime.datetime.now(datetime.timezone.utc)
iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S.000Z")
if tool == "t3_thread_list":
    import os
    if args.get("cursor") == 1:
        if os.path.exists(os.path.dirname(__file__) + "/fail2"):
            print("page 2 unreadable", file=sys.stderr)
            sys.exit(1)
        print(json.dumps({"threads": [{"threadId": "th-over", "updatedAt": iso(now)}], "total": 3}))
    else:
        rows = [{"threadId": "th-under", "updatedAt": iso(now)},
                {"threadId": "th-stalled", "updatedAt": iso(now - datetime.timedelta(hours=2))}]
        print(json.dumps({"threads": rows, "nextCursor": 1, "total": 3}))
else:
    print("{}")
SH
chmod +x "$W"/t3mcp
echo "--- page 2 unreadable: nothing stopped"
touch "$W"/fail2
python3 "$ROOT"/coordinator/bin/coordq spend 2>&1
echo "exit $?"
echo "interrupt count: $(grep -c interrupt "$W"/t3mcp.calls)"
rm "$W"/fail2
echo "--- spend run (over-cap card on page 2)"
python3 "$ROOT"/coordinator/bin/coordq spend 2>&1
echo "exit $?"
echo "--- interrupt calls"
grep interrupt "$W"/t3mcp.calls
echo "--- second run, interrupt count"
python3 "$ROOT"/coordinator/bin/coordq spend 2>&1
grep -c interrupt "$W"/t3mcp.calls
echo "--- status stuck"
python3 "$ROOT"/coordinator/bin/coordq status 2>&1 | python3 -c "import sys,json;print(json.load(sys.stdin)['stuck'])" 2>&1 | tail -3
