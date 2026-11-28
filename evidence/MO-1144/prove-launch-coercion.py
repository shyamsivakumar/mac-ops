import importlib.machinery
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
scratch = Path(tempfile.mkdtemp())
fake = scratch / "t3mcp"
fake.write_text('''#!/usr/bin/env python3
import json, sys
if sys.argv[1] == "schema":
    sys.exit(1)
args = json.load(sys.stdin)
strategy = args.get("workspaceStrategy")
if "prompt" in args:
    print('Unknown argument "prompt". Accepted arguments: environmentId, projectId, scratch, title, message', file=sys.stderr)
    sys.exit(1)
if strategy is not None and not isinstance(strategy, dict):
    print('Expected { type: "root" } | { type: "existing_worktree" } | { type: "worktree" }', file=sys.stderr)
    sys.exit(1)
print(json.dumps({"thread": {"threadId": "t-1"}, "echo": args}))
''')
fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
os.environ.update({"COORDQ_DIR": str(scratch), "COORD_JOURNAL_DIR": str(scratch), "COORDQ_T3MCP": str(fake)})
(scratch / "config.json").write_text('{"cap": 1}')
sys.path.insert(0, str(root / "coordinator" / "overnight"))
coordq = importlib.machinery.SourceFileLoader("coordq_proof", str(root / "coordinator" / "bin" / "coordq")).load_module()
coordq.with_model = lambda args: (args, None)

cases = {
    "prompt and string root": {"taskType": "chore", "projectId": "p", "title": "t", "prompt": "brief", "workspaceStrategy": "root"},
    "string worktree": {"taskType": "chore", "projectId": "p", "title": "t", "message": "brief", "workspaceStrategy": "worktree"},
    "object strategy kept": {"taskType": "chore", "projectId": "p", "title": "t", "message": "brief", "workspaceStrategy": {"type": "root"}},
}
failed = False
for name, args in cases.items():
    code, out = coordq.call("t3_thread_launch", args, "rules")
    sent = json.loads(out)["echo"] if code == 0 else None
    print(f"{name}: exit {code} {'sent ' + json.dumps({k: sent[k] for k in ('workspaceStrategy',)} | {'has_message': 'message' in sent, 'has_prompt': 'prompt' in sent}) if sent else out}")
    failed |= code != 0
print((scratch / "dispatch.log").read_text() if (scratch / "dispatch.log").exists() else "no coercion logged")
sys.exit(1 if failed else 0)
