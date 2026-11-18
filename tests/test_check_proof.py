"""The proof file the check writes, and the gate brief that reads it."""
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "coordinator" / "bin"


def load(path, name):
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ProofFileTest(unittest.TestCase):
    def test_path_carries_the_ticket(self):
        proof_file = load(BIN / "proof_file.py", "proof_file")
        self.assertEqual(proof_file.path_for("MO", 501),
                         "evidence/MO-501/check-proof.md")
        self.assertEqual(proof_file.path_for("MO", None),
                         "evidence/check-proof.md")
        self.assertEqual(proof_file.path_for(None, 501),
                         "evidence/check-proof.md")

    def test_section_carries_the_file_to_the_gate(self):
        proof_file = load(BIN / "proof_file.py", "proof_file")
        text = "| Check | Result |\n| --- | --- |\n| syntax | passed |"
        section = proof_file.section(proof_file.FOUND, text, "evidence/MO-501/check-proof.md")
        self.assertIn("evidence/MO-501/check-proof.md", section)
        self.assertIn("passed", section)

    def test_section_says_when_there_is_no_proof_file(self):
        proof_file = load(BIN / "proof_file.py", "proof_file")
        section = proof_file.section(proof_file.MISSING, None, "evidence/MO-501/check-proof.md")
        self.assertIn("carries none", section)
        self.assertIn("does not block", section)

    def test_a_failed_read_is_not_a_missing_file(self):
        proof_file = load(BIN / "proof_file.py", "proof_file")
        section = proof_file.section(proof_file.UNREADABLE, "the read timed out",
                                     "evidence/MO-501/check-proof.md")
        self.assertIn("could not be read", section)
        self.assertNotIn("carries none", section)

    def test_fetch_reports_a_missing_file_and_a_failed_read_apart(self):
        proof_file = load(BIN / "proof_file.py", "proof_file")

        class Run:
            def __init__(self, returncode, stdout="", stderr=""):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        cases = [
            (Run(1, stderr="gh: Not Found (HTTP 404)"), proof_file.MISSING),
            (Run(1, stderr="gh: could not connect"), proof_file.UNREADABLE),
            (Run(0, stdout="not json"), proof_file.UNREADABLE),
            (Run(0, stdout='{"content": ""}'), proof_file.UNREADABLE),
            (Run(0, stdout='{"content": "", "encoding": "none"}'), proof_file.UNREADABLE),
            (Run(0, stdout='{"content": "aGk=", "encoding": "base64"}'), proof_file.FOUND),
        ]
        for run, expected in cases:
            with patch.object(subprocess, "run", return_value=run):
                state, _ = proof_file.fetch("a/b", "evidence/MO-501/check-proof.md", "a" * 40)
            self.assertEqual(state, expected)

    def test_an_existing_empty_file_is_not_a_missing_file(self):
        """A file that exists and carries nothing is a failed read."""
        proof_file = load(BIN / "proof_file.py", "proof_file")

        class Run:
            returncode = 0
            stdout = '{"content": "", "encoding": "base64"}'
            stderr = ""

        with patch.object(subprocess, "run", return_value=Run()):
            state, detail = proof_file.fetch("a/b", "evidence/MO-501/check-proof.md", "a" * 40)
        self.assertEqual(state, proof_file.UNREADABLE)
        self.assertIn("empty", detail)
        section = proof_file.section(state, detail, "evidence/MO-501/check-proof.md")
        self.assertIn("could not be read", section)
        self.assertNotIn("carries none", section)

    def test_gate_brief_reads_the_proof_file(self):
        gate_policy = load(BIN / "gate_policy.py", "gate_policy")
        settings = {"key": "MO"}
        brief = gate_policy.build_gate_brief(settings, "shyamsivakumar/mac-ops", 501, 12,
                                             "a" * 40, False, proof="| syntax | passed |",
                                             proof_path="evidence/MO-501/check-proof.md",
                                             proof_state="found")
        self.assertIn("evidence/MO-501/check-proof.md", brief)
        self.assertIn("| syntax | passed |", brief)
        self.assertIn(f"Builder check: PASS {'a' * 40}", brief)

    def test_gate_brief_says_when_the_proof_file_is_missing(self):
        gate_policy = load(BIN / "gate_policy.py", "gate_policy")
        brief = gate_policy.build_gate_brief({"key": "MO"}, "shyamsivakumar/mac-ops", 501, 12,
                                             "a" * 40, False, proof=None,
                                             proof_path="evidence/MO-501/check-proof.md",
                                             proof_state="missing")
        self.assertIn("carries none", brief)

    def test_gate_brief_names_a_failed_read(self):
        gate_policy = load(BIN / "gate_policy.py", "gate_policy")
        brief = gate_policy.build_gate_brief({"key": "MO"}, "shyamsivakumar/mac-ops", 501, 12,
                                             "a" * 40, False, proof=None,
                                             proof_path="evidence/MO-501/check-proof.md",
                                             proof_state="unreadable")
        self.assertIn("could not be read", brief)


