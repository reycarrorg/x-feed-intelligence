#!/usr/bin/env python3
"""Gate 2 validator, store, analysis, rendering, backup, and purge evidence."""

from __future__ import annotations

import copy
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from xfi.analysis import aggregate_authors, analyze_posts, build_model_handoff, validate_analysis
from xfi.canonical import canonical_bytes, canonicalize, digest, local_post_id, pretty_bytes, primary_author
from xfi.errors import StoreError, ValidationError
from xfi.render import html_escape, markdown_escape, neutralize_formula, private_markdown, sanitize
from xfi.store import APPLICATION_ID, MIGRATION_CHECKSUM, Store
from xfi.validation import load_and_validate_envelope, read_bounded_file, sensitive_category

FIXTURES = ROOT / "fixtures" / "synthetic" / "v1"
SCHEMAS = ROOT / "schemas" / "v1"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def rekey_session(envelope: dict, session_id: str) -> dict:
    value = copy.deepcopy(envelope)
    value["session"]["session_id"] = session_id
    provenance_map = {}
    for index, observation in enumerate(value["observations"]):
        observation["session_id"] = session_id
        observation["observation_id"] = f"{session_id}-observation-{index:03d}"
        for pindex, provenance in enumerate(observation["provenance"]):
            old = provenance["provenance_id"]
            new = f"{session_id}-provenance-{index:03d}-{pindex:02d}"
            provenance["provenance_id"] = new
            provenance_map[old] = new
        for relationship in observation["relationships"]:
            relationship["provenance_ids"] = [provenance_map.get(item, item) for item in relationship.get("provenance_ids", [])]
        for media in observation["media"]:
            media["provenance_ids"] = [provenance_map.get(item, item) for item in media.get("provenance_ids", [])]
    value["content_digest"] = digest(value)
    return value


