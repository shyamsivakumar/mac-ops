import importlib.util, pathlib, subprocess, sys, tempfile

SRC = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("fc", SRC)
fc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fc)

repo = pathlib.Path(tempfile.mkdtemp(prefix="scope-proof-"))
fc.ROOT = repo


def check(paths, rules):
    if "base" in fc.check_finding_rules.__code__.co_varnames[: fc.check_finding_rules.__code__.co_argcount]:
        return fc.check_finding_rules(paths, rules, base)
    return fc.check_finding_rules(paths, rules)


def sh(*args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


sh("init", "-q", "-b", "main")
sh("config", "user.email", "p@example.invalid")
sh("config", "user.name", "proof")
(repo / "guard.py").write_text('REASON = "git stash is denied"\nx = 1\n')
sh("add", "-A")
sh("commit", "-qm", "base")
base = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
stash = {"id": "no-git-stash", "check": "grep", "paths": "*.py", "pattern": r"\bgit\s+stash\b", "message": "stash"}
whole = dict(stash, id="whole-file", scope="file")

(repo / "guard.py").write_text('REASON = "git stash is denied"\nx = 2\n')
print("unrelated edit, added scope :", check(["guard.py"], [stash]))
print("unrelated edit, file scope  :", check(["guard.py"], [whole]))
(repo / "guard.py").write_text('REASON = "git stash is denied"\nx = 2\nrun("git stash")\n')
print("added stash line            :", check(["guard.py"], [stash]))
try:
    check(["guard.py"], [dict(stash, scope="bogus")])
except ValueError as error:
    print("bad scope                   :", error)
