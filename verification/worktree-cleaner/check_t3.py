"""MO-125 safety regression: isolated Git repositories and a paginated t3mcp CLI."""
from __future__ import annotations

import json
import os
from pathlib import Path
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


def thread(thread_id: str, path: Path | None, *, status: str = "running", settled: bool = False) -> dict:
    return {"threadId": thread_id, "status": status, "settled": settled, "updatedAt": "2026-11-12T00:00:00.000Z", "worktreePath": None if path is None else str(path)}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mo125-t3-") as tmp:
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
        base_sha = commit(repo, "base.txt", "base\n")
        git(repo, "push", "-u", "origin", "main")
        shas = {}
        names = ("merged", "active", "cwd-only", "idle", "waiting", "completed", "unknown", "dirty", "unpublished")
        for name in names:
            sha = commit(repo, f"{name}.txt", name + "\n")
            shas[name] = sha
            git(repo, "branch", name, sha)
            if name != "unpublished":
                git(repo, "push", "origin", "main")
        paths = {name: trees / name for name in names}
        for name, path in paths.items():
            git(repo, "worktree", "add", str(path), name)
        detached = trees / "detached"
        git(repo, "worktree", "add", "--detach", str(detached), base_sha)
        age_reflog(detached)
        (paths["dirty"] / "dirty.txt").write_text("uncommitted\n")
        for path in (code / "strategy-replay-workbench", code / "slash-eureka" / "dbt", code / "slash-eureka" / "omni"):
            command(["git", "init", str(path)])
        threads = [thread(f"scratch-{i}", None) for i in range(100)]
        threads.extend([
            thread("other-project-active", paths["active"]),
            thread("subdir-only", paths["cwd-only"] / "subdir", status="starting"),
            thread("waiting", paths["waiting"], status="waiting"),
            thread("queued", paths["completed"], status="queued"),
            thread("completed-unsettled", paths["idle"], status="completed"),
            thread("idle-unsettled", paths["unknown"], status="idle"),
            thread("settled-merged", paths["merged"], status="completed", settled=True),
        ])
        fixture = base / "fixture.json"
        calls = base / "calls.jsonl"
        counter = base / "counter"
        payload = {
            "threads": threads,
            "lateThreads": threads + [thread("late-merged", paths["merged"]), thread("late-detached", detached)],
            "altPath": str(paths["active"]),
            "present": [base_sha] + [sha for name, sha in shas.items() if name != "unpublished"],
            "prs": {name: [{"number": i + 1, "state": "MERGED", "headRefName": name, "headRefOid": sha}] for i, (name, sha) in enumerate(shas.items())},
        }
        fixture.write_text(json.dumps(payload))
        bin_dir = base / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
d = json.loads(Path(os.environ['MO125_FIXTURE']).read_text())
if args[:2] == ['repo', 'view']:
    print('fixture/fixture-repo')
elif args[0] == 'api':
    sha = args[1].rsplit('/', 1)[-1]
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
import json, os, sys
from pathlib import Path
tool = sys.argv[2]
a = json.loads(sys.argv[3])
assert sys.argv[1] == 'call' and tool in ('t3_thread_list', 't3_thread_read')
counter = Path(os.environ['MO125_COUNTER'])
scan = int(counter.read_text()) if counter.exists() else 0
if tool == 't3_thread_list':
    assert a['allProjects'] is True and 1 <= a['limit'] <= 100
    assert set(a) == {'allProjects', 'settled', 'limit', 'cursor'} and a['settled'] is False
    cursor = a['cursor']
    if cursor == 0:
        scan += 1
        counter.write_text(str(scan))
with Path(os.environ['MO125_CALLS']).open('a') as f:
    f.write(json.dumps({'scan': scan, 'tool': tool, **a}) + '\\n')
mode = os.environ.get('MO125_MODE', 'normal')
if mode == 'unavailable' or (mode == 't3-final' and scan >= 3) or (mode == 't3-immediate' and scan >= 5):
    sys.exit(1)
if mode == 'invalid-json':
    print('not json')
    sys.exit(0)
d = json.loads(Path(os.environ['MO125_FIXTURE']).read_text())
all_threads = d['lateThreads'] if mode == 'late' and scan >= 5 else d['threads']
if mode in ('churn', 'path-change', 'settled-flip'):
    all_threads = [dict(t, updatedAt=f'2026-11-12T00:00:00.{scan:03d}Z') for t in all_threads]
    for t in all_threads:
        if t['threadId'] == 'waiting' and mode == 'path-change' and scan % 2:
            t['worktreePath'] = d['altPath']
        if t['threadId'] == 'waiting' and mode == 'settled-flip':
            t['settled'] = scan % 2 == 0
if tool == 't3_thread_read':
    if mode == 'read-unavailable':
        sys.exit(1)
    row = next(t for t in all_threads if t['threadId'] == a['threadId'])
    if mode == 'missing-path':
        row = {k: v for k, v in row.items() if k != 'worktreePath'}
    print(json.dumps({'thread': row}))
    sys.exit(0)