class ValidatorTests(unittest.TestCase):
    def test_valid_frozen_envelopes_and_digests(self):
        for name in ("dom-session.json", "recording-session.json"):
            expected = load(name)
            actual = load_and_validate_envelope((FIXTURES / name).read_bytes(), SCHEMAS)
            self.assertEqual(expected["content_digest"], digest(actual))

    def test_malformed_deep_oversized_and_digest_reject(self):
        cases = [(b"{}", "REJECTED_SCHEMA"), (b'{"schema_version":"99"}', "REJECTED_VERSION"), (b"not-json", "REJECTED_SCHEMA")]
        deep: object = "leaf"
        for _ in range(65): deep = [deep]
        cases.append((json.dumps({"schema_version": "1.0.0", "value": deep}).encode(), "REJECTED_DEPTH"))
        cases.append((b" " * 5_242_881, "REJECTED_PACKET_LIMIT"))
        mutated = load("dom-session.json")
        mutated["session"]["collector_version"] = "changed"
        cases.append((canonical_bytes(mutated), "REJECTED_DIGEST"))
        for raw, code in cases:
            with self.subTest(code=code), self.assertRaises(ValidationError) as caught:
                load_and_validate_envelope(raw, SCHEMAS)
            self.assertEqual(code, caught.exception.code)

    def test_strict_json_duplicate_nonfinite_and_unicode_rejections(self):
        envelope = load("dom-session.json")
        valid = canonical_bytes(envelope)
        cases = [
            (b'{"schema_version":"1.0.0",' + valid[1:], "REJECTED_DUPLICATE_KEY"),
            (json.dumps({**envelope, "numeric_canary": float("nan")}, allow_nan=True).encode(), "REJECTED_NONFINITE_NUMBER"),
            (json.dumps({**envelope, "numeric_canary": float("inf")}, allow_nan=True).encode(), "REJECTED_NONFINITE_NUMBER"),
            (b'{"schema_version":"\\ud800"}', "REJECTED_UNICODE"),
            (b"\xff", "REJECTED_SCHEMA"),
        ]
        for raw, code in cases:
            with self.subTest(code=code), self.assertRaises(ValidationError) as caught:
                load_and_validate_envelope(raw, SCHEMAS)
            self.assertEqual(code, caught.exception.code)
            self.assertNotIn("canary", str(caught.exception).casefold())

    def test_relationship_targets_normalize_and_dangling_or_contradictory_reject(self):
        envelope = load("dom-session.json")
        posts = canonicalize(envelope["observations"])
        source = local_post_id("platform_id", "synthetic-post-100")
        quote = next(post for post in posts if post["platform_post_id"] == "synthetic-post-200")
        self.assertEqual([("quotes", source)], [(item["kind"], item["source_local_post_id"]) for item in quote["relationships"]])
        self.assertTrue({item["source_local_post_id"] for post in posts for item in post["relationships"]} <= {post["local_post_id"] for post in posts})
        dangling = copy.deepcopy(envelope)
        next(observation for observation in dangling["observations"] if observation["relationships"])["relationships"][0]["source_platform_post_id"] = "missing-platform-post"
        dangling["content_digest"] = digest(dangling)
        with self.assertRaises(ValidationError) as missing: load_and_validate_envelope(canonical_bytes(dangling), SCHEMAS)
        self.assertEqual("REJECTED_REFERENCE", missing.exception.code)
        contradictory = copy.deepcopy(envelope)
        next(observation for observation in contradictory["observations"] if observation["relationships"])["relationships"][0]["source_local_post_id"] = local_post_id("platform_id", "synthetic-post-300")
        contradictory["content_digest"] = digest(contradictory)
        with self.assertRaises(ValidationError) as conflict: load_and_validate_envelope(canonical_bytes(contradictory), SCHEMAS)
        self.assertEqual("REJECTED_REFERENCE", conflict.exception.code)
        dangling_provenance = copy.deepcopy(envelope)
        next(observation for observation in dangling_provenance["observations"] if observation["media"])["media"][0]["provenance_ids"] = ["missing-provenance"]
        dangling_provenance["content_digest"] = digest(dangling_provenance)
        with self.assertRaises(ValidationError) as evidence: load_and_validate_envelope(canonical_bytes(dangling_provenance), SCHEMAS)
        self.assertEqual("REJECTED_REFERENCE", evidence.exception.code)

    def test_bounded_file_read_rejects_before_decode_without_echo(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            oversized = root / "SECRET-CANARY.json"
            with oversized.open("wb") as stream: stream.truncate(5_242_881)
            with self.assertRaises(ValidationError) as size: read_bounded_file(oversized)
            self.assertEqual("REJECTED_PACKET_LIMIT", size.exception.code)
            self.assertNotIn("SECRET-CANARY", str(size.exception))
            target = root / "target.json"
            target.write_text("{}")
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaises(ValidationError) as linked: read_bounded_file(link)
            self.assertEqual("REJECTED_INPUT_FILE", linked.exception.code)

    def test_private_and_secret_values_reject_without_echo(self):
        for case in load("privacy-rejection.json")["cases"]:
            code = sensitive_category(case["packet"])
            rendered = json.dumps({"code": code})
            self.assertEqual(case["expected_category"], code)
            self.assertNotIn(case["must_not_echo"], rendered)
        self.assertIsNone(sensitive_category({"token_count": 12, "summary": "safe synthetic control"}))

    def test_relation_dedup_deterministic_and_collisions(self):
        dom = load("dom-session.json")["observations"]
        baseline = canonicalize(dom)
        self.assertEqual(5, len(baseline))
        self.assertEqual(baseline, canonicalize(list(reversed(dom))))
        for case in load("dedup-role-collisions.json")["cases"]:
            left = {"relationships": [{"kind": case["relationship_kind"]}], "authors": case["authors_left"]}
            right = {"relationships": [{"kind": case["relationship_kind"]}], "authors": case["authors_right"]}
            self.assertEqual(case["expected_primary_left"], primary_author(left))
            self.assertEqual(case["expected_primary_right"], primary_author(right))
            self.assertEqual(case["expected_automatic_merge"], primary_author(left) == primary_author(right))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "private.sqlite"
        self.envelope = load("dom-session.json")

    def tearDown(self): self.temp.cleanup()

    def test_configuration_import_idempotence_and_foreign_keys(self):
        with Store(self.db) as store:
            self.assertEqual(1, store.connection.execute("PRAGMA foreign_keys").fetchone()[0])
            self.assertEqual(1, store.connection.execute("PRAGMA secure_delete").fetchone()[0])
            self.assertEqual("wal", store.connection.execute("PRAGMA journal_mode").fetchone()[0])
            self.assertEqual(APPLICATION_ID, store.connection.execute("PRAGMA application_id").fetchone()[0])
            self.assertEqual(MIGRATION_CHECKSUM, store.connection.execute("SELECT value FROM meta WHERE key='migration_checksum'").fetchone()[0])
            first = store.import_envelope(self.envelope)
            second = store.import_envelope(self.envelope)
            self.assertFalse(first.idempotent)
            self.assertTrue(second.idempotent)
            with self.assertRaises(StoreError) as orphan:
                store.add_analysis({"analysis_id": "orphan", "local_post_id": "missing"})
            self.assertEqual("ORPHAN_ANALYSIS_REJECTED", orphan.exception.code)
        with Store(self.db) as reopened:
            self.assertEqual(1, reopened.connection.execute("PRAGMA secure_delete").fetchone()[0])

    def test_import_failure_rolls_back_and_digest_conflict(self):
        with Store(self.db) as store:
            with self.assertRaises(StoreError): store.import_envelope(self.envelope, inject_failure=True)
            self.assertEqual(0, store.connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
            store.import_envelope(self.envelope)
            other = copy.deepcopy(self.envelope)
            other["content_digest"] = "sha256:" + "0" * 64
            with self.assertRaises(StoreError) as caught: store.import_envelope(other)
            self.assertEqual("IDEMPOTENCE_DIGEST_CONFLICT", caught.exception.code)

    def test_cross_session_canonical_reuse_conflict_and_shared_purge(self):
        second = rekey_session(self.envelope, "synthetic-dom-002")
        with Store(self.db) as store:
            store.import_envelope(self.envelope)
            store.import_envelope(second)
            self.assertEqual(5, store.connection.execute("SELECT COUNT(*) FROM canonical_posts").fetchone()[0])
            self.assertEqual(12, store.connection.execute("SELECT COUNT(*) FROM post_observations").fetchone()[0])
            reused = next(post for post in store.list_posts("synthetic-dom-002") if post["platform_post_id"] == "synthetic-post-100")
            self.assertEqual(4, len(reused["observation_ids"]))
            self.assertEqual("platform_id", reused["deduplication"]["method"])
            before_failed_purge = {row[0]: bytes(row[1]) for row in store.connection.execute("SELECT local_post_id,record_json FROM canonical_posts")}
            with self.assertRaises(StoreError): store.purge_session("synthetic-dom-001", vacuum=False, inject_failure=True)
            self.assertEqual(before_failed_purge, {row[0]: bytes(row[1]) for row in store.connection.execute("SELECT local_post_id,record_json FROM canonical_posts")})
            first_purge = store.purge_session("synthetic-dom-001", vacuum=False)
            self.assertEqual("PURGE_COMPLETED", first_purge["status"])
            self.assertEqual(5, store.connection.execute("SELECT COUNT(*) FROM canonical_posts").fetchone()[0])
            self.assertEqual(6, store.connection.execute("SELECT COUNT(*) FROM post_observations").fetchone()[0])
            retained = [json.loads(row[0]) for row in store.connection.execute("SELECT record_json FROM canonical_posts")]
            retained_json = json.dumps(retained, sort_keys=True)
            self.assertNotIn("synthetic-dom-001-observation", retained_json)
            self.assertNotIn("prov-dom-", retained_json)
            self.assertTrue(all(item.startswith("synthetic-dom-002-observation") for post in retained for item in post["observation_ids"]))
            self.assertTrue(all(item.startswith("synthetic-dom-002-observation") for post in retained for item in post["deduplication"]["evidence_observation_ids"]))
            self.assertTrue(all(item.startswith("synthetic-dom-002-provenance") for post in retained for relation in post["relationships"] for item in relation["provenance_ids"]))
            self.assertTrue(all(item.startswith("synthetic-dom-002-provenance") for post in retained for media in post["media"] for item in media["provenance_ids"]))
            store.purge_session("synthetic-dom-002", vacuum=False)
            self.assertEqual(0, store.connection.execute("SELECT COUNT(*) FROM canonical_posts").fetchone()[0])

        conflict_db = self.root / "conflict.sqlite"
        conflict = rekey_session(self.envelope, "synthetic-dom-conflict")
        conflict["observations"] = [conflict["observations"][0]]
        conflict["observations"][0]["visible_text"] = "Contradictory synthetic value 999"
        conflict["content_digest"] = digest(conflict)
        with Store(conflict_db) as store:
            store.import_envelope(self.envelope)
            with self.assertRaises(StoreError) as caught: store.import_envelope(conflict)
            self.assertEqual("CANONICAL_CONFLICT", caught.exception.code)
            self.assertEqual(1, store.connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])

    def test_arbitrary_database_rejected(self):
        arbitrary = self.root / "arbitrary.sqlite"
        sqlite3.connect(arbitrary).close()
        with self.assertRaises(StoreError) as caught: Store(arbitrary)
        self.assertEqual("ARBITRARY_DATABASE_REJECTED", caught.exception.code)

    def test_nonlocal_database_and_backup_are_rejected_before_write(self):
        with self.assertRaises(StoreError) as database: Store(Path("/Volumes/xfi-nonlocal-test/private.sqlite"))
        self.assertEqual("NONLOCAL_DATABASE_REJECTED", database.exception.code)
        with Store(self.db) as store:
            with self.assertRaises(StoreError) as backup: store.backup(Path("/Volumes/xfi-nonlocal-test/backup.sqlite"), "2030-01-02")
        self.assertEqual("NONLOCAL_BACKUP_REJECTED", backup.exception.code)

    def test_backup_restore_isolation_integrity_and_no_overwrite(self):
        backup, restored = self.root / "backup.sqlite", self.root / "restored.sqlite"
        with Store(self.db) as store:
            store.import_envelope(self.envelope)
            evidence = store.backup(backup, "2030-01-02")
            self.assertEqual("ok", evidence["integrity"])
            with self.assertRaises(StoreError): store.backup(backup, "2030-01-02")
        result = Store.restore(backup, restored)
        self.assertEqual("RESTORED_ISOLATED_COPY", result["status"])
        with Store(restored) as restored_store:
            restored_store.connection.execute("UPDATE meta SET value='isolated' WHERE key='schema_version'")
            restored_store.connection.commit()
        with Store(self.db) as original:
            self.assertEqual("1", original.connection.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0])
        link = self.root / "backup-link.sqlite"
        link.symlink_to(backup)
        with self.assertRaises(StoreError) as linked: Store.restore(link, self.root / "linked-restore.sqlite")
        self.assertEqual("RESTORE_PATH_REJECTED", linked.exception.code)

    def test_purge_rollback_vacuum_cleanup_and_orphans(self):
        derived = self.root / "derived-frame.tmp"
        derived.write_text("synthetic")
        with Store(self.db) as store:
            store.import_envelope(self.envelope)
            preview = store.purge_preview("synthetic-dom-001")
            self.assertEqual(6, preview["observation_count"])
            with self.assertRaises(StoreError): store.purge_session("synthetic-dom-001", inject_failure=True)
            self.assertEqual(1, store.connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
            result = store.purge_session("synthetic-dom-001", vacuum=True, temp_paths=[derived], temp_root=self.root)
            self.assertEqual("PURGE_COMPLETED", result["status"])
            self.assertEqual("TRUNCATED", result["checkpoint"])
            self.assertEqual("VACUUM_COMPLETED", result["vacuum"])
            self.assertFalse(derived.exists())
            self.assertEqual(0, store.connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0])
            self.assertEqual(0, store.connection.execute("SELECT COUNT(*) FROM canonical_posts").fetchone()[0])

    def test_purge_insufficient_space_is_honest(self):
        with Store(self.db) as store:
            store.import_envelope(self.envelope)
            result = store.purge_session("synthetic-dom-001", vacuum=True, free_space_override=0)
            self.assertEqual("PURGE_INCOMPLETE", result["status"])
            self.assertEqual("VACUUM_NOT_RUN", result["vacuum"])
            self.assertNotIn("securely", result["message"])

    def test_purge_refuses_unscoped_temp_deletion(self):
        unrelated = self.root / "unrelated.txt"
        unrelated.write_text("preserve")
        with Store(self.db) as store:
            store.import_envelope(self.envelope)
            result = store.purge_session("synthetic-dom-001", vacuum=False, temp_paths=[unrelated])
        self.assertEqual("PURGE_INCOMPLETE", result["status"])
        self.assertTrue(unrelated.exists())

    def test_open_reader_reports_busy_checkpoint_without_post_stop_refs(self):
        with Store(self.db) as store:
            store.import_envelope(self.envelope)
            reader = sqlite3.connect(self.db)
            reader.execute("BEGIN")
            reader.execute("SELECT * FROM sessions").fetchall()
            result = store.purge_session("synthetic-dom-001", vacuum=False)
            reader.close()
            self.assertIn(result["checkpoint"], {"BUSY", "TRUNCATED"})
            self.assertEqual(0, result["remaining_sessions"])


