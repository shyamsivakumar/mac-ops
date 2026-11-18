"""MO-1073 regression: bootstrap files do not make a worktree dirty, and a
finished worktree whose commits are already on the remote default branch is
removed automatically."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/worktree-cleaner/cleaner.py"
RULES = ROOT / "coordinator/config/AGENT-RULES.md"


def command(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"fixture command failed: {Path(argv[0]).name} {argv[1] if len(argv) > 1 else ''} {result.stderr}")
    return result.stdout.strip()


def git(repo: Path, *args: str) -> str:
    return command(["git", "-C", str(repo), *args])


def commit(repo: Path, name: str, content: str) -> str:
    (repo / name).write_text(content, encoding="utf-8")
    git(repo, "add", name)
    command(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-m", name])
    return git(repo, "rev-parse", "HEAD")


def rules_block() -> str:
    """The exact standing rules block an agent bootstrap writes."""
    return RULES.read_text(encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mo1073-") as tmp:
        base = Path(tmp)
        code = base / "Code"
        repo = code / "fixture-repo"
        remote = base / "remote.git"
        trees = code / ".worktrees"
        trees.mkdir(parents=True)
        command(["git", "init", "--bare", str(remote)])
        command(["git", "init", "-b", "main", str(repo)])
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "fixture@example.test")
        git(repo, "remote", "add", "origin", str(remote))
        commit(repo, "base.txt", "base\n")
        (repo / "AGENTS.md").write_text("# Fixture repository rules\n", encoding="utf-8")
        git(repo, "add", "AGENTS.md")
        command(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-m", "agents"])
        (repo / "x.specstory").mkdir(parents=True)
        (repo / "x.specstory" / "notes").write_text("notes\n", encoding="utf-8")
        git(repo, "add", "x.specstory/notes")
        command(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-m", "notes"])
        # A committed bootstrap file, so a worktree can rename it.
        (repo / ".specstory").mkdir()
        commit(repo, ".specstory/old.md", "old\n")
        git(repo, "push", "-u", "origin", "main")
        git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        shas: dict[str, str] = {}
        for name in ("bootstrap", "real", "onmain", "offmain", "partial", "renamed", "shifted", "marker"):
            sha = commit(repo, f"{name}.txt", name + "\n")
            shas[name] = sha
            git(repo, "branch", name, sha)
            if name != "offmain":
                git(repo, "push", "origin", "main")
        # A commit that is only on master, never on the default branch main.
        git(repo, "checkout", "-b", "masteronly")
        shas["masteronly"] = commit(repo, "master-only.txt", "master\n")
        git(repo, "push", "origin", "masteronly:master")
        git(repo, "fetch", "origin")
        git(repo, "checkout", "main")
        paths = {name: trees / name for name in shas}
        for name, path in paths.items():
            git(repo, "worktree", "add", str(path), name)
        # The bootstrap edits an agent bootstrap leaves in a worktree.
        for name in ("bootstrap", "real"):
            path = paths[name]
            with (path / "AGENTS.md").open("a", encoding="utf-8") as handle:
                handle.write(rules_block())
            (path / ".specstory" / "history").mkdir(parents=True)
            (path / ".specstory" / "history" / "session.md").write_text("history\n", encoding="utf-8")
            (path / ".agents").mkdir(parents=True)
            (path / ".agents" / "legacy-instructions.md").write_text("legacy\n", encoding="utf-8")
        (paths["real"] / "real-work.txt").write_text("real work\n", encoding="utf-8")
        # A rename of one bootstrap file onto another is the bootstrap too, and
        # it has already taken the source away, so the cleanup restores it.
        git(paths["bootstrap"], "mv", ".specstory/old.md", ".specstory/new.md")
        # One rule added by hand is not the bootstrap block: real work.
        with (paths["partial"] / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write("- CI is agent checks only: no Woodpecker, no GitHub Actions.\n")
        # A rename of a real file into .specstory/ is real work.
        (paths["renamed"] / ".specstory").mkdir(exist_ok=True)
        git(paths["renamed"], "mv", "renamed.txt", ".specstory/renamed.txt")
        # A real file whose name starts like a bootstrap path is real work.
        (paths["shifted"] / "x.specstory" / "notes").write_text("edited\n", encoding="utf-8")
        # The rules block plus one genuine line is real work. The change is staged,
        # so the status record keeps its columns and the file cannot hide behind
        # a line that looks like a diff marker.
        with (paths["marker"] / "AGENTS.md").open("a", encoding="utf-8") as handle:
            handle.write(rules_block() + "++ genuine edit\n")
        git(paths["marker"], "add", "AGENTS.md")
        # An Ascend repository is never touched.
        ascend = code / "ascend-mcp"
        command(["git", "init", "-b", "main", str(ascend)])
        git(ascend, "config", "user.name", "Fixture")
        git(ascend, "config", "user.email", "fixture@example.test")
        ascend_sha = commit(ascend, "ascend.txt", "ascend\n")
        git(ascend, "branch", "ascend-branch")
        ascend_tree = trees / "ascend-tree"
        git(ascend, "worktree", "add", str(ascend_tree), "ascend-branch")

        fixture = base / "fixture.json"
        fixture.write_text(json.dumps({
            "present": [shas[name] for name in ("bootstrap", "real", "onmain", "partial", "renamed", "shifted", "marker", "masteronly")] + [ascend_sha],
            "prs": {name: [{"number": 7, "state": "MERGED", "headRefName": name, "headRefOid": shas[name]}] for name in ("bootstrap", "partial", "renamed", "shifted", "marker")},
            "contained": {"main": [shas[name] for name in ("bootstrap", "real", "onmain", "partial", "renamed", "shifted", "marker")]},
        }))
        bin_dir = base / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
d = json.loads(Path(os.environ['MO1073_FIXTURE']).read_text())
if args[:2] == ['repo', 'view']:
    if 'defaultBranchRef' in args:
        print('main')
    else:
        print('fixture/fixture-repo')
elif args[0] == 'api':
    path = args[1]
    if '/compare/' in path:
        base, _, head = path.split('/compare/', 1)[1].partition('...')
        print('behind' if head in d.get('contained', {}).get(base, []) else 'ahead')
    else:
        sha = path.rsplit('/', 1)[-1]
        if sha not in d['present']:
            sys.exit(1)
        print(sha)
elif args[:2] == ['pr', 'list']:
    print(json.dumps(d['prs'].get(args[args.index('--head') + 1], [])))
else:
    sys.exit(2)
''')
        gh.chmod(0o755)
        t3mcp = bin_dir / "t3mcp"
        t3mcp.write_text("""#!/usr/bin/env python3
