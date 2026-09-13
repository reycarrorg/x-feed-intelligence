#!/usr/bin/env python3
"""macOS Apple Vision recording evidence and portable unavailable-path checks."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xfi.canonical import canonicalize, local_post_id
from xfi.errors import XFIError
from xfi.recording import find_helper, ingest, preflight
from xfi.validation import SchemaValidator


class RecordingTests(unittest.TestCase):
    def test_unavailable_platform_diagnostic(self):
        with mock.patch("xfi.recording.sys.platform", "linux"):
            with self.assertRaises(XFIError) as caught: find_helper()
        self.assertEqual("PLATFORM_UNAVAILABLE_APPLE_VISION", caught.exception.code)

    def test_preflight_rejects_size_and_interval_before_native_decode(self):
        with tempfile.TemporaryDirectory() as temporary:
            small = Path(temporary) / "small.mov"
            small.write_bytes(b"x")
            with mock.patch("xfi.recording._run") as native:
                with self.assertRaises(XFIError) as interval: preflight(small, (0, 0, 1, 1), interval_ms=0)
                self.assertEqual("RECORDING_INTERVAL_REJECTED", interval.exception.code)
                native.assert_not_called()
            large = Path(temporary) / "large.mov"
            with large.open("wb") as stream: stream.truncate(2_147_483_649)
            with mock.patch("xfi.recording._run") as native:
                with self.assertRaises(XFIError) as size: preflight(large, (0, 0, 1, 1))
                self.assertEqual("RECORDING_FILE_LIMIT", size.exception.code)
                native.assert_not_called()

    @unittest.skipUnless(sys.platform == "darwin", "Apple Vision is a macOS platform facility")
    def test_authored_synthetic_movie_preflight_ocr_tracking_and_metrics(self):
        helper = ROOT / "build" / "native" / "xfi-recording-helper"
        if not helper.is_file() or (ROOT / "native/recording-helper/main.swift").stat().st_mtime > helper.stat().st_mtime:
            subprocess.run([str(ROOT / "scripts" / "build_recording_helper.sh"), str(helper.parent)], check=True)
        with tempfile.TemporaryDirectory() as temporary:
            movie = Path(temporary) / "authored-synthetic.mov"
            generated = subprocess.run([str(helper), "generate-synthetic", str(movie)], check=True, capture_output=True, text=True)
            self.assertEqual("AUTHORED_SYNTHETIC_RECORDING", json.loads(generated.stdout)["kind"])
            before = movie.read_bytes()
            info = preflight(movie, (0, 0, 1280, 720), helper=helper)
            self.assertEqual("avc1", info["codec"])
            self.assertEqual(1, info["worker_limit"])
            self.assertFalse(info["raw_recording_copied"])
            with self.assertRaises(XFIError) as crop_error: preflight(movie, (1200, 700, 500, 500), helper=helper)
            self.assertEqual("CROP_OUT_OF_BOUNDS", crop_error.exception.code)
            result = ingest(movie, (0, 0, 1280, 720), helper=helper, synthetic=True)
            self.assertEqual(before, movie.read_bytes(), "original recording changed")
            envelope = result["envelope"]
            schema = ROOT / "schemas" / "v1" / "envelope.schema.json"
            SchemaValidator(schema.parent).validate(envelope, json.loads(schema.read_text()), schema)
            posts = canonicalize(envelope["observations"])
            self.assertEqual(4, len(posts))
            self.assertEqual(1.0, 4 / len(posts))
            self.assertEqual(1.0, len(posts) / 4)
            labels = sorted(post["promotion"]["status"] for post in posts)
            self.assertEqual(["ambiguous", "organic", "organic", "promoted"], labels)
            self.assertEqual(1.0, 2 / 2, "unambiguous promotion separation")
            self.assertEqual(1, sum(len(post["relationships"]) for post in posts))
            quote = next(post for post in posts if post["platform_post_id"] == "shared-quote-001")
            self.assertEqual([("quotes", local_post_id("platform_id", "shared-source-001"))], [(edge["kind"], edge["source_local_post_id"]) for edge in quote["relationships"]])
            self.assertEqual(5, result["ocr"]["candidate_frame_count"])
            self.assertEqual(1, result["ocr"]["worker_count"])
            self.assertEqual([], list(Path(temporary).glob("*.png")), "derived frames persisted")


if __name__ == "__main__": unittest.main(verbosity=2)
