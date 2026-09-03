"""Machine proof for agent validation gates."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))

import agent_gate_proof as agp


class AgentGateProofTests(unittest.TestCase):
    def _facade_tree(self, tmp: str) -> tuple[Path, Path]:
        """Temp APP tree with a fresh facade report, plus the proof path to use.

        The facade gate cross-checks the mtime of docs/_FACADE_AUDIT_REPORT.txt under APP.
        Pointing APP at a temp tree keeps that check deterministic — reading the real
        checkout made the test pass only within an hour of an actual facade audit.
        """
        root = Path(tmp)
        report = root / "docs" / "_FACADE_AUDIT_REPORT.txt"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("facade audit\n", encoding="utf-8")
        return root, report

    def test_record_and_verify_fresh_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, _report = self._facade_tree(tmp)
            proof = root / "proof.json"
            with mock.patch.object(agp, "PROOF_PATH", proof), mock.patch.object(
                agp, "APP", root
            ), mock.patch.object(agp, "git_head", return_value="abc123"):
                agp.record_gate("facade", cmd="test", exports=124, prune_candidates=0)
                errors, _ = agp.verify_gates(
                    ["facade"],
                    max_age_minutes=60,
                    require_git_match=True,
                )
                self.assertEqual(errors, [])

    def test_facade_gate_rejects_stale_report(self) -> None:
        """A recorded facade gate is not trusted when its report predates the window."""
        with tempfile.TemporaryDirectory() as tmp:
            root, report = self._facade_tree(tmp)
            proof = root / "proof.json"
            stale = time.time() - (60 + 30) * 60
            os.utime(report, (stale, stale))
            with mock.patch.object(agp, "PROOF_PATH", proof), mock.patch.object(
                agp, "APP", root
            ), mock.patch.object(agp, "git_head", return_value="abc123"):
                agp.record_gate("facade", cmd="test", exports=124, prune_candidates=0)
                errors, _ = agp.verify_gates(
                    ["facade"],
                    max_age_minutes=60,
                    require_git_match=True,
                )
            self.assertTrue(any("older than allowed window" in e for e in errors), errors)

    def test_verify_missing_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proof = Path(tmp) / "proof.json"
            proof.write_text(
                json.dumps({"version": 1, "git_head": "abc", "gates": {}}),
                encoding="utf-8",
            )
            with mock.patch.object(agp, "PROOF_PATH", proof), mock.patch.object(
                agp, "git_head", return_value="abc"
            ):
                errors, _ = agp.verify_gates(["t2"])
                self.assertTrue(any("not recorded" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