threads = [t for t in all_threads if t['settled'] is a['settled']]
cursor = a['cursor']
rows = threads[cursor:cursor + a['limit']]
next_cursor = cursor + len(rows) if cursor + len(rows) < len(threads) else None
page = {'threads': rows, 'total': len(threads), 'nextCursor': next_cursor}
if mode == 'truncated' and cursor:
    page['threads'] = rows[:-1]
if mode == 'duplicate' and cursor:
    page['threads'][0] = threads[0]
if mode == 'changed-total' and cursor:
    page['total'] += 1
if mode == 'loop':
    page['nextCursor'] = cursor
if mode == 'missing-cursor':
    del page['nextCursor']
if mode == 'snapshot-change' and scan >= 2 and cursor == 0:
    page['threads'][0] = {**page['threads'][0], 'threadId': 'new-thread-same-total'}
print(json.dumps(page))
""")
        t3mcp.chmod(0o755)
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", MO125_FIXTURE=str(fixture), MO125_CALLS=str(calls), MO125_COUNTER=str(counter))
        args = [sys.executable, str(SCRIPT), "--code-root", str(code), "--state-root", str(base / "state")]
        refs_before = git(remote, "for-each-ref", "--format=%(refname):%(objectname)", "refs/heads")
        dry = json.loads(command(args + ["--dry-run"], env=env))
        assert dry["eligible"] == 2 and dry["removed"] == 0, dry
        assert dry["t3_threads_scanned"] == 106 and dry["t3_pages_scanned"] == 4
        assert dry["held_reasons"]["t3_thread_unfinished"] == 6
        held_linked = [row for row in dry["rows"] if not row["main_checkout"] and row["t3_threads"]]
        assert len(held_linked) == 6
        assert next(row for row in held_linked if Path(row["path"]).resolve() == paths["active"].resolve())["t3_threads"] == ["other-project-active"]
        assert not any(row["eligible"] for row in held_linked)
        assert dry["held_reasons"]["worktree_dirty"] == 1
        assert dry["held_reasons"]["remote_commit_unverified"] == 1
        assert dry["excluded_repositories"] == 3
        for mode in ("unavailable", "invalid-json", "truncated", "duplicate", "changed-total", "loop", "missing-cursor", "missing-path", "read-unavailable", "snapshot-change"):
            counter.write_text("0")
            result = subprocess.run(args + ["--apply"], env=dict(env, MO125_MODE=mode), capture_output=True, text=True)
            assert result.returncode == 2, (mode, result.stdout, result.stderr)
            assert all(path.is_dir() for path in paths.values()) and detached.is_dir(), mode
        for mode in ("churn", "path-change", "settled-flip"):
            counter.write_text("0")
            calls.write_text("")
            result = subprocess.run(args + ["--dry-run"], env=dict(env, MO125_MODE=mode), capture_output=True, text=True)
            list_passes = sum(1 for line in calls.read_text().splitlines() if json.loads(line)["tool"] == "t3_thread_list" and json.loads(line)["cursor"] == 0)
            if mode == "churn":
                assert result.returncode == 0, (mode, result.stderr)
                churned = json.loads(result.stdout)
                assert churned["eligible"] == dry["eligible"] and churned["held_reasons"] == dry["held_reasons"], churned
                assert list_passes == 2, list_passes
            else:
                assert result.returncode == 2 and "t3_list_changed" in result.stderr, (mode, result.stdout, result.stderr)
                assert list_passes == 6, (mode, list_passes)
        for mode in ("t3-final", "t3-immediate", "late"):
            counter.write_text("0")
            applied = json.loads(command(args + ["--apply"], env=dict(env, MO125_MODE=mode)))
            assert applied["removed"] == 0 and paths["merged"].is_dir() and detached.is_dir(), (mode, applied)
            if mode == "late":
                assert applied["held_reasons"]["t3_thread_unfinished"] == 8
        counter.write_text("0")
        applied = json.loads(command(args + ["--apply"], env=env))
        assert applied["removed"] == 2 and not paths["merged"].exists() and not detached.exists(), applied
        assert all(path.is_dir() for name, path in paths.items() if name != "merged")
        assert git(remote, "for-each-ref", "--format=%(refname):%(objectname)", "refs/heads") == refs_before
        assert git(repo, "show-ref", "--verify", "refs/heads/merged")
        report = Path(applied["daily_report"]).read_text()
        assert str(paths["dirty"]) in report and str(paths["unpublished"]) in report
        assert "cwd-only" in report and "other-project-active" in report
        requests = [json.loads(line) for line in calls.read_text().splitlines()]
        assert any(request.get("cursor") == 100 for request in requests)
        assert all(request["tool"] == "t3_thread_read" or (request["allProjects"] and request["limit"] <= 100) for request in requests)
        print(json.dumps({"ok": True, "t3_held": 6, "pages_per_pass": 2, "passes": 2, "fixture_removed": applied["removed"], "failure_modes_blocked": 15, "updated_at_churn_tolerated": True, "remote_refs_preserved": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
