import datetime
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = {
    "main": ("git", "rev-parse", "origin/main"),
    "github": ("gh", "api", "repos/shyamsivakumar/mac-ops/commits/main", "--jq", ".sha"),
    "t3": ("t3mcp", "call", "t3_thread_list", '{"limit":1}'),
}


class SmokeFailure(Exception):
    pass


def read(command, runner=subprocess.run):
    if tuple(command) not in COMMANDS.values():
        raise SmokeFailure("command denied")
    try:
        result = runner(list(command), cwd=ROOT, capture_output=True, text=True,
                        timeout=15, check=False)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise SmokeFailure("service unavailable or timed out") from None
    if result.returncode:
        raise SmokeFailure("read failed (authentication or service unavailable)")
    if len(result.stdout) > 1024 * 1024:
        raise SmokeFailure("response too large")
    return result.stdout.strip()


def smoke(runner=subprocess.run, clock=None):
    stamp = (clock or (lambda: datetime.datetime.now(datetime.timezone.utc)))()
    main = read(COMMANDS["main"], runner)
    remote = read(COMMANDS["github"], runner)
    if not re.fullmatch(r"[0-9a-f]{40}", main) or remote != main:
        raise SmokeFailure("main identity mismatch; fetch origin before retrying")
    try:
        payload = json.loads(read(COMMANDS["t3"], runner))
    except (ValueError, TypeError):
        raise SmokeFailure("invalid T3 response") from None
    if not isinstance(payload, dict) or payload.get("isError") or not isinstance(payload.get("threads"), list):
        raise SmokeFailure("T3 thread list unavailable")
    return stamp.isoformat(), main


def main():
    try:
        for attempt in (1, 2):
            stamp, sha = smoke()
            print(f"PASS live-smoke run={attempt} timestamp={stamp} main={sha}")
    except SmokeFailure as exc:
        print(f"FAIL live-smoke: {exc}")
        return 1
    return 0


def fixture():
    import contextlib
    import io
    from types import SimpleNamespace
    from unittest.mock import patch
    sha = "a" * 40
    calls = []

    def runner(command, **kwargs):
        calls.append(tuple(command))
        assert kwargs == dict(cwd=ROOT, capture_output=True, text=True, timeout=15, check=False)
        outputs = {"main": sha, "github": sha, "t3": '{"threads":[]}'}
        name = next(key for key, value in COMMANDS.items() if value == tuple(command))
        return SimpleNamespace(returncode=0, stdout=outputs[name], stderr="private diagnostic")

    with patch.object(subprocess, "Popen", side_effect=AssertionError("live process forbidden")):
        assert smoke(runner)[1] == sha
        assert calls == list(COMMANDS.values())

        def rejects_writes():
            for command in (("gh", "api", "repos/x/y", "--method", "POST"),
                            ("t3mcp", "call", "t3_thread_send", "{}"),
                            ("t3mcp", "call", "t3_thread_launch", "{}"),
                            ("gh", "pr", "merge"), ("gh", "issue", "close"),
                            ("gh", "issue", "comment"), ("gh", "issue", "edit", "--add-label", "x"),
                            ("git", "push")):
                before = len(calls)
                try:
                    read(command, runner)
                except SmokeFailure:
                    pass
                else:
                    raise AssertionError("write accepted")
                assert len(calls) == before

        rejects_writes()
        with patch(__name__ + ".read", return_value="write accepted"):
            try:
                rejects_writes()
            except AssertionError:
                pass
            else:
                raise AssertionError("negative control accepted disabled allowlist")
        for response in (SimpleNamespace(returncode=1, stdout="secret", stderr="secret"),
                         SimpleNamespace(returncode=0, stdout="secret", stderr="secret")):
            try:
                smoke(lambda *args, **kwargs: response)
            except SmokeFailure as exc:
                assert "secret" not in str(exc)
            else:
                raise AssertionError("invalid service response accepted")
        for output in ('{}', '{"threads":null}', '{"isError":true,"threads":[]}', 'private diagnostic'):
            def bad_t3(command, **kwargs):
                result = runner(command, **kwargs)
                if tuple(command) == COMMANDS["t3"]:
                    result.stdout = output
                return result
            try:
                smoke(bad_t3)
            except SmokeFailure:
                pass
            else:
                raise AssertionError("invalid T3 payload accepted")
        for error in (OSError("private diagnostic"), subprocess.TimeoutExpired("private", 15)):
            def unavailable(*args, **kwargs):
                raise error
            try:
                smoke(unavailable)
            except SmokeFailure as exc:
                assert "private" not in str(exc)
            else:
                raise AssertionError("unavailable service accepted")
        with patch(__name__ + ".smoke", return_value=("fixture-time", sha)) as probe:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                assert main() == 0
            assert probe.call_count == 2
            assert output.getvalue().splitlines() == [
                f"PASS live-smoke run={n} timestamp=fixture-time main={sha}" for n in (1, 2)]
        with patch(__name__ + ".smoke", side_effect=[("fixture-time", sha), SmokeFailure("read failed")]):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                assert main() == 1
            assert output.getvalue().splitlines()[-1] == "FAIL live-smoke: read failed"
