#!/usr/bin/env python3
import argparse
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

LOGS_DB = Path.home() / ".codex" / "logs_2.sqlite"
HOST = re.compile(r"/codex (?:.* )?app-server .*thread_unload_delay_secs=0")
SERVERS = (
    ("pen", re.compile(r"/mcp-server-darwin-arm64( |$)")),
    ("paper", re.compile(r"/paper mcp$")),
    ("node_repl", re.compile(r"/cua_node/bin/node_repl( |$)")),
    ("xcodebuildmcp", re.compile(r"(npm exec xcodebuildmcp|/xcodebuildmcp mcp$)")),
)
MATCH_WINDOW_SECS = 3


def snapshot():
    out = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,lstart=,command="], capture_output=True, text=True, check=True
    ).stdout
    procs = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\s+(\d+)\s+(\w{3} \w{3}\s+\d+ [\d:]{8} \d{4})\s+(.*)", line)
        pid, ppid, lstart, command = m.groups()
        procs[int(pid)] = {
            "ppid": int(ppid),
            "start": int(time.mktime(time.strptime(re.sub(r"\s+", " ", lstart), "%a %b %d %H:%M:%S %Y"))),
            "command": command,
        }
    return procs


def server_name(command):
    return next((name for name, pattern in SERVERS if pattern.search(command)), None)


def descendants(procs, pid):
    kids = [p for p, info in procs.items() if info["ppid"] == pid]
    return kids + [d for k in kids for d in descendants(procs, k)]


def mcp_sets(procs, host_pid):
    sets = {}
    for pid, info in procs.items():
        if info["ppid"] == host_pid and server_name(info["command"]):
            sets.setdefault(info["start"], []).append(pid)
    return {
        start: sorted({m for pid in pids for m in [pid, *descendants(procs, pid)]})
        for start, pids in sets.items()
    }


def host_threads(host_pid):
    db = sqlite3.connect(f"file:{LOGS_DB}?mode=ro", uri=True)
    rows = db.execute(
        "SELECT thread_id, MIN(ts), MAX(ts), MAX(feedback_log_body LIKE '%Agent loop exited%')"
        " FROM logs WHERE process_uuid LIKE ? AND thread_id IS NOT NULL GROUP BY thread_id",
        (f"pid:{host_pid}:%",),
    ).fetchall()
    return [{"id": r[0], "first": r[1], "last": r[2], "exited": bool(r[3])} for r in rows]


def classify(set_start, threads):
    matches = [t for t in threads if abs(t["first"] - set_start) <= MATCH_WINDOW_SECS]
    if not matches:
        return "unknown", "-"
    ids = ",".join(t["id"] for t in matches)
    if all(t["exited"] for t in matches):
        return "stale-looking", ids
    return "live", ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="accepted for the ticket proof command; this tool only reports")
    parser.parse_args()
    procs = snapshot()
    hosts = [pid for pid, info in procs.items() if HOST.search(info["command"])]
    if not hosts:
        print("mcp_reaper: no codex app-server host found", file=sys.stderr)
        return 2
    keep = stale = unknown = 0
    for host in hosts:
        try:
            threads = host_threads(host)
        except sqlite3.Error as e:
            print(f"mcp_reaper: cannot read {LOGS_DB}: {e}", file=sys.stderr)
            return 2
        for start, pids in sorted(mcp_sets(procs, host).items()):
            verdict, thread_ids = classify(start, threads)
            names = ",".join(f"{server_name(procs[p]['command']) or 'child'}:{p}" for p in pids)
            print(f"{verdict} host={host} set_start={time.strftime('%H:%M:%S', time.localtime(start))} thread={thread_ids} {names}")
            if verdict == "stale-looking":
                stale += 1
            elif verdict == "live":
                keep += 1
            else:
                unknown += 1
    print(f"mcp_reaper: stale_looking_sets={stale} live_sets={keep} unknown_sets={unknown} (report only, nothing signalled)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
