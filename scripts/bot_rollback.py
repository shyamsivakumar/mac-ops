#!/usr/bin/env python3
"""Roll Bot 1 and Bot 2 back to their recorded rollback SHA, then check them.

The promotion path records what it moved each bot from. For a bot whose live
commit is carried by a git ref, that record is GitHub's push history for the
ref: every promotion is a push, and the push keeps the commit the ref held
before it (``before``). The command reads the push that produced the live
commit and takes its ``before`` as the rollback target. It prints the exact
steps for every bot: the live-ref fetch, the precheck, the rollback and the
health check. The dry run is the default and reads only. With ``--execute`` it
runs the rollback and the health check; that is the operator's decision and
this ticket does not run it.

Which bot lives on which ref, which commands roll it back and which URL says
it is healthy are facts about the bots, so they live in one config file,
``config/bot-rollback.json``. The command reads that file and never writes it.

A rollback command holds the token ``{sha}`` where the recorded SHA goes. A
command without that token gets the SHA as its last argument.

The rollback SHA is taken from the config when the config pins one, and from
the ref's push history otherwise. A bot whose rollback SHA cannot be read is
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
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "bot-rollback.json"
CONFIG_SCHEMA_VERSION = 1
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ZERO_SHA = "0" * 40


class ConfigError(Exception):
    """The config is missing, unreadable or does not hold a usable record."""


class Bot:
    """One bot, as the config records it."""

    def __init__(self, bot_id, label, repository, live_ref, rollback_sha,
                 rollback_commands, health_url_env, health_path, health_command,
                 health_must_show_sha, health_sha_field, health_timeout_seconds):
        self.id = bot_id
        self.label = label
        self.repository = repository
        self.live_ref = live_ref
        self.rollback_sha = rollback_sha
        self.rollback_commands = rollback_commands
        self.health_url_env = health_url_env
        self.health_path = health_path
        self.health_command = health_command
        self.health_must_show_sha = health_must_show_sha
        self.health_sha_field = health_sha_field
        self.health_timeout_seconds = health_timeout_seconds


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
        health_must_show_sha = entry.get("healthMustShowSha", False)
        if not isinstance(health_must_show_sha, bool):
            raise ConfigError(f"bot {bot_id}: healthMustShowSha must be true or false")
        health_timeout_seconds = entry.get("healthTimeoutSeconds", 0)
        if not isinstance(health_timeout_seconds, int) or isinstance(health_timeout_seconds, bool):
            raise ConfigError(f"bot {bot_id}: healthTimeoutSeconds must be a whole number of seconds")
        if health_timeout_seconds < 0:
            raise ConfigError(f"bot {bot_id}: healthTimeoutSeconds cannot be negative")
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
                health_must_show_sha,
                _text(entry, "healthShaField", bot_id, required=False) or "sourceSha",
                health_timeout_seconds,
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


def push_history(repo, branch):
    """GitHub's push records for a branch, newest first, as (before, after) pairs.

    Returns None when the history cannot be read.
    """
    code, output = run(
        ["gh", "api", f"repos/{{owner}}/{{repo}}/activity?ref=refs/heads/{branch}&per_page=1",
         "--jq", '.[] | "\(.before) \(.after)"'],
        cwd=repo,
    )
    if code != 0:
        return None
    pairs = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 2 and all(SHA_PATTERN.match(part) for part in parts):
            pairs.append((parts[0], parts[1]))
    return pairs


def live_branch(bot):
    """The branch name behind the live ref, e.g. paper-live for origin/paper-live."""
    return bot.live_ref.split("/", 1)[-1] if bot.live_ref else None


def recorded_rollback_sha(bot, repo, live_sha):
    """The SHA the promotion path moved the bot from, and why it is missing if it is.

    Returns (sha, problem). The promotion is the latest push to the live
    branch; the commit that branch held before that push is the SHA it moved
    the bot from, however many commits the push advanced.
    """
    if bot.rollback_sha:
        return bot.rollback_sha, None
    if not bot.live_ref or not live_sha:
        return None, None
    history = push_history(repo, live_branch(bot))
    if not history:
        return None, f"the push history of {live_branch(bot)} cannot be read"
    before, after = history[0]
    if after != live_sha:
        return None, (
            f"the latest recorded push to {live_branch(bot)} ends at {after}, not at the live "
            f"commit {live_sha}; fetch the ref or pin the rollback SHA in the config"
        )
    if before == ZERO_SHA:
        return None, (
            f"the first push to {live_branch(bot)} created the branch, so it recorded no commit to "
            "roll back to; pin the rollback SHA in the config"
        )
    return before, None


def health_url(bot):
    """The URL that says the bot is healthy, or None when it is not set."""
    if not bot.health_url_env:
        return None
    value = os.environ.get(bot.health_url_env, "").strip()
    if not value:
        return None
    return value.rstrip("/") + bot.health_path


def health_command(bot, reveal=False):
    """The health check for a bot, as the command that runs it.

    The printed form names the variable that holds the URL and never its
    value, because the value may carry credentials. Only the run form
    expands it.
    """
    if bot.health_command:
        return list(bot.health_command)
    url = health_url(bot) if reveal else None
    return ["curl", "-fsS", url if url else f"${bot.health_url_env}{bot.health_path}"]


def redact(bot, text):
    """The text with the bot's health URL and any URL credentials taken out."""
    value = os.environ.get(bot.health_url_env, "").strip() if bot.health_url_env else ""
    if value:
        text = text.replace(value, f"${bot.health_url_env}")
    return re.sub(r"(?<=://)[^/@\s]+@", "", text)


