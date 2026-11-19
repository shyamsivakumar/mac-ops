#!/usr/bin/env python3
"""Roll Bot 1 and Bot 2 back to their recorded rollback SHA, then check them.

The promotion path records what it moved each bot from. For a bot whose live
commit is carried by a git ref, that record is the ref's own history: the
promotion path pushes the new commit to the ref, so the commit before it is
the rollback target the path moved from. The command reads that record and
prints the exact steps for every bot: the precheck, the rollback and the
health check. The dry run is the default and reads only. With ``--execute`` it
runs the rollback and the health check; that is the operator's decision and
this ticket does not run it.

Which bot lives on which ref, which commands roll it back and which URL says
it is healthy are facts about the bots, so they live in one config file,
``config/bot-rollback.json``. The command reads that file and never writes it.

A rollback command holds the token ``{sha}`` where the recorded SHA goes. A
command without that token gets the SHA as its last argument.

The rollback SHA is taken from the config when the config pins one, and from
the ref's history otherwise. A bot whose rollback SHA cannot be read is
reported as unresolved and stops the run: a rollback to a guessed commit is
worse than no rollback.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "bot-rollback.json"
CONFIG_SCHEMA_VERSION = 1
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class ConfigError(Exception):
    """The config is missing, unreadable or does not hold a usable record."""


class Bot:
    """One bot, as the config records it."""

    def __init__(self, bot_id, label, repository, live_ref, rollback_sha,
                 rollback_commands, health_url_env, health_path, health_command):
        self.id = bot_id
        self.label = label
        self.repository = repository
        self.live_ref = live_ref
        self.rollback_sha = rollback_sha
        self.rollback_commands = rollback_commands
        self.health_url_env = health_url_env
        self.health_path = health_path
        self.health_command = health_command


def _text(entry, key, bot_id, required=True):
    value = entry.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigError(f"bot {bot_id}: {key} must be a non-empty string")
    if "\0" in value:
        raise ConfigError(f"bot {bot_id}: {key} holds a NUL byte")
    return value


def _command_list(entry, key, bot_id, required=True):
    value = entry.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, list) or not value:
        raise ConfigError(f"bot {bot_id}: {key} must be a non-empty list of arguments")
    for part in value:
        if not isinstance(part, str) or not part:
            raise ConfigError(f"bot {bot_id}: {key} holds an argument that is not a string")
        if "\0" in part:
            raise ConfigError(f"bot {bot_id}: {key} holds an argument with a NUL byte")
    return list(value)


def _command_lists(entry, key, bot_id):
    """A list of commands, each a list of arguments."""
    value = entry.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise ConfigError(f"bot {bot_id}: {key} must be a non-empty list of commands")
    commands = []
    for command in value:
        if not isinstance(command, list) or not command:
            raise ConfigError(f"bot {bot_id}: every {key} entry must be a non-empty list of arguments")
        for part in command:
            if not isinstance(part, str) or not part:
                raise ConfigError(f"bot {bot_id}: {key} holds an argument that is not a string")
            if "\0" in part:
                raise ConfigError(f"bot {bot_id}: {key} holds an argument with a NUL byte")
        commands.append(list(command))
    return commands


def parse_config(raw):
    """Turn the config text into the list of bots it records."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"the config is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("the config must hold a JSON object")
    version = data.get("schemaVersion")
    if version != CONFIG_SCHEMA_VERSION:
        raise ConfigError(
            f"the config schema version is {version!r}, this command reads {CONFIG_SCHEMA_VERSION}"
        )
    bots = data.get("bots")
    if not isinstance(bots, list) or not bots:
        raise ConfigError("the config records no bots")
    parsed = []
    seen = set()
    for entry in bots:
        if not isinstance(entry, dict):
            raise ConfigError("every bot in the config must be a JSON object")
        bot_id = _text(entry, "id", "unknown")
        if bot_id in seen:
            raise ConfigError(f"the config records bot {bot_id} twice")
        seen.add(bot_id)
        rollback_sha = entry.get("rollbackSha")
        if rollback_sha is not None and (
            not isinstance(rollback_sha, str) or not SHA_PATTERN.match(rollback_sha)
        ):
            raise ConfigError(f"bot {bot_id}: rollbackSha must be a 40 character commit SHA")
        parsed.append(
            Bot(
                bot_id,
                _text(entry, "label", bot_id, required=False) or bot_id,
                _text(entry, "repository", bot_id),
                _text(entry, "liveRef", bot_id, required=False),
                rollback_sha,
                _command_lists(entry, "rollbackCommands", bot_id),
                _text(entry, "healthUrlEnv", bot_id, required=False),
                _text(entry, "healthPath", bot_id, required=False) or "/health",
                _command_list(entry, "healthCommand", bot_id, required=False),
            )
        )
    return parsed


