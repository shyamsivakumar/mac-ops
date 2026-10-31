import json, os, shutil, signal, subprocess, sys, time
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
BASE = Path(os.environ["TMPDIR"]) / "iib-repro"
sys.path.insert(0, str(WT / "scripts"))
sys.path.insert(0, str(WT))
import install_if_behind as iib

GATE = {"passed": True, "reasons": []}
iib.check_gate = lambda *a, **k: dict(GATE)


def sh(*argv, cwd=None):
    return subprocess.run([str(a) for a in argv], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def git(repo, *a):
    return sh("git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", *a)


def build(name):
    root = BASE / name
    if root.exists():
        shutil.rmtree(root)
    home = root / "home"
    home.mkdir(parents=True)
    os.chmod(home, 0o755)
    origin, staging, checkout = root / "origin.git", root / "staging", home / "mac-ops-main"
    sh("git", "init", "--bare", "-b", "main", origin)
    sh("git", "clone", "-q", WT, staging)
    git(staging, "checkout", "-q", "-B", "main")
    git(staging, "remote", "add", "up", origin)
    git(staging, "push", "-q", "up", "main")
    sh("git", "clone", "-q", "-b", "main", origin, checkout)
    old = git(checkout, "rev-parse", "HEAD")
    iib_kwargs = dict(checkout=checkout, home=home, state_dir=home / ".local/state/mac-ops")
    return root, home, staging, checkout, old, iib_kwargs


def install_old(home, checkout, old, kw):
    p = iib.installer.paths(home, checkout)
    p["state"] = kw["state_dir"]
    iib.installer.install(p, checkout, migrate=False, no_start=True, source_commit=old)


def push_new(staging):
    (staging / "heavy.py").write_text((staging / "heavy.py").read_text() + "\n# newer release\n")
    git(staging, "commit", "-qam", "newer release")
    git(staging, "push", "-q", "up", "main")
    return git(staging, "rev-parse", "HEAD")


def firing(kw):
    return iib.run_install_if_behind(**kw, no_start=True, observe_seconds=60, poll_interval=1, no_fetch=False)


def summarize(label, r, home, checkout):
    st = iib.read_installation_status(checkout, home / ".local/state/mac-ops")
    print(f"[{label}] decision={r['decision']} reason={r['reason']!r} installed={r.get('installed')}")
    print(f"[{label}] receipt source_commit={st['source_commit'][:7]} release={st['release_name']}")


def scenario(name, kill):
    root, home, staging, checkout, old, kw = build(name)
    install_old(home, checkout, old, kw)
    new = push_new(staging)
    print(f"\n=== {name}: old={old[:7]} new={new[:7]} ===")
    if kill:
        child = subprocess.Popen([sys.executable, __file__, "child", name])
        t0 = time.time()
        while time.time() - t0 < 60:
            st = iib.read_installation_status(checkout, kw["state_dir"])
            if st["source_commit"] == new:
                break
            time.sleep(0.05)
        else:
            raise SystemExit("receipt never updated")
        time.sleep(2)
        print(f"receipt shows new commit after {time.time()-t0:.1f}s; child alive={child.poll() is None}; SIGKILL")
        child.send_signal(signal.SIGKILL)
        child.wait()
        t = time.time()
        r = firing(kw)
        print(f"third firing took {time.time()-t:.1f}s")
        summarize("third firing", r, home, checkout)
    else:
        t = time.time()
        r = firing(kw)
        print(f"firing took {time.time()-t:.1f}s")
        summarize("control", r, home, checkout)
        print("observation reasons:", (r.get("observation") or {}).get("reasons"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        root = BASE / sys.argv[2]
        home = root / "home"
        firing(dict(checkout=home / "mac-ops-main", home=home, state_dir=home / ".local/state/mac-ops"))
    else:
        scenario("kill", True)
        scenario("control", False)