class AnalysisRenderTests(unittest.TestCase):
    def test_classification_scoring_author_and_authority(self):
        posts = canonicalize(load("dom-session.json")["observations"])
        records = analyze_posts(posts)
        self.assertEqual(3, len(records))
        self.assertTrue(any(r["classification"] == "E_SCAM_MANIPULATIVE_UNSAFE" for r in records))
        for record in records: validate_analysis(record)
        for author in aggregate_authors(posts, records): self.assertFalse(author["performed"])
        handoff = build_model_handoff(posts, "classification")
        self.assertEqual([], handoff["trusted_control"]["tool_authority"]["allowed_tools"])
        self.assertTrue(all(value is False for value in handoff["authority_result"].values()))

    def test_golden_sanitizer_byte_exact(self):
        actual = pretty_bytes(sanitize(load("sanitizer-input.json")))
        self.assertEqual((FIXTURES / "sanitizer-expected.json").read_bytes(), actual)

    def test_markdown_html_formula_injection_are_data(self):
        payload = '<script>alert(1)</script> **admin** =SUM(1,1)'
        self.assertNotIn("<script>", html_escape(payload))
        self.assertIn("\\*\\*admin\\*\\*", markdown_escape(payload))
        self.assertTrue(neutralize_formula(" \t=SUM(1,1)").startswith("'"))
        posts = canonicalize(load("dom-session.json")["observations"])
        rendered = private_markdown(load("dom-session.json")["session"], posts, analyze_posts(posts)).decode()
        self.assertIn("Performed: `false`", rendered)
        self.assertIn("\\[", markdown_escape("[link](javascript:alert(1))"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