def read_config(path):
    """Read the config at path and return the bots it records."""
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"the config is not valid UTF-8: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"the config cannot be read: {exc}") from exc
    return parse_config(raw)


def run(command, cwd=None, timeout=300):
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


def repository_of(bot):
    """The absolute path of the repository the bot lives in."""
    return Path(os.path.expanduser(bot.repository)).resolve()


def git(repo, *args):
    """Run one git command in the repository and return its exit code and output."""
    return run(["git", "-C", str(repo), *args])


def ref_commit(repo, ref):
    """The commit a ref points at, or None when the ref cannot be read."""
    code, output = git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if code != 0:
        return None
    sha = output.strip().splitlines()[-1].strip() if output.strip() else ""
    return sha if SHA_PATTERN.match(sha) else None


def recorded_rollback_sha(bot, repo):
    """The SHA the promotion path moved the bot from, or None when it is not recorded.

    A ref that the promotion path pushes to keeps its own history: the entry
    before the last one is the commit the path moved the bot from.
    """
    if bot.rollback_sha:
        return bot.rollback_sha
    if not bot.live_ref:
        return None
    code, output = git(repo, "rev-parse", "--verify", f"{bot.live_ref}@{{1}}^{{commit}}")
    if code != 0:
        return None
    sha = output.strip().splitlines()[-1].strip() if output.strip() else ""
    return sha if SHA_PATTERN.match(sha) else None


def health_url(bot):
    """The URL that says the bot is healthy, or None when it is not set."""
    if not bot.health_url_env:
        return None
    value = os.environ.get(bot.health_url_env, "").strip()
    if not value:
        return None
    return value.rstrip("/") + bot.health_path


def health_command(bot):
    """The health check for a bot, as the command that runs it."""
    if bot.health_command:
        return list(bot.health_command)
    url = health_url(bot)
    return ["curl", "-fsS", url if url else f"${bot.health_url_env}{bot.health_path}"]


def rollback_command(command, sha):
    """One rollback command with the recorded SHA in place."""
    if any("{sha}" in part for part in command):
        return [part.replace("{sha}", sha) for part in command]
    return list(command) + [sha]