import json, sys
tool = sys.argv[2]
assert tool == 't3_thread_list'
print(json.dumps({'threads': [], 'total': 0, 'nextCursor': None}))
""")
        t3mcp.chmod(0o755)
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", MO1073_FIXTURE=str(fixture))
        args = [sys.executable, str(SCRIPT), "--code-root", str(code), "--state-root", str(base / "state")]
        dry = json.loads(command(args + ["--dry-run"], env=env))
        by_name = {Path(row["path"]).name: row for row in dry["rows"]}
        assert dry["eligible"] == 2, dry["categories"]
        assert by_name["bootstrap"]["eligible"] is True, by_name["bootstrap"]["reasons"]
        assert by_name["bootstrap"]["dirty"] is False, by_name["bootstrap"]
        assert sorted(by_name["bootstrap"]["bootstrap_changes"]) == [".agents/legacy-instructions.md", ".specstory/history/session.md", ".specstory/new.md", "AGENTS.md"], by_name["bootstrap"]
        assert by_name["real"]["eligible"] is False and "worktree_dirty" in by_name["real"]["reasons"], by_name["real"]
        assert by_name["partial"]["eligible"] is False and "worktree_dirty" in by_name["partial"]["reasons"], by_name["partial"]
        assert by_name["partial"]["bootstrap_changes"] == [], by_name["partial"]
        assert by_name["renamed"]["eligible"] is False and "worktree_dirty" in by_name["renamed"]["reasons"], by_name["renamed"]
        assert by_name["renamed"]["bootstrap_changes"] == [], by_name["renamed"]
        assert by_name["shifted"]["eligible"] is False and "worktree_dirty" in by_name["shifted"]["reasons"], by_name["shifted"]
        assert by_name["shifted"]["bootstrap_changes"] == [], by_name["shifted"]
        assert by_name["marker"]["eligible"] is False and "worktree_dirty" in by_name["marker"]["reasons"], by_name["marker"]
        assert by_name["marker"]["bootstrap_changes"] == [], by_name["marker"]
        assert by_name["masteronly"]["eligible"] is False, by_name["masteronly"]
        assert by_name["masteronly"].get("published_on_default_branch") is not True, by_name["masteronly"]
        assert by_name["onmain"]["eligible"] is True, by_name["onmain"]["reasons"]
        assert by_name["onmain"]["published_on_default_branch"] is True, by_name["onmain"]
        assert by_name["offmain"]["eligible"] is False, by_name["offmain"]["reasons"]
        assert dry["excluded_repositories"] == 1, dry["excluded_repositories"]
        assert any(Path(row["path"]).resolve() == ascend_tree.resolve() and row["reason"] == "Ascend repository" for row in dry["excluded_rows"]), dry["excluded_rows"]

        applied = json.loads(command(args + ["--apply"], env=env))
        assert applied["removed"] == 2, applied["categories"]
        assert not paths["bootstrap"].exists() and not paths["onmain"].exists(), applied
        assert paths["real"].exists() and paths["offmain"].exists(), applied
        assert paths["partial"].exists() and paths["renamed"].exists(), applied
        assert paths["shifted"].exists() and paths["marker"].exists(), applied
        assert paths["masteronly"].exists(), applied
        assert ascend_tree.exists(), "ascend worktree must stay"
        log = (base / "worktree-cleaner.log").read_text(encoding="utf-8")
        entries = [json.loads(line) for line in log.splitlines()]
        removed = [entry for entry in entries if entry["event"] == "removed"]
        assert len(removed) == 2, removed
        for entry in removed:
            assert entry["repo"] and entry["path"] and entry["branch"] and entry["head"], entry
            assert entry.get("eligible_reason"), entry
        assert any(entry["path"].endswith("bootstrap") for entry in removed), removed
        assert any(entry["path"].endswith("onmain") for entry in removed), removed
        assert git(repo, "show-ref", "--verify", "refs/heads/bootstrap")
        assert git(repo, "show-ref", "--verify", "refs/heads/real")
        print(json.dumps({"ok": True, "removed": applied["removed"], "bootstrap_only_removed": True, "real_work_kept": True, "ascend_untouched": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
