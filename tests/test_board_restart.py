import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import board_restart


BASE = 1_700_000_000
FAILED = "omp/openai-codex/gpt-6.1-terra"
NEXT = "codex/gpt-6.1-terra"


def row(task_id, **overrides):
    base = {"id": task_id, "state": "error", "stage": "working", "msg": "The agent has exited",
            "app": "omp", "title": "t", "research": None, "archivedAt": None, "kind": None}
    base.update(overrides)
    return base


def meta(**overrides):
    base = {"settings": {"worker.agent": FAILED}, "after": ["strategy-replay-workbench/126"],
            "exitedAt": (BASE - 1000) * 1000, "link": {"pane": "w1:p1"}, "stage": "working"}
    base.update(overrides)
    return base


class BoardRestartTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def tick_at(self, now, rows, tasks, panes=None):
        return board_restart.tick(now=now, dry_run=True, rows=rows, panes=panes or {},
                                   tasks=tasks, state_path=self.state)

    def test_cycle_skips_the_agent_that_failed(self):
        agent, cursor = board_restart.next_agent(FAILED, 0)
        self.assertEqual(agent, NEXT)
        self.assertEqual(cursor, 2)
        agent, cursor = board_restart.next_agent("claude", 0)
        self.assertEqual(agent, FAILED)
        self.assertEqual(cursor, 1)
        agent, _cursor = board_restart.next_agent("cursor", 1)
        self.assertEqual(agent, NEXT)

    def test_dead_rows_and_the_rows_left_alone(self):
        exited = row("repo/1")
        self.assertEqual(board_restart.classify(exited, meta()), "agent_exited")
        unsent = row("repo/1", stage="failed", msg="Not started: its instructions sit unsent in its box")
        self.assertEqual(board_restart.classify(unsent, meta(failure={"stage": "send"})), "not_started")
        early = row("repo/1", state="working", msg="Has not started yet: pressing enter again")
        self.assertEqual(board_restart.classify(early, meta()), "has_not_started_yet")
        quiet = row("repo/1", state="working", stage="working", msg="Reading the board")
        self.assertIsNone(board_restart.classify(quiet, meta()))
        self.assertEqual(board_restart.exclusion(exited, meta(researchRun=True)), "research")
        self.assertEqual(board_restart.exclusion(row("repo/1", stage="reviewing"), meta()), "in_review")
        self.assertEqual(board_restart.exclusion(row("repo/1", msg="Finishing"), meta()), "finishing")
        self.assertEqual(board_restart.exclusion(row("repo/1", state="blocked"), meta()), "blocked")

    def test_same_row_twice_a_minute_apart_restarts_on_the_next_agent(self):
        task = "strategy-replay-workbench/126"
        rows = [row(task)]
        tasks = {task: meta()}
        first = self.tick_at(BASE, rows, tasks)
        self.assertEqual(first["actions"], [])
        second = self.tick_at(BASE + 61, rows, tasks)
        self.assertEqual(len(second["actions"]), 1)
        result = second["actions"][0]["result"]
        self.assertEqual(result["agent"], NEXT)
        self.assertTrue(result["wait_kept"])
        self.assertEqual(result["wait_before"], ["strategy-replay-workbench/126"])
        commands = [" ".join(step["command"][1:]) for step in result["steps"]]
        self.assertEqual(commands, [
            "stop strategy-replay-workbench/126",
            "delegate strategy-replay-workbench/126 --worker.agent codex/gpt-6.1-terra",
        ])

    def test_unsent_row_uses_the_boards_own_restart(self):
        task = "strategy-replay-workbench/119"
        rows = [row(task, stage="failed", msg="Not started: its instructions sit unsent in its box")]
        tasks = {task: meta(failure={"stage": "send"})}
        self.tick_at(BASE, rows, tasks)
        second = self.tick_at(BASE + 61, rows, tasks)
        commands = [" ".join(step["command"][1:]) for step in second["actions"][0]["result"]["steps"]]
        self.assertEqual(commands, [
            "set worker.agent codex/gpt-6.1-terra --task strategy-replay-workbench/119",
            "retry strategy-replay-workbench/119",
        ])

    def test_machine_wide_failure_and_a_fresh_exit_are_left(self):
        task = "repo/2"
        rows = [row(task, stage="failed", msg="Could not start: herdr did not answer in time")]
        tasks = {task: meta(failure={"stage": "start"})}
        self.tick_at(BASE, rows, tasks)
        second = self.tick_at(BASE + 61, rows, tasks)
        self.assertEqual(second["actions"], [])
        self.assertEqual(board_restart.read_state(self.state)["tasks"][task]["skip"], "machine_wide_failure")

        fresh = "repo/3"
        fresh_rows = [row(fresh)]
        fresh_tasks = {fresh: meta(exitedAt=(BASE + 61) * 1000)}
        self.tick_at(BASE, fresh_rows, fresh_tasks)
        later = self.tick_at(BASE + 61, fresh_rows, fresh_tasks)
        self.assertEqual(later["actions"], [])

    def test_three_restarts_in_an_hour_then_one_more_after_the_hour(self):
        task = "repo/4"
        rows = [row(task)]
        tasks = {task: meta()}
        self.tick_at(BASE, rows, tasks)
        for step in range(1, 4):
            result = self.tick_at(BASE + 61 * step, rows, tasks)
            self.assertEqual(result["actions"][0]["action"], "restart")
        capped = self.tick_at(BASE + 61 * 4, rows, tasks)
        self.assertEqual(capped["actions"], [])
        self.assertEqual(board_restart.read_state(self.state)["tasks"][task]["skip"], "restart_cap")
        after = self.tick_at(BASE + 61 * 4 + 3600, rows, tasks)
        self.assertEqual(after["actions"][0]["action"], "restart")

    def test_tell_waits_until_the_new_agent_is_up_and_skips_a_finished_turn(self):
        task = "repo/5"
        rows = [row(task)]
        tasks = {task: meta()}
        self.tick_at(BASE, rows, tasks)
        self.tick_at(BASE + 61, rows, tasks)
        tasks[task]["startedAgentAt"] = (BASE + 70) * 1000
        quiet = [row(task, state="working", stage="working", msg="")]
        early = self.tick_at(BASE + 70, quiet, tasks)
        self.assertEqual(early["actions"], [])
        told = self.tick_at(BASE + 61 + 20, quiet, tasks)
        self.assertEqual(told["actions"][0]["action"], "tell")
        command = told["actions"][0]["steps"][0]["command"][1:]
        self.assertEqual(command[:2], ["tell", task])
        self.assertIn("Restarted on codex/gpt-6.1-terra", command[2])

        other = "repo/6"
        other_rows = [row(other)]
        other_tasks = {other: meta()}
        self.tick_at(BASE, other_rows, other_tasks)
        self.tick_at(BASE + 61, other_rows, other_tasks)
        other_tasks[other]["startedAgentAt"] = (BASE + 90) * 1000
        finished = [row(other, state="working", stage="working", msg="Finishing")]
        dropped = self.tick_at(BASE + 61 + 20, finished, other_tasks)
        self.assertEqual(dropped["actions"], [])
        self.assertNotIn("pending_tell", board_restart.read_state(self.state)["tasks"][other])

    def test_board_cap_stops_a_second_task(self):
        old = board_restart.MAX_RESTARTS_PER_HOUR_BOARD
        board_restart.MAX_RESTARTS_PER_HOUR_BOARD = 1
        try:
            rows = [row("repo/7"), row("repo/8")]
            tasks = {"repo/7": meta(), "repo/8": meta()}
            self.tick_at(BASE, rows, tasks)
            second = self.tick_at(BASE + 61, rows, tasks)
        finally:
            board_restart.MAX_RESTARTS_PER_HOUR_BOARD = old
        self.assertEqual([item["task"] for item in second["actions"]], ["repo/7"])
        self.assertEqual(board_restart.read_state(self.state)["tasks"]["repo/8"]["skip"], "board_restart_cap")


if __name__ == "__main__":
    unittest.main()
