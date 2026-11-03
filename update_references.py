#!/usr/bin/env python3
"""Inventory or update active load-tool references, preserving original files."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

HOME = Path.home()
WIKI = HOME / "Code/llmwiki"
SCRIPTS = ("heavy.py", "load_backstop.py", "board_governor.py")
DOCS = ("source/docs/reference/executor.md", "source/docs/reference/herdr.md",
        "source/docs/how-to/pause-heavy-jobs-before-the-mac-locks-up.md",
        "source/docs/how-to/auto-size-board-agent-slots.md",
        "source/docs/explanation/deployment-acceptance-evidence.md",
        "source/docs/explanation/agent-storage-cleanup.md",
        "runtime/codex/skills/graceful-degradation/SKILL.md")


def candidates():
    roots = [WIKI / "runtime", WIKI / "source/docs", HOME / ".claude", HOME / ".codex"]
    args = ["rg", "-l", "--hidden", "--glob", "!**/sessions/**", "--glob", "!**/memories/**",
            "--glob", "!**/projects/**", "--glob", "!**/plugins/cache/**", "--glob", "!**/history*",
            "--glob", "!**/logs/**", "--glob", "!**/shell_snapshots/**", "--glob", "!**/debug/**",
            "--glob", "!**/file-history/**", "--glob", "!**/paste-cache/**", r"\.multica-codex"]
    profiles = [HOME / name for name in (".zshrc", ".zprofile", ".bashrc", ".bash_profile", ".profile")]
    result = subprocess.run(args + [str(p) for p in roots + profiles if p.exists()], capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr[:200])
    return [Path(line) for line in result.stdout.splitlines()]


def save(path, text, backup):
    if text == path.read_text():
        return False
    backup.mkdir(mode=0o700, parents=True, exist_ok=True)
    digest = hashlib.sha256(str(path).encode()).hexdigest()[:16]
    target = backup / (digest + "-" + path.name)
    if not target.exists():
        target.write_bytes(path.read_bytes())
    path.write_text(text)
    return True


def apply(backup):
    changed = []
    for name in SCRIPTS:
        path = WIKI / "runtime/codex/scripts" / name
        if not path.exists():
            continue
        code = ('#!/usr/bin/env python3\nimport runpy,sys\n'
                'from pathlib import Path\n'
                'runtime = Path.home() / ".local/state/mac-ops/installation.json"\n'
                'import json\n'
                'root = Path(json.loads(runtime.read_text())["release"])\n'
                'sys.path.insert(0, str(root))\n'
                'if __name__ == "__main__":\n'
                f'    runpy.run_path(str(root / {name!r}), run_name="__main__")\n'
                'else:\n'
                f'    globals().update(runpy.run_path(str(root / {name!r})))\n')
        if save(path, code, backup):
            changed.append(str(path))
    replacements = {
        "~/.multica-codex/heavy.sh": "~/.local/bin/heavy",
        "~/.multica-codex/heavy.py": "~/Code/mac-ops/heavy.py",
        "~/.multica-codex/board-governor/board_governor.py": "~/Code/mac-ops/board_governor.py",
        "~/.multica-codex/load-backstop/load_backstop.py": "~/Code/mac-ops/load_backstop.py",
        "~/.multica-codex/": "~/.local/state/mac-ops/",
        'Path.home() / ".multica-codex/board-governor.jsonl"': 'Path.home() / ".local/state/mac-ops/legacy-board-governor.jsonl"',
        'Path.home() / ".multica-codex/heavy.py"': 'Path.home() / ".local/bin/heavy"',
    }
    files = [WIKI / name for name in DOCS if "/how-to/" not in name]
    files += [WIKI / "runtime/codex/scripts/replay_memory_gate.py"]
    files += [p for p in candidates() if p.parent == HOME or p.name in ("settings.json", "config.toml")]
    for path in files:
        if not path.is_file():
            continue
        old = path.read_text()
        new = old
        historical = any(x in str(path) for x in ("/reference/", "/explanation/", "/skills/"))
        mapping = dict(replacements)
        if historical:
            mapping["~/.multica-codex/"] = "~/_archive/multica-codex-20261027/"
        for before, after in mapping.items():
            new = new.replace(before, after)
            new = new.replace(before.replace("~/", str(HOME) + "/"), after.replace("~/", str(HOME) + "/"))
        if save(path, new, backup):
            changed.append(str(path))
    for name in ("pause-heavy-jobs-before-the-mac-locks-up", "auto-size-board-agent-slots"):
        path = WIKI / "source/docs/how-to" / (name + ".md")
        if path.exists():
            title = "Use the Mac load tools" if name.startswith("pause") else "Adjust Mac load capacity"
            text = ("# " + title + "\n\n"
                    "The local mac-ops repository owns heavy, the load controller and their installation. "
                    "See [the mac-ops guide](../../../../mac-ops/README.md).\n\n"
                    "Install from `~/Code/mac-ops` with `./install.sh`. Use `heavy <command>` for expensive work "
                    "and `heavy --review <command>` for reviews. Runtime state is in `~/.local/state/mac-ops`; "
                    "the shell entry point is `~/.local/bin/heavy`. No Multica service is required.\n\n"
                    "The controller grows one heavy slot after a healthy window and pauses work under sustained "
                    "pressure. It never raises capacity on missing or bad readings. The same controller changes "
                    "board.agents through the local board command. It raises by one after a healthy window "
                    "with memory for one more agent, and cuts immediately on pressure. No upstream plugin "
                    "change is required. The second governor plist stays unloaded to avoid duplicate services.\n\n"
                    "Migration preserves running legacy supervisors and blocks new starts until they drain. "
                    "Uninstall archives wrappers and launchd plists and retains job state. See the repository "
                    "state charts and verification skill for exact coverage and limits.\n")
            if save(path, text, backup):
                changed.append(str(path))
    installer = WIKI / "runtime/codex/scripts/install_heavy.py"
    if installer.exists():
        code = ('#!/usr/bin/env python3\nimport os\nfrom pathlib import Path\n'
                'script = Path.home() / "Code/mac-ops/install.sh"\n'
                'os.execv(str(script), [str(script), "install"])\n')
        if save(installer, code, backup):
            changed.append(str(installer))
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = {"active_reference_files": list(map(str, candidates()))}
    if args.apply:
        json.loads((HOME / ".local/state/mac-ops/installation.json").read_text())
        backup = HOME / ".local/state/mac-ops/reference-backups" / str(time.time_ns())
        result["changed"] = apply(backup)
        result["backup"] = str(backup)
        result["remaining_reference_files"] = list(map(str, candidates()))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
