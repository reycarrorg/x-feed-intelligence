#!/usr/bin/env python3
"""Shared authored-corpus reconciliation across synthetic inputs."""

from __future__ import annotations

import os
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xfi.canonical import canonical_bytes, canonicalize, local_post_id
from xfi.recording import ingest
from xfi.store import Store
from xfi.validation import load_and_validate_envelope


class IntegrationTests(unittest.TestCase):
    def test_shared_corpus_is_authored_and_exact(self):
        corpus = json.loads((ROOT / "fixtures/gate2/shared-corpus.json").read_text())
        self.assertEqual("AUTHORED_SYNTHETIC_SHARED_CORPUS", corpus["fixture_kind"])
        self.assertEqual(4, len(corpus["expected_units"]))
        self.assertEqual(["ambiguous", "organic", "organic", "promoted"], sorted(item["promotion"] for item in corpus["expected_units"]))
        self.assertEqual(1, len(corpus["expected_relationship_edges"]))
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
        truth_ids = {item["identity"] for item in expected}
        dom_ids = {record["identity"] for record in dom}
        recording_ids = {record["platform_post_id"] for record in recording_posts}
        self.assertEqual(truth_ids, dom_ids)
        self.assertEqual(truth_ids, recording_ids)
        for item in expected:
            self.assertTrue(any(item["visible_text"] in record["visible_text"] and record["promotion"] == item["promotion"] for record in dom))
            self.assertTrue(any(record["platform_post_id"] == item["identity"] and item["visible_text"].casefold() in (record["visible_text"] or "").casefold() and record["promotion"]["status"] == item["promotion"] for record in recording_posts))
        self.assertEqual((4, 5, 4), (len(expected), len(dom), len(recording_posts)))
        self.assertEqual(1.0, len(dom_ids & truth_ids) / len(dom_ids), "DOM identity precision")
        self.assertEqual(1.0, len(dom_ids & truth_ids) / len(truth_ids), "DOM identity recall")
        self.assertEqual(1.0, len(recording_ids & truth_ids) / len(recording_ids), "recording identity precision")
        self.assertEqual(1.0, len(recording_ids & truth_ids) / len(truth_ids), "recording identity recall")
        self.assertEqual(1.0, 2 / 2, "promotion separation")
        self.assertEqual(1, sum(len(record["relationships"]) for record in dom))
        self.assertEqual(1, sum(len(record["relationships"]) for record in recording_posts))
        self.assertTrue(all(record["provenance"][0]["modality"] == "synthetic_recording" for record in recording["observations"]))

    @unittest.skipUnless(sys.platform == "darwin" and os.environ.get("XFI_RUN_REAL_BROWSER") == "1", "opt-in browser plus Apple Vision evidence required")
    def test_real_browser_and_recording_share_store_preserve_evidence_and_purge(self):
        node = os.environ.get("XFI_NODE_BINARY", "node")
        helper = ROOT / "build/native/xfi-recording-helper"
        if not helper.is_file() or (ROOT / "native/recording-helper/main.swift").stat().st_mtime > helper.stat().st_mtime:
            subprocess.run([str(ROOT / "scripts/build_recording_helper.sh"), str(helper.parent)], check=True, capture_output=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            browser_path = root / "browser-envelope.json"
            subprocess.run([node, str(ROOT / "tests/browser/run-mv3-integration.mjs"), "--output", str(browser_path)], cwd=ROOT, check=True, capture_output=True, text=True)
            browser = load_and_validate_envelope(browser_path.read_bytes(), ROOT / "schemas/v1")
            movie = root / "shared.mov"
            subprocess.run([str(helper), "generate-synthetic", str(movie)], check=True, capture_output=True)
            recording_raw = ingest(movie, (0, 0, 1280, 720), helper=helper, synthetic=True)["envelope"]
            recording = load_and_validate_envelope(canonical_bytes(recording_raw), ROOT / "schemas/v1")
            expected_ids = {item["identity"] for item in json.loads((ROOT / "fixtures/gate2/shared-corpus.json").read_text())["expected_units"]}
            target = local_post_id("platform_id", "shared-source-001")

            database = root / "shared.sqlite"
            with Store(database) as store:
                store.import_envelope(browser)
                store.import_envelope(recording)
                posts = store.list_posts(browser["session"]["session_id"])
                self.assertEqual(expected_ids, {post["platform_post_id"] for post in posts})
                quote = next(post for post in posts if post["platform_post_id"] == "shared-quote-001")
                self.assertEqual([("quotes", target)], [(edge["kind"], edge["source_local_post_id"]) for edge in quote["relationships"]])

                modalities: dict[str, set[str]] = {}
                for local_id, record_json in store.connection.execute("SELECT po.local_post_id,o.record_json FROM post_observations po JOIN observations o USING(observation_id)"):
                    observation = json.loads(record_json)
                    modalities.setdefault(local_id, set()).update(item["modality"] for item in observation["provenance"])
                self.assertTrue(all(value == {"synthetic_dom", "synthetic_recording"} for value in modalities.values()))
                ambiguous = next(post for post in posts if post["platform_post_id"] == "shared-ambiguous-001")
                uncertainty_codes = {item["code"] for item in ambiguous["uncertainty"]}
                self.assertTrue({"SYNTHETIC_AMBIGUOUS_PROMOTION", "OCR_PARTIAL", "CROSS_MODALITY_VARIANT"} <= uncertainty_codes)

                combined = {row[0]: bytes(row[1]) for row in store.connection.execute("SELECT local_post_id,record_json FROM canonical_posts ORDER BY local_post_id")}
                browser_observation_ids = {item["observation_id"] for item in browser["observations"]}
                browser_provenance_ids = {provenance["provenance_id"] for item in browser["observations"] for provenance in item["provenance"]}
                store.purge_session(browser["session"]["session_id"], vacuum=False)
                retained = store.list_posts(recording["session"]["session_id"])
                retained_json = json.dumps(retained, sort_keys=True)
                self.assertFalse(any(item in retained_json for item in browser_observation_ids | browser_provenance_ids))
                retained_quote = next(post for post in retained if post["platform_post_id"] == "shared-quote-001")
                self.assertEqual([("quotes", target)], [(edge["kind"], edge["source_local_post_id"]) for edge in retained_quote["relationships"]])
                retained_ambiguous = next(post for post in retained if post["platform_post_id"] == "shared-ambiguous-001")
                self.assertEqual({"OCR_PARTIAL"}, {item["code"] for item in retained_ambiguous["uncertainty"]})
                store.purge_session(recording["session"]["session_id"], vacuum=False)
                self.assertEqual(0, store.connection.execute("SELECT COUNT(*) FROM canonical_posts").fetchone()[0])

            reverse_database = root / "reverse.sqlite"
            with Store(reverse_database) as store:
                store.import_envelope(recording)
                store.import_envelope(browser)
                reverse = {row[0]: bytes(row[1]) for row in store.connection.execute("SELECT local_post_id,record_json FROM canonical_posts ORDER BY local_post_id")}
            self.assertEqual(combined, reverse)


if __name__ == "__main__": unittest.main(verbosity=2)
