"""The Harbor example task keeps the shape the eval harness needs."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "evals/harbor/tasks/example"


class HarborEvalTask(unittest.TestCase):
    def test_task_has_every_file_the_harness_reads(self):
        for name in ("instruction.md", "task.toml", "environment/Dockerfile",
                     "tests/test.sh", "solution/solve.sh"):
            self.assertTrue((TASK / name).is_file(), name)

    def test_verifier_writes_a_reward(self):
        verifier = (TASK / "tests/test.sh").read_text()
        self.assertIn("/logs/verifier/reward.txt", verifier)

    def test_verifier_runs_in_the_agent_sandbox(self):
        config = (TASK / "task.toml").read_text()
        self.assertIn('environment_mode = "shared"', config)

    def test_runner_uses_the_pi_agent(self):
        runner = (ROOT / "evals/harbor/run-example.sh").read_text()
        self.assertIn("-a pi", runner)

    def test_runner_passes_the_key_by_name_only(self):
        runner = (ROOT / "evals/harbor/run-example.sh").read_text()
        self.assertIn("--api-key-name", runner)
        self.assertNotIn("MINIMAX_API_KEY=", runner)


if __name__ == "__main__":
    unittest.main()
