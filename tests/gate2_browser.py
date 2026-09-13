#!/usr/bin/env python3
"""Synthetic harness lifecycle, capability denial, and promotion evidence."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xfi.browser import browser_runtime_preflight, promotion_safe


class BrowserHarnessTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((ROOT / "contracts/v1/manifest.synthetic-test-only.json").read_text())
        self.manifest = json.loads((ROOT / "harness/synthetic/manifest.json").read_text())
        self.proposal = json.loads((ROOT / "contracts/v1/manifest.proposal.json").read_text())

    def test_exact_manifest_and_no_live_origin_strings(self):
        self.assertEqual(self.contract, self.manifest)
        tree = "\n".join(path.read_text() for path in (ROOT / "harness/synthetic").glob("*") if path.is_file())
        for forbidden in ("https://" + "x.com", "twitter.com", "api." + "x.com"):
            self.assertNotIn(forbidden, tree)
        self.assertEqual(["https://fixture.example.invalid/*"], self.manifest["host_permissions"])
        self.assertEqual(["storage"], self.manifest["permissions"])
        script = (ROOT / "harness/synthetic/synthetic-harness.js").read_text()
        for required in ("MutationObserver", "IntersectionObserver", "document.visibilityState", "getClientRects", "USER_START", "USER_EXPORT", "detach"):
            self.assertIn(required, script)

    def test_accessibility_controls_are_textual_keyboard_native_and_zoomable(self):
        control = (ROOT / "harness/synthetic/control.html").read_text()
        self.assertEqual(5, control.count("<button"))
        for label in ("Arm synthetic collector", "Start synthetic capture", "Export synthetic packet", "Stop synthetic capture", "Discard synthetic draft"):
            self.assertIn(f'aria-label="{label}"', control)
        self.assertIn('role="status"', control)
        self.assertIn("State: INACTIVE", control)
        self.assertIn("color is never the only signal", control)

    def test_promotion_guard_positive_and_negative_controls(self):
        paths = ["manifest.json", "src/xfi/cli.py", "NOTICE", "bom.json"]
        self.assertTrue(promotion_safe(self.proposal, paths))
        leaked = copy.deepcopy(self.proposal)
        leaked["host_permissions"] = ["https://fixture.example.invalid/*"]
        self.assertFalse(promotion_safe(leaked, paths))
        self.assertFalse(promotion_safe(self.proposal, paths + ["synthetic-harness.js"]))
        self.assertFalse(promotion_safe(self.proposal, paths + ["fixtures/synthetic/v1/dom-session.json"]))

    def test_browser_runtime_preflight_is_honest_and_nonexecuting(self):
        value = browser_runtime_preflight()
        self.assertFalse(value["execution_authorized"])
        self.assertIn(value["status"], {"BROWSER_RUNTIME_UNAVAILABLE", "REVIEWED_BROWSER_DECLARED"})

    @unittest.skipUnless(sys.platform == "darwin", "JavaScriptCore VM evidence is a macOS platform check")
    def test_capability_denied_vm_lifecycle_mutation_visibility_and_stops(self):
        binary = ROOT / "build/native/xfi-harness-vm"
        if not binary.is_file():
            subprocess.run([str(ROOT / "scripts/build_harness_vm.sh"), str(binary.parent)], check=True)
        result = subprocess.run([str(binary), str(ROOT / "harness/synthetic/synthetic-harness.js")], check=True, capture_output=True, text=True)
        value = json.loads(result.stdout)
        self.assertEqual(["INACTIVE", True, "ARMED", True, "CAPTURING"], value["lifecycle"])
        self.assertTrue(value["edgeAccepted"])
        self.assertFalse(value["sameIdentityMutation"])
        self.assertTrue(value["reusedNodeAccepted"])
        self.assertFalse(value["hiddenAccepted"])
        self.assertFalse(value["belowAccepted"])
        self.assertEqual(2, value["exportRecordCount"])
        self.assertEqual("STOPPED", value["stopped"]["state"])
        self.assertFalse(value["postStopAccepted"])
        self.assertTrue(all(count == 0 for count in value["stopped"]["effects"].values()))
        self.assertEqual({"fetch": "undefined", "xhr": "undefined", "websocket": "undefined", "document": "undefined"}, value["capabilities"])
        self.assertEqual(12, len(value["stopResults"]))
        for stopped in value["stopResults"].values():
            self.assertEqual("ERROR", stopped["state"])
            self.assertEqual(0, stopped["observerCount"])
            self.assertEqual(0, stopped["timerCount"])
            self.assertEqual(0, stopped["domReferenceCount"])
            self.assertFalse(stopped["postStopAccepted"])
            self.assertTrue(stopped["queueStable"])


if __name__ == "__main__": unittest.main(verbosity=2)
