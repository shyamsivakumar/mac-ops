"""Unit tests for the agent cost report (no network, no real session).

The fixture is a fake pi home: session logs written into a temporary
directory, and a fake ``gh`` that answers with in-memory pull requests. Every
string in the fixture is synthetic and no real secret is used anywhere.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from session_traces import cost_report
from session_traces.cost_report import (
    PrIndex,
    SessionCost,
    attribute,
    build_report,
    is_refactor,
    read_session,
    render_markdown,
)

REPO = "shyamsivakumar/mac-ops"
OTHER_REPO = "shyamsivakumar/openscan"

OTHER_PRS = [
    {
        "number": 11,
        "title": "Refactor the import path",
        "body": "Refs #6",
        "headRefName": "t3/import-path",
        "state": "MERGED",
        "mergedAt": "2026-11-17T20:00:00Z",
        "createdAt": "2026-11-17T10:00:00Z",
        "url": "https://github.com/shyamsivakumar/openscan/pull/11",
    }
]

PRS = [
    {
        "number": 487,
        "title": "Write down how the board's calls are bounded",
        "body": "Refs #482",
        "headRefName": "t3/bounded-calls",
        "state": "MERGED",
        "mergedAt": "2026-11-17T18:14:00Z",
        "createdAt": "2026-11-17T17:00:00Z",
        "url": "https://github.com/shyamsivakumar/mac-ops/pull/487",
    },
    {
        "number": 501,
        "title": "Rename the lane driver module",
        "body": "Refs #500",
        "headRefName": "t3/rename-lane",
        "state": "MERGED",
        "mergedAt": "2026-11-16T18:00:00Z",
        "createdAt": "2026-11-16T12:00:00Z",
        "url": "https://github.com/shyamsivakumar/mac-ops/pull/501",
    },
]


def _session_file(
    root: Path,
    *,
    name: str,
    stamp: str,
    cwd: str,
    cost: float,
    model: str = "test-model-1",
) -> Path:
    directory = root / "agent" / "sessions" / "worktree"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stamp}_session.jsonl"
    lines = [
        {
            "type": "session",
            "version": 3,
            "id": "session",
            "timestamp": stamp,
            "cwd": cwd,
        },
        {"type": "session_info", "name": name, "timestamp": stamp},
        {
            "type": "message",
            "timestamp": stamp,
            "message": {
                "role": "assistant",
                "model": model,
                "usage": {
                    "input": 100,
                    "output": 200,
                    "cacheRead": 300,
                    "totalTokens": 600,
                    "cost": {
                        "input": cost / 2,
                        "output": cost / 2,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "total": cost,
                        "totalFromProvider": False,
                    },
                },
            },
        },
    ]
    path.write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8"
    )
    return path


def _two_turn_session_file(
    root: Path,
    *,
    name: str,
    first_stamp: str,
    second_stamp: str,
    cwd: str,
    first_cost: float,
    second_cost: float,
) -> Path:
    """A session with one turn before midnight and one turn after it."""
    directory = root / "agent" / "sessions" / "worktree"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{first_stamp}_session.jsonl"

    def turn(stamp: str, cost: float) -> dict:
        return {
            "type": "message",
            "timestamp": stamp,
            "message": {
                "role": "assistant",
                "model": "test-model-1",
                "usage": {
                    "input": 10,
                    "output": 20,
                    "cacheRead": 30,
                    "totalTokens": 60,
                    "cost": {
                        "input": cost / 2,
                        "output": cost / 2,
                        "cacheRead": 0,
                        "cacheWrite": 0,
                        "total": cost,
                        "totalFromProvider": False,
                    },
                },
            },
        }

    lines = [
        {
            "type": "session",
            "version": 3,
            "id": "session",
            "timestamp": first_stamp,
            "cwd": cwd,
        },
        {"type": "session_info", "name": name, "timestamp": first_stamp},
        turn(first_stamp, first_cost),
        turn(second_stamp, second_cost),
    ]
    path.write_text(
        "\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8"
    )
    return path


def _attribution(
    session_id: str,
    cost: float,
    number: int,
    day: str,
    repo: str = "shyamsivakumar/mac-ops",
    title: str | None = None,
) -> cost_report.SessionAttribution:
    """An attributed session for the window tests."""
    session = cost_report.SessionCost(
        session_id=session_id,
        path=f"/tmp/{session_id}.jsonl",
        pi_home="/tmp",
        cwd="/tmp",
        name=None,
        cost_usd=cost,
        day=day,
    )
    return cost_report.SessionAttribution(
        session=session,
        repo=repo,
        pr_number=number,
        pr_title=title,
        pr_merged_at="2026-11-14T02:14:35Z" if number == 259 else None,
    )


class CostReportTests(unittest.TestCase):
    def test_read_session_sums_usage_cost_and_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _session_file(
                root,
                name="MO-482 review #487",
                stamp="2026-11-17T18:00:00.000Z",
                cwd="/tmp/worktree",
                cost=1.25,
            )
            session = read_session(path, root)
        self.assertIsNotNone(session)
        self.assertEqual(session.name, "MO-482 review #487")
        self.assertEqual(session.cwd, "/tmp/worktree")
        self.assertAlmostEqual(session.cost_usd, 1.25)
        self.assertEqual(session.input_tokens, 100)
        self.assertEqual(session.output_tokens, 200)
        self.assertEqual(session.cache_read_tokens, 300)
        self.assertEqual(session.total_tokens, 600)
        self.assertEqual(session.models, ["test-model-1"])

    def test_read_session_skips_a_broken_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _session_file(
                root,
                name="MO-482 review #487",
                stamp="2026-11-17T18:00:00.000Z",
                cwd="/tmp/worktree",
                cost=0.5,
            )
            with path.open("a", encoding="utf-8") as handle:
                handle.write("{not json\n")
            session = read_session(path, root)
        self.assertIsNotNone(session)
        self.assertAlmostEqual(session.cost_usd, 0.5)

    def test_review_name_picks_the_pull_request(self):
        session = SessionCost(
            session_id="s1",
            path="/tmp/s1.jsonl",
            pi_home="/tmp",
            cwd="/tmp",
            name="MO-482 review #487 1dfedc8",
        )
        index = PrIndex()
        index._by_repo[REPO] = PRS
        out = attribute(session, index, repo=REPO)
        self.assertEqual(out.pr_number, 487)
        self.assertEqual(out.kind, "review")
        self.assertEqual(out.pr_key, f"{REPO}#487")

    def test_ticket_name_picks_the_pull_request_that_closes_it(self):
        session = SessionCost(
            session_id="s2",
            path="/tmp/s2.jsonl",
            pi_home="/tmp",
            cwd="/tmp",
            name="MO-482 · Write down how the board's calls are bounded",
        )
        index = PrIndex()
        index._by_repo[REPO] = PRS
        out = attribute(session, index, repo=REPO)
        self.assertEqual(out.pr_number, 487)
        self.assertEqual(out.kind, "ticket")

    def test_a_session_with_no_pull_request_is_unattributed(self):
        session = SessionCost(
            session_id="s3",
            path="/tmp/s3.jsonl",
            pi_home="/tmp",
            cwd="/tmp",
            name="MO-999 · nothing references this issue",
        )
        index = PrIndex()
        index._by_repo[REPO] = PRS
        out = attribute(session, index, repo=REPO)
        self.assertIsNone(out.pr_number)
        self.assertEqual(out.pr_key, "unattributed")
        self.assertTrue(out.reason)

    def test_report_totals_reconcile_with_the_session_totals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _session_file(
                root,
                name="MO-482 review #487",
                stamp="2026-11-17T18:00:00.000Z",
                cwd="/tmp/worktree",
                cost=2.0,
            )
            _session_file(
                root,
                name="MO-999 · nothing references this issue",
                stamp="2026-11-17T19:00:00.000Z",
                cwd="/tmp/worktree",
                cost=1.0,
            )
            original_prs = cost_report.gh_prs
            original_repo = cost_report.repo_of
            original_branch = cost_report.branch_of
            cost_report.gh_prs = lambda repo: list(PRS)
            cost_report.repo_of = lambda cwd: REPO
            cost_report.branch_of = lambda cwd: None
            try:
                report = build_report(
                    "2026-11-17",
                    pi_root=root,
                    before_days=2,
                    after_days=1,
                    repos=[REPO],
                )
            finally:
                cost_report.gh_prs = original_prs
                cost_report.repo_of = original_repo
                cost_report.branch_of = original_branch
        self.assertTrue(report["reconciled"])
        self.assertAlmostEqual(report["total_cost_usd"], 3.0)
        self.assertAlmostEqual(report["attributed_cost_usd"], 2.0)
        self.assertAlmostEqual(report["unattributed_cost_usd"], 1.0)
        self.assertAlmostEqual(
            report["attributed_cost_usd"] + report["unattributed_cost_usd"],
            report["total_cost_usd"],
        )
        self.assertEqual(report["pr_count"], 1)
        self.assertAlmostEqual(report["cost_per_pr_usd"], 2.0)

    def test_a_pull_request_opened_after_the_session_is_not_its_pull_request(self):
        session = SessionCost(
            session_id="s4",
            path="/tmp/s4.jsonl",
            pi_home="/tmp",
            cwd="/tmp",
            name="MO-482 · a ticket that had two pull requests",
            started_at="2026-11-13T12:00:00Z",
        )
        index = PrIndex()
        index._by_repo[REPO] = [
            {
                "number": 900,
                "title": "a later fix for the same ticket",
                "body": "Refs #482",
                "headRefName": "t3/later",
                "state": "OPEN",
                "createdAt": "2026-11-18T00:00:00Z",
                "mergedAt": None,
            },
            {
                "number": 487,
                "title": "the pull request the session worked on",
                "body": "Refs #482",
                "headRefName": "t3/earlier",
                "state": "MERGED",
                "createdAt": "2026-11-12T00:00:00Z",
                "mergedAt": "2026-11-17T18:14:00Z",
            },
        ]
        out = attribute(session, index, repo=REPO)
        self.assertEqual(out.pr_number, 487)
        self.assertEqual(out.kind, "ticket")

    def test_a_session_with_no_pull_request_yet_stays_unattributed(self):
        session = SessionCost(
            session_id="s5",
            path="/tmp/s5.jsonl",
            pi_home="/tmp",
            cwd="/tmp",
            name="MO-482 · a ticket whose pull request came later",
            started_at="2026-11-13T12:00:00Z",
        )
        index = PrIndex()
        index._by_repo[REPO] = [
            {
                "number": 900,
                "title": "a later fix for the same ticket",
                "body": "Refs #482",
                "headRefName": "t3/later",
                "state": "OPEN",
                "createdAt": "2026-11-18T00:00:00Z",
                "mergedAt": None,
            }
        ]
        out = attribute(session, index, repo=REPO)
        self.assertIsNone(out.pr_number)
        self.assertIn("existed when the session ran", out.reason)

    def test_the_window_mean_counts_every_pull_request(self):
        summary = cost_report._window_summary(
            [
                _attribution("a", 1.0, 1, "2026-11-10"),
                _attribution("b", 3.0, 2, "2026-11-10"),
                _attribution("c", 0.0, 3, "2026-11-10"),
            ],
            "shyamsivakumar/mac-ops",
            ["2026-11-10"],
        )
        self.assertEqual(summary["prs"], 3)
        self.assertAlmostEqual(summary["total_cost_usd"], 4.0)
        self.assertAlmostEqual(summary["mean_cost_per_pr_usd"], 4.0 / 3)

    def test_the_before_and_after_windows_use_local_days(self):
        merge = "2026-11-14T02:14:35Z"  # 2026-11-13 18:14 in Los Angeles
        index = PrIndex()
        index._by_repo[REPO] = [
            {
                "number": 259,
                "title": "Refactor the refill log",
                "body": "",
                "headRefName": "t3/refill",
                "state": "MERGED",
                "createdAt": "2026-11-13T00:00:00Z",
                "mergedAt": merge,
            }
        ]
        attributions = [
            _attribution("a", 1.0, 259, "2026-11-13", title="Refactor the refill log"),
            _attribution("b", 2.0, 260, "2026-11-14"),
        ]
        rows = cost_report.refactor_comparison(
            attributions,
            index,
            before_days=2,
            after_days=2,
            collected_days=["2026-11-11", "2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15"],
        )
        self.assertEqual(len(rows), 1)
        # The merge is 2026-11-13 18:14 in Los Angeles, so the days before it
        # are 2026-11-11 and 2026-11-12, and the days after it are 2026-11-14
        # and 2026-11-15. A UTC window would have skipped 2026-11-14.
        self.assertIn("2026-11-12", rows[0]["before"]["days"])
        self.assertIn("2026-11-14", rows[0]["after"]["days"])
        self.assertNotIn("2026-11-13", rows[0]["before"]["days"])

    def test_a_session_is_priced_on_the_day_each_turn_ran(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _two_turn_session_file(
                root,
                name="MO-482 review #487",
                # 2026-11-16 15:30 and 2026-11-17 00:30 in Los Angeles.
                first_stamp="2026-11-16T23:30:00.000Z",
                second_stamp="2026-11-17T08:30:00.000Z",
                cwd="/tmp/worktree",
                first_cost=1.0,
                second_cost=2.0,
            )
            session = cost_report.read_session(path, root)
            slices = cost_report.split_by_day(session)
        self.assertEqual([part.day for part in slices], ["2026-11-16", "2026-11-17"])
        self.assertAlmostEqual(slices[0].cost_usd, 1.0)
        self.assertAlmostEqual(slices[1].cost_usd, 2.0)

    def test_a_branch_pull_request_opened_after_the_session_is_rejected(self):
        session = SessionCost(
            session_id="s6",
            path="/tmp/s6.jsonl",
            pi_home="/tmp",
            cwd="/tmp",
            name="MO-482 · a ticket whose pull request came later",
            started_at="2026-11-13T12:00:00Z",
        )
        index = PrIndex()
        index._by_repo[REPO] = [
            {
                "number": 900,
                "title": "the branch's only pull request, opened later",
                "body": "",
                "headRefName": "t3/later",
                "state": "OPEN",
                "createdAt": "2026-11-18T00:00:00Z",
                "mergedAt": None,
            }
        ]
        out = attribute(session, index, repo=REPO, branch="t3/later")
        self.assertIsNone(out.pr_number)
        self.assertEqual(out.pr_key, "unattributed")

    def test_a_named_pull_request_opened_after_the_session_is_rejected(self):
        session = SessionCost(
            session_id="s7",
            path="/tmp/s7.jsonl",
            pi_home="/tmp",
            cwd="/tmp",
            name="MO-482 review #900",
            started_at="2026-11-13T12:00:00Z",
        )
        index = PrIndex()
        index._by_repo[REPO] = [
            {
                "number": 900,
                "title": "a pull request opened later",
                "body": "",
                "headRefName": "t3/later",
                "state": "OPEN",
                "createdAt": "2026-11-18T00:00:00Z",
                "mergedAt": None,
            }
        ]
        out = attribute(session, index, repo=REPO)
        self.assertIsNone(out.pr_number)
        self.assertIn("opened after the session ran", out.reason)

    def test_the_repo_filter_scopes_the_refactor_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _session_file(
                root,
                name="MO-482 review #487",
                stamp="2026-11-17T18:00:00.000Z",
                cwd="/tmp/mac-ops-worktree",
                cost=2.0,
            )
            _session_file(
                root,
                name="OPN-6 review #11",
                stamp="2026-11-17T19:00:00.000Z",
                cwd="/tmp/openscan-worktree",
                cost=3.0,
            )
            original_prs = cost_report.gh_prs
            original_repo = cost_report.repo_of
            original_branch = cost_report.branch_of
            cost_report.gh_prs = lambda repo: (
                list(PRS) if repo == REPO else list(OTHER_PRS)
            )
            cost_report.repo_of = lambda cwd: (
                REPO if "mac-ops" in str(cwd) else OTHER_REPO
            )
            cost_report.branch_of = lambda cwd: None
            try:
                unscoped = build_report(
                    "2026-11-17",
                    pi_root=root,
                    before_days=2,
                    after_days=1,
                )
                scoped = build_report(
                    "2026-11-17",
                    pi_root=root,
                    before_days=2,
                    after_days=1,
                    repos=[REPO],
                )
            finally:
                cost_report.gh_prs = original_prs
                cost_report.repo_of = original_repo
                cost_report.branch_of = original_branch
        self.assertIn(
            f"{OTHER_REPO}#11",
            [row["pr"] for row in unscoped["refactor_comparison"]],
        )
        self.assertEqual(
            [row["pr"] for row in scoped["refactor_comparison"]],
            [],
            "the other repository's refactor must not be in the comparison",
        )
        self.assertAlmostEqual(scoped["total_cost_usd"], 2.0)
        self.assertAlmostEqual(unscoped["total_cost_usd"], 5.0)
        self.assertTrue(scoped["reconciled"])

    def test_refactor_is_read_from_the_title(self):
        self.assertTrue(is_refactor("Rename the lane driver module"))
        self.assertFalse(is_refactor("Board: skip needs stays under a minute"))
        self.assertFalse(is_refactor(None))

    def test_markdown_names_the_totals(self):
        report = {
            "day": "2026-11-17",
            "generated_at": "2026-11-18T00:00:00Z",
            "measured_days": ["2026-11-16", "2026-11-17"],
            "session_count": 2,
            "total_cost_usd": 3.0,
            "attributed_cost_usd": 2.0,
            "unattributed_cost_usd": 1.0,
            "reconciled": True,
            "pr_count": 1,
            "cost_per_pr_usd": 2.0,
            "prs": [
                {
                    "pr": f"{REPO}#487",
                    "repo": REPO,
                    "number": 487,
                    "title": "Write down how the board's calls are bounded",
                    "state": "MERGED",
                    "merged_at": "2026-11-17T18:14:00Z",
                    "url": "https://example.invalid/487",
                    "sessions": 1,
                    "cost_usd": 2.0,
                    "tokens": 600,
                    "kinds": {"review": 1},
                    "models": ["test-model-1"],
                }
            ],
            "repos": [
                {
                    "repo": REPO,
                    "prs": 1,
                    "cost_usd": 2.0,
                    "mean_cost_per_pr_usd": 2.0,
                }
            ],
            "unattributed_sessions": [],
            "refactor_comparison": [],
        }
        markdown = render_markdown(report)
        self.assertIn("Agent cost per PR — 2026-11-17", markdown)
        self.assertIn(f"{REPO}#487", markdown)
        self.assertIn("Totals reconciled: **yes**", markdown)


if __name__ == "__main__":
    unittest.main()
