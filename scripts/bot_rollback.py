#!/usr/bin/env python3
"""Roll Bot 1 and Bot 2 back to their recorded rollback SHA, then check them.

The promotion path records what it moved each bot from. That record is the
rollback ledger: one file, one entry per bot, holding the SHA the promotion
path rolled back from, the ref that carries the live commit, the command that
puts the bot back on that SHA, and the command that says the bot is healthy.

This command reads that ledger and prints the exact steps for every bot: the
precheck, the rollback and the health check. The dry run is the default and
reads only. With ``--execute`` it runs the rollback and the health check; that
is the operator's decision and this ticket does not run it.

The ledger is written by the promotion path, not by this command. Its schema
is version 1:

    {
      "schemaVersion": 1,
      "bots": [
        {
          "id": "bot1",
          "label": "Bot 1, the paper-live trader",
          "rollbackSha": "<40 hex>",
          "liveRef": "origin/paper-live",
          "rollbackCommand": ["node", "scripts/srw_promote_paper_live.cjs",
                              "--break-glass-rollback"],
          "healthCommand": ["node", "scripts/srw_trader_health.cjs"]
        }
      ]
    }

``rollbackCommand`` and ``healthCommand`` are argument lists without the SHA;
the SHA is appended to the rollback command. Both run in the repository the
ledger belongs to, so relative paths in the commands resolve there.
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

LEDGER_SCHEMA_VERSION = 1
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_SRW_REPO = Path.home() / "Code" / "strategy-replay-workbench"
LEDGER_RELATIVE = Path(".git") / "srw-deploy-receipts" / "rollback.json"


class LedgerError(Exception):
    """The ledger is missing, unreadable or does not hold a usable record."""


class Bot:
    """One bot, as the promotion path recorded it."""

    def __init__(self, bot_id, label, rollback_sha, live_ref, rollback_command, health_command):
        self.id = bot_id
        self.label = label
        self.rollback_sha = rollback_sha
        self.live_ref = live_ref
        self.rollback_command = rollback_command
        self.health_command = health_command


def _command_list(entry, key, bot_id):
    value = entry.get(key)
    if not isinstance(value, list) or not value:
        raise LedgerError(f"bot {bot_id}: {key} must be a non-empty list of arguments")
    for part in value:
        if not isinstance(part, str) or not part:
            raise LedgerError(f"bot {bot_id}: {key} holds an argument that is not a string")
    return list(value)


def parse_ledger(raw):
    """Turn the ledger text into the list of bots it records."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LedgerError(f"the ledger is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LedgerError("the ledger must hold a JSON object")
    version = data.get("schemaVersion")
    if version != LEDGER_SCHEMA_VERSION:
        raise LedgerError(
            f"the ledger schema version is {version!r}, this command reads {LEDGER_SCHEMA_VERSION}"
        )
    bots = data.get("bots")
    if not isinstance(bots, list) or not bots:
        raise LedgerError("the ledger records no bots")
    parsed = []
    seen = set()
    for entry in bots:
        if not isinstance(entry, dict):
            raise LedgerError("every bot in the ledger must be a JSON object")
        bot_id = entry.get("id")
        if not isinstance(bot_id, str) or not bot_id:
            raise LedgerError("every bot in the ledger needs a string id")
        if bot_id in seen:
            raise LedgerError(f"the ledger records bot {bot_id} twice")
        seen.add(bot_id)
        rollback_sha = entry.get("rollbackSha")
        if not isinstance(rollback_sha, str) or not SHA_PATTERN.match(rollback_sha):
            raise LedgerError(f"bot {bot_id}: rollbackSha must be a 40 character commit SHA")
        live_ref = entry.get("liveRef")
        if live_ref is not None and (not isinstance(live_ref, str) or not live_ref):
            raise LedgerError(f"bot {bot_id}: liveRef must be a string when it is present")
        label = entry.get("label")
        if label is not None and not isinstance(label, str):
            raise LedgerError(f"bot {bot_id}: label must be a string when it is present")
        parsed.append(
            Bot(
                bot_id,
                label or bot_id,
                rollback_sha,
                live_ref,
                _command_list(entry, "rollbackCommand", bot_id),
                _command_list(entry, "healthCommand", bot_id),
            )
        )
    return parsed


def read_ledger(path):
    """Read the ledger at path and return the bots it records."""
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LedgerError(f"the ledger cannot be read: {exc}") from exc
    return parse_ledger(raw)


