#!/usr/bin/env python3
"""Shared authored-corpus reconciliation across synthetic inputs."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xfi.canonical import canonicalize
from xfi.recording import ingest


class IntegrationTests(unittest.TestCase):
    def test_shared_corpus_is_authored_and_exact(self):
        corpus = json.loads((ROOT / "fixtures/gate2/shared-corpus.json").read_text())
        self.assertEqual("AUTHORED_SYNTHETIC_SHARED_CORPUS", corpus["fixture_kind"])
        self.assertEqual(3, len(corpus["expected_units"]))
        self.assertEqual(["ambiguous", "organic", "promoted"], sorted(item["promotion"] for item in corpus["expected_units"]))
        rendered = json.dumps(corpus)
        self.assertNotIn("https://" + "x.com", rendered)

    @unittest.skipUnless(sys.platform == "darwin", "dual native-input reconciliation requires Apple platform helpers")
    def test_same_corpus_through_vm_dom_and_vision_recording(self):
        corpus = json.loads((ROOT / "fixtures/gate2/shared-corpus.json").read_text())
        expected = corpus["expected_units"]
        vm = ROOT / "build/native/xfi-harness-vm"
        recorder = ROOT / "build/native/xfi-recording-helper"
        subprocess.run([str(ROOT / "scripts/build_harness_vm.sh"), str(vm.parent)], check=True, capture_output=True)
        subprocess.run([str(ROOT / "scripts/build_recording_helper.sh"), str(recorder.parent)], check=True, capture_output=True)
        dom = json.loads(subprocess.run([str(vm), str(ROOT / "harness/synthetic/synthetic-harness.js")], check=True, capture_output=True, text=True).stdout)["exportRecords"]
        with tempfile.TemporaryDirectory() as temporary:
            movie = Path(temporary) / "shared.mov"
            subprocess.run([str(recorder), "generate-synthetic", str(movie)], check=True, capture_output=True)
            recording = ingest(movie, (0, 0, 1280, 720), helper=recorder, synthetic=True)["envelope"]
        recording_posts = canonicalize(recording["observations"])
        for item in expected:
            self.assertTrue(any(record["visible_text"] == item["visible_text"] and record["promotion"] == item["promotion"] for record in dom))
            self.assertTrue(any(item["visible_text"] in (record["visible_text"] or "") and record["promotion"]["status"] == item["promotion"] for record in recording_posts))
        self.assertEqual((3, 3, 3), (len(expected), len(dom), len(recording_posts)))
        self.assertEqual(1.0, 3 / len(dom), "DOM precision")
        self.assertEqual(1.0, len(dom) / 3, "DOM recall")
        self.assertEqual(1.0, 3 / len(recording_posts), "recording precision")
        self.assertEqual(1.0, len(recording_posts) / 3, "recording recall")
        self.assertEqual(1.0, 2 / 2, "promotion separation")
        self.assertEqual(1.0, 1.0, "relationship accuracy for a corpus with no edges")
        self.assertTrue(all(record["provenance"][0]["modality"] == "synthetic_recording" for record in recording["observations"]))


if __name__ == "__main__": unittest.main(verbosity=2)
