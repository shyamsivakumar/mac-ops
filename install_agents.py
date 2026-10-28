#!/usr/bin/env python3
"""Install pi and omp board-worker parity from the mac-ops checkout."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

MANIFEST_NAME = "manifest.json"
RECEIPT_NAME = "agents-installation.json"
SKILL_NAMES = (
    "herdr-projects",
    "plain-writing",
    "shyams-voice",
    "how-we-build",
    "search-router",
)


def expand(path: str | Path, home: Path) -> Path:
    return Path(os.path.expanduser(str(path).replace("~/", str(home) + "/"))).resolve()


def load_manifest(checkout: Path) -> dict:
    data = json.loads((checkout / "runtime/agents" / MANIFEST_NAME).read_text())
    home = Path.home()
    for key in ("llmwiki_root", "codex_skills", "project_skills", "omp_runtime"):
        if key in data:
            data[key] = str(expand(data[key], home))
    return data


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".mac-ops-agents-" + str(os.getpid()))
    tmp.write_text(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def backup(path: Path, folder: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / path.name
    if target.exists() or target.is_symlink():
        target = folder / (path.name + "." + str(time.time_ns()))
    if path.is_symlink() or path.is_file():
        path.rename(target)
    elif path.is_dir():
        shutil.move(str(path), str(target))


def link(source: Path, target: Path, backups: Path) -> None:
    if target.is_symlink() and target.resolve() == source.resolve():
        return
    if target.exists() or target.is_symlink():
        backup(target, backups)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(source)


def merge_unique(existing: list, additions: list) -> list:
    seen = set()
    out = []
    for item in list(existing) + list(additions):
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def merge_pi_settings(
    agent_dir: Path,
    overlay: dict,
    codex_skills: str,
    project_skills: str,
    backups: Path,
) -> None:
    settings_path = agent_dir / "settings.json"
    current = {}
    if settings_path.exists():
        current = json.loads(settings_path.read_text())
        backup(settings_path, backups)
    skills = merge_unique(overlay.get("skills", []), current.get("skills") or [])
    skills = [str(expand(s, Path.home())) for s in skills]
    for path in (codex_skills, project_skills):
        if path not in skills:
            skills.append(path)
    enabled = merge_unique(
        current.get("enabledModels") or [], overlay.get("enabledModels") or []
    )
    merged = dict(current)
    merged["skills"] = skills
    merged["enabledModels"] = enabled
    for key, value in overlay.items():
        if key in ("skills", "enabledModels"):
            continue
        merged[key] = value
    atomic_write(settings_path, json.dumps(merged, indent=2) + "\n", 0o600)


def _list_after_key(text: str, key: str) -> list[str] | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != key + ":":
            continue
        items = []
        for follow in lines[index + 1 :]:
            if follow.startswith("  - "):
                items.append(follow[4:].strip())
                continue
            if follow.strip() and not follow.startswith(" "):
                break
            if follow.strip() == "":
                continue
            if not follow.startswith("  "):
                break
        return items
    return None


def _nested_list(text: str, parent: str, child: str) -> list[str]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != parent + ":":
            continue
        for sub in range(index + 1, len(lines)):
            if lines[sub].strip() == child + ":":
                items = []
                for follow in lines[sub + 1 :]:
                    if follow.startswith("    - "):
                        items.append(follow[6:].strip())
                        continue
                    if follow.strip() and not follow.startswith("    "):
                        break
                return items
    return []


def _rewrite_omp_config(text: str, enabled: list[str], directories: list[str]) -> str:
    lines = text.splitlines()
    out = []
    index = 0
    replaced_enabled = False
    replaced_directories = False
    while index < len(lines):
        line = lines[index]
        if line.strip() == "enabledModels:":
            out.append("enabledModels:")
            for item in enabled:
                out.append("  - " + item)
            replaced_enabled = True
            index += 1
            while index < len(lines) and lines[index].startswith("  - "):
                index += 1
            continue
        if line.strip() == "skills:":
            out.append(line)
            index += 1
            while (
                index < len(lines)
                and lines[index].startswith("  ")
                and lines[index].strip() != "customDirectories:"
            ):
                out.append(lines[index])
                index += 1
            if index < len(lines) and lines[index].strip() == "customDirectories:":
                out.append("  customDirectories:")
                for item in directories:
                    out.append("    - " + item)
                replaced_directories = True
                index += 1
                while index < len(lines) and lines[index].startswith("    - "):
                    index += 1
                continue
            out.append("  customDirectories:")
            for item in directories:
                out.append("    - " + item)
            replaced_directories = True
            continue
        out.append(line)
        index += 1
    if not replaced_enabled:
        out.append("enabledModels:")
        for item in enabled:
            out.append("  - " + item)
    if not replaced_directories:
        out.append("skills:")
        out.append("  customDirectories:")
        for item in directories:
            out.append("    - " + item)
    return "\n".join(out).rstrip() + "\n"


def merge_omp_config(agent_dir: Path, overlay_path: Path, backups: Path) -> None:
    config_path = agent_dir / "config.yml"
    overlay = json.loads(overlay_path.read_text())
    text = config_path.read_text() if config_path.exists() else ""
    if config_path.exists():
        backup(config_path, backups)
    enabled = merge_unique(
        _list_after_key(text, "enabledModels") or [],
        overlay.get("enabledModels") or [],
    )
    directories = merge_unique(
        _nested_list(text, "skills", "customDirectories") or [],
        [
            str(expand(p, Path.home()))
            for p in (overlay.get("skills") or {}).get("customDirectories") or []
        ],
    )
    deduped = []
    seen_dirs = set()
    for item in directories:
        key = str(expand(item, Path.home()))
        if key in seen_dirs:
            continue
        seen_dirs.add(key)
        deduped.append(item if str(item).startswith("~") else key)
    directories = deduped
    updated = _rewrite_omp_config(text, enabled, directories)
    atomic_write(config_path, updated, 0o600)


def install_skill_links(agent_skills: Path, codex_skills: Path, backups: Path) -> None:
    agent_skills.mkdir(parents=True, exist_ok=True)
    for name in SKILL_NAMES:
        source = codex_skills / name
        if not source.is_dir():
            continue
        target = agent_skills / name
        link(source, target, backups)


def trust_board_paths(trust_path: Path, paths: list[Path], backups: Path) -> None:
    current = {}
    if trust_path.exists():
        current = json.loads(trust_path.read_text())
        backup(trust_path, backups)
    for path in paths:
        current[str(path)] = True
    current.pop("folders", None)
    atomic_write(trust_path, json.dumps(current, indent=2) + "\n", 0o600)


EXECUTOR_MCP_KEY = "executor"


def merge_executor_mcp(template: Path, target: Path, backups: Path) -> None:
    desired = json.loads(template.read_text())
    executor = desired.get("mcpServers", {}).get(EXECUTOR_MCP_KEY)
    if not isinstance(executor, dict):
        raise TypeError("Template missing executor mcpServers entry: " + str(template))
    current: dict = {}
    if target.exists():
        current = json.loads(target.read_text())
    servers = dict(current.get("mcpServers") or {})
    if servers.get(EXECUTOR_MCP_KEY) == executor:
        return
    if target.exists():
        backup(target, backups)
    servers[EXECUTOR_MCP_KEY] = executor
    merged = dict(current)
    merged["mcpServers"] = servers
    atomic_write(target, json.dumps(merged, indent=2) + "\n", 0o600)


def prove_model(command: list[str], token: str) -> dict:
    proc = subprocess.run(
        command, check=False, capture_output=True, text=True, timeout=180
    )
    return {
        "argv": command,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-2000:],
        "ok": proc.returncode == 0 and token in proc.stdout,
    }


def install(checkout: Path, refresh_models: bool, prove: bool, use_heavy: bool) -> dict:
    manifest = load_manifest(checkout)
    home = Path.home()
    state = home / ".local/state/mac-ops"
    backups = state / "agents-backups" / str(time.time_ns())
    pi_agent = home / ".pi/agent"
    omp_agent = home / ".omp/agent"
    llmwiki = Path(manifest["llmwiki_root"])
    codex_skills = Path(manifest["codex_skills"])
    project_skills = Path(manifest["project_skills"])
    omp_runtime = Path(manifest["omp_runtime"])
    report = {"manifest": manifest, "actions": [], "proof": {}}

    for path in (llmwiki, codex_skills, omp_runtime):
        if not path.is_dir():
            raise RuntimeError("Missing reference path: " + str(path))

    link(checkout / "runtime/pi/AGENTS.md", pi_agent / "AGENTS.md", backups)
    report["actions"].append("linked pi AGENTS.md")

    link(omp_runtime / "AGENTS.md", omp_agent / "AGENTS.md", backups)
    link(omp_runtime / "WATCHDOG.md", omp_agent / "WATCHDOG.md", backups)
    link(omp_runtime / "agents", omp_agent / "agents", backups)
    report["actions"].append("linked omp rules and agents")

    merge_pi_settings(
        pi_agent,
        json.loads((checkout / "runtime/pi/settings.overlay.json").read_text()),
        str(codex_skills),
        str(project_skills),
        backups,
    )
    report["actions"].append("merged pi settings.json")

    install_skill_links(pi_agent / "skills", codex_skills, backups)
    report["actions"].append("linked pi skill shortcuts")

    merge_executor_mcp(checkout / "runtime/pi/mcp.json", pi_agent / "mcp.json", backups)
    merge_executor_mcp(
        checkout / "runtime/omp/mcp.json", omp_agent / "mcp.json", backups
    )
    report["actions"].append("merged executor MCP entry into mcp.json")

    merge_omp_config(omp_agent, checkout / "runtime/omp/board.overlay.json", backups)
    report["actions"].append("merged omp config.yml board overlay")

    trust_board_paths(
        pi_agent / "trust.json",
        [
            home / ".herdr-projects/data/coordinator/default/chat",
            home / ".herdr-projects/data/tasks",
        ],
        backups,
    )
    report["actions"].append("updated pi trust.json for board paths")

    gate = subprocess.run(
        [sys.executable, str(checkout / "scripts/install_pi_gate.py"), "install"],
        check=False,
        capture_output=True,
        text=True,
    )
    report["pi_input_gate"] = {
        "exit_code": gate.returncode,
        "stdout": gate.stdout[-2000:],
        "stderr": gate.stderr[-2000:],
    }
    if gate.returncode != 0:
        raise RuntimeError("pi input gate install failed")

    report["actions"].append("installed pi first-message input gate")

    if refresh_models:
        refresh_cmd = ["pi", "update", "--models"]
        if use_heavy:
            refresh_cmd = [str(home / ".local/bin/heavy")] + refresh_cmd
        proc = subprocess.run(
            refresh_cmd, check=False, capture_output=True, text=True, timeout=300
        )
        report["pi_model_refresh"] = {
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        }
        if proc.returncode != 0:
            report["actions"].append(
                "pi model refresh failed (non-fatal; use --model-refresh after re-auth)"
            )

    if prove:
        token_pi = "TERRA_PI_OK"
        token_omp = "TERRA_OMP_OK"
        pi_cmd = [
            "pi",
            "-p",
            "--no-session",
            "--model",
            manifest.get("board_worker_model_pi") or manifest["board_worker_model"],
            "--thinking",
            "max",
            "--no-tools",
            f"Reply with exactly {token_pi} and nothing else.",
        ]
        omp_cmd = [
            "omp",
            "-p",
            "--no-session",
            "--model",
            manifest["board_worker_model"],
            "--thinking",
            "max",
            "--no-tools",
            f"Reply with exactly {token_omp} and nothing else.",
        ]
        if use_heavy:
            heavy = str(home / ".local/bin/heavy")
            pi_cmd = [heavy] + pi_cmd
            omp_cmd = [heavy] + omp_cmd
        report["proof"]["pi"] = prove_model(pi_cmd, token_pi)
        report["proof"]["omp"] = prove_model(omp_cmd, token_omp)
        if not report["proof"]["pi"]["ok"] or not report["proof"]["omp"]["ok"]:
            raise RuntimeError("Model proof failed; see proof section in receipt")

    receipt = {
        "owner": manifest["owner"],
        "checkout": str(checkout),
        "installed_at": time.time(),
        "source_commit": subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
        "board_worker_agent_pi": manifest["board_worker_agent_pi"],
        "board_worker_agent_omp": manifest["board_worker_agent_omp"],
        "board_worker_model": manifest["board_worker_model"],
        "report": report,
    }
    atomic_write(state / RECEIPT_NAME, json.dumps(receipt, indent=2) + "\n")
    return receipt


def status() -> None:
    receipt_path = Path.home() / ".local/state/mac-ops" / RECEIPT_NAME
    if receipt_path.exists():
        print(receipt_path.read_text())
    else:
        print("Agent parity not installed (no receipt).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("install", "status"), nargs="?", default="install"
    )
    parser.add_argument(
        "--model-refresh",
        action="store_true",
        help="Run pi update --models (optional; failures are recorded, not fatal)",
    )
    parser.add_argument("--no-prove", action="store_true")
    parser.add_argument("--no-heavy", action="store_true")
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parent
    if args.action == "status":
        status()
        return
    receipt = install(
        checkout,
        refresh_models=args.model_refresh,
        prove=not args.no_prove,
        use_heavy=not args.no_heavy,
    )
    print(
        json.dumps(
            {
                "installed": True,
                "receipt": str(Path.home() / ".local/state/mac-ops" / RECEIPT_NAME),
                "proof": receipt["report"].get("proof"),
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print("mac-ops agents: " + str(exc), file=sys.stderr)
        sys.exit(1)
