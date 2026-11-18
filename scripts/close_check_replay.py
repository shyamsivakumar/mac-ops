#!/usr/bin/env python3
"""Replay the close checklist on merged pull requests.

The checklist reads a merged pull request and its ticket and answers four
questions: is the diff inside the ticket's scope, does the pull request
carry a proof file, did every check in that file pass, and does the pull
request carry a cost note once the cost report exists.

This script runs it on the pull requests named on the command line and
prints one report each. A `RESULT: FAIL` line is the work that goes back
to its builder; the ticket stays open.
"""
import argparse
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "coordinator", "bin")
if BIN not in sys.path:
    sys.path.insert(0, BIN)


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replay the close checklist on merged pull requests.")
    parser.add_argument("--repo", default="shyamsivakumar/mac-ops")
    parser.add_argument("--pr", required=True, type=int, action="append",
                        help="a merged pull request number; repeat for more")
    args = parser.parse_args(argv)
    close_check = load(os.path.join(BIN, "close_check.py"), "close_check")
    failed = 0
    for pr in args.pr:
        try:
            result = close_check.run_check(args.repo, pr)
        except RuntimeError as exc:
            print(f"close check: {args.repo}#{pr} could not be read: {exc}")
            failed += 1
            continue
        print(f"close check: {args.repo}#{pr} (merge {result['merge'][:12]})")
        for item in result["items"]:
            print(f"{item['item']}: {item['status']} - {item['detail']}")
        target = f" {args.repo}#{result['issue']}" if result["issue"] is not None else ""
        failed_items = close_check.blocking(result["items"])
        print(f"RESULT: {'FAIL' if failed_items else 'PASS'}{target}")
        if failed_items:
            print("The work goes back to its builder and the ticket stays open.")
        print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
