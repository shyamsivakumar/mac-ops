## Proof run: red 1dab2c1791f22a41318cf4da3ad78c71945126d6

```sh
python3 -c 'import importlib.machinery, importlib.util, json, sys; from pathlib import Path; sys.path.insert(0, "coordinator/bin"); l = importlib.machinery.SourceFileLoader("ticket_cli", "coordinator/bin/ticket"); s = importlib.util.spec_from_loader("ticket_cli", l); m = importlib.util.module_from_spec(s); l.exec_module(m); cfg = json.loads(Path("coordinator/config/tickets.json").read_text()); t = {"url": "https://example.invalid/1", "reviewerAlias": "astra", "type": "research", "body": "body", "arm": None}; out = m.assemble_brief(cfg, t, "ticket:test:a1", {"comments": []}); assert "/Users/shyamsivakumar/Code/llmwiki/runtime/codex/skills/research/SKILL.md" in out, "missing research skill pointer in type:research brief"'
```

```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
AssertionError: missing research skill pointer in type:research brief

```

{"state": "red", "exit": 1, "matched": true, "ref": "1dab2c1791f22a41318cf4da3ad78c71945126d6"}
## Proof run: green eca45f2d64a45dd5fd3ca0458a93a8127aa4a0b7

```sh
python3 -c 'import importlib.machinery, importlib.util, json, sys; from pathlib import Path; sys.path.insert(0, "coordinator/bin"); l = importlib.machinery.SourceFileLoader("ticket_cli", "coordinator/bin/ticket"); s = importlib.util.spec_from_loader("ticket_cli", l); m = importlib.util.module_from_spec(s); l.exec_module(m); cfg = json.loads(Path("coordinator/config/tickets.json").read_text()); t = {"url": "https://example.invalid/1", "reviewerAlias": "astra", "type": "research", "body": "body", "arm": None}; out = m.assemble_brief(cfg, t, "ticket:test:a1", {"comments": []}); assert "/Users/shyamsivakumar/Code/llmwiki/runtime/codex/skills/research/SKILL.md" in out, "missing research skill pointer in type:research brief"'
```

```

```

{"state": "green", "exit": 0, "matched": null, "ref": "eca45f2d64a45dd5fd3ca0458a93a8127aa4a0b7"}