class CheckProofTest(unittest.TestCase):
    def test_the_proof_file_lists_every_check(self):
        check = load(ROOT / "scripts" / "mac_ops_fast_check.py", "mac_ops_fast_check")
        proof = check.Proof("evidence/MO-501/check-proof.md")
        proof.check("python syntax: a.py", "python3 -c 'import ast' a.py", lambda: None)
        proof.check("tests: tests.test_a", "python3 -m unittest tests.test_a", lambda: None)
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "check-proof.md"
            proof.path = str(path)
            proof.write("b" * 40, False)
            text = path.read_text()
        self.assertIn("python syntax: a.py", text)
        self.assertIn("passed", text)
        self.assertIn("Checked commit: `{}`".format("b" * 40), text)
        self.assertIn("Working tree clean when the checks ran: yes", text)

    def test_a_failed_check_stops_the_run_and_the_rest_is_not_run(self):
        check = load(ROOT / "scripts" / "mac_ops_fast_check.py", "mac_ops_fast_check")
        proof = check.Proof("evidence/MO-501/check-proof.md")

        def boom():
            raise subprocess.CalledProcessError(1, "python3 -m unittest tests.test_a")

        proof.check("tests: tests.test_a", "python3 -m unittest tests.test_a", boom)
        proof.check("heavy help", "python3 heavy.py --help", lambda: None)
        self.assertTrue(proof.failed)
        self.assertEqual([row[2] for row in proof.rows], ["failed", "not run"])

    def test_a_missing_tool_is_recorded_as_not_run(self):
        check = load(ROOT / "scripts" / "mac_ops_fast_check.py", "mac_ops_fast_check")
        proof = check.Proof("evidence/MO-501/check-proof.md")

        def missing():
            raise check.NotRun("uvx is not installed")

        proof.check("ruff F,B", "uvx ruff@0.14.0 check", missing)
        self.assertFalse(proof.failed)
        self.assertEqual([row[2] for row in proof.rows], ["not run"])
        self.assertIn("uvx is not installed", proof.rows[0][3])

    def test_the_ruff_command_pins_the_version_and_the_rule_sets(self):
        check = load(ROOT / "scripts" / "mac_ops_fast_check.py", "mac_ops_fast_check")
        command = check.ruff_command(".")
        self.assertEqual(command[:2], ["uvx", f"ruff@{check.RUFF_VERSION}"])
        self.assertEqual(check.RUFF_RULES, "F,B")
        self.assertIn("--select", command)
        self.assertIn("F,B", command)
        self.assertEqual(command[-1], ".")

    def test_a_finding_outside_the_baseline_fails_and_one_inside_it_does_not(self):
        check = load(ROOT / "scripts" / "mac_ops_fast_check.py", "mac_ops_fast_check")
        baseline = {("a.py", "F841", "Local variable `x` is assigned to but never used"): 2}
        known = {("a.py", "F841", "Local variable `x` is assigned to but never used"): 2}
        self.assertEqual(check.new_findings(known, baseline), [])
        current = dict(known)
        current[("b.py", "F841", "Local variable `y` is assigned to but never used")] = 1
        extra = check.new_findings(current, baseline)
        self.assertEqual(len(extra), 1)
        self.assertEqual(extra[0][1], 1)

    def test_the_baseline_file_round_trips(self):
        check = load(ROOT / "scripts" / "mac_ops_fast_check.py", "mac_ops_fast_check")
        counts = {("a.py", "F841", "Local variable `x` is assigned to but never used"): 2}
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "ruff-baseline.txt"
            check.write_baseline(counts, path)
            self.assertEqual(check.read_baseline(path), counts)

    def test_the_check_keeps_the_original_deadlines(self):
        """The proof file must not let a slower run pass the check."""
        source = (ROOT / "scripts" / "mac_ops_fast_check.py").read_text()
        self.assertIn('run(selftest, timeout=60)', source)
        self.assertIn('run(tlc_command, cwd=scratch, timeout=55)', source)


if __name__ == "__main__":
    unittest.main()
