#!/usr/bin/env python3
"""Install the mac-ops deny rules (#530) into each tool's enforcement point.

One deny list, one source: runtime/agents/deny-rules.json. It is installed as:

- Claude Code (~/.claude/settings.json): permissions.deny entries generated
  from the list, plus a PreToolUse hook (deny-merge-guard.py) for the push and
  merge rules permissions.deny cannot express.
- Each pi instance directory: extensions/deny-guard.ts with the list embedded.
  It runs the same hook file for shell commands.
- The scope files agents read: the list as prose.

The list only denies. A reinstall snapshots every file it can touch before it
changes anything, and any failure puts the snapshot back, so a failed
reinstall never leaves fewer protections than the install it replaced.
Uninstall removes what install added and restores what install replaced.
"""

from __future__ import annotations

import argparse
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
GUARD_MARKER = "/*__MAC_OPS_DENY_SPEC__*/{}"
OWNER = "mac-ops/deny-rules.v1"
BEGIN = "<!-- BEGIN mac-ops deny-rules -->"
END = "<!-- mac-ops deny-rules END -->"


def expand(p: str, root: Path) -> str:
    return str(root) + p[1:] if p.startswith("~") else p


def derive_text_re(path_re: str) -> str:
    """The path regex with each `$` anchor widened to end, whitespace, quote or separator."""
    return re.sub(r"(?<!\\)\$", lambda _m: "(?=$|[\\s'\";|)&])", path_re)


def ascend_text_res(roots: list[str], home: str) -> list[str]:
    """One regex per Ascend root matching the absolute path, ~/..., $HOME/... and ${HOME}/...."""
    out = []
    for root in roots:
        prefixes = {re.escape(root)}
        if root.startswith(home + "/"):
            rest = re.escape(root[len(home) :])
            prefixes |= {"~" + rest, "\\$HOME" + rest, "\\$\\{HOME\\}" + rest}
        out.append("(?:" + "|".join(sorted(prefixes)) + ")(?![\\w-])")
    return out


def claude_deny(spec: dict, root: Path) -> list[str]:
    tools = ("Read", "Edit")
    entries = []
    for p in spec["ascend_roots"] + spec["secret_dirs"]:
        for form in (p, "/" + expand(p, root)):
            entries += [f"{tool}({form}/**)" for tool in tools]
    for glob in spec["secret_globs"]:
        entries += [f"{tool}({glob})" for tool in tools]
    for p in spec["ascend_roots"]:
        for form in (p, "$HOME" + p[1:]):
            entries += [
                f"Bash({command} {form}:*)" for command in spec["ascend_read_commands"]
            ]
    entries += [f"Bash(git push {flag}:*)" for flag in spec["push_force_flags"]]
    entries += [
        f"Bash(git push origin {branch}:*)" for branch in spec["push_protected"]
    ]
    return entries


def render_guard(spec: dict, root: Path) -> str:
    template = GUARD_TEMPLATE.read_text()
    if template.count(GUARD_MARKER) != 1:
        raise RuntimeError(
            "deny-guard.ts must contain the spec marker exactly once: " + GUARD_MARKER
        )
    roots = [expand(p, root) for p in spec["ascend_roots"]]
    embedded = {
        "ascend_roots": roots,
        "ascend_text_res": ascend_text_res(roots, str(root)),
        "secret_file_re": spec["secret_file_re"],
        "secret_text_re": derive_text_re(spec["secret_file_re"]),
        "ascend_bash_reason": spec["ascend_bash_reason"],
        "secret_bash_reason": spec["secret_bash_reason"],
        "hook_path": expand(spec["claude_code"]["hook"]["target"], root),
    }
    return template.replace(GUARD_MARKER, json.dumps(embedded, indent=2))


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".mac-ops-deny-" + str(os.getpid()))
    tmp.write_text(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(data, dict):
        raise TypeError(f"{path} is not a JSON object; refusing to edit it")
    return data


def write_json(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, indent=2) + "\n")


def split_section(text: str) -> tuple[str, str]:
    head = text.split(BEGIN, 1)[0].rstrip("\n")
    tail = text.split(END, 1)[1].lstrip("\n") if END in text else ""
    return head, tail


