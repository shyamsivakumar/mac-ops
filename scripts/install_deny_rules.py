#!/usr/bin/env python3
"""Install the mac-ops deny rules (#530) into each tool's enforcement point.

One deny list, one source: runtime/agents/deny-rules.json. It is installed as:

- Claude Code (~/.claude/settings.json): permissions.deny entries for the
  families that are denied even with approval, permissions.ask entries for the
  families that ask the owner (a settings deny beats a hook, so an ask family
  cannot stay in deny), plus a PreToolUse hook (deny-merge-guard.py) for the
  push, merge, cloud and removal rules permissions cannot express.
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
import time
from pathlib import Path

ROOT_REPO = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT_REPO / "runtime/agents/deny-rules.json"
GUARD_TEMPLATE = ROOT_REPO / "runtime/agents/deny-guard.ts"
GUARD_MARKER = "/*__MAC_OPS_DENY_SPEC__*/{}"
HOOK_CONSTANTS = ("ASCEND_ROOTS", "SECRET_DIRS", "SECRET_FILE_RE", "FAMILY_MODES", "AUDIT_PATH")
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


def family_modes(spec: dict) -> dict[str, str]:
    return {name: family["mode"] for name, family in spec["families"].items()}


def claude_rules(spec: dict, root: Path) -> dict[str, list[str]]:
    """Settings entries by decision. Edits of secret files and force-push flags stay denied.

    The Ascend tree has no settings entries: a settings rule cannot tell an Ascend session
    from any other, so the hook decides it. `retired` lists the entries earlier installs wrote."""
    modes = family_modes(spec)
    rules: dict[str, list[str]] = {"deny": [], "ask": [], "retired": []}

    def add(entry: str, family: str | None) -> None:
        mode = modes[family] if family else "deny"
        rules[mode].append(entry)

    for p in spec["ascend_roots"]:
        for form in (p, "/" + expand(p, root)):
            for tool in ("Read", "Edit"):
                rules["retired"].append(f"{tool}({form}/**)")
    for p in spec["secret_dirs"]:
        for form in (p, "/" + expand(p, root)):
            add(f"Read({form}/**)", "secret_files")
            add(f"Edit({form}/**)", None)
    for glob in spec["secret_globs"]:
        add(f"Read({glob})", "secret_files")
        add(f"Edit({glob})", None)
    for p in spec["ascend_roots"]:
        for form in (p, "$HOME" + p[1:]):
            for command in spec["ascend_read_commands"]:
                rules["retired"].append(f"Bash({command} {form}:*)")
    for flag in spec["push_force_flags"]:
        add(f"Bash(git push {flag}:*)", None)
    for branch in spec["push_protected"]:
        add(f"Bash(git push origin {branch}:*)", "push_protected")
    for family, commands in spec["claude_ask_commands"].items():
        for command in commands:
            add(f"Bash({command}:*)", family)
    return {mode: list(dict.fromkeys(entries)) for mode, entries in rules.items()}


def drop_managed(permissions: dict, saved: dict) -> dict:
    """The permissions with what a previous install added removed and what it moved to ask put back in deny."""
    result = dict(permissions)
    for key, receipt_key in (("deny", "managed_deny"), ("ask", "managed_ask")):
        if key in result:
            owned = saved.get(receipt_key) or []
            result[key] = [e for e in result[key] if e not in owned]
    moved = saved.get("moved_from_deny") or []
    if moved:
        deny = result.get("deny") or []
        result["deny"] = deny + [e for e in moved if e not in deny]
    return result


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
        "family_modes": family_modes(spec),
        "audit_log": expand(spec["audit_log"], root),
        "hook_path": expand(spec["claude_code"]["hook"]["target"], root),
    }
    return template.replace(GUARD_MARKER, json.dumps(embedded, indent=2))


def render_hook(spec: dict, root: Path) -> str:
    text = (ROOT_REPO / spec["claude_code"]["hook"]["source"]).read_text()
    values = {
        "ASCEND_ROOTS": [expand(p, root) for p in spec["ascend_roots"]],
        "SECRET_DIRS": [expand(p, root) for p in spec["secret_dirs"]],
        "SECRET_FILE_RE": spec["secret_file_re"],
        "FAMILY_MODES": family_modes(spec),
        "AUDIT_PATH": expand(spec["audit_log"], root),
    }
    for name in HOOK_CONSTANTS:
        text, count = re.subn(
            rf"^{name} = .*$",
            lambda _m, name=name: f"{name} = {json.dumps(values[name])}",
            text,
            flags=re.M,
        )
        if count != 1:
            raise RuntimeError(f"deny-merge-guard.py must define {name} on one line exactly once")
    return text


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


def check_markers(text: str, path: Path) -> None:
    opening, closing = text.count(BEGIN), text.count(END)
    misordered = opening == closing == 1 and text.index(BEGIN) > text.index(END)
    if opening != closing or opening > 1 or misordered:
        raise RuntimeError(
            f"{path} has unbalanced mac-ops deny-rules markers; fix it by hand, nothing was changed"
        )


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
        check_markers(text, path)
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

    def merge_claude(self, spec: dict) -> dict:
        settings = load_json(self.settings())
        permissions = dict(settings.get("permissions") or {})
        rules = claude_rules(spec, self.root)
        current_deny = list(permissions.get("deny") or [])
        ask = list(permissions.get("ask") or [])
        dropped = rules["ask"] + rules["retired"]
        moved = [e for e in current_deny if e in dropped]
        deny = [e for e in current_deny if e not in dropped]
        ask = [e for e in ask if e not in rules["retired"]]
        added_deny = [e for e in rules["deny"] if e not in deny]
        added_ask = [e for e in rules["ask"] if e not in ask]
        permissions["deny"] = deny + added_deny
        permissions["ask"] = ask + added_ask
        settings["permissions"] = permissions
        hooks = dict(settings.get("hooks") or {})
        pre = list(hooks.get("PreToolUse") or [])
        command = self.hook_command(spec)
        matcher = spec["claude_code"]["hook"]["matcher"]
        registered = any(
            entry.get("matcher") == matcher
            and any(h.get("command") == command for h in entry.get("hooks") or [])
            for entry in pre
        )
        if not registered:
            pre.append(
                {
                    "matcher": matcher,
                    "hooks": [{"type": "command", "command": command, "timeout": 10}],
                }
            )
        hooks["PreToolUse"] = pre
        settings["hooks"] = hooks
        write_json(self.settings(), settings)
        return {
            "added_deny": added_deny,
            "added_ask": added_ask,
            "moved_from_deny": moved,
            "registered": not registered,
        }

    def unmerge_claude(self, saved: dict, spec: dict) -> str:
        settings = load_json(self.settings())
        if "permissions" in settings:
            settings["permissions"] = drop_managed(settings["permissions"], saved)
        command = self.hook_command(spec)
        hooks = settings.get("hooks") or {}
        if saved.get("hook_registered") and "PreToolUse" in hooks:
            pre = []
            for entry in hooks["PreToolUse"]:
                ours = entry.get("matcher") == saved.get("hook_matcher", "Bash")
                inner = [
                    h
                    for h in entry.get("hooks") or []
                    if not (ours and h.get("command") == command)
                ]
                if inner or not entry.get("hooks"):
                    pre.append(
                        dict(entry, hooks=inner) if entry.get("hooks") else entry
                    )
            hooks["PreToolUse"] = pre
        write_json(self.settings(), settings)
        return "cleaned"

    def install(self, spec: dict) -> dict:
        repo_scope = ROOT_REPO / spec["scope_files"]["repo"]
        if "\n".join(spec["scope_section"]) not in repo_scope.read_text():
            raise RuntimeError(
                f"{spec['scope_files']['repo']} must contain the scope section from deny-rules.json"
            )
        saved = load_json(self.receipt)
        if saved and saved.get("owner") != OWNER:
            raise RuntimeError("Unrecognized deny-rules receipt; refusing to overwrite")
        for target in self.guard_targets(spec):
            if target.is_file() and OWNER not in target.read_text():
                raise RuntimeError(
                    f"{target} is a guard this installer does not own; move it aside or merge its rules into deny-rules.json, nothing was changed"
                )
        for path in self.scope_paths(spec):
            if path.is_file() and not path.is_symlink():
                check_markers(path.read_text(), path)
        stamp = str(time.time_ns())
        snapshot = self.snapshot(spec, self.backups / stamp / "snapshot")
        self.prior = self.backups / stamp / "prior"
        try:
            if saved:
                self.uninstall(spec)
            return self.apply(spec)
        except BaseException:
            self.restore(snapshot)
            raise

    def claim(self, path: Path, prior_files: dict) -> None:
        saved = self.copy_aside(path, self.prior)
        prior_files[str(path)] = str(saved) if saved else None

    def apply(self, spec: dict) -> dict:
        prior_files: dict = {}
        merged = self.merge_claude(spec)
        actions = [
            f"claude settings: +{len(merged['added_deny'])} deny entries, "
            f"+{len(merged['added_ask'])} ask entries, "
            f"{len(merged['moved_from_deny'])} existing deny entries moved to ask or retired",
            f"claude hook: registered={merged['registered']}",
        ]
        hook = self.hook_target(spec)
        self.claim(hook, prior_files)
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.unlink(missing_ok=True)
        atomic_write(hook, render_hook(spec, self.root), 0o700)
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
                "managed_deny": merged["added_deny"],
                "managed_ask": merged["added_ask"],
                "moved_from_deny": merged["moved_from_deny"],
                "hook_registered": merged["registered"],
                "hook_matcher": spec["claude_code"]["hook"]["matcher"],
                "prior_files": prior_files,
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
        for path in self.scope_paths(spec):
            if path.is_file() and not path.is_symlink():
                check_markers(path.read_text(), path)
        actions = ["claude settings: " + self.unmerge_claude(saved, spec)]
        for target, backup in (saved.get("prior_files") or {}).items():
            Path(target).unlink(missing_ok=True)
            if backup:
                shutil.copy2(backup, target, follow_symlinks=False)
                actions.append(f"restored {target}")
        for path in self.scope_paths(spec):
            actions.append(f"scope {path}: " + self.remove_scope_section(path))
        self.receipt.unlink()
        return {"uninstalled": True, "actions": actions}

    def status(self, spec: dict) -> dict:
        permissions = load_json(self.settings()).get("permissions") or {}
        deny = permissions.get("deny") or []
        ask = permissions.get("ask") or []
        rules = claude_rules(spec, self.root)
        guard = render_guard(spec, self.root)
        return {
            "installed": bool(load_json(self.receipt)),
            "claude_deny_missing": [e for e in rules["deny"] if e not in deny],
            "claude_ask_missing": [e for e in rules["ask"] if e not in ask],
            "claude_ask_still_denied": [e for e in rules["ask"] if e in deny],
            "claude_ascend_entries_present": [
                e for e in rules["retired"] if e in deny or e in ask
            ],
            "merge_hook_file": self.hook_target(spec).is_file(),
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

    def plan(self, spec: dict) -> dict:
        """What install would change, computed without writing anything."""
        saved = load_json(self.receipt)
        current = load_json(self.settings()).get("permissions") or {}
        permissions = drop_managed(current, saved)
        rules = claude_rules(spec, self.root)
        dropped = rules["ask"] + rules["retired"]
        deny = [e for e in permissions.get("deny") or [] if e not in dropped]
        ask = [e for e in permissions.get("ask") or [] if e not in rules["retired"]]
        deny_added = [e for e in rules["deny"] if e not in deny]
        ask_added = [e for e in rules["ask"] if e not in ask]

        def file_state(path: Path, text: str) -> str:
            if not path.is_file():
                return "new"
            return "identical" if path.read_text() == text else "changed"

        return {
            "dry_run": True,
            "claude_settings": {
                "deny_entries": [len(current.get("deny") or []), len(deny) + len(deny_added)],
                "ask_entries": [len(current.get("ask") or []), len(ask) + len(ask_added)],
                "ascend_entries_left": [
                    e for e in deny + deny_added + ask + ask_added if e in rules["retired"]
                ],
            },
            "claude_hook": {
                str(self.hook_target(spec)): file_state(
                    self.hook_target(spec), render_hook(spec, self.root)
                )
            },
            "pi_guards": {
                str(t): file_state(t, render_guard(spec, self.root))
                for t in self.guard_targets(spec)
            },
            "backups": f"every existing managed file is copied under {self.backups}/<timestamp>/snapshot before any change",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "status", "uninstall"])
    parser.add_argument(
        "--root",
        "--target-root",
        type=Path,
        default=Path.home(),
        help="home root the agent and Claude directories live under",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with install: print what would change and write nothing",
    )
    args = parser.parse_args()
    if args.dry_run and args.action != "install":
        parser.error("--dry-run only applies to install")
    spec = json.loads(SPEC_PATH.read_text())
    installer = Installer(args.root.expanduser().resolve())
    action = "plan" if args.dry_run else args.action
    print(json.dumps(getattr(installer, action)(spec), indent=2))


if __name__ == "__main__":
    main()
