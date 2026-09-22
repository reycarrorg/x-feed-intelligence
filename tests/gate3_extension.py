#!/usr/bin/env python3
"""Gate 3 live-DOM schema, core integration, and prohibited-capability checks."""

from __future__ import annotations

import copy
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xfi.analysis import analyze_posts
from xfi.canonical import canonical_bytes, digest
from xfi.cli import load_envelope
from xfi.errors import ValidationError
from xfi.store import Store
from xfi.validation import load_and_validate_envelope


def live_envelope() -> dict:
    session_id = "live-dom-test-001"
    synthetic_status_id = "1234567890123456789"
    observation_id = f"{session_id}-observation-000"
    provenance_id = f"{session_id}-provenance-000"
    value = {
        "schema_version": "2.0.0",
        "session": {
            "session_id": session_id,
            "schema_version": "2.0.0",
            "source": "live_dom",
            "started_at": "2030-01-02T03:04:05Z",
            "ended_at": "2030-01-02T03:05:05Z",
            "origin": "https://x.com",
            "collector_version": "hybrid-extension-test",
            "privacy_profile": "default_local",
            "collection_mode": "manual_scroll",
            "limits": {
                "max_candidates": 100,
                "max_duration_seconds": 900,
                "max_packet_bytes": 5_242_880,
            },
        },
        "observations": [{
            "observation_id": observation_id,
            "session_id": session_id,
            "appearance_index": 0,
            "top_level": True,
            "visibility_ratio": 0.75,
            "document_visible": True,
            "platform_post_id": synthetic_status_id,
            "canonical_permalink": "https://x.com/example/status/" + synthetic_status_id,
            "visible_text": "Synthetic release note with a documentation link and measured limitations.",
            "displayed_timestamp": "2030-01-02T03:04:30Z",
            "authors": [{
                "local_author_id": "author-example",
                "platform_author_id": None,
                "display_name": "Example",
                "handle": "example",
                "role": "original",
                "identity_confidence": 0.95,
                "uncertainty_codes": [],
            }],
            "relationships": [],
            "media": [],
            "promotion": {"status": "organic", "evidence": ["none"], "confidence": 0.8},
            "provenance": [{
                "provenance_id": provenance_id,
                "modality": "live_dom",
                "collector_version": "hybrid-extension-test",
                "parser_or_ocr_version": "visible-x-dom-test",
                "field": "visible_card",
                "observed_at": "2030-01-02T03:04:30Z",
                "video_time_ms": None,
                "crop_xywh": None,
                "confidence": 0.9,
            }],
            "uncertainty": [],
            "input_location": {"viewport_time_ms": 25_000, "video_time_ms": None, "crop_xywh": None},
            "preview_grade": "B",
            "preview_reasons": ["contains inspectable evidence language or a source lead"],
        }],
        "collection_events": [
            {"event_code": "SESSION_STARTED", "at": "2030-01-02T03:04:05Z", "safe_detail_code": None},
            {"event_code": "OBSERVATION_ACCEPTED", "at": "2030-01-02T03:04:30Z", "safe_detail_code": "COUNT_ONLY"},
            {"event_code": "STOPPED_USER", "at": "2030-01-02T03:05:05Z", "safe_detail_code": None},
        ],
        "content_digest": "",
    }
    value["content_digest"] = digest(value)
    return value