class Installer:
    def __init__(self, root: Path):
        self.root = root
        self.state = root / ".local/state/mac-ops"
        self.receipt = self.state / "deny-rules-receipt.json"
        self.backups = self.state / "deny-rules-backups"
        self.prior = self.backups

    def settings(self) -> Path:
        return self.root / ".claude/settings.json"

    def t3_settings(self, spec: dict) -> Path:
        return Path(expand(spec["t3_gate_instance"]["settings"], self.root))

    def hook_target(self, spec: dict) -> Path:
        return Path(expand(spec["claude_code"]["hook"]["target"], self.root))

    def guard_targets(self, spec: dict) -> list[Path]:
        return [
            Path(expand(p, self.root)) / "extensions/deny-guard.ts"
            for p in spec["pi_instances"]
        ]

    def scope_paths(self, spec: dict) -> list[Path]:
        files = spec["scope_files"]
        return [Path(expand(p, self.root)) for p in files["copies"] + [files["claude"]]]

    def managed_paths(self, spec: dict) -> list[Path]:
        return [
            self.settings(),
            self.t3_settings(spec),
            self.hook_target(spec),
            self.receipt,
            *self.guard_targets(spec),
            *self.scope_paths(spec),
        ]

    def copy_aside(self, path: Path, folder: Path) -> Path | None:
        if not (path.exists() or path.is_symlink()):
            return None
        target = folder / path.relative_to(self.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target, follow_symlinks=False)
        return target

    def snapshot(self, spec: dict, folder: Path) -> dict[Path, Path | None]:
        return {
            path: self.copy_aside(path, folder) for path in self.managed_paths(spec)
        }

    def restore(self, snapshot: dict[Path, Path | None]) -> None:
        for path, saved in snapshot.items():
            if saved is None:
                path.unlink(missing_ok=True)
            else:
                path.unlink(missing_ok=True)
                shutil.copy2(saved, path, follow_symlinks=False)

    def write_scope_section(self, path: Path, spec: dict) -> str:
        if path.is_symlink():
            return "skipped (symlink; covered by the repo file)"
        text = path.read_text() if path.exists() else ""
        head, tail = split_section(text) if BEGIN in text else (text.rstrip("\n"), "")
        section = (
            BEGIN
            + "\n"
            + "\n".join(spec["scope_section"]).rstrip("\n")
            + "\n"
            + END
            + "\n"
        )
        atomic_write(path, (head + "\n\n" if head else "") + section + tail)
        return "installed"

    def remove_scope_section(self, path: Path) -> str:
        if (
            not path.exists()
            or path.is_symlink()
            or BEGIN not in (text := path.read_text())
        ):
            return "absent"
        head, tail = split_section(text)
        updated = (head + "\n" if head else "") + tail
        if updated.strip():
            atomic_write(path, updated)
        else:
            path.unlink()
        return "removed"

    def hook_command(self, spec: dict) -> str:
        return f"python3 {self.hook_target(spec)}"

    def merge_claude(self, spec: dict) -> tuple[list[str], bool]:
        settings = load_json(self.settings())
        permissions = dict(settings.get("permissions") or {})
        deny = list(permissions.get("deny") or [])
        added = [
            entry
            for entry in dict.fromkeys(claude_deny(spec, self.root))
            if entry not in deny
        ]
        permissions["deny"] = deny + added
        settings["permissions"] = permissions
        hooks = dict(settings.get("hooks") or {})
        pre = list(hooks.get("PreToolUse") or [])
        command = self.hook_command(spec)
        registered = any(
            h.get("command") == command
            for entry in pre
            for h in entry.get("hooks") or []
        )
        if not registered:
            matcher = spec["claude_code"]["hook"]["matcher"]
            pre.append(
                {
                    "matcher": matcher,
                    "hooks": [{"type": "command", "command": command, "timeout": 10}],
                }
            )
        hooks["PreToolUse"] = pre
        settings["hooks"] = hooks
        write_json(self.settings(), settings)
        return added, not registered

    def unmerge_claude(self, saved: dict, spec: dict) -> str:
        settings = load_json(self.settings())
        permissions = settings.get("permissions") or {}
        managed = saved.get("managed_deny") or []
        if "deny" in permissions:
            permissions["deny"] = [e for e in permissions["deny"] if e not in managed]
        command = self.hook_command(spec)
        hooks = settings.get("hooks") or {}
        if saved.get("hook_registered") and "PreToolUse" in hooks:
            pre = []
            for entry in hooks["PreToolUse"]:
                inner = [
                    h for h in entry.get("hooks") or [] if h.get("command") != command
                ]
                if inner or not entry.get("hooks"):
                    pre.append(
                        dict(entry, hooks=inner) if entry.get("hooks") else entry
                    )
            hooks["PreToolUse"] = pre
        write_json(self.settings(), settings)
        return "cleaned"

    def merge_t3_gate(self, spec: dict, enabled: bool | None) -> dict | None:
        conf = spec["t3_gate_instance"]
        settings = load_json(self.t3_settings(spec))
        instances = dict(settings.get("providerInstances") or {})
        prior = instances.get(conf["instanceId"])
        base = prior or {}
        role = {
            "name": conf["env"]["name"],
            "value": conf["env"]["value"],
            "sensitive": False,
        }
        others = [
            e for e in base.get("environment") or [] if e.get("name") != role["name"]
        ]
        instances[conf["instanceId"]] = {
            **base,
            "driver": base.get("driver", conf["driver"]),
            "displayName": base.get("displayName", conf["displayName"]),
            "enabled": base.get("enabled", True) if enabled is None else enabled,
            "environment": others + [role],
        }
        settings["providerInstances"] = instances
        write_json(self.t3_settings(spec), settings)
        return prior

    def unmerge_t3_gate(self, spec: dict, saved: dict) -> str:
        settings = load_json(self.t3_settings(spec))
        instances = settings.get("providerInstances") or {}
        instance_id = spec["t3_gate_instance"]["instanceId"]
        if instance_id not in instances:
            return "absent"
        prior = saved.get("t3_prior")
        if prior is not None:
            instances[instance_id] = prior
        else:
            del instances[instance_id]
        if not instances:
            settings.pop("providerInstances", None)
        write_json(self.t3_settings(spec), settings)
        return "restored" if prior is not None else "removed"

    def install(self, spec: dict) -> dict:
        repo_scope = ROOT_REPO / spec["scope_files"]["repo"]
        if "\n".join(spec["scope_section"]) not in repo_scope.read_text():
            raise RuntimeError(
                f"{spec['scope_files']['repo']} must contain the scope section from deny-rules.json"
            )
        saved = load_json(self.receipt)
        if saved and saved.get("owner") != OWNER:
            raise RuntimeError("Unrecognized deny-rules receipt; refusing to overwrite")
        stamp = str(time.time_ns())
        snapshot = self.snapshot(spec, self.backups / stamp / "snapshot")
        self.prior = self.backups / stamp / "prior"
        gate_id = spec["t3_gate_instance"]["instanceId"]
        instances = load_json(self.t3_settings(spec)).get("providerInstances") or {}
        enabled = instances.get(gate_id, {}).get("enabled") if saved else None
        try:
            if saved:
                self.uninstall(spec)
            return self.apply(spec, enabled)
        except BaseException:
            self.restore(snapshot)
            raise

    def claim(self, path: Path, prior_files: dict) -> None:
        saved = self.copy_aside(path, self.prior)
        prior_files[str(path)] = str(saved) if saved else None

    def apply(self, spec: dict, enabled: bool | None) -> dict:
        prior_files: dict = {}
        added, registered = self.merge_claude(spec)
        actions = [
            f"claude settings: +{len(added)} deny entries",
            f"claude hook: registered={registered}",
        ]
        hook = self.hook_target(spec)
        self.claim(hook, prior_files)
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.unlink(missing_ok=True)
        source = ROOT_REPO / spec["claude_code"]["hook"]["source"]
        shutil.copyfile(source, hook)
        os.chmod(hook, os.stat(source).st_mode | stat.S_IXUSR)
        t3_prior = self.merge_t3_gate(spec, enabled)
        guard = render_guard(spec, self.root)
        for target in self.guard_targets(spec):
            self.claim(target, prior_files)
            atomic_write(target, guard)
            actions.append(f"pi guard: {target}")
        for path in self.scope_paths(spec):
            actions.append(f"scope {path}: " + self.write_scope_section(path, spec))
        write_json(
            self.receipt,
            {
                "owner": OWNER,
                "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "backups": str(self.prior),
                "managed_deny": added,
                "hook_registered": registered,
                "prior_files": prior_files,
                "t3_touched": True,
                "t3_prior": t3_prior,
            },
        )
        return {"owner": OWNER, "actions": actions, "backups": str(self.prior)}

    def uninstall(self, spec: dict) -> dict:
        saved = load_json(self.receipt)
        if not saved:
            return {"installed": False}
        if saved.get("owner") != OWNER:
            raise RuntimeError(
                "Unrecognized deny-rules receipt; refusing to touch anything"
            )
        actions = ["claude settings: " + self.unmerge_claude(saved, spec)]
        actions.append("t3 gate instance: " + self.unmerge_t3_gate(spec, saved))
        for target, backup in saved["prior_files"].items():
            Path(target).unlink(missing_ok=True)
            if backup:
                shutil.copy2(backup, target, follow_symlinks=False)
                actions.append(f"restored {target}")
        for path in self.scope_paths(spec):
            actions.append(f"scope {path}: " + self.remove_scope_section(path))
        self.receipt.unlink()
        return {"uninstalled": True, "actions": actions}

    def status(self, spec: dict) -> dict:
        deny = (load_json(self.settings()).get("permissions") or {}).get("deny") or []
        guard = render_guard(spec, self.root)
        instances = load_json(self.t3_settings(spec)).get("providerInstances") or {}
        return {
            "installed": bool(load_json(self.receipt)),
            "claude_deny_missing": [
                e for e in claude_deny(spec, self.root) if e not in deny
            ],
            "merge_hook_file": self.hook_target(spec).is_file(),
            "t3_gate_instance": spec["t3_gate_instance"]["instanceId"] in instances,
            "pi_guards": {
                str(t): (
                    "installed"
                    if t.is_file() and t.read_text() == guard
                    else "stale"
                    if t.exists()
                    else "missing"
                )
                for t in self.guard_targets(spec)
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "status", "uninstall"])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home(),
        help="home root the agent and Claude directories live under",
    )
    args = parser.parse_args()
    spec = json.loads(SPEC_PATH.read_text())
    installer = Installer(args.root.expanduser().resolve())
    print(json.dumps(getattr(installer, args.action)(spec), indent=2))


if __name__ == "__main__":
    main()
