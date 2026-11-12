#!/usr/bin/env python3
"""One-off: rewrite old ticket ledger markers in GitHub issue comments.

Finds every comment in the repos named by tickets.json that contains
`<!-- empryo-ticket {...} -->`. Dry run (the default) prints counts per repo and
the comment ids. `--apply` edits each comment in place, replacing the marker
name and the receipt key `empq` with `coordq`.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

CONFIG_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "coordinator/config/tickets.json",
    Path.home() / ".coordinator/tickets.json",
)
OLD_MARKER = re.compile(r"<!-- empryo-ticket (\{.*?\}) -->")


def gh(args):
    result = subprocess.run(
        ["gh"] + args, capture_output=True, text=True, timeout=120, check=False
    )
    if result.returncode != 0:
        sys.exit(f"gh {' '.join(args[:3])} failed: {result.stderr.strip()}")
    return result.stdout


def repos():
    for path in CONFIG_CANDIDATES:
        if path.exists():
            return list(json.loads(path.read_text())["repos"])
    sys.exit("tickets.json not found")


def comments_with_old_marker(repo):
    out = gh(
        [
            "api",
            "--paginate",
            f"repos/{repo}/issues/comments?per_page=100",
            "--jq",
            ".[] | {id, body, login: .user.login, url: .issue_url}",
        ]
    )
    found = []
    for line in out.splitlines():
        comment = json.loads(line)
        if OLD_MARKER.search(comment["body"] or ""):
            found.append(comment)
    return found


def migrate(body):
    def rewrite(match):
        entry = json.loads(match.group(1))
        if "empq" in entry:
            entry = {
                ("coordq" if key == "empq" else key): value
                for key, value in entry.items()
            }
        return f"<!-- coordinator-ticket {json.dumps(entry, separators=(',', ':'))} -->"

    return OLD_MARKER.sub(rewrite, body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (the default)")
    mode.add_argument("--apply", action="store_true", help="edit the comments in place")
    args = parser.parse_args()
    total = 0
    for repo in repos():
        found = comments_with_old_marker(repo)
        total += len(found)
        print(
            f"{repo}: {len(found)} comments with the old marker"
            + (f" ids {[c['id'] for c in found]}" if found else "")
        )
        if not args.apply:
            continue
        for comment in found:
            gh(
                [
                    "api",
                    "-X",
                    "PATCH",
                    f"repos/{repo}/issues/comments/{comment['id']}",
                    "-f",
                    f"body={migrate(comment['body'])}",
                ]
            )
            print(f"  edited {comment['id']}")
    print(
        f"total: {total} comments"
        + ("" if args.apply else " (dry run, nothing edited)")
    )


if __name__ == "__main__":
    main()
