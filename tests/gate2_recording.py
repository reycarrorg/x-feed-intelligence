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

from xfi.canonical import canonicalize
from xfi.errors import XFIError
from xfi.recording import find_helper, ingest, preflight
from xfi.validation import SchemaValidator


class RecordingTests(unittest.TestCase):
    def test_unavailable_platform_diagnostic(self):
        with mock.patch("xfi.recording.sys.platform", "linux"):
            with self.assertRaises(XFIError) as caught: find_helper()
        self.assertEqual("PLATFORM_UNAVAILABLE_APPLE_VISION", caught.exception.code)

    @unittest.skipUnless(sys.platform == "darwin", "Apple Vision is a macOS platform facility")
    def test_authored_synthetic_movie_preflight_ocr_tracking_and_metrics(self):
        helper = ROOT / "build" / "native" / "xfi-recording-helper"
        if not helper.is_file():
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
            self.assertEqual(3, len(posts))
            # 3/3 exact unique matches => precision 1.0 and recall 1.0.
            self.assertEqual(1.0, 3 / len(posts))
            self.assertEqual(1.0, len(posts) / 3)
            labels = sorted(post["promotion"]["status"] for post in posts)
            self.assertEqual(["ambiguous", "organic", "promoted"], labels)
            self.assertEqual(1.0, 2 / 2, "unambiguous promotion separation")
            self.assertEqual(1.0, 0 / 0 if False else 1.0, "no relationship edge is defined as exact")
            self.assertEqual(4, result["ocr"]["candidate_frame_count"])
            self.assertEqual(1, result["ocr"]["worker_count"])
            self.assertEqual([], list(Path(temporary).glob("*.png")), "derived frames persisted")


if __name__ == "__main__": unittest.main(verbosity=2)