def run(command, cwd=None, timeout=60):
    """Run a command and return its exit code and its output."""
    try:
        result = subprocess.run(
            [str(part) for part in command],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()


def live_sha(repo, ref):
    """The commit the live ref points at, or None when it cannot be read."""
    code, output = run(["git", "-C", str(repo), "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=repo)
    if code != 0:
        return None
    sha = output.strip().splitlines()[-1].strip() if output.strip() else ""
    return sha if SHA_PATTERN.match(sha) else None


def commit_known(repo, sha):
    """True when the checkout holds that commit."""
    code, _ = run(["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"], cwd=repo)
    return code == 0


def steps_for(bot, repo, current):
    """The exact steps for one bot: precheck, rollback, health check."""
    steps = []
    if bot.live_ref and current:
        steps.append(
            (
                "precheck",
                ["git", "-C", str(repo), "merge-base", "--is-ancestor", bot.rollback_sha, current],
            )
        )
    steps.append(("rollback", bot.rollback_command + [bot.rollback_sha]))
    steps.append(("health check", list(bot.health_command)))
    return steps


def describe(bot, repo, current):
    """The lines the dry run prints for one bot."""
    lines = [f"{bot.label} ({bot.id})", f"  recorded rollback SHA: {bot.rollback_sha}"]
    if bot.live_ref:
        if current:
            lines.append(f"  current live commit:   {bot.live_ref} = {current}")
        else:
            lines.append(f"  current live commit:   {bot.live_ref} = unknown")
    else:
        lines.append("  current live commit:   not recorded")
    for name, command in steps_for(bot, repo, current):
        lines.append(f"  step {name}: {shlex.join(command)}")
    return lines


def report_missing(bot, repo, lines):
    """Note the recorded SHA when the checkout does not hold it."""
    if not commit_known(repo, bot.rollback_sha):
        lines.append(
            f"  note: this checkout does not hold {bot.rollback_sha}; the rollback needs a checkout that does"
        )
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="Roll the bots back to their recorded rollback SHA")
    parser.add_argument("--dry-run", action="store_true", help="print the steps and change nothing (default)")
    parser.add_argument("--execute", action="store_true", help="run the rollback and the health check")
    parser.add_argument("--bot", help="roll back one bot, by id")
    parser.add_argument("--srw-repo", type=Path, default=DEFAULT_SRW_REPO, help="the repository the bots live in")
    parser.add_argument("--ledger", type=Path, help="the rollback ledger (default: the repository's receipts folder)")
    args = parser.parse_args(argv)
    if args.dry_run and args.execute:
        parser.error("--dry-run and --execute cannot both be given")

    repo = Path(args.srw_repo)
    ledger_path = args.ledger or (repo / LEDGER_RELATIVE)
    try:
        bots = read_ledger(ledger_path)
    except LedgerError as exc:
        print(f"bot-rollback: {exc}", file=sys.stderr)
        return 1
    if args.bot:
        bots = [bot for bot in bots if bot.id == args.bot]
        if not bots:
            print(f"bot-rollback: the ledger records no bot {args.bot}", file=sys.stderr)
            return 1

    if args.execute:
        return execute(bots, repo)
    return dry_run(bots, repo, ledger_path)


def dry_run(bots, repo, ledger_path):
    """Print the exact steps for each bot and change nothing."""
    print(f"bot-rollback: dry run; the ledger is {ledger_path}")
    failures = 0
    for bot in bots:
        current = live_sha(repo, bot.live_ref) if bot.live_ref else None
        lines = describe(bot, repo, current)
        report_missing(bot, repo, lines)
        if bot.live_ref and current:
            code, _ = run(
                ["git", "-C", str(repo), "merge-base", "--is-ancestor", bot.rollback_sha, current],
                cwd=repo,
            )
            if code != 0:
                lines.append("  note: the recorded SHA is not an ancestor of the live commit")
                failures += 1
        for line in lines:
            print(line)
    return 1 if failures else 0


def execute(bots, repo):
    """Roll each bot back and then check that it is healthy."""
    failures = 0
    for bot in bots:
        current = live_sha(repo, bot.live_ref) if bot.live_ref else None
        for name, command in steps_for(bot, repo, current):
            print(f"bot-rollback: {bot.id}: {name}: {shlex.join(command)}")
            code, output = run(command, cwd=repo, timeout=300)
            if output:
                print(output)
            if code != 0:
                print(f"bot-rollback: {bot.id}: {name} failed with exit {code}", file=sys.stderr)
                failures += 1
                break
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
