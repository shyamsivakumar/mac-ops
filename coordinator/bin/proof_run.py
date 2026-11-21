"""Run a ticket's proof command against a ref in a throwaway worktree."""
import argparse, json, os, re, shutil, signal, subprocess, sys, tempfile

SHA = re.compile(r"^[0-9a-f]{40}$")
TIMEOUT = 120


def parse_body(text):
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines)
                  if line.strip().lower().startswith("proof command:")), None)
    if start is None:
        raise ValueError("the ticket body carries no proof command")
    inline = lines[start].split(":", 1)[1].strip()
    if len(inline) > 1 and inline.startswith("`") and inline.endswith("`"):
        inline = inline.strip("`").strip()
    cmd_lines = [inline] if inline else []
    i = start + 1
    if not cmd_lines and i < len(lines) and lines[i].strip().startswith("```"):
        i += 1
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```") or line.strip().lower().startswith(("expected on", "expected red signature")):
            break
        cmd_lines.append(line)
        i += 1
    cmd = "\n".join(cmd_lines).strip()
    if not cmd:
        raise ValueError("the ticket body carries no proof command")
    expected_main = expected_head = signature = None
    for line in lines[i:i + 6]:
        low = line.strip().lower()
        if low.startswith("expected red signature:"):
            signature = line.split(":", 1)[1].strip() or None
        elif low.startswith("expected on main:"):
            expected_main = line.split(":", 1)[1].strip()
        elif low.startswith("expected on the head:"):
            expected_head = line.split(":", 1)[1].strip()
    return {"cmd": cmd, "expected_main": expected_main, "expected_head": expected_head,
            "signature": signature}


def _resolve(repo_dir, ref):
    proc = subprocess.run(["git", "-C", repo_dir, "rev-parse", "--verify", "--end-of-options",
                           f"{ref}^{{commit}}"], capture_output=True, text=True)
    sha = proc.stdout.strip()
    if proc.returncode or not SHA.match(sha):
        print(f"proof_run: cannot resolve {ref!r} to a commit in {repo_dir}", file=sys.stderr)
        raise SystemExit(2)
    return sha


def _execute(cmd, cwd, env):
    proc = subprocess.Popen(["sh", "-c", cmd], cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        output, _ = proc.communicate(timeout=TIMEOUT)
        return proc.returncode, output, False
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        output, _ = proc.communicate()
        return 124, output, True


def run(mode, repo_dir, ref, cmd, signature=None, record=None):
    sha = _resolve(repo_dir, ref)
    tmp = tempfile.mkdtemp(prefix="proof-run-")
    checkout = os.path.join(tmp, "checkout")
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C"}
    for name, key in (("home", "HOME"), ("coordq", "COORDQ_DIR"),
                      ("journal", "COORD_JOURNAL_DIR"), ("tmp", "TMPDIR")):
        env[key] = os.path.join(tmp, name)
        os.makedirs(env[key], exist_ok=True)
    try:
        subprocess.run(["git", "-C", repo_dir, "worktree", "add", "--detach", checkout, sha],
                       check=True, capture_output=True, text=True)
        code, output, timed_out = _execute(cmd, checkout, env)
    finally:
        subprocess.run(["git", "-C", repo_dir, "worktree", "remove", "--force", checkout],
                       capture_output=True, text=True)
        shutil.rmtree(tmp, ignore_errors=True)
    matched = bool(re.search(signature, output)) if signature else None
    if timed_out:
        state = "unresolved"
    elif mode == "red":
        state = "red" if code != 0 and (signature is None or matched) else "unresolved"
    else:
        state = "green" if code == 0 else "unresolved"
    result = {"state": state, "exit": code, "matched": matched, "ref": sha}
    if record:
        block = (f"## Proof run: {mode} {sha}\n\n```sh\n{cmd}\n```\n\n"
                 f"```\n{output[-4000:]}\n```\n\n{json.dumps(result)}\n")
        with open(record, "a", encoding="utf-8") as handle:
            handle.write(block)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("red", "green"))
    parser.add_argument("--repo-dir", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--cmd", required=True)
    parser.add_argument("--signature")
    parser.add_argument("--record")
    args = parser.parse_args(argv)
    result = run(args.mode, args.repo_dir, args.ref, args.cmd, args.signature, args.record)
    print(json.dumps(result))
    return 0 if result["state"] == args.mode else 1


if __name__ == "__main__":
    sys.exit(main())
