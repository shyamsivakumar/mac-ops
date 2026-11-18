"""The proof file the check writes, and the gate brief that reads it."""
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path
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
        self.assertIsNone(proof_file.path_for("MO", None))
        self.assertIsNone(proof_file.path_for(None, 501))

    def test_section_carries_the_file_to_the_gate(self):
        proof_file = load(BIN / "proof_file.py", "proof_file")
        text = "| Check | Result |\n| --- | --- |\n| syntax | passed |"
        section = proof_file.section(text, "evidence/MO-501/check-proof.md")
        self.assertIn("evidence/MO-501/check-proof.md", section)
        self.assertIn("passed", section)

    def test_section_says_when_there_is_no_proof_file(self):
        proof_file = load(BIN / "proof_file.py", "proof_file")
        section = proof_file.section(None, "evidence/MO-501/check-proof.md")
        self.assertIn("carries none", section)
        self.assertIn("does not block", section)

    def test_gate_brief_reads_the_proof_file(self):
        gate_policy = load(BIN / "gate_policy.py", "gate_policy")
        settings = {"key": "MO"}
        brief = gate_policy.build_gate_brief(settings, "shyamsivakumar/mac-ops", 501, 12,
                                             "a" * 40, False, proof="| syntax | passed |",
                                             proof_path="evidence/MO-501/check-proof.md")
        self.assertIn("evidence/MO-501/check-proof.md", brief)
        self.assertIn("| syntax | passed |", brief)
        self.assertIn(f"Builder check: PASS {'a' * 40}", brief)

    def test_gate_brief_says_when_the_proof_file_is_missing(self):
        gate_policy = load(BIN / "gate_policy.py", "gate_policy")
        brief = gate_policy.build_gate_brief({"key": "MO"}, "shyamsivakumar/mac-ops", 501, 12,
                                             "a" * 40, False, proof=None,
                                             proof_path="evidence/MO-501/check-proof.md")
        self.assertIn("carries none", brief)


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


if __name__ == "__main__":
    unittest.main()
