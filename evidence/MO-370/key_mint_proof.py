#!/usr/bin/env python3
"""Proof for MO-370: the ticket CLI mints the key when it opens a ticket.

The run is hermetic. A fake `gh` on PATH answers the paged issue list and
records the issue create, so nothing touches GitHub.

    python3 evidence/MO-370/key_mint_proof.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TICKET = ROOT / "coordinator" / "bin" / "ticket"

# The fake gh reads the issue history out of FAKE_GH_PAGES: one JSON file per
# page, served in order. A page with fewer than 100 issues ends the list.
FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
log = os.environ["FAKE_GH_LOG"]
if args[:2] == ["issue", "list"]:
    print(json.dumps(json.load(open(os.environ["FAKE_GH_ISSUES"]))))
elif args[:1] == ["api"]:
    page = int(args[1].split("page=")[-1].split("&")[0])
    path = os.path.join(os.environ["FAKE_GH_PAGES"], f"page-{page}.json")
    if os.path.exists(path):
        print(open(path).read())
    else:
        print("[]")
elif args[:2] == ["issue", "create"]:
    with open(log, "a") as handle:
        handle.write(json.dumps(args) + "\\n")
    print("https://github.com/fixture/repo/issues/999")
else:
    sys.stderr.write("unexpected gh call: " + " ".join(args) + "\\n")
    sys.exit(1)
"""


def write_page(pages_dir, page, rows):
    (pages_dir / f"page-{page}.json").write_text(json.dumps(rows))


def run_ticket(env, args):
    result = subprocess.run([sys.executable, str(TICKET)] + args, capture_output=True, text=True, env=env)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def main():
    failures = []

    def check(name, ok, detail):
        print(f"[{'PASS' if ok else 'FAIL'}] {name} -> {detail}")
        if not ok:
            failures.append(name)

    with tempfile.TemporaryDirectory(prefix="mo-370-proof-") as tmp:
        tmp = Path(tmp)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "gh"
        fake.write_text(FAKE_GH)
        fake.chmod(0o755)
        log = tmp / "gh.log"
        pages = tmp / "pages"
        pages.mkdir()
        # Page 1 holds the recent tickets, page 2 the older ones, and a pull
        # request whose title carries a key that is not a ticket.
        first_page = [
            {"number": 41, "title": "MO-1016 · the last keyed ticket"},
            {"number": 42, "title": "a ticket with no key at all"},
            {"number": 43, "title": "MO-1017 · a key that is already taken"},
            {"number": 44, "title": "MO-5000 · a pull request title, not a ticket", "pull_request": {"url": "x"}},
        ]
        # The API fills a page with 100 issues and only the last page is short.
        first_page += [{"number": 100 + i, "title": f"filler {i}"} for i in range(96)]
        write_page(pages, 1, first_page)
        write_page(pages, 2, [
            {"number": 12, "title": "MO-5001 · an older ticket on a later page"},
        ])
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
               "FAKE_GH_LOG": str(log), "FAKE_GH_PAGES": str(pages),
               "TICKET_CACHE": str(tmp / "cache")}

        # 1. A keyless title is keyed past every key the repo uses, on any page.
        code, out, err = run_ticket(env, ["open", "--repo", "shyamsivakumar/mac-ops",
                                          "--title", "Prove that a keyless title is keyed", "--dry-run"])
        plan = json.loads(out) if out else {}
        ok = code == 0 and plan.get("title") == "MO-5002 · Prove that a keyless title is keyed"
        check("keyless title dry run", ok, out or err)

        # 2. A keyed title passes as it is, and nothing is opened in a dry run.
        code, out, err = run_ticket(env, ["open", "--repo", "shyamsivakumar/mac-ops",
                                          "--title", "MO-5020 · a title that brings its own key", "--dry-run"])
        plan = json.loads(out) if out else {}
        ok = code == 0 and plan.get("key") == "MO-5020"
        check("keyed title dry run", ok, out or err)

        # 3. A key that is already taken on a later page is refused.
        code, out, err = run_ticket(env, ["open", "--repo", "shyamsivakumar/mac-ops",
                                          "--title", "MO-5001 · an older ticket on a later page", "--dry-run"])
        ok = code == 2 and "already used by issue #12" in err
        check("taken key on a later page refused", ok, err or out)

        # 4. A key from another repo is refused.
        code, out, err = run_ticket(env, ["open", "--repo", "shyamsivakumar/mac-ops",
                                          "--title", "SRW-900 · the wrong repo's key", "--dry-run"])
        ok = code == 2 and "does not match repo key MO" in err
        check("wrong key prefix refused", ok, err or out)

        # 5. --require-key refuses a keyless title with a clear message.
        code, out, err = run_ticket(env, ["open", "--repo", "shyamsivakumar/mac-ops",
                                          "--title", "A title with no key", "--require-key", "--dry-run"])
        ok = code == 2 and "missing key in title" in err
        check("require-key refused", ok, err or out)

        # 6. The real create writes the minted title and always a body.
        code, out, err = run_ticket(env, ["open", "--repo", "shyamsivakumar/mac-ops",
                                          "--title", "Prove that a keyless title is keyed",
                                          "--label", "stage:todo,type:chore,priority:3"])
        created = log.read_text().strip().splitlines() if log.exists() else []
        args = json.loads(created[-1]) if created else []
        ok = (code == 0 and args[:4] == ["issue", "create", "-R", "shyamsivakumar/mac-ops"]
              and "MO-5002 · Prove that a keyless title is keyed" in args
              and "stage:todo,type:chore,priority:3" in args)
        check("create wrote the minted title", ok, created[-1] if created else err)
        ok = args.count("--body") == 1
        check("create always sends a body", ok, " ".join(args))

        # 7. A repo that is not in tickets.json is refused.
        code, out, err = run_ticket(env, ["open", "--repo", "someone/else", "--title", "No key here", "--dry-run"])
        ok = code == 2 and "not configured in tickets.json" in err
        check("unknown repo refused", ok, err or out)

        # 8. A history that never ends is refused, so a key is never minted
        #    from a list that may be short.
        endless = tmp / "endless"
        endless.mkdir()
        for page in range(1, 205):
            write_page(endless, page, [{"number": page * 100 + i, "title": f"MO-{page * 100 + i} · an endless history"}
                                       for i in range(100)])
        env2 = {**env, "FAKE_GH_PAGES": str(endless)}
        code, out, err = run_ticket(env2, ["open", "--repo", "shyamsivakumar/mac-ops",
                                           "--title", "A title past an endless history", "--dry-run"])
        ok = code == 2 and "cannot be checked" in err
        check("an unreadable history is refused", ok, err or out)

    print("MO-370 key mint proof:", "passed" if not failures else f"failed: {', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
