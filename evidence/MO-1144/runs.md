# MO-1144 runs

## Ticket proof command

```
D=$(mktemp -d); COORDQ_DIR=$D COORD_JOURNAL_DIR=$D python3 -c "import importlib.machinery as m;c=m.SourceFileLoader('c','coordinator/bin/coordq').load_module();a=c.coerce_launch_args('t3_thread_launch',{'workspaceStrategy':'root','prompt':'b'});assert a=={'workspaceStrategy':{'type':'root'},'message':'b'},a"
```

Before (origin/main ed088e4f):
```
AttributeError: module 'c' has no attribute 'coerce_launch_args'
exit 
```
After (head):
```
exit 0
```

## Fake t3mcp (rejects `prompt` and a string strategy), `python3 evidence/MO-1144/prove-launch-coercion.py [checkout]`

Before (origin/main):
```
prompt and string root: exit 1 Unknown argument "prompt". Accepted arguments: environmentId, projectId, scratch, title, message
string worktree: exit 1 Expected { type: "root" } | { type: "existing_worktree" } | { type: "worktree" }
object strategy kept: exit 0 sent {"workspaceStrategy": {"type": "root"}, "has_message": true, "has_prompt": false}
no coercion logged
```
After (head):
```
prompt and string root: exit 0 sent {"workspaceStrategy": {"type": "root"}, "has_message": true, "has_prompt": false}
string worktree: exit 0 sent {"workspaceStrategy": {"type": "worktree", "baseRef": "origin/main", "startFromOrigin": true}, "has_message": true, "has_prompt": false}
object strategy kept: exit 0 sent {"workspaceStrategy": {"type": "root"}, "has_message": true, "has_prompt": false}
2026-11-27 21:24:46 t3_thread_launch workspaceStrategy string coerced to an object
2026-11-27 21:24:46 t3_thread_launch prompt renamed to message
2026-11-27 21:24:47 t3_thread_launch workspaceStrategy string coerced to an object

```
