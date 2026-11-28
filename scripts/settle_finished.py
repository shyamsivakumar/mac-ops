#!/usr/bin/env python3
import argparse
import collections
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [
    os.path.join(ROOT, "coordinator", "overnight"),
    os.path.join(ROOT, "coordinator", "bin"),
]

import journal
import lane_driver as lane

EXCLUDED = re.compile(r"ascend|slash-eureka", re.IGNORECASE)
BUSY = {"running", "waiting", "queued", "starting", "preparing"}


def fail(reason):
    sys.exit(f"settle_finished: {reason}")


def read_threads():
    threads, cursor = [], 0
    while cursor is not None:
        page = lane.t3(
            "t3_thread_list",
            {
                "allProjects": True,
                "statuses": ["completed"],
                "settled": False,
                "limit": 100,
                "cursor": cursor,
            },
        )
        if not isinstance(page.get("threads"), list):
            fail("the T3 thread list could not be read")
        threads += page["threads"]
        cursor = page.get("nextCursor")
    return threads


def project_roots():
    roots, seen = {}, set()
    cursor = None
    while True:
        args = {"limit": 100}
        if cursor is not None:
            args["cursor"] = cursor
        page = lane.t3("t3_project_list", args)
        projects = page.get("projects") if isinstance(page, dict) else None
        if not isinstance(projects, list):
            fail("the T3 project list could not be read")
        for p in projects:
            roots[p["id"]] = f"{p.get('title', '')} {p.get('workspaceRoot', '')}"
        next_cursor = page.get("nextCursor")
        if not projects or next_cursor is None or next_cursor == "" or next_cursor in seen:
            break
        seen.add(next_cursor)
        cursor = next_cursor
    return roots


def verdict_threads():
    found = set()
    for path in glob.glob(os.path.join(journal.journal_dir(), "events-*.jsonl")):
        with open(path) as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("event") == "gate_verdict" and (row.get("data") or {}).get(
                    "verdict"
                ) in ("PASS", "FAIL"):
                    found.add(row.get("thread"))
    return found


def closed_ticket_threads():
    if not os.path.exists(lane.RECEIPTS):
        fail("the dispatch receipts are missing")
    with open(lane.RECEIPTS) as handle:
        receipts = json.load(handle)
    tickets = {}
    for key, thread in receipts.items():
        found = re.fullmatch(r"ticket:(.+)#(\d+)(?::a\d+)?", key)
        if found and not EXCLUDED.search(found[1]):
            tickets.setdefault(found[1], {}).setdefault(int(found[2]), []).append(
                thread
            )
    closed = set()
    for repo, numbers in tickets.items():
        rows = json.loads(
            lane.run(
                [
                    "gh",
                    "issue",
                    "list",
                    "-R",
                    repo,
                    "--state",
                    "closed",
                    "--limit",
                    "5000",
                    "--json",
                    "number",
                ]
            )
            or "[]"
        )
        for row in rows:
            closed.update(numbers.get(row["number"], ()))
    return closed


def finished_reason(thread, closed, verdicts):
    prs = thread.get("pullRequests") or []
    if prs and all(pr.get("state") != "open" for pr in prs):
        return "pull request merged or closed"
    if thread["threadId"] in closed:
        return "ticket issue closed"
    if thread["threadId"] in verdicts:
        return "gate verdict recorded"
    return None


def skip_reason(thread, roots):
    if thread.get("pinned"):
        return "pinned"
    if thread.get("snoozed"):
        return "snoozed"
    if thread.get("status") in BUSY:
        return "running or waiting"
    if thread.get("blockedOnThreadWait") or thread.get("pendingBackgroundTasks"):
        return "blocked"
    text = " ".join(
        [thread.get("title", ""), roots.get(thread.get("projectId"), "")]
        + [pr.get("repository", "") for pr in thread.get("pullRequests") or []]
    )
    if EXCLUDED.search(text):
        return "Ascend or slash-eureka"
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Settle completed T3 threads whose work is finished."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="count and sample only (the default)"
    )
    mode.add_argument("--apply", action="store_true", help="settle the threads")
    apply = parser.parse_args().apply
    threads, roots = read_threads(), project_roots()
    closed, verdicts = closed_ticket_threads(), verdict_threads()
    picked, skipped, unfinished = [], collections.Counter(), 0
    for thread in threads:
        skip = skip_reason(thread, roots)
        if skip:
            skipped[skip] += 1
            continue
        reason = finished_reason(thread, closed, verdicts)
        if reason:
            picked.append((thread, reason))
        else:
            unfinished += 1
    print(
        f"{'apply' if apply else 'dry run'}: {len(threads)} completed unsettled threads"
    )
    for reason, count in collections.Counter(r for _, r in picked).most_common():
        print(f"  settle: {count:4} {reason}")
    for reason, count in skipped.most_common():
        print(f"  skip:   {count:4} {reason}")
    print(f"  skip:   {unfinished:4} work not finished")
    for thread, reason in picked[:10]:
        print(
            f"  sample: {thread['threadId'][-12:]} {thread.get('title', '')[:60]!r} ({reason})"
        )
    if not apply:
        return 0
    failed = sum(not lane.settle_dead_run(thread["threadId"]) for thread, _ in picked)
    print(f"settled {len(picked) - failed}, failed {failed}")
    return int(bool(failed))


if __name__ == "__main__":
    sys.exit(main())
