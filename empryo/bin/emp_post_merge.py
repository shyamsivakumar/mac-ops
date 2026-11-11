"""Post-merge live sync for a merged pull request.

Fast-forwards the repository's live main checkout under ~/Code, runs the
repository's declared install step, and copies the declared config files that
the merge changed into ~/.empryo. Every step is best effort: a skipped or
failed step is reported, never raised, so a merge is never undone by it.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

GIT_TIMEOUT = 60
INSTALL_TIMEOUT = 300
REASON_LIMIT = 300
REPO_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
CHECKOUT_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")
CONFIG_DIR = "empryo/config"
NEVER_SYNCED = ("routing.json", "config.json", "tickets.json")


def _reason(text):
    """A short single-line reason that is safe to keep in the merge record."""
    return " ".join(str(text or "").split())[:REASON_LIMIT]


def _git(checkout, *args, timeout=GIT_TIMEOUT):
    """Run git in the checkout without ever prompting for credentials."""
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    environment.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True,
                          timeout=timeout, check=False, env=environment, stdin=subprocess.DEVNULL)


def _origin_repo(url):
    """The owner/name a GitHub remote points at, or None when it points elsewhere."""
    url = (url or "").strip()
    if url.endswith(".git"):
        url = url[:-4]
    url = url.rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "ssh://git@github.com/", "git@github.com:"):
        if url.lower().startswith(prefix):
            url = url[len(prefix):]
            break
    else:
        return None
    parts = url.split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return parts[0].lower() + "/" + parts[1].lower()


def _decision(output):
    """The decision an install script printed as JSON, when it printed one."""
    decoder = json.JSONDecoder()
    index = output.find("{")
    while index >= 0:
        try:
            data, _ = decoder.raw_decode(output[index:])
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("decision"):
            return data
        index = output.find("{", index + 1)
    return {}


def _install(checkout, command, timeout):
    """Run the declared install step and report what it decided.

    A deferral (exit 75) is not a failure: the machine was busy and the owner
    retries on its next firing.
    """
    argv = [str(part).replace("{checkout}", str(checkout)).replace("{python}", sys.executable)
            for part in command]
    try:
        run = subprocess.run(argv, cwd=str(checkout), capture_output=True, text=True, timeout=timeout,
                             check=False, stdin=subprocess.DEVNULL,
                             env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    except subprocess.TimeoutExpired:
        return {"status": "failed", "reason": "the install step timed out"}
    except OSError as e:
        return {"status": "failed", "reason": _reason(e)}
    data = _decision(run.stdout)
    decision = data.get("decision")
    reason = _reason(data.get("reason"))
    if decision == "deferred" or run.returncode == 75:
        return {"status": "deferred", "decision": decision or "deferred", "reason": reason}
    if decision in ("rolled_back", "error") or run.returncode == 2:
        return {"status": "failed", "decision": decision, "reason": reason}
    if run.returncode == 0:
        return {"status": "ok", "decision": decision}
    return {"status": "failed", "reason": reason or "the install step exited " + str(run.returncode)}


def _sync_config(checkout, home, names, sha, changed):
    """Copy the declared config files the merge changed into ~/.empryo.

    A file the merge did not change is left alone, and the file it replaces is
    kept next to it as <name>.before-<shortsha>.
    """
    synced = []
    for name in names or []:
        record = {"file": name}
        if name not in ("EMPRYO.md", "hooks.json", "agents/code-reviewer.md"):
            record.update({"status": "skipped", "reason": "a merge never syncs this file"})
            synced.append(record)
            continue
        if CONFIG_DIR + "/" + name not in changed:
            record.update({"status": "unchanged", "reason": "not changed by fast-forward"})
            synced.append(record)
            continue
        source = Path(checkout) / CONFIG_DIR / name
        target = Path(home) / ".empryo" / name
        if not source.is_file():
            record.update({"status": "skipped", "reason": "the checkout does not have it"})
            synced.append(record)
            continue
        try:
            if target.exists() and target.read_bytes() == source.read_bytes():
                record.update({"status": "unchanged", "reason": "already current"})
                synced.append(record)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                backup = target.parent / (target.name + ".before-" + str(sha or "")[:7])
                with open(backup, "xb") as out, open(target, "rb") as source_file:
                    shutil.copyfileobj(source_file, out)
                record["backup"] = str(backup)
            temporary = target.parent / (target.name + ".tmp")
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)
            record["status"] = "copied"
        except OSError as e:
            record.update({"status": "failed", "reason": _reason(e)})
        synced.append(record)
    return synced


def post_merge(repo, base, home, config_path=None, changed_files=None):
    """Fast-forward the live checkout of a merged repository and run its install step.

    The report says what the fast-forward did, what the install step decided and
    which config files the merge changed.
    """
    result = {"status": "skipped", "configured": False, "base": base, "fastForward": {"status": "skipped"},
              "install": {"status": "skipped"}, "configSync": []}

    def skip(reason):
        result["reason"] = _reason(reason)
        result["fastForward"]["reason"] = result["reason"]
        result["install"]["reason"] = result["reason"]
        return result

    if base != "main":
        return skip("the pull request did not target main")
    if not REPO_PATTERN.fullmatch(repo):
        return skip("the repository identity is not usable")
    path = Path(config_path or Path(home) / ".empryo" / "post-merge.json")
    try:
        with open(path) as handle:
            config = json.load(handle)
    except FileNotFoundError:
        return skip("there is no post-merge configuration at " + str(path))
    except (OSError, ValueError) as e:
        return skip("the post-merge configuration is unreadable: " + _reason(e))
    if not isinstance(config, dict):
        return skip("the post-merge configuration is not an object")
    entry = None
    for key, value in config.items():
        if isinstance(key, str) and key.lower() == repo.lower() and isinstance(value, dict):
            entry = value
            break
    if entry is None:
        entry = {}
    result["configured"] = True
    name = entry.get("checkout") or repo.split("/")[-1]
    if not CHECKOUT_PATTERN.fullmatch(name) or name in (".", ".."):
        return skip("the configured checkout name is not usable")
    checkout = Path(home) / "Code" / name
    if not (checkout / ".git").is_dir():
        return skip("there is no checkout at " + str(checkout))
    origin = _git(checkout, "config", "--get", "remote.origin.url")
    if origin.returncode != 0:
        return skip("the checkout has no origin remote")
    if _origin_repo(origin.stdout) != repo.lower():
        return skip("the checkout origin does not match " + repo)
    branch = _git(checkout, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch.returncode != 0 or branch.stdout.strip() != "main":
        return skip("the checkout is not on main")
    status = _git(checkout, "status", "--porcelain", "--untracked-files=all")
    if status.returncode != 0:
        return skip("the checkout status is unreadable: " + _reason(status.stderr))
    if status.stdout.strip():
        return skip("the checkout has local changes")
    old_head = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    fetch = _git(checkout, "fetch", "origin", "main")
    if fetch.returncode != 0:
        return skip("fetch failed: " + _reason(fetch.stderr))
    merge = _git(checkout, "merge", "--ff-only", "origin/main")
    if merge.returncode != 0:
        return skip("fast-forward failed: " + _reason(merge.stderr))
    head = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    remote = _git(checkout, "rev-parse", "origin/main").stdout.strip()
    if head != remote:
        return skip("the local main is ahead of origin/main")
    result["fastForward"] = {"status": "ok", "from": old_head[:7], "to": head[:7]}
    command = entry.get("install")
    if command:
        result["install"] = _install(checkout, command, entry.get("timeout", INSTALL_TIMEOUT))
    else:
        result["install"] = {"status": "skipped", "reason": "no install step is declared"}
    if result["install"]["status"] in ("failed", "deferred"):
        result["configSync"] = [{"status": "skipped", "reason": "install did not complete"}]
    elif entry.get("configSync") and changed_files is None:
        result["configSync"] = [{"status": "skipped", "reason": "cannot determine pull request files"}]
    else:
        result["configSync"] = _sync_config(checkout, home, entry.get("configSync"), head, changed_files or [])
    result["status"] = "failed" if result["install"]["status"] == "failed" else "ok"
    return result
