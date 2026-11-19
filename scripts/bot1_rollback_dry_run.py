#!/usr/bin/env python3
"""Print what a Bot 1 rollback would do. Read-only: it never deploys.

Railway deploys the ``paper-live`` branch of strategy-replay-workbench, so the
Bot 1 production service keeps a deployment history. The newest successful
deployment is production. The rollback SHA is the commit of the newest earlier
deployment that ran a different commit. If an earlier deployment in between has
no usable commit, the run stops: that deployment could be the real rollback
target. The command that moves Bot 1 back is the break-glass rollback of the
promotion script, which is printed and never run. The only external call is one
``railway deployment list``.
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT = "7eee29d1-22a7-42a4-aec0-8e8552c864c5"
ENVIRONMENT = "89f6e6f6-9390-4743-8719-189c6fe8624e"
SERVICE = "1b9388df-b470-4b35-8320-6910d2846a34"
SRW_REPO = Path.home() / "Code" / "strategy-replay-workbench"
DEPLOYMENT_LIMIT = 50


class RollbackRecordError(Exception):
    """The deployment history does not hold a usable rollback record."""


def list_deployments():
    command = [
        "railway",
        "deployment",
        "list",
        "--project",
        PROJECT,
        "--environment",
        ENVIRONMENT,
        "--service",
        SERVICE,
        "--limit",
        str(DEPLOYMENT_LIMIT),
        "--json",
    ]
    unreadable = RollbackRecordError(
        "the Bot 1 deployment history cannot be read from Railway"
    )
    try:
        result = subprocess.run(
            command, text=True, capture_output=True, timeout=120, check=False
        )
        if result.returncode != 0:
            raise unreadable
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise unreadable from exc


def read_record(deployment):
    """Return (created, status, id, sha) for one deployment; sha is None when unusable."""
    invalid = RollbackRecordError(
        "the Bot 1 deployment history contains an invalid record"
    )
    if not isinstance(deployment, dict) or not isinstance(deployment.get("meta"), dict):
        raise invalid
    try:
        created = datetime.fromisoformat(deployment["createdAt"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError):
        raise invalid from None
    if created.tzinfo is None:
        raise invalid
    sha = deployment["meta"].get("commitHash")
    if not (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)):
        sha = None
    return created, deployment.get("status"), deployment.get("id"), sha


def plan(deployments):
    """Return (production deployment id, production SHA, rollback SHA), newest first."""
    if not isinstance(deployments, list):
        raise RollbackRecordError("the Bot 1 deployment history is not a list")
    records = sorted(map(read_record, deployments), key=lambda r: r[0], reverse=True)
    production = next((i for i, r in enumerate(records) if r[1] == "SUCCESS"), None)
    if production is None:
        raise RollbackRecordError(
            "no successful Bot 1 production deployment is in the history"
        )
    _, _, deployment_id, current_sha = records[production]
    if not isinstance(deployment_id, str) or not deployment_id or current_sha is None:
        raise RollbackRecordError(
            "the production deployment has no ID or no valid commit SHA"
        )
    for _, status, _, sha in records[production + 1 :]:
        if status not in ("SUCCESS", "REMOVED"):
            continue
        if sha is None:
            raise RollbackRecordError(
                "an earlier Bot 1 deployment has no valid commit SHA, so the rollback SHA cannot be trusted"
            )
        if sha != current_sha:
            return deployment_id, current_sha, sha
    raise RollbackRecordError(
        "no earlier Bot 1 deployment ran a different commit, so no rollback SHA is recorded"
    )


def main(load=list_deployments):
    try:
        deployment_id, current_sha, rollback = plan(load())
    except RollbackRecordError as exc:
        print(f"bot1-rollback-dry-run: {exc}", file=sys.stderr)
        return 1
    command = [
        "node",
        "scripts/srw_promote_paper_live.cjs",
        "--break-glass-rollback",
        rollback,
    ]
    print("bot1-rollback-dry-run: nothing was deployed and no state was written")
    print(f"recorded rollback SHA: {rollback}")
    print(f"production deployment: {deployment_id} at {current_sha}")
    print(f"would run in {SRW_REPO}: {' '.join(command)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
