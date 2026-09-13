#!/usr/bin/env python3
"""End-to-end CLI evidence for retention, backup/restore, report, and review surfaces."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKET = ROOT / "fixtures/synthetic/v1/dom-session.json"


class CLITests(unittest.TestCase):
    def command(self, *arguments: object, expected: int = 0) -> dict:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        completed = subprocess.run([sys.executable, "-m", "xfi", *map(str, arguments)], cwd=ROOT, env=environment, capture_output=True, text=True)
        self.assertEqual(expected, completed.returncode, completed.stderr or completed.stdout)
        return json.loads(completed.stdout if expected == 0 else completed.stderr)

    def test_full_local_operator_surface(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "private.sqlite"
            backup = root / "backup.sqlite"
            restored = root / "restored.sqlite"
            report = root / "private-report.json"
            decision = root / "decision.json"
            imported = self.command("import", PACKET, "--database", database)
            session = imported["session_id"]
            self.assertEqual("ANALYZED", self.command("analyze", "--database", database, "--session", session)["status"])
            report_result = self.command("report", "--database", database, "--session", session, "--output", report, "--format", "json")
            self.assertEqual("PRIVATE_REPORT_CREATED", report_result["status"])
            backup_result = self.command("backup", "--database", database, "--output", backup, "--created-on", "2030-01-02")
            self.assertEqual("BACKUP_CREATED", backup_result["status"])
            self.assertIn("separate retained copy", backup_result["caveat"])
            self.assertEqual("BACKUP_EXISTS", self.command("backup", "--database", database, "--output", backup, "--created-on", "2030-01-02", expected=2)["code"])
            restored_result = self.command("restore", backup, "--output", restored)
            self.assertEqual("RESTORED_ISOLATED_COPY", restored_result["status"])
            self.assertEqual("RESTORE_DESTINATION_EXISTS", self.command("restore", backup, "--output", restored, expected=2)["code"])
            preview = self.command("purge-preview", "--database", database, "--session", session)
            self.assertEqual(6, preview["observation_count"])
            mismatch = self.command("purge", "--database", database, "--session", session, "--confirm-session", "wrong", expected=2)
            self.assertEqual("PURGE_CONFIRMATION_MISMATCH", mismatch["code"])
            decision.write_text(json.dumps({"decision_id": "decision-001", "reviewer_local_id": "reviewer-local", "decided_at": "2030-01-02T00:00:00Z", "reason": "Synthetic evidence review", "decision_type": "classification", "prior_post_ids": [], "observation_ids": []}))
            recorded = self.command("review-decision", decision, "--database", database)
            self.assertFalse(recorded["performed_account_action"])
            purged = self.command("purge", "--database", database, "--session", session, "--confirm-session", session, "--no-vacuum")
            self.assertEqual("PURGE_COMPLETED", purged["status"])
            self.assertTrue(backup.exists() and restored.exists(), "purge must preserve separately retained backup/restore copies")

    def test_cli_rejections_do_not_echo_path_or_canary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            oversized = root / "DO-NOT-ECHO-CANARY.json"
            with oversized.open("wb") as stream: stream.truncate(5_242_881)
            result = self.command("validate", oversized, expected=2)
            rendered = json.dumps(result)
            self.assertEqual("REJECTED_PACKET_LIMIT", result["code"])
            self.assertNotIn("DO-NOT-ECHO-CANARY", rendered)


if __name__ == "__main__": unittest.main(verbosity=2)
