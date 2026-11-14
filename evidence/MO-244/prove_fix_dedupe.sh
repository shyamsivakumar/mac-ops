#!/usr/bin/env bash
# Proof for MO-244 (mac-ops #254): coordq fix sends the findings for one head
# only once. The rig is hermetic: a temporary COORDQ_DIR, a temporary HOME, a
# stub t3mcp and a stub gh. The live queue is never read nor written.
#
#   bash evidence/MO-244/prove_fix_dedupe.sh
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="$(mktemp -d)"
QUEUE="$WORK/queue"
REPO="shyamsivakumar/strategy-replay-workbench"
PR=974
ISSUE=251
HEAD_A="1111111111111111111111111111111111111111"
HEAD_B="2222222222222222222222222222222222222222"

mkdir -p "$WORK/bin" "$QUEUE" "$WORK/home"
echo '{"cap": 5}' > "$QUEUE/config.json"

cat > "$WORK/bin/t3mcp" <<'STUB'
#!/usr/bin/env python3
"""Stub of the T3 MCP CLI. The gate thread's last message ends VERDICT: FAIL."""
import json, os, sys
tool = sys.argv[2]
try:
    args = json.loads(sys.stdin.read() or "{}")
except ValueError:
    args = {}
if tool == "t3_thread_list":
    print(json.dumps({"total": 0}))
elif tool == "t3_thread_read":
    print(json.dumps({"thread": {"threadId": args.get("threadId")},
                      "items": [{"type": "assistant_message",
                                 "text": "Findings.\n\n- major: one finding\n\nVERDICT: FAIL"}]}))
else:
    print(json.dumps({"ok": True, "tool": tool}))
STUB

cat > "$WORK/bin/gh" <<'STUB'
#!/usr/bin/env python3
"""Stub of the gh CLI. It serves one open pull request at PROOF_HEAD."""
import json, os, sys
head = os.environ["PROOF_HEAD"]
print(json.dumps({"number": int(os.environ["PROOF_PR"]), "state": "open",
                  "head": {"sha": head}, "body": "Refs #251\n\nBuilder check: PASS " + head}))
STUB
chmod +x "$WORK/bin/t3mcp" "$WORK/bin/gh"

export COORDQ_DIR="$QUEUE"
export COORDQ_T3MCP="$WORK/bin/t3mcp"
export HOME="$WORK/home"
export PROOF_PR="$PR"
export PATH="$WORK/bin:$PATH"

receipts() {
  cat > "$QUEUE/dispatch-receipts.json" <<JSON
{
  "gate:${REPO}#${PR}:$1": "thread-gate-974",
  "ticket:${REPO}#${ISSUE}:a1": "thread-builder-251"
}
JSON
}

items() { python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1]))["items"]))' "$QUEUE/queue.json"; }
fix() { python3 "$ROOT/coordinator/bin/coordq" fix "${REPO}#${PR}"; echo "exit=$?"; }

echo "=== queue items before: 0"
echo
echo "=== first fix on head ${HEAD_A}"
receipts "$HEAD_A"; export PROOF_HEAD="$HEAD_A"
fix
echo "=== queue items after the first fix: $(items)"
echo
echo "=== second fix on head ${HEAD_A}"
fix
echo "=== queue items after the second fix: $(items)"
echo
echo "=== first fix on the new head ${HEAD_B}"
receipts "$HEAD_B"; export PROOF_HEAD="$HEAD_B"
fix
echo "=== queue items after the fix on the new head: $(items)"
echo
echo "=== fixedHeads"
python3 -c 'import json,sys;q=json.load(open(sys.argv[1]));print(json.dumps(q.get("fixedHeads"),indent=1));print("items:",[(i["id"],i["tool"],i["title"]) for i in q["items"]])' "$QUEUE/queue.json"
