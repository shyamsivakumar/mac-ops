#!/usr/bin/env python3
"""Print what a Bot 1 rollback would do. Read-only: it never deploys.

Railway deploys the ``paper-live`` branch of strategy-replay-workbench, so the
Bot 1 production service keeps a deployment history. The newest successful
deployment is production. The rollback SHA is the commit of the newest earlier
deployment that ran a different commit. The command that moves Bot 1 back is
the break-glass rollback of the promotion script, which is printed and never
run. The only external call is one ``railway deployment list``.
"""

import json
import re
import subprocess
import sys
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
        "railway", "deployment", "list", "--project", PROJECT,
        "--environment", ENVIRONMENT, "--service", SERVICE,
        "--limit", str(DEPLOYMENT_LIMIT), "--json",
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
        deployments = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise unreadable from exc
    if not isinstance(deployments, list):
        raise unreadable
    return deployments


def deployment_sha(deployment):
    return (deployment.get("meta") or {}).get("commitHash")


def plan(deployments):
    """Return (production deployment, rollback SHA) from the deployment history."""
    if not isinstance(deployments, list) or any(
        not isinstance(d, dict)
        or not isinstance(d.get("meta", {}), dict)
        or not isinstance(d.get("createdAt", ""), str)
        for d in deployments
    ):
        raise RollbackRecordError("the Bot 1 deployment history contains an invalid record")
    deployments = sorted(
        deployments, key=lambda d: d.get("createdAt", ""), reverse=True
    )
    production = next(
        (d for d in deployments if d.get("status") == "SUCCESS"),
        None,
    )
    if production is None:
        raise RollbackRecordError(
            "no successful Bot 1 production deployment is in the history"
        )
    if not isinstance(production.get("id"), str) or not production["id"].strip():
        raise RollbackRecordError("the production deployment has no ID")
    current_sha = deployment_sha(production)
    if not isinstance(current_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", current_sha):
        raise RollbackRecordError("the production deployment has no valid commit SHA")
    rollback = None
    for deployment in deployments[deployments.index(production) + 1 :]:
        if deployment.get("status") not in ("SUCCESS", "REMOVED"):
            continue
        sha = deployment_sha(deployment)
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
            raise RollbackRecordError("the rollback deployment has no valid commit SHA")
        if sha.lower() != current_sha.lower():
            rollback = sha
            break
    if rollback is None:
        raise RollbackRecordError(
            "no earlier Bot 1 deployment ran a different commit, so no rollback SHA is recorded"
        )
    return production, rollback


def main(load=list_deployments):
    try:
        production, rollback = plan(load())
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
    print(f"production deployment: {production['id']} at {deployment_sha(production)}")
    print(f"would run in {SRW_REPO}: {' '.join(command)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