class Plan:
    """What the command knows about one bot, and what is still missing."""

    def __init__(self, bot, repo):
        self.bot = bot
        self.repo = repo
        self.live_sha = ref_commit(repo, bot.live_ref) if bot.live_ref else None
        self.rollback_sha = recorded_rollback_sha(bot, repo)
        self.problems = []
        if not bot.live_ref:
            self.problems.append("no live ref is recorded for this bot")
        elif not self.live_sha:
            self.problems.append(f"the live ref {bot.live_ref} cannot be read")
        if not bot.rollback_commands:
            self.problems.append("no rollback command is recorded for this bot")
        if not self.rollback_sha:
            self.problems.append("no rollback SHA is recorded for this bot")
        elif not self.known(self.rollback_sha):
            self.problems.append(f"the checkout does not hold {self.rollback_sha}")
        if not bot.health_command:
            if not bot.health_url_env:
                self.problems.append("no health check is recorded for this bot")
            elif not health_url(bot):
                self.problems.append(f"{bot.health_url_env} is not set, so there is no health check")
        if self.rollback_sha and self.live_sha and not self.ancestor():
            self.problems.append(
                f"the recorded rollback SHA {self.rollback_sha} is not an ancestor of the live commit"
            )

    def known(self, sha):
        code, _ = git(self.repo, "cat-file", "-e", f"{sha}^{{commit}}")
        return code == 0

    def ancestor(self):
        code, _ = git(self.repo, "merge-base", "--is-ancestor", self.rollback_sha, self.live_sha)
        return code == 0

    def steps(self):
        """The exact steps for this bot: precheck, rollback, health check."""
        steps = []
        if self.live_sha and self.rollback_sha:
            steps.append(
                (
                    "precheck",
                    ["git", "-C", str(self.repo), "merge-base", "--is-ancestor",
                     self.rollback_sha, self.live_sha],
                )
            )
        if self.rollback_sha and self.bot.rollback_commands:
            for command in self.bot.rollback_commands:
                steps.append(("rollback", rollback_command(command, self.rollback_sha)))
        steps.append(("health check", health_command(self.bot)))
        return steps


def describe(plan):
    """The lines the dry run prints for one bot."""
    bot = plan.bot
    lines = [f"{bot.label} ({bot.id})"]
    lines.append(f"  repository:            {plan.repo}")
    if bot.live_ref:
        live = plan.live_sha or "unknown"
        lines.append(f"  live ref:              {bot.live_ref} = {live}")
    else:
        lines.append("  live ref:              not recorded")
    lines.append(f"  recorded rollback SHA: {plan.rollback_sha or 'not recorded'}")
    for name, command in plan.steps():
        lines.append(f"  step {name}: {shlex.join(command)}")
    for problem in plan.problems:
        lines.append(f"  problem: {problem}")
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description="Roll the bots back to their recorded rollback SHA")
    parser.add_argument("--dry-run", action="store_true", help="print the steps and change nothing (default)")
    parser.add_argument("--execute", action="store_true", help="run the rollback and the health check")
    parser.add_argument("--bot", help="roll back one bot, by id")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="the bot config")
    args = parser.parse_args(argv)
    if args.dry_run and args.execute:
        parser.error("--dry-run and --execute cannot both be given")

    try:
        bots = read_config(args.config)
    except ConfigError as exc:
        print(f"bot-rollback: {exc}", file=sys.stderr)
        return 1
    if args.bot:
        bots = [bot for bot in bots if bot.id == args.bot]
        if not bots:
            print(f"bot-rollback: the config records no bot {args.bot}", file=sys.stderr)
            return 1

    plans = [Plan(bot, repository_of(bot)) for bot in bots]
    if args.execute:
        return execute(plans)
    return dry_run(plans, args.config)


def dry_run(plans, config_path):
    """Print the exact steps for each bot and change nothing."""
    print(f"bot-rollback: dry run; the config is {config_path}")
    problems = 0
    for plan in plans:
        for line in describe(plan):
            print(line)
        problems += len(plan.problems)
    return 1 if problems else 0


def execute(plans):
    """Roll each bot back and then check that it is healthy."""
    for plan in plans:
        if plan.problems:
            for problem in plan.problems:
                print(f"bot-rollback: {plan.bot.id}: {problem}", file=sys.stderr)
            print(f"bot-rollback: {plan.bot.id}: nothing was rolled back", file=sys.stderr)
            return 1
    for plan in plans:
        for name, command in plan.steps():
            print(f"bot-rollback: {plan.bot.id}: {name}: {shlex.join(command)}")
            code, output = run(command, cwd=plan.repo)
            if output:
                print(output)
            if code != 0:
                print(f"bot-rollback: {plan.bot.id}: {name} failed with exit {code}", file=sys.stderr)
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
