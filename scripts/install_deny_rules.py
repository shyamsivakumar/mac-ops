#!/usr/bin/env python3
"""Install the mac-ops deny rules (#530) into each tool's enforcement point.

One deny list, one source: runtime/agents/deny-rules.json. This script
installs it where each tool actually checks tools:

- Claude Code (~/.claude/settings.json, read by the T3 claudeAgent driver
  and Claude Code tabs): permissions.deny entries, plus a PreToolUse hook
  for the one rule permissions.deny cannot express (gh pr merge without
  --match-head-commit; gate threads keep the pinned merge).
- Each pi instance directory (~/.pi/agent, -minimax, -glm, -deepseek,
  -openai-api, -anthropic-api): extensions/deny-guard.ts with the list
  embedded, auto-discovered by pi on startup.
- The scope files the agents read get the same list as prose: the repo
  runtime/pi/AGENTS.md (this must already contain it; the installer
  refuses otherwise), the two unlinked AGENTS.md copies, and
  ~/.claude/CLAUDE.md.

The list only denies; nothing here allows anything. Every file edited is
backed up first to ~/.local/state/mac-ops/deny-rules-backups/<timestamp>/.
Uninstall removes exactly what install added and puts back what it replaced:
the receipt records which deny entries and which hook registration install
added, the backup of every file it overwrote, and the prior gate instance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import time
from pathlib import Path

ROOT_REPO = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT_REPO / "runtime/agents/deny-rules.json"
GUARD_TEMPLATE = ROOT_REPO / "runtime/agents/deny-guard.ts"
MERGE_HOOK_SOURCE = ROOT_REPO / "runtime/agents/deny-merge-guard.py"
GUARD_MARKER = "/*__MAC_OPS_DENY_SPEC__*/{}"
OWNER = "mac-ops/deny-rules.v1"
BEGIN = "<!-- BEGIN mac-ops deny-rules -->"
END = "<!-- mac-ops deny-rules END -->"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expand(p: str, root: Path) -> str:
    s = str(p)
    if s == "~":
        return str(root)
    if s.startswith("~/"):
        s = str(root) + s[1:]
    return os.path.expanduser(s)


def derive_text_re(path_re: str) -> str:
    """The path regex anchored with `$`; the command-text form uses a boundary.

    Every `$` in the path form is an anchor (the pattern never matches a
    literal dollar), so each one widens into a lookahead for end, whitespace,
    a quote or a shell separator.
    """
    boundary = "(?=$|[\\s'\";|)&])"
    return re.sub(r"(?<!\\)\$", lambda _m: boundary, path_re)


def ascend_text_res(roots: list[str], home: str) -> list[str]:
    """One regex per Ascend root matching every spelling an agent might type:
    the absolute path, ~/..., $HOME/... and ${HOME}/...."""
    out = []
    for root in roots:
        prefixes = {re.escape(root)}
        if root.startswith(home + "/"):
            rest = re.escape(root[len(home):])
            prefixes |= {
                "~" + rest,
                "\\$HOME" + rest,
                "\\$\\{HOME\\}" + rest,
            }
        out.append("(?:" + "|".join(sorted(prefixes)) + ")(?![\\w-])")
    return out


def build_pi_spec(spec: dict, root: Path) -> dict:
    roots = [expand(p, root) for p in spec["ascend_roots"]]
    return {
        "owner": spec["owner"],
        "issue": spec["issue"],
        "ascend_roots": roots,
        "ascend_text_res": ascend_text_res(roots, str(root)),
        "secret_file_re": spec["secret_file_re"],
        "secret_text_re": derive_text_re(spec["secret_file_re"]),
        "push_deny": spec["push_deny"],
        "merge_deny": spec["merge_deny"],
        "ascend_bash_reason": spec["ascend_bash_reason"],
        "secret_bash_reason": spec["secret_bash_reason"],
    }


def render_guard(spec: dict, root: Path) -> str:
    template = GUARD_TEMPLATE.read_text()
    if template.count(GUARD_MARKER) != 1:
        raise RuntimeError(
            "deny-guard.ts must contain the spec marker exactly once: " + GUARD_MARKER
        )
    embedded = json.dumps(build_pi_spec(spec, root), indent=2)
    return template.replace(GUARD_MARKER, embedded)


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".mac-ops-deny-" + str(os.getpid()))
    tmp.write_text(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


class Installer:
    def __init__(self, root: Path):
        self.root = root
        self.state = root / ".local/state/mac-ops"
        self.receipt = self.state / "deny-rules-receipt.json"
        self.backups: Path | None = None

    def backup(self, path: Path) -> None:
        if not path.exists() and not path.is_symlink():
            return
        assert self.backups is not None
        target = self.backups / path.relative_to(self.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return
        if path.is_symlink() or path.is_file():
            shutil.copy2(path, target, follow_symlinks=False)
        else:
            shutil.copytree(path, target)

    def scope_text(self, spec: dict) -> str:
        return "\n".join(spec["scope_section"])

    def managed_section(self, spec: dict) -> str:
        return BEGIN + "\n" + self.scope_text(spec).rstrip("\n") + "\n" + END + "\n"

    def write_scope_section(self, path: Path, spec: dict) -> str:
        if path.is_symlink():
            return "skipped (symlink; covered by the repo file)"
        text = path.read_text() if path.exists() else ""
        if BEGIN in text:
            head = text.split(BEGIN, 1)[0].rstrip("\n")
            tail = text.split(END, 1)[1].lstrip("\n") if END in text else ""
        else:
            head = text.rstrip("\n")
            tail = ""
        updated = (head + "\n\n" if head else "") + self.managed_section(spec) + tail
        self.backup(path)
        atomic_write(path, updated)
        return "installed"

    def remove_scope_section(self, path: Path) -> str:
        if not path.exists() or path.is_symlink():
            return "absent"
        text = path.read_text()
        if BEGIN not in text or END not in text:
            return "absent"
        head = text.split(BEGIN, 1)[0].rstrip("\n")
        tail = text.split(END, 1)[1].lstrip("\n") if END in text else ""
        updated = (head + "\n" if head else "") + tail
        self.backup(path)
        if updated.strip():
            atomic_write(path, updated)
        else:
            path.unlink()
        return "removed"

    def claude_settings(self) -> Path:
        return self.root / ".claude/settings.json"

    def hook_command(self, spec: dict) -> str:
        target = expand(spec["claude_code"]["hook"]["target"], self.root)
        return f"python3 {target}"

    def merge_claude(self, spec: dict) -> dict:
        path = self.claude_settings()
        current = load_json(path)
        if not isinstance(current, dict):
            raise RuntimeError(f"{path} is not a JSON object; refusing to edit it")
        self.backup(path)
        settings = dict(current)
        permissions = dict(settings.get("permissions") or {})
        deny = list(permissions.get("deny") or [])
        added = [entry for entry in spec["claude_code"]["deny"] if entry not in deny]
        deny += added
        permissions["deny"] = deny
        settings["permissions"] = permissions

        hooks = dict(settings.get("hooks") or {})
        pre = [dict(entry) for entry in (hooks.get("PreToolUse") or [])]
        command = self.hook_command(spec)
        present = any(
            any(h.get("command") == command for h in entry.get("hooks") or [])
            for entry in pre
        )
        hook_added = False
        if not present:
            pre.append(
                {
                    "matcher": spec["claude_code"]["hook"]["matcher"],
                    "hooks": [{"type": "command", "command": command, "timeout": 10}],
                }
            )
            hook_added = True
        hooks["PreToolUse"] = pre
        settings["hooks"] = hooks
        atomic_write(path, json.dumps(settings, indent=2) + "\n")
        return {"deny_added": added, "hook_registered": hook_added}

    def claim(self, path: Path, prior_files: dict) -> None:
        prior_files[str(path)] = None
        if path.is_file() or path.is_symlink():
            self.backup(path)
            prior_files[str(path)] = str(self.backups / path.relative_to(self.root))

    def unmerge_claude(self, saved: dict, spec: dict) -> dict:
        path = self.claude_settings()
        settings = load_json(path)
        if not isinstance(settings, dict):
            return {"claude_settings": "absent"}
        self.backup(path)
        changed = False
        managed = saved.get("managed_deny") or []
        permissions = settings.get("permissions")
        if isinstance(permissions, dict) and isinstance(permissions.get("deny"), list):
            kept = [e for e in permissions["deny"] if e not in managed]
            if kept != permissions["deny"]:
                permissions["deny"] = kept
                changed = True
        command = self.hook_command(spec)
        hooks = settings.get("hooks")
        if (
            saved.get("hook_registered")
            and isinstance(hooks, dict)
            and isinstance(hooks.get("PreToolUse"), list)
        ):
            pre = []
            for entry in hooks["PreToolUse"]:
                inner = [
                    h for h in (entry.get("hooks") or []) if h.get("command") != command
                ]
                if len(inner) != len(entry.get("hooks") or []):
                    changed = True
                    if inner:
                        entry = dict(entry, hooks=inner)
                    else:
                        continue
                pre.append(entry)
            hooks["PreToolUse"] = pre
        if changed:
            atomic_write(path, json.dumps(settings, indent=2) + "\n")
        return {"claude_settings": "cleaned" if changed else "already clean"}

    def t3_settings(self) -> Path:
        return self.root / ".t3/userdata/settings.json"

    def merge_t3_gate(self, spec: dict) -> dict | None:
        conf = spec["t3_gate_instance"]
        path = self.t3_settings()
        current = load_json(path)
        if current and not isinstance(current, dict):
            raise RuntimeError(f"{path} is not a JSON object; refusing to edit it")
        self.backup(path)
        settings = dict(current or {})
        instances = dict(settings.get("providerInstances") or {})
        prior = instances.get(conf["instanceId"])
        instances[conf["instanceId"]] = {
            "driver": conf["driver"],
            "displayName": conf["displayName"],
            "enabled": True,
            "environment": [
                {
                    "name": conf["env"]["name"],
                    "value": conf["env"]["value"],
                    "sensitive": False,
                }
            ],
        }
        settings["providerInstances"] = instances
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, json.dumps(settings, indent=2) + "\n")
        return prior

    def unmerge_t3_gate(self, spec: dict, saved: dict) -> str:
        path = self.t3_settings()
        settings = load_json(path)
        if not isinstance(settings, dict):
            return "absent"
        instances = settings.get("providerInstances")
        if not isinstance(instances, dict):
            return "absent"
        instance_id = spec["t3_gate_instance"]["instanceId"]
        if instance_id not in instances:
            return "absent"
        self.backup(path)
        prior = saved.get("t3_prior")
        if prior is not None:
            instances[instance_id] = prior
        else:
            del instances[instance_id]
        if not instances:
            settings.pop("providerInstances", None)
        atomic_write(path, json.dumps(settings, indent=2) + "\n")
        return "restored" if prior is not None else "removed"

    def install(self, spec: dict) -> dict:
        repo_scope = ROOT_REPO / spec["scope_files"]["repo"]
        if self.scope_text(spec) not in repo_scope.read_text():
            raise RuntimeError(
                f"{spec['scope_files']['repo']} must contain the scope section from "
                "deny-rules.json; update the repo file so prose and enforcement match"
            )
        saved = load_json(self.receipt)
        if saved and saved.get("owner") != OWNER:
            raise RuntimeError("Unrecognized deny-rules receipt; refusing to overwrite")
        if saved:
            self.uninstall(spec, quiet=True)
        self.backups = self.state / "deny-rules-backups" / str(time.time_ns())
        report: dict = {"owner": OWNER, "actions": []}
        prior_files: dict = {}

        merged = self.merge_claude(spec)
        report["actions"].append(f"claude settings: +{len(merged['deny_added'])} deny entries")
        report["actions"].append(
            "claude merge hook: " + ("registered" if merged["hook_registered"] else "already present")
        )
        hook_target = Path(expand(spec["claude_code"]["hook"]["target"], self.root))
        hook_target.parent.mkdir(parents=True, exist_ok=True)
        self.claim(hook_target, prior_files)
        hook_target.unlink(missing_ok=True)
        shutil.copyfile(MERGE_HOOK_SOURCE, hook_target)
        os.chmod(hook_target, os.stat(MERGE_HOOK_SOURCE).st_mode | stat.S_IXUSR)
        report["actions"].append("claude merge hook file installed")
        t3_prior = self.merge_t3_gate(spec)
        report["actions"].append("t3 gate instance: installed")

        guard = render_guard(spec, self.root)
        for entry in spec["pi_instances"]:
            agent_dir = Path(expand(entry, self.root))
            target = agent_dir / "extensions/deny-guard.ts"
            self.claim(target, prior_files)
            atomic_write(target, guard)
            report["actions"].append(f"pi guard: {target}")

        for entry in spec["scope_files"]["copies"]:
            path = Path(expand(entry, self.root))
            report["actions"].append(f"scope {path}: " + self.write_scope_section(path, spec))
        claude_md = Path(expand(spec["scope_files"]["claude"], self.root))
        report["actions"].append(f"scope {claude_md}: " + self.write_scope_section(claude_md, spec))

        receipt = {
            "owner": OWNER,
            "spec_sha256": digest(SPEC_PATH),
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "backups": str(self.backups),
            "managed_deny": merged["deny_added"],
            "hook_registered": merged["hook_registered"],
            "prior_files": prior_files,
            "scope_copies": [expand(e, self.root) for e in spec["scope_files"]["copies"]],
            "scope_claude": str(claude_md),
            "t3_gate_instance": spec["t3_gate_instance"]["instanceId"],
            "t3_prior": t3_prior,
        }
        atomic_write(self.receipt, json.dumps(receipt, indent=2) + "\n")
        report["backups"] = str(self.backups)
        return report

    def uninstall(self, spec: dict, quiet: bool = False) -> dict:
        saved = load_json(self.receipt)
        if not saved:
            if quiet:
                return {"actions": ["nothing installed"]}
            print(json.dumps({"installed": False}))
            return {"installed": False}
        if saved.get("owner") != OWNER:
            raise RuntimeError("Unrecognized deny-rules receipt; refusing to touch anything")
        self.backups = self.state / "deny-rules-backups" / ("uninstall-" + str(time.time_ns()))
        report = {"actions": []}
        report.update(self.unmerge_claude(saved, spec))
        report["actions"].append("t3 gate instance: " + self.unmerge_t3_gate(spec, saved))
        for target, backup in (saved.get("prior_files") or {}).items():
            path = Path(target)
            if path.is_file() or path.is_symlink():
                path.unlink()
                report["actions"].append(f"removed {path}")
            if backup:
                shutil.copy2(backup, path, follow_symlinks=False)
                report["actions"].append(f"restored {path}")
        for scope in (saved.get("scope_copies") or []) + (
            [saved["scope_claude"]] if saved.get("scope_claude") else []
        ):
            report["actions"].append(f"scope {scope}: " + self.remove_scope_section(Path(scope)))
        self.receipt.unlink()
        report["uninstalled"] = True
        if not quiet:
            print(json.dumps(report, indent=2))
        return report

    def status(self, spec: dict) -> dict:
        saved = load_json(self.receipt)
        settings = load_json(self.claude_settings())
        deny = (settings.get("permissions") or {}).get("deny") or []
        missing_deny = [e for e in spec["claude_code"]["deny"] if e not in deny]
        guards = {}
        for entry in spec["pi_instances"]:
            target = Path(expand(entry, self.root)) / "extensions/deny-guard.ts"
            guards[str(target)] = (
                "installed"
                if target.is_file() and self._guard_current(target, spec)
                else ("stale" if target.exists() else "missing")
            )
        hook = Path(expand(spec["claude_code"]["hook"]["target"], self.root))
        t3 = load_json(self.t3_settings())
        t3_instances = t3.get("providerInstances") if isinstance(t3, dict) else None
        gate_instance = spec["t3_gate_instance"]["instanceId"]
        return {
            "installed": bool(saved),
            "spec_sha256": digest(SPEC_PATH),
            "receipt": saved or None,
            "claude_deny_missing": missing_deny,
            "merge_hook_file": hook.is_file(),
            "t3_gate_instance": (
                gate_instance in (t3_instances or {})
            ),
            "pi_guards": guards,
            "backups": saved.get("backups") if saved else None,
        }

    def _guard_current(self, target: Path, spec: dict) -> bool:
        try:
            return target.read_text() == render_guard(spec, self.root)
        except RuntimeError:
            return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "status", "uninstall"])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home(),
        help="home root the agent and Claude directories live under (tests)",
    )
    args = parser.parse_args()
    spec = json.loads(SPEC_PATH.read_text())
    installer = Installer(args.root.expanduser().resolve())
    if args.action == "install":
        print(json.dumps(installer.install(spec), indent=2))
    elif args.action == "uninstall":
        installer.uninstall(spec)
    else:
        print(json.dumps(installer.status(spec), indent=2))


if __name__ == "__main__":
    main()
