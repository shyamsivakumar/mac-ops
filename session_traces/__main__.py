"""CLI: python3 -m session_traces collect|eval|run-daily."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .collect import collect_and_store
from .cost_report import DEFAULT_PI_ROOT, build_report, render
from .eval_day import write_day_report
from .store import day_key, posthog_api_key

LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def _parse_day(value: str | None) -> tuple[datetime, datetime, str]:
    """Return [start, end) UTC covering a local calendar day, plus the day key."""
    if value:
        start_local = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
    else:
        now = datetime.now(LOCAL_TZ)
        start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    day = start_local.strftime("%Y-%m-%d")
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc), day


def _previous_local_day() -> str:
    now = datetime.now(LOCAL_TZ)
    prev = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return prev.strftime("%Y-%m-%d")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="MO-124 session traces and daily evals"
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=None,
        help="Override ~/.local/state/mac-ops",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    collect_p = sub.add_parser("collect", help="Collect scrubbed traces for a day")
    collect_p.add_argument(
        "--day", help="Local calendar day YYYY-MM-DD (default: today)"
    )
    collect_p.add_argument(
        "--no-export",
        action="store_true",
        help="Skip PostHog export even when a key is present",
    )
    collect_p.add_argument(
        "--dry-run-export",
        action="store_true",
        help="Build the PostHog batch but do not POST",
    )

    eval_p = sub.add_parser("eval", help="Score stored traces for a day")
    eval_p.add_argument("--day", help="Local calendar day YYYY-MM-DD (default: today)")
    eval_p.add_argument(
        "--baseline-day",
        help="Prior day JSON to flag regressions against",
    )

    daily = sub.add_parser(
        "run-daily",
        help="Collect previous local day (default), reconcile unfinished, eval",
    )
    daily.add_argument(
        "--day",
        help="Local calendar day YYYY-MM-DD (default: previous local day)",
    )
    daily.add_argument("--no-export", action="store_true")
    daily.add_argument("--baseline-day", default=None)

    cost = sub.add_parser("cost", help="Agent cost per pull request for a local day")
    cost.add_argument("--day", help="Local calendar day YYYY-MM-DD (default: today)")
    cost.add_argument("--pi-root", type=Path, default=DEFAULT_PI_ROOT)
    cost.add_argument("--repo", help="Only pull requests of this owner/name")

    sub.add_parser("status", help="Show store paths and PostHog key presence")

    args = parser.parse_args(argv)

    if args.cmd == "status":
        info = {
            "posthog_key_present": bool(posthog_api_key()),
            "state_root": str(args.state_root)
            if args.state_root
            else str(Path.home() / ".local/state/mac-ops"),
            "local_tz": str(LOCAL_TZ),
        }
        print(json.dumps(info, indent=2))
        return 0

    if args.cmd == "collect":
        start, end, day = _parse_day(args.day)
        result = collect_and_store(
            since=start,
            until=end,
            state_root=args.state_root,
            export=not args.no_export,
            dry_run_export=args.dry_run_export,
        )
        result["day"] = day
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "cost":
        day = args.day or day_key()
        sys.stdout.write(render(build_report(day, args.pi_root, args.repo)))
        return 0

    if args.cmd == "eval":
        day = args.day or day_key()
        result = write_day_report(
            day, root=args.state_root, baseline_day=args.baseline_day
        )
        print(json.dumps(result, indent=2))
        md = Path(result["md"])
        if md.is_file():
            print(md.read_text(encoding="utf-8"))
        return 0

    if args.cmd == "run-daily":
        # Default: previous local day so the 17:30 job covers a finished calendar day.
        day_arg = args.day or _previous_local_day()
        start, end, day = _parse_day(day_arg)
        collect_result = collect_and_store(
            since=start,
            until=end,
            state_root=args.state_root,
            export=not args.no_export,
            reconcile_unfinished=True,
        )
        # Regenerate every day whose traces changed (requested day + reconciled).
        changed_days = list(collect_result.get("days") or [day])
        if day not in changed_days:
            changed_days.insert(0, day)
        eval_results = []
        for d in changed_days:
            if args.baseline_day is not None and d == day:
                baseline = args.baseline_day
            else:
                baseline = (
                    datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=LOCAL_TZ)
                    - timedelta(days=1)
                ).strftime("%Y-%m-%d")
            eval_results.append(
                write_day_report(d, root=args.state_root, baseline_day=baseline)
            )
        primary = next((e for e in eval_results if e["day"] == day), eval_results[0])
        out = {
            "collect": collect_result,
            "eval": primary,
            "evals": eval_results,
            "day": day,
            "days_reported": [e["day"] for e in eval_results],
        }
        # Manifest for daily.sh to copy every regenerated report into evidence.
        from .store import evals_dir as _evals_dir

        manifest_dir = _evals_dir(args.state_root)
        manifest_dir.mkdir(parents=True, exist_ok=True)
        (manifest_dir / "_last_daily.json").write_text(
            json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(out, indent=2))
        md = Path(primary["md"])
        if md.is_file():
            sys.stdout.write(md.read_text(encoding="utf-8"))
        return 0

    parser.error(f"unknown command {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
