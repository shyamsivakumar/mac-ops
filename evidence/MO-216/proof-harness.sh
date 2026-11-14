#!/bin/sh
# MO-216 proof harness: a dry shift whose fixture carries a fake key in a
# thread report and in a pull request title. Read only outside the fixture
# root: the board, the queue and the threads are all stubbed.
set -u
REPO="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
FIX="$WORK/overnight"
KEY="ghp_EXAMPLEEXAMPLEEXAMPLEEXAMPLE"
mkdir -p "$WORK/bin" "$FIX/queue"

cat > "$WORK/bin/ticket" <<'STUBEOF'
#!/bin/sh
cat <<'JSON'
{"issues":[{"repo":"shyamsivakumar/mac-ops","key":"MO-999","number":999,
"title":"Fixture ticket for the redaction proof",
"url":"https://github.com/shyamsivakumar/mac-ops/issues/999",
"stage":"todo","priority":3,"type":"standard","builder":"opus","reviewer":"opus",
"problems":[],"updatedAt":"2026-11-14T00:00:00Z"}]}
JSON
STUBEOF

cat > "$WORK/bin/gh" <<'STUBEOF'
#!/bin/sh
case "$1 $2" in
  "pr list")
    cat <<'JSON'
[{"number":123,"title":"Fixture pull request GITHUB_TOKEN=ghp_EXAMPLEEXAMPLEEXAMPLEEXAMPLE",
"url":"https://github.com/shyamsivakumar/mac-ops/pull/123","isDraft":false,
"headRefName":"t/mo216-fixture","baseRefName":"main","headRefOid":"deadbeef",
"updatedAt":"2026-11-14T00:00:00Z","body":"Refs #999"}]
JSON
    ;;
  "issue list")
    echo '[{"number":999,"title":"Fixture ticket for the redaction proof","body":"A ticket body with no secret in it."}]'
    ;;
  "pr checks")
    echo '[{"name":"agent-check","state":"SUCCESS","bucket":"pass"}]'
    ;;
  "pr view")
    echo '{"files":[{"path":"README.md"}],"mergedAt":null}'
    ;;
  *)
    echo '{}'
    ;;
esac
STUBEOF

cat > "$WORK/bin/t3mcp" <<'STUBEOF'
#!/bin/sh
# A stub t3mcp. The gate thread's report carries a fake key; the builder
# thread says something else, so the shift sends the findings on.
payload="$3"
case "$payload" in
  *t-mo216-gate*)
    cat <<'JSON'
{"thread":{"threadId":"t-mo216-gate","createdAt":"2026-11-14T11:00:00Z","updatedAt":"2026-11-14T12:00:00Z","status":"completed"},
"items":[{"type":"assistant_message","text":"The gate found one defect.\n\nThe builder printed GITHUB_TOKEN=ghp_EXAMPLEEXAMPLEEXAMPLEEXAMPLE while it worked.\n\nVERDICT: FAIL"}]}
JSON
    ;;
  *t-mo216-builder*)
    cat <<'JSON'
{"thread":{"threadId":"t-mo216-builder","createdAt":"2026-11-14T10:00:00Z","updatedAt":"2026-11-14T11:30:00Z","status":"completed"},
"items":[{"type":"assistant_message","text":"I am still working on the ticket."}]}
JSON
    ;;
  *)
    echo '{"threads":[]}'
    ;;
esac
STUBEOF

chmod +x "$WORK/bin/ticket" "$WORK/bin/gh" "$WORK/bin/t3mcp"

cat > "$FIX/queue/config.json" <<'JSON'
{"slotCap": 6}
JSON
cat > "$FIX/queue/queue.json" <<'JSON'
{"gatedHeads": {}, "items": []}
JSON
cat > "$FIX/queue/dispatch-receipts.json" <<'JSON'
{"gate:shyamsivakumar/mac-ops#123:deadbeef": "t-mo216-gate",
 "ticket:shyamsivakumar/mac-ops#999:a1": "t-mo216-builder"}
JSON

export OVERNIGHT_TICKET="$WORK/bin/ticket"
export OVERNIGHT_GH="$WORK/bin/gh"
export OVERNIGHT_T3MCP="$WORK/bin/t3mcp"
export COORDQ_DIR="$FIX/queue"

echo "### 1. the old module (origin/main) prints the key to the console"
git -C "$REPO" show origin/main:coordinator/overnight/overnight > "$WORK/overnight-old"
python3 "$WORK/overnight-old" board --json > "$WORK/board-old.json" 2>"$WORK/board-old.err"
echo "old: the fake key in the console output: $(grep -c "$KEY" "$WORK/board-old.json")"

echo "### 2. the new module prints the same board"
python3 "$REPO/coordinator/overnight/overnight" board --json > "$WORK/board-new.json" 2>"$WORK/board-new.err"
echo "new: the fake key in the console output: $(grep -c "$KEY" "$WORK/board-new.json")"
echo "new: redactions in the console output: $(grep -c 'REDACTED' "$WORK/board-new.json")"

echo "### 3. a dry shift with the fake key in the thread report"
python3 "$REPO/coordinator/overnight/overnight" policy --root "$FIX" > "$WORK/policy.log" 2>&1
python3 "$REPO/coordinator/overnight/overnight" shift --root "$FIX" > "$WORK/shift.log" 2>"$WORK/shift.err"
echo "shift exit: $?"

echo "### 4. the morning report"
python3 "$REPO/coordinator/overnight/overnight" report --root "$FIX" --date 2026-11-14 > "$WORK/report.log" 2>&1
echo "report exit: $?"

echo "### 5. the grep"
echo "the records under the fixture root:"
find "$FIX" -type f | sed "s|$FIX|<root>|" | sort
echo "the fake key under .overnight:"
grep -r "$KEY" "$FIX"; echo "grep exit=$? (1 means no match)"
echo "the fake key in the shift's own console output: $(grep -c "$KEY" "$WORK/shift.log")"
echo "redactions in the shift's own console output: $(grep -c 'REDACTED' "$WORK/shift.log")"
echo "the receipt the shift wrote:"
cat "$FIX/receipts/MO-999.md" 2>/dev/null
echo "WORK=$WORK"
