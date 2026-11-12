"""MO-125 safety regression: isolated Git repositories and a paginated emp CLI."""
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


def thread(thread_id: str, path: Path, *, status: str = "running", settled: bool = False, cwd_only: bool = False) -> dict:
    return {
        "threadId": thread_id,
        "projectId": "another-project",
        "status": status,
        "settled": settled,
        "activeRunId": "run" if status == "running" else None,
        "pendingRequestCount": 0,
        "worktreePath": None if cwd_only else str(path),
        "cwd": str(path),
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="mo125-empryo-") as tmp:
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
        threads = [thread(f"finished-{i}", repo, status="completed", settled=True) for i in range(100)]
        threads.extend([
            thread("other-project-active", paths["active"]),
            thread("cwd-only", paths["cwd-only"] / "subdir", cwd_only=True),
            thread("idle-unsettled", paths["idle"], status="idle"),
            thread("waiting", paths["waiting"], status="waiting"),
            thread("completed-unsettled", paths["completed"], status="completed"),
            thread("future-status", paths["unknown"], status="new-state", settled=True),
        ])
        threads[-6]["cwd"] = str(repo)
        fixture = base / "fixture.json"
        calls = base / "calls.jsonl"
        counter = base / "counter"
        payload = {
            "threads": threads,
            "lateThreads": threads + [thread("late-merged", paths["merged"]), thread("late-detached", detached)],
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
        emp = bin_dir / "emp"
        emp.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
assert sys.argv[1:3] == ['call', 'emp_thread_list']
a = json.loads(sys.argv[3])
assert a['allProjects'] is True and 1 <= a['limit'] <= 100
assert set(a) == {'allProjects', 'limit', 'cursor'}
cursor = a['cursor']
counter = Path(os.environ['MO125_COUNTER'])
scan = int(counter.read_text()) if counter.exists() else 0
if cursor == 0:
    scan += 1
    counter.write_text(str(scan))
with Path(os.environ['MO125_CALLS']).open('a') as f:
    f.write(json.dumps({'scan': scan, **a}) + '\\n')
mode = os.environ.get('MO125_MODE', 'normal')
if mode == 'unavailable' or (mode == 'hub-final' and scan >= 3) or (mode == 'hub-immediate' and scan >= 5):
    sys.exit(1)
if mode == 'invalid-json':
    print('not json')
    sys.exit(0)
d = json.loads(Path(os.environ['MO125_FIXTURE']).read_text())
threads = d['lateThreads'] if mode == 'late' and scan >= 5 else d['threads']
rows = threads[cursor:cursor + a['limit']]
next_cursor = cursor + len(rows) if cursor + len(rows) < len(threads) else None
page = {'projectId': None, 'threads': rows, 'total': len(threads), 'nextCursor': next_cursor}
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
if mode == 'wrong-project':
    page['projectId'] = 'one-project-only'
if mode == 'pathless':
    page['threads'][0] = {**threads[0], 'settled': False, 'cwd': None, 'worktreePath': None}
if mode == 'missing-path':
    del page['threads'][0]['cwd']
if mode == 'snapshot-change' and scan >= 2 and cursor == 0:
    page['threads'][0]['threadId'] = 'new-thread-same-total'
print(json.dumps(page))
''')
        emp.chmod(0o755)
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}", MO125_FIXTURE=str(fixture), MO125_CALLS=str(calls), MO125_COUNTER=str(counter))
        args = [sys.executable, str(SCRIPT), "--code-root", str(code), "--state-root", str(base / "state")]
        refs_before = git(remote, "for-each-ref", "--format=%(refname):%(objectname)", "refs/heads")
        dry = json.loads(command(args + ["--dry-run"], env=env))
        assert dry["eligible"] == 2 and dry["removed"] == 0, dry
        assert dry["empryo_threads_scanned"] == 106 and dry["empryo_pages_scanned"] == 4
        assert dry["held_reasons"]["empryo_thread_unfinished"] == 7
        held_linked = [row for row in dry["rows"] if not row["main_checkout"] and row["empryo_threads"]]
        assert len(held_linked) == 6
        assert next(row for row in held_linked if Path(row["path"]).resolve() == paths["active"].resolve())["empryo_threads"] == ["other-project-active"]
        assert not any("t3" in key or "unknown" in key for key in dry["held_reasons"])
        assert dry["held_reasons"]["worktree_dirty"] == 1
        assert dry["held_reasons"]["remote_commit_unverified"] == 1
        assert dry["excluded_repositories"] == 3
        for mode in ("unavailable", "invalid-json", "truncated", "duplicate", "changed-total", "loop", "missing-cursor", "wrong-project", "pathless", "missing-path", "snapshot-change"):
            counter.write_text("0")
            result = subprocess.run(args + ["--apply"], env=dict(env, MO125_MODE=mode), capture_output=True, text=True)
            assert result.returncode == 2, (mode, result.stdout, result.stderr)
            assert all(path.is_dir() for path in paths.values()) and detached.is_dir(), mode
        for mode in ("hub-final", "hub-immediate", "late"):
            counter.write_text("0")
            applied = json.loads(command(args + ["--apply"], env=dict(env, MO125_MODE=mode)))
            assert applied["removed"] == 0 and paths["merged"].is_dir() and detached.is_dir(), (mode, applied)
            if mode == "late":
                assert applied["held_reasons"]["empryo_thread_unfinished"] == 9
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
        assert any(request["cursor"] == 100 for request in requests)
        assert all(request["allProjects"] and request["limit"] <= 100 for request in requests)
        print(json.dumps({"ok": True, "empryo_held": 6, "pages_per_pass": 2, "passes": 2, "fixture_removed": applied["removed"], "failure_modes_blocked": 14, "remote_refs_preserved": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