def reported_sha(output, field):
    """The revision the health output reports in the named field, or None."""
    try:
        value = json.loads(output)
    except ValueError:
        return None
    for key in field.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value if isinstance(value, str) else None


def fetch_command(plan):
    """The command that refreshes the live ref from its remote, or None."""
    bot = plan.bot
    if not bot.live_ref or "/" not in bot.live_ref:
        return None
    remote, branch = bot.live_ref.split("/", 1)
    code, output = git(plan.repo, "remote")
    if code != 0 or remote not in output.split():
        return None
    return ["git", "-C", str(plan.repo), "fetch", "-q", remote,
            f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}"]


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
        self.rollback_sha, history_problem = recorded_rollback_sha(bot, repo, self.live_sha)
        self.problems = []
        if not bot.live_ref:
            self.problems.append("no live ref is recorded for this bot")
        elif not self.live_sha:
            self.problems.append(f"the live ref {bot.live_ref} cannot be read")
        if not bot.rollback_commands:
            self.problems.append("no rollback command is recorded for this bot")
        if history_problem:
            self.problems.append(history_problem)
        elif not self.rollback_sha:
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
        """The exact steps for this bot; a step that is not recorded has no command."""
        steps = []
        fetch = fetch_command(self)
        if fetch:
            steps.append(("fetch live ref", fetch))
        if self.live_sha and self.rollback_sha:
            steps.append(
                (
                    "precheck",
                    ["git", "-C", str(self.repo), "merge-base", "--is-ancestor",
                     self.rollback_sha, self.live_sha],
                )
            )
        else:
            steps.append(("precheck", None))
        if self.rollback_sha and self.bot.rollback_commands:
            for command in self.bot.rollback_commands:
                steps.append(("rollback", rollback_command(command, self.rollback_sha)))
        else:
            steps.append(("rollback", None))
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
        shown = shlex.join(command) if command else "not recorded"
        lines.append(f"  step {name}: {shown}")
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


def run_health(plan):
    """Run the health check and wait for the bot to report the rollback SHA.

    A health check that answers before the rollback has landed says nothing
    about the rollback. When the config asks for it, the command keeps asking
    until the bot's deployed-revision field equals the rollback SHA or the
    timeout runs out. Only that field counts: the SHA appearing anywhere else
    in the output, such as a ``previous`` field, proves nothing.
    """
    command = health_command(plan.bot, reveal=True)
    must_match = plan.bot.health_must_show_sha and plan.rollback_sha
    deadline = time.time() + plan.bot.health_timeout_seconds
    code, output = run(command, cwd=plan.repo)
    while must_match and reported_sha(output, plan.bot.health_sha_field) != plan.rollback_sha \
            and time.time() < deadline:
        time.sleep(5)
        code, output = run(command, cwd=plan.repo)
    if must_match and reported_sha(output, plan.bot.health_sha_field) != plan.rollback_sha:
        return 1, output or f"the health check did not report {plan.rollback_sha} in {plan.bot.health_sha_field}"
    return code, output


def execute(plans):
    """Roll each resolved bot back and then check that it is healthy.

    A bot with an unresolved problem is skipped and the run exits non-zero;
    the other bots still run. A failed step stops the run.
    """
    skipped = False
    for plan in plans:
        if plan.problems:
            skipped = True
            for problem in plan.problems:
                print(f"bot-rollback: {plan.bot.id}: {problem}", file=sys.stderr)
            print(f"bot-rollback: {plan.bot.id}: nothing was rolled back", file=sys.stderr)
            continue
        for name, command in plan.steps():
            print(f"bot-rollback: {plan.bot.id}: {name}: {shlex.join(command)}")
            if name == "health check":
                code, output = run_health(plan)
            else:
                code, output = run(command, cwd=plan.repo)
            if output:
                print(redact(plan.bot, output))
            if code == 0 and name == "fetch live ref":
                live = ref_commit(plan.repo, plan.bot.live_ref)
                if live != plan.live_sha:
                    print(
                        f"bot-rollback: {plan.bot.id}: the live ref moved from {plan.live_sha} to "
                        f"{live} after the plan was made; nothing was rolled back",
                        file=sys.stderr,
                    )
                    return 1
            if code != 0:
                print(f"bot-rollback: {plan.bot.id}: {name} failed with exit {code}", file=sys.stderr)
                return 1
    return 1 if skipped else 0


if __name__ == "__main__":
    sys.exit(main())