class LiveEnvelopeTests(unittest.TestCase):
    def test_v2_validates_through_old_and_parent_schema_entrypoints(self):
        expected = live_envelope()
        for schema_root in (ROOT / "schemas" / "v1", ROOT / "schemas"):
            actual = load_and_validate_envelope(canonical_bytes(expected), schema_root)
            self.assertEqual("manual_scroll", actual["session"]["collection_mode"])
            self.assertEqual(expected["content_digest"], digest(actual))

    def test_v2_imports_and_uses_existing_analysis_core(self):
        envelope = load_and_validate_envelope(canonical_bytes(live_envelope()), ROOT / "schemas")
        with tempfile.TemporaryDirectory() as temporary:
            with Store(Path(temporary) / "private.sqlite") as store:
                result = store.import_envelope(envelope)
                posts = store.list_posts(result.session_id)
                analyses = analyze_posts(posts)
        self.assertEqual(1, result.canonical_count)
        self.assertEqual("B_PROMISING_VERIFY", analyses[0]["classification"])
        self.assertFalse(analyses[0]["recommendations"][0]["performed"])

    def test_assisted_packet_quote_context_and_links_survive_validation(self):
        envelope = live_envelope()
        envelope["session"]["collection_mode"] = "assisted_scroll"
        envelope["session"]["limits"] = {"max_candidates": 10_000, "max_duration_seconds": 28_800, "max_packet_bytes": 15_728_640}
        observation = envelope["observations"][0]
        observation["first_observed_at"] = "2030-01-02T03:04:30Z"
        observation["last_observed_at"] = "2030-01-02T03:04:45Z"
        observation["outbound_links"] = [{"url": "https://example.org/report", "title": "Report", "description": "Visible summary"}]
        observation["quote_context"] = {"platform_post_id": "222", "canonical_permalink": "https://x.com/quoted/status/" + "222", "display_name": "Quoted", "handle": "quoted", "visible_text": "Visible quoted text", "media": []}
        observation["authors"][0]["role"] = "quoting"
        observation["relationships"] = [{"kind": "quotes", "source_local_post_id": observation["observation_id"] + "-quoted-source", "source_platform_post_id": "222", "confidence": 0.9, "provenance_ids": [observation["provenance"][0]["provenance_id"]]}]
        envelope["content_digest"] = digest(envelope)
        actual = load_and_validate_envelope(canonical_bytes(envelope), ROOT / "schemas")
        self.assertEqual("Visible quoted text", actual["observations"][0]["quote_context"]["visible_text"])
        self.assertEqual("https://example.org/report", actual["observations"][0]["outbound_links"][0]["url"])

    def test_legacy_live_packet_cannot_exceed_its_declared_100_card_limit(self):
        envelope = live_envelope()
        envelope["observations"] *= 101
        envelope["content_digest"] = digest(envelope)
        with self.assertRaises(ValidationError) as over_limit:
            load_and_validate_envelope(canonical_bytes(envelope), ROOT / "schemas")
        self.assertEqual("REJECTED_COUNT_LIMIT", over_limit.exception.code)

    def test_automatic_collection_modes_and_broader_origins_reject(self):
        for mutation in ("mode", "origin", "visibility"):
            value = copy.deepcopy(live_envelope())
            if mutation == "mode":
                value["session"]["collection_mode"] = "automatic_scroll"
            elif mutation == "origin":
                value["session"]["origin"] = "https://twitter.com"
            else:
                value["observations"][0]["visibility_ratio"] = 0.49
            value["content_digest"] = digest(value)
            with self.subTest(mutation=mutation), self.assertRaises(ValidationError):
                load_and_validate_envelope(canonical_bytes(value), ROOT / "schemas")

    def test_ten_thousand_visible_cards_validate_and_import_but_next_card_rejects(self):
        envelope = live_envelope()
        envelope["session"]["limits"] = {
            "max_candidates": 10_000,
            "max_duration_seconds": 28_800,
            "max_packet_bytes": 134_217_728,
        }
        template = envelope["observations"][0]
        observations = []
        for index in range(10_000):
            item = copy.deepcopy(template)
            item["observation_id"] = f"live-dom-test-001-observation-{index:05d}"
            item["appearance_index"] = index
            item["platform_post_id"] = str(1234567890123456789 + index)
            item["canonical_permalink"] = f"https://x.com/example/status/{item['platform_post_id']}"
            item["provenance"][0]["provenance_id"] = f"live-dom-test-001-provenance-{index:05d}"
            item["visible_text"] = f"Synthetic visible card {index}. " + ("Measured documentation and limitations. " * 15)
            observations.append(item)
        envelope["observations"] = observations
        envelope["content_digest"] = digest(envelope)
        raw = canonical_bytes(envelope)
        self.assertGreater(len(raw), 5_242_880)
        with tempfile.TemporaryDirectory() as temporary:
            packet = Path(temporary) / "synthetic-volume.json"
            packet.write_bytes(raw)
            actual = load_envelope(packet)
            with Store(Path(temporary) / "private.sqlite") as store:
                result = store.import_envelope(actual)
        self.assertEqual(10_000, result.canonical_count)

        envelope["observations"].append(copy.deepcopy(observations[-1]))
        with self.assertRaises(ValidationError) as over_limit:
            load_and_validate_envelope(canonical_bytes(envelope), ROOT / "schemas")
        self.assertEqual("REJECTED_COUNT_LIMIT", over_limit.exception.code)


class CapabilityBoundaryTests(unittest.TestCase):
    def test_extension_source_has_no_network_or_account_action_primitive(self):
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "extension").rglob("*.ts"))
            if "node_modules" not in path.parts and ".output" not in path.parts and ".wxt" not in path.parts
        )
        forbidden = {
            "unbounded scroll call": r"\b(?:scrollTo|scrollIntoView)\s*\(",
            "network fetch": r"\bfetch\s*\(",
            "XHR": r"\bXMLHttpRequest\b",
            "web socket": r"\bWebSocket\b",
            "network interception": r"\b(?:webRequest|declarativeNetRequest)\b",
            "cookie access": r"\b(?:document\.cookie|browser\.cookies|chrome\.cookies)\b",
            "private API": r"\b(?:graphql|api\.twitter|api\.x\.com)\b",
        }
        for label, pattern in forbidden.items():
            with self.subTest(label=label):
                self.assertIsNone(re.search(pattern, sources, flags=re.IGNORECASE))
        collector = (ROOT / "extension" / "entrypoints" / "collector.content.ts").read_text(encoding="utf-8")
        self.assertEqual(1, len(re.findall(r"\.scrollTop\s*=", sources)))
        self.assertIn("target.scrollTop = oldTop + step", collector)
        self.assertIn("Math.min(160, Math.max(80", collector)
        self.assertIn("networkRequests: 0", sources)
        self.assertIn("accountActions: 0", sources)

    def test_permission_and_origin_source_contract_is_exact(self):
        config = (ROOT / "extension" / "wxt.config.ts").read_text(encoding="utf-8")
        collector = (ROOT / "extension" / "entrypoints" / "collector.content.ts").read_text(encoding="utf-8")
        self.assertIn("optional_host_permissions: ['https://x.com/*']", config)
        self.assertIsNone(re.search(r"^\s*host_permissions\s*:", config, flags=re.MULTILINE))
        self.assertIn("browser === 'firefox' ? ['downloads', 'storage'] : ['downloads', 'storage', 'offscreen']", config)
        self.assertIn("matches: ['https://x.com/*']", collector)
        self.assertIn("'assisted_scroll' : 'manual_scroll'", collector)
        self.assertNotIn("xfi-lifecycle-indicator", collector)
        self.assertIn("this.host.attachShadow({ mode: 'closed' })", collector)
        self.assertIn("this.host.id = 'xfi-counter-bubble'", collector)
        self.assertNotIn("XFI_PANEL_TOGGLE", collector)
        popup = (ROOT / "extension" / "entrypoints" / "popup" / "main.ts").read_text(encoding="utf-8")
        self.assertNotIn("createObjectURL", popup)
        self.assertIn("XFI_SAVE_EXPORT", popup)


if __name__ == "__main__":
    unittest.main(verbosity=2)
