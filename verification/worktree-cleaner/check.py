from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/worktree-cleaner/cleaner.py"


def command(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"fixture command failed: {Path(argv[0]).name} {argv[1] if len(argv) > 1 else ''}")
    return result.stdout.strip()


def git(repo: Path, *args: str) -> str:
    return command(["git", "-C", str(repo), *args])


def commit(repo: Path, name: str, content: str) -> str:
    (repo / name).write_text(content, encoding="utf-8")
    git(repo, "add", name)
    command(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-m", name])
    return git(repo, "rev-parse", "HEAD")


def seed_state(path: Path, active_path: Path, unknown_path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE orchestration_v2_projection_metadata(projection_name TEXT, schema_version INTEGER, last_sequence INTEGER, updated_at TEXT);
        CREATE TABLE orchestration_v2_projection_threads(thread_id TEXT, project_id TEXT, title TEXT, default_provider TEXT, runtime_mode TEXT, interaction_mode TEXT, active_provider_thread_id TEXT, created_at TEXT, updated_at TEXT, archived_at TEXT, deleted_at TEXT, payload_json TEXT, provider_instance_id TEXT);
        CREATE TABLE orchestration_v2_projection_runs(run_id TEXT, thread_id TEXT, ordinal INTEGER, provider TEXT, provider_thread_id TEXT, status TEXT, requested_at TEXT, completed_at TEXT, payload_json TEXT, provider_instance_id TEXT);
        CREATE TABLE orchestration_v2_projection_provider_threads(provider_thread_id TEXT, thread_id TEXT, owner_node_id TEXT, provider TEXT, provider_session_id TEXT, status TEXT, first_run_ordinal INTEGER, last_run_ordinal INTEGER, updated_at TEXT, payload_json TEXT, driver TEXT, provider_instance_id TEXT);
        CREATE TABLE orchestration_v2_projection_provider_sessions(provider_session_id TEXT, thread_id TEXT, provider TEXT, status TEXT, model TEXT, updated_at TEXT, payload_json TEXT, driver TEXT, provider_instance_id TEXT);
        CREATE TABLE orchestration_v2_projection_runtime_requests(runtime_request_id TEXT, thread_id TEXT, node_id TEXT, provider_turn_id TEXT, kind TEXT, status TEXT, created_at TEXT, resolved_at TEXT, payload_json TEXT);
        CREATE TABLE orchestration_v2_projection_subagents(subagent_id TEXT, thread_id TEXT, run_id TEXT, parent_node_id TEXT, provider TEXT, provider_thread_id TEXT, child_thread_id TEXT, origin TEXT, status TEXT, started_at TEXT, completed_at TEXT, updated_at TEXT, payload_json TEXT, driver TEXT, provider_instance_id TEXT, completion_delivery_state TEXT);
        CREATE TABLE orchestration_v2_thread_launch_workflows(command_id TEXT, thread_id TEXT, project_id TEXT, status TEXT, title TEXT, worktree_path TEXT, branch TEXT, setup_committed INTEGER, thread_committed INTEGER, message_committed INTEGER, last_error TEXT, created_at TEXT, updated_at TEXT);
    """)
    conn.execute("INSERT INTO orchestration_v2_projection_metadata VALUES ('threads', 1, 1, 'now')")
    for idx, target in enumerate((active_path, unknown_path), start=1):
        thread_id = f"fixture-thread-{idx}"
        payload = json.dumps({"id": thread_id, "worktreePath": str(target)})
        conn.execute("INSERT INTO orchestration_v2_projection_threads(thread_id,payload_json) VALUES (?,?)", (thread_id, payload))
        if target == active_path:
            conn.execute("INSERT INTO orchestration_v2_projection_runs(run_id,thread_id,status) VALUES (?,?,?)", (f"run-{idx}", thread_id, "running"))
        if target == unknown_path:
            conn.execute("INSERT INTO orchestration_v2_thread_launch_workflows(command_id,status,worktree_path) VALUES (?,?,?)", ("launch-unknown", "running", str(target)))
    conn.commit()
    conn.close()


def age_reflog(path: Path) -> None:
    gitfile = path / ".git"
    admin = Path(gitfile.read_text(encoding="utf-8").strip().split("gitdir: ", 1)[1])
    log = admin / "logs/HEAD"
    lines = log.read_text(encoding="utf-8").splitlines()
    aged = []
    for line in lines:
        prefix, separator, message = line.partition("\t")
        fields = prefix.split()
        fields[-2] = str(int(time.time()) - 25 * 60 * 60)
        aged.append(" ".join(fields) + (separator + message if separator else ""))
    log.write_text("\n".join(aged) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mo125-worktree-cleaner-") as tmp:
        base = Path(tmp)
        code = base / "Code"
        repo = code / "fixture-repo"
        remote = base / "fixture-remote.git"
        worktrees = code / ".worktrees"
        worktrees.mkdir(parents=True)
        command(["git", "init", "--bare", str(remote)])
        command(["git", "init", "-b", "main", str(repo)])
        command(["git", "-C", str(repo), "config", "user.name", "Fixture"])
        command(["git", "-C", str(repo), "config", "user.email", "fixture@example.test"])
        git(repo, "remote", "add", "origin", str(remote))
        base_sha = commit(repo, "base.txt", "base\n")
        git(repo, "push", "-u", "origin", "main")
        branch_shas: dict[str, str] = {}
        for name in ("merged", "active", "unknown", "dirty", "unpublished"):
            sha = commit(repo, f"{name}.txt", name + "\n")
            branch_shas[name] = sha
            git(repo, "branch", name, sha)
            if name != "unpublished":
                git(repo, "push", "origin", "main")
        paths = {name: worktrees / name for name in branch_shas}
        for name, path in paths.items():
            command(["git", "-C", str(repo), "worktree", "add", str(path), name])
        detached = worktrees / "detached"
        command(["git", "-C", str(repo), "worktree", "add", "--detach", str(detached), base_sha])
        age_reflog(detached)
        (paths["dirty"] / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
        for excluded in (code / "strategy-replay-workbench", code / "renamed-checkout", code / "slash-eureka" / "dbt", code / "slash-eureka" / "omni"):
            command(["git", "init", str(excluded)])
        (code / ".git" / "claude").mkdir(parents=True)
        state_db = base / "state.sqlite"
        seed_state(state_db, paths["active"], paths["unknown"])
        present = {base_sha, branch_shas["merged"], branch_shas["active"], branch_shas["unknown"], branch_shas["dirty"]}
        pr_map = {
            "merged": [{"number": 21, "state": "MERGED", "headRefName": "merged", "headRefOid": branch_shas["merged"]}],
            "active": [{"number": 22, "state": "CLOSED", "headRefName": "active", "headRefOid": branch_shas["active"]}],
            "unknown": [
                {"number": 23, "state": "CLOSED", "headRefName": "unknown", "headRefOid": branch_shas["unknown"]},
                {"number": 26, "state": "OPEN", "headRefName": "unknown", "headRefOid": branch_shas["unknown"]},
            ],
            "dirty": [{"number": 24, "state": "CLOSED", "headRefName": "dirty", "headRefOid": branch_shas["dirty"]}],
            "unpublished": [{"number": 25, "state": "CLOSED", "headRefName": "unpublished", "headRefOid": branch_shas["unpublished"]}],
        }
        inputs = base / "github.json"
        inputs.write_text(json.dumps({"present": sorted(present), "prs": pr_map, "repositories": {"renamed-checkout": "slash-eureka/dbt"}}), encoding="utf-8")
        bin_dir = base / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
data = json.loads(Path(os.environ['MO125_GITHUB_FIXTURE']).read_text())
if args[:2] == ['repo', 'view']:
    print(data.get('repositories', {}).get(Path.cwd().name, 'fixture/fixture-repo'))
elif args and args[0] == 'api':
    sha = args[1].rsplit('/', 1)[-1]
    if sha.lower() in {item.lower() for item in data['present']}:
        print(sha)
    else:
        sys.exit(1)
elif args[:2] == ['pr', 'list']:
    branch = args[args.index('--head') + 1]
    assert ':' not in branch
    print(json.dumps(data['prs'].get(branch, [])))
else:
    sys.exit(2)
""", encoding="utf-8")
        gh.chmod(0o755)
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", MO125_GITHUB_FIXTURE=str(inputs))
        state_root = base / "state"
        args = [sys.executable, str(SCRIPT), "--code-root", str(code), "--state-root", str(state_root), "--t3-db", str(state_db)]
        refs_before = git(remote, "for-each-ref", "--format=%(refname):%(objectname)", "refs/heads")
        dry = json.loads(command(args + ["--dry-run"], env=env))
        assert dry["mode"] == "dry-run" and dry["eligible"] == 2 and dry["removed"] == 0, dry
        assert paths["merged"].is_dir() and detached.is_dir()
        assert dry["held_reasons"].get("t3_thread_active") == 1
        assert dry["held_reasons"].get("t3_status_unknown") == 1
        assert dry["held_reasons"].get("t3_launch_in_progress") == 1
        assert dry["held_reasons"].get("github_pr_open") == 1
        assert dry["held_reasons"].get("worktree_dirty") == 1
        assert dry["held_reasons"].get("remote_commit_unverified", 0) >= 1
        assert dry["excluded_repositories"] == 4
        bad_db = base / "unrecognized-state.sqlite"
        sqlite3.connect(bad_db).close()
        blocked = subprocess.run(args + ["--t3-db", str(bad_db), "--apply"], env=env, capture_output=True, text=True, check=False)
        assert blocked.returncode == 2 and paths["merged"].is_dir() and detached.is_dir()
        conn = sqlite3.connect(state_db)
        conn.execute("UPDATE orchestration_v2_projection_metadata SET schema_version = 999")
        conn.commit()
        conn.close()
        blocked = subprocess.run(args + ["--apply"], env=env, capture_output=True, text=True, check=False)
        assert blocked.returncode == 2 and "t3_state_version_unrecognized" in blocked.stderr
        assert paths["merged"].is_dir() and detached.is_dir()
        conn = sqlite3.connect(state_db)
        conn.execute("UPDATE orchestration_v2_projection_metadata SET schema_version = 1")
        conn.commit()
        conn.close()
        applied = json.loads(command(args + ["--apply"], env=env))
        assert applied["removed"] == 2, applied
        assert not paths["merged"].exists() and not detached.exists()
        assert paths["active"].is_dir() and paths["unknown"].is_dir() and paths["dirty"].is_dir() and paths["unpublished"].is_dir()
        refs_after = git(remote, "for-each-ref", "--format=%(refname):%(objectname)", "refs/heads")
        assert refs_after == refs_before
        assert git(repo, "show-ref", "--verify", "refs/heads/merged")
        removals = (state_root.parent / "worktree-cleaner.log").read_text(encoding="utf-8").splitlines()
        assert len(removals) == 4
        assert sum(json.loads(line)["event"] == "removed" for line in removals) == 2
        assert Path(applied["daily_report"]).parent == code / "coordinator" / "evidence"
        assert dry["per_repo"][str(repo.resolve())]["would_remove"] == 2
        report = Path(applied["daily_report"]).read_text(encoding="utf-8")
        assert str(paths["dirty"]) in report and str(paths["unpublished"]) in report
        print(json.dumps({"ok": True, "dry_run_eligible": dry["eligible"], "removed_in_fixture": applied["removed"], "held_reasons": applied["held_reasons"], "remote_refs_preserved": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
