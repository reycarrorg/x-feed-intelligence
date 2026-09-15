"""Deterministic, standard-library test suite for Gate 2 work package G2.1."""

from __future__ import annotations

import copy
import json
import random
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Add src to sys.path so x_core_store can be imported
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from x_core_store.canonical import (
    canonical_permalink,
    compact_bytes,
    digest_without_field,
    levenshtein_distance,
    normalized_text,
    sha256_digest,
)
from x_core_store.dedup import (
    canonicalize,
    has_merge_conflict,
    media_key,
    observation_key,
    primary_author,
    temporal_review_candidate,
)
from x_core_store.exceptions import (
    APPLICATION_ID,
    BACKUP_CAVEATS,
    PURGE_CAVEATS,
    PURGE_INCOMPLETE,
    REJECTED_COUNT_LIMIT,
    REJECTED_CREDENTIAL_FIELD,
    REJECTED_CREDENTIAL_VALUE,
    REJECTED_DEPTH,
    REJECTED_DIGEST_MISMATCH,
    REJECTED_FIELD_LIMIT,
    REJECTED_PACKET_LIMIT,
    REJECTED_PRIVATE_SURFACE,
    REJECTED_SCHEMA,
    REJECTED_STOP_VIOLATION,
    REJECTED_VERSION,
    SESSION_ID_COLLISION,
    UNSUPPORTED_APPLICATION_ID,
    CoreStoreError,
    MigrationError,
    SecurityError,
    StoreError,
    ValidationError,
)
from x_core_store.migrations import MIGRATIONS, migration_checksum
from x_core_store.store import CanonicalStore, MAX_BACKUP_BYTES, ReviewDecision
from x_core_store.validator import EnvelopeValidator, sensitive_category

FIXTURES = ROOT / "fixtures" / "synthetic" / "v1"
SCHEMAS = ROOT / "schemas" / "v1"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class TestG21CanonicalStore(unittest.TestCase):
    """Test suite covering the complete G2.1 work breakdown slice."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name).resolve()
        self.db_path = self.temp_path / "test_canonical_store.sqlite"
        self.store = CanonicalStore(self.db_path, schemas_dir=SCHEMAS)
        self.validator = EnvelopeValidator(schemas_dir=SCHEMAS)

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Synthetic envelopes transactional import and oracle counts
    # -------------------------------------------------------------------------
    def test_synthetic_envelopes_import_and_oracles(self) -> None:
        """Verify both synthetic envelopes import transactionally and match Gate 1 counts."""
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        rec_envelope = load_json(FIXTURES / "recording-session.json")

        # Import DOM session
        dom_result = self.store.import_envelope(dom_envelope)
        self.assertEqual(dom_result["status"], "IMPORTED")
        self.assertEqual(dom_result["session_id"], "synthetic-dom-001")
        self.assertEqual(dom_result["observations_count"], 6)
        self.assertEqual(dom_result["canonical_posts_count"], 5)
        self.assertEqual(dom_result["organic_count"], 3)
        self.assertEqual(dom_result["promoted_count"], 1)
        self.assertEqual(dom_result["ambiguous_count"], 1)

        # Verify DB state for DOM session
        session_row = self.store.get_session("synthetic-dom-001")
        self.assertIsNotNone(session_row)
        self.assertEqual(session_row["source"], "synthetic_dom")
        self.assertEqual(session_row["origin"], "https://fixture.example.invalid")

        posts = self.store.list_canonical_posts("synthetic-dom-001")
        self.assertEqual(len(posts), 5)

        # Check relationships in DOM session (quote from post-200 to post-100)
        quote_posts = [p for p in posts if any(r["kind"] == "quotes" for r in p["relationships"])]
        self.assertEqual(len(quote_posts), 1)
        self.assertEqual(quote_posts[0]["relationships"][0]["source_platform_post_id"], "synthetic-post-100")

        # Import recording session
        rec_result = self.store.import_envelope(rec_envelope)
        self.assertEqual(rec_result["status"], "IMPORTED")
        self.assertEqual(rec_result["session_id"], "synthetic-recording-001")
        self.assertEqual(rec_result["observations_count"], 4)
        self.assertEqual(rec_result["canonical_posts_count"], 3)
        self.assertEqual(rec_result["organic_count"], 2)
        self.assertEqual(rec_result["promoted_count"], 0)
        self.assertEqual(rec_result["ambiguous_count"], 1)

        rec_posts = self.store.list_canonical_posts("synthetic-recording-001")
        self.assertEqual(len(rec_posts), 3)

        # Verify total sessions stored
        sessions = self.store.list_sessions()
        self.assertEqual(len(sessions), 2)

    # -------------------------------------------------------------------------
    # 2. Idempotent import and collision handling
    # -------------------------------------------------------------------------
    def test_idempotent_import(self) -> None:
        """Re-importing identical envelope succeeds without duplicating rows."""
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        res1 = self.store.import_envelope(dom_envelope)
        self.assertEqual(res1["status"], "IMPORTED")

        res2 = self.store.import_envelope(dom_envelope)
        self.assertEqual(res2["status"], "ALREADY_IMPORTED")

        # Counts must not increase
        posts = self.store.list_canonical_posts("synthetic-dom-001")
        self.assertEqual(len(posts), 5)
        sessions = self.store.list_sessions()
        self.assertEqual(len(sessions), 1)

    def test_session_id_collision_rejected(self) -> None:
        """Importing a different envelope with an existing session_id raises SESSION_ID_COLLISION."""
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        self.store.import_envelope(dom_envelope)

        tampered = copy.deepcopy(dom_envelope)
        tampered["observations"][0]["visible_text"] = "Modified text with updated digest"
        tampered["content_digest"] = digest_without_field(tampered)

        with self.assertRaises(StoreError) as ctx:
            self.store.import_envelope(tampered)
        self.assertEqual(ctx.exception.category, SESSION_ID_COLLISION)

    # -------------------------------------------------------------------------
    # 3. Malformed, deep, oversized, and type violations
    # -------------------------------------------------------------------------
    def test_malformed_missing_version(self) -> None:
        val = {"observations": []}
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate_envelope(val)
        self.assertEqual(ctx.exception.category, REJECTED_SCHEMA)

    def test_malformed_unknown_version(self) -> None:
        canary = "99.0.0-DO-NOT-ECHO"
        val = {"schema_version": canary, "observations": []}
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate_envelope(val)
        self.assertEqual(ctx.exception.category, REJECTED_VERSION)
        self.assertNotIn(canary, str(ctx.exception))

    def test_non_rfc3339_timestamp_rejected(self) -> None:
        envelope = copy.deepcopy(load_json(FIXTURES / "recording-session.json"))
        envelope["session"]["started_at"] = "2030-01-02 10:00:00"
        envelope["content_digest"] = digest_without_field(envelope)
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate_envelope(envelope)
        self.assertEqual(ctx.exception.category, REJECTED_SCHEMA)

    def test_timezone_aware_stop_ordering(self) -> None:
        envelope = copy.deepcopy(load_json(FIXTURES / "dom-session.json"))
        stop = next(event for event in envelope["collection_events"] if event["event_code"] == "INJECTION_CONTENT")
        stop["at"] = "2030-01-02T10:04:00+01:00"
        envelope["observations"][0]["provenance"][0]["observed_at"] = "2030-01-02T09:04:01Z"
        envelope["content_digest"] = digest_without_field(envelope)
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate_envelope(envelope)
        self.assertEqual(ctx.exception.category, REJECTED_STOP_VIOLATION)

    def test_malformed_wrong_type(self) -> None:
        val = {"schema_version": "1.0.0", "observations": "not-an-array"}
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate_envelope(val)
        self.assertEqual(ctx.exception.category, REJECTED_SCHEMA)

    def test_resource_limit_depth_65(self) -> None:
        leaf: object = "leaf"
        for _ in range(65):
            leaf = [leaf]
        val = {"schema_version": "1.0.0", "nested": leaf}
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate_envelope(val)
        self.assertEqual(ctx.exception.category, REJECTED_DEPTH)

    def test_resource_limit_field_10001(self) -> None:
        val = {"schema_version": "1.0.0", "long_field": "x" * 10001}
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate_envelope(val)
        self.assertEqual(ctx.exception.category, REJECTED_FIELD_LIMIT)

    def test_resource_limit_observations_251(self) -> None:
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        oversized = copy.deepcopy(dom_envelope)
        base_obs = dom_envelope["observations"][0]
        oversized["observations"] = [
            {**base_obs, "observation_id": f"extra-{i}", "appearance_index": i}
            for i in range(251)
        ]
        oversized["content_digest"] = digest_without_field(oversized)
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate_envelope(oversized)
        self.assertEqual(ctx.exception.category, REJECTED_COUNT_LIMIT)

    def test_resource_limit_packet_5242881(self) -> None:
        oversized_bytes = b"x" * 5242881
        with self.assertRaises(ValidationError) as ctx:
            self.store.import_envelope(oversized_bytes)
        self.assertEqual(ctx.exception.category, REJECTED_PACKET_LIMIT)

    # -------------------------------------------------------------------------
    # 4. Sensitive data rejection and non-echo guarantees
    # -------------------------------------------------------------------------
    def test_sensitive_data_rejection_and_no_echo(self) -> None:
        """Verify all privacy negative control cases are rejected without echoing secrets."""
        cases = load_json(FIXTURES / "privacy-rejection.json")["cases"]
        for case in cases:
            cat = sensitive_category(case["packet"])
            self.assertEqual(
                cat,
                case["expected_category"],
                f"Privacy rejection category mismatch for {case['name']}",
            )
            # Ensure calling store with sensitive payload rejects safely
            with self.assertRaises(SecurityError) as ctx:
                self.store.import_envelope(case["packet"])
            self.assertEqual(ctx.exception.category, case["expected_category"])
            err_msg = str(ctx.exception)
            self.assertNotIn(
                case["must_not_echo"],
                err_msg,
                f"Canary secret was echoed in error message for {case['name']}",
            )

    def test_safe_negative_control_not_rejected(self) -> None:
        safe_payload = {
            "token_count": 12,
            "public_source_url": "https://research.example.invalid",
            "summary": "Ordinary synthetic text.",
        }
        self.assertIsNone(sensitive_category(safe_payload))

    # -------------------------------------------------------------------------
    # 5. Semantic invariants: stop violation and origin pairing
    # -------------------------------------------------------------------------
    def test_stop_event_violation_rejected(self) -> None:
        dom_envelope = copy.deepcopy(load_json(FIXTURES / "dom-session.json"))
        # Add an observation after the INJECTION_CONTENT stop event at 10:04:00Z
        dom_envelope["observations"][0]["provenance"][0]["observed_at"] = "2030-01-02T10:05:01Z"
        dom_envelope["content_digest"] = digest_without_field(dom_envelope)

        with self.assertRaises(ValidationError) as ctx:
            self.store.import_envelope(dom_envelope)
        self.assertEqual(ctx.exception.category, REJECTED_STOP_VIOLATION)

    def test_source_origin_cross_invariants(self) -> None:
        dom_envelope = copy.deepcopy(load_json(FIXTURES / "dom-session.json"))
        dom_envelope["session"]["origin"] = "https://x.com"
        dom_envelope["content_digest"] = digest_without_field(dom_envelope)
        with self.assertRaises(ValidationError) as ctx:
            self.store.import_envelope(dom_envelope)
        self.assertEqual(ctx.exception.category, REJECTED_SCHEMA)

    def test_content_digest_mismatch_rejected(self) -> None:
        dom_envelope = copy.deepcopy(load_json(FIXTURES / "dom-session.json"))
        dom_envelope["content_digest"] = "sha256:" + "0" * 64
        with self.assertRaises(ValidationError) as ctx:
            self.store.import_envelope(dom_envelope)
        self.assertEqual(ctx.exception.category, REJECTED_DIGEST_MISMATCH)

    # -------------------------------------------------------------------------
    # 6. Deduplication determinism and order invariance
    # -------------------------------------------------------------------------
    def test_dedup_order_invariance(self) -> None:
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        rec_envelope = load_json(FIXTURES / "recording-session.json")

        baseline_dom = canonicalize(dom_envelope["observations"])
        baseline_rec = canonicalize(rec_envelope["observations"])

        for observations, baseline in ((dom_envelope["observations"], baseline_dom), (rec_envelope["observations"], baseline_rec)):
            # Reversed order
            self.assertEqual(canonicalize(list(reversed(observations))), baseline)
            # 20 random permutations
            for seed in range(20):
                shuffled = list(observations)
                random.Random(seed).shuffle(shuffled)
                self.assertEqual(canonicalize(shuffled), baseline)

        for canonical_post in [*baseline_dom, *baseline_rec]:
            self.validator.validate_canonical_post(canonical_post)
            self.assertNotIn("method", canonical_post)

    def test_dedup_role_collisions(self) -> None:
        role_cases = load_json(FIXTURES / "dedup-role-collisions.json")["cases"]
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        role_template = copy.deepcopy(dom_envelope["observations"][2])

        for case in role_cases:
            pair = []
            for side, authors in (("left", case["authors_left"]), ("right", case["authors_right"])):
                obs = copy.deepcopy(role_template)
                obs["observation_id"] = f"{case['name']}-{side}"
                obs["appearance_index"] = len(pair)
                obs["platform_post_id"] = None
                obs["canonical_permalink"] = None
                obs["authors"] = authors
                obs["relationships"] = [{"kind": case["relationship_kind"], "source_local_post_id": "shared-source"}]
                pair.append(obs)

            self.assertEqual(primary_author(pair[0]), case["expected_primary_left"])
            self.assertEqual(primary_author(pair[1]), case["expected_primary_right"])
            merged = len(canonicalize(pair)) == 1
            self.assertEqual(merged, case["expected_automatic_merge"])

    def test_dedup_conflicts_prevent_merge(self) -> None:
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        a = copy.deepcopy(dom_envelope["observations"][0])
        b = copy.deepcopy(dom_envelope["observations"][1])
        a["platform_post_id"] = "post-conflict-a"
        b["platform_post_id"] = "post-conflict-b"
        self.assertEqual(len(canonicalize([a, b])), 2)

    def test_temporal_review_candidate(self) -> None:
        rec_envelope = load_json(FIXTURES / "recording-session.json")
        obs0 = rec_envelope["observations"][0]
        obs1 = copy.deepcopy(rec_envelope["observations"][1])
        obs1["visible_text"] = obs1["visible_text"].replace("careful", "carefu")

        # Near OCR text qualifies for temporal review candidate
        self.assertTrue(temporal_review_candidate(obs0, obs1))

        # Short text does not qualify
        short_a = copy.deepcopy(obs0)
        short_b = copy.deepcopy(obs1)
        short_a["visible_text"] = "Short synthetic text."
        short_b["visible_text"] = "Short synthetic t3xt."
        self.assertFalse(temporal_review_candidate(short_a, short_b))

    # -------------------------------------------------------------------------
    # 7. Rollback on transactional failure
    # -------------------------------------------------------------------------
    def test_transactional_rollback_on_failure(self) -> None:
        """Inject failure during import and prove 0 rows remain committed."""
        cursor = self.store.connection.cursor()
        with self.assertRaises(sqlite3.IntegrityError):
            with self.store.connection:
                # Simulate failed import transaction
                cursor.execute("BEGIN IMMEDIATE;")
                cursor.execute(
                    "INSERT INTO sessions (session_id, schema_version, source, started_at, ended_at, collector_version, privacy_profile, limits_json, content_digest, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                    ("rollback-test", "1.0.0", "synthetic_dom", "2030-01-01T00:00:00Z", "2030-01-01T00:01:00Z", "v1", "default_local", "{}", "sha256:abc", "now")
                )
                # Intentionally insert duplicate observation PK
                cursor.execute(
                    "INSERT INTO observations (observation_id, session_id, appearance_index, visibility_ratio, document_visible, input_location_json) VALUES (?, ?, ?, ?, ?, ?);",
                    ("obs-1", "rollback-test", 0, 1.0, 1, "{}")
                )
                cursor.execute(
                    "INSERT INTO observations (observation_id, session_id, appearance_index, visibility_ratio, document_visible, input_location_json) VALUES (?, ?, ?, ?, ?, ?);",
                    ("obs-1", "rollback-test", 1, 1.0, 1, "{}")
                )

        # Verify 0 rows persisted
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE session_id = 'rollback-test';")
        self.assertEqual(cursor.fetchone()[0], 0)
        cursor.execute("SELECT COUNT(*) FROM observations WHERE session_id = 'rollback-test';")
        self.assertEqual(cursor.fetchone()[0], 0)

    # -------------------------------------------------------------------------
    # 8. Foreign keys and SQLite pragmas
    # -------------------------------------------------------------------------
    def test_sqlite_pragmas_and_foreign_keys(self) -> None:
        cursor = self.store.connection.cursor()
        cursor.execute("PRAGMA foreign_keys;")
        self.assertEqual(cursor.fetchone()[0], 1)

        cursor.execute("PRAGMA secure_delete;")
        self.assertEqual(cursor.fetchone()[0], 1)

        cursor.execute("PRAGMA journal_mode;")
        self.assertEqual(cursor.fetchone()[0].upper(), "WAL")

        cursor.execute("PRAGMA application_id;")
        self.assertEqual(cursor.fetchone()[0], APPLICATION_ID)

        # Foreign key violation must fail
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO observations (observation_id, session_id, appearance_index, visibility_ratio, document_visible, input_location_json) VALUES (?, ?, ?, ?, ?, ?);",
                ("obs-nonexistent-session", "nonexistent-session-id", 0, 1.0, 1, "{}")
            )

    def test_reopen_preserves_pragmas(self) -> None:
        self.store.close()
        reopened = CanonicalStore(self.db_path, schemas_dir=SCHEMAS)
        cursor = reopened.connection.cursor()
        cursor.execute("PRAGMA foreign_keys;")
        self.assertEqual(cursor.fetchone()[0], 1)
        cursor.execute("PRAGMA secure_delete;")
        self.assertEqual(cursor.fetchone()[0], 1)
        cursor.execute("PRAGMA application_id;")
        self.assertEqual(cursor.fetchone()[0], APPLICATION_ID)
        reopened.close()

    def test_reject_arbitrary_sqlite_database(self) -> None:
        arbitrary_path = self.temp_path / "arbitrary.sqlite"
        conn = sqlite3.connect(str(arbitrary_path))
        conn.execute("CREATE TABLE foo (bar TEXT);")
        conn.commit()
        conn.close()

        with self.assertRaises(StoreError) as ctx:
            CanonicalStore(arbitrary_path, schemas_dir=SCHEMAS)
        self.assertEqual(ctx.exception.category, UNSUPPORTED_APPLICATION_ID)

    # -------------------------------------------------------------------------
    # 9. Versioned migrations and checksum verification
    # -------------------------------------------------------------------------
    def test_migrations_checksum_verification(self) -> None:
        cursor = self.store.connection.cursor()
        cursor.execute("SELECT version, name, checksum FROM schema_migrations ORDER BY version ASC;")
        rows = cursor.fetchall()
        self.assertEqual(len(rows), len(MIGRATIONS))
        for row, expected in zip(rows, MIGRATIONS):
            self.assertEqual(row["version"], expected["version"])
            self.assertEqual(row["name"], expected["name"])
            self.assertEqual(row["checksum"], migration_checksum(expected["sql"]))

        # Tampering with checksum in schema_migrations causes failure on reopen
        cursor.execute("UPDATE schema_migrations SET checksum = 'tampered-checksum' WHERE version = 1;")
        self.store.close()

        with self.assertRaises(MigrationError) as ctx:
            CanonicalStore(self.db_path, schemas_dir=SCHEMAS)
        self.assertEqual(ctx.exception.category, "MIGRATION_ERROR")

    # -------------------------------------------------------------------------
    # 10. Review decisions persistence
    # -------------------------------------------------------------------------
    def test_review_decisions_persistence(self) -> None:
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        self.store.import_envelope(dom_envelope)

        decision = ReviewDecision(
            decision_id="rev-decision-001",
            decision_type="human_merge",
            reviewer_id="reviewer-local-01",
            created_at="2030-01-02T12:00:00Z",
            reason="Reviewer confirmed temporal OCR candidates represent the same post.",
            target_canonical_id="local-target-100",
            source_canonical_ids=["local-source-a", "local-source-b"],
            observation_ids=["dom-observation-000", "dom-observation-001"],
            metadata={"confidence": 0.99},
        )
        dec_id = self.store.record_review_decision(decision)
        self.assertEqual(dec_id, "rev-decision-001")

        decisions = self.store.list_review_decisions("local-target-100")
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].reviewer_id, "reviewer-local-01")
        self.assertEqual(decisions[0].source_canonical_ids, ["local-source-a", "local-source-b"])

    # -------------------------------------------------------------------------
    # 11. Backup creation, verification, and restoration
    # -------------------------------------------------------------------------
    def test_backup_and_restore(self) -> None:
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        self.store.import_envelope(dom_envelope)

        backup_file = self.temp_path / "backup_dom.sqlite"
        record = self.store.create_backup(backup_file)
        self.assertEqual(record.backup_path, str(backup_file.resolve()))
        self.assertTrue(backup_file.is_file())

        # Overwrite without confirmation flag fails
        with self.assertRaises(StoreError):
            self.store.create_backup(backup_file, overwrite=False)

        # Backup recorded in inventory
        backups = self.store.list_backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].sha256, record.sha256)

        # Restore from backup into a fresh database
        fresh_db_path = self.temp_path / "restored_store.sqlite"
        with CanonicalStore(fresh_db_path, schemas_dir=SCHEMAS) as restored_store:
            restored_store.restore_backup(backup_file)
            posts = restored_store.list_canonical_posts("synthetic-dom-001")
            self.assertEqual(len(posts), 5)
            session = restored_store.get_session("synthetic-dom-001")
            self.assertIsNotNone(session)

    # -------------------------------------------------------------------------
    # 12. Transactional session purge and documented caveats
    # -------------------------------------------------------------------------
    def test_session_purge_and_caveats(self) -> None:
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        rec_envelope = load_json(FIXTURES / "recording-session.json")
        self.store.import_envelope(dom_envelope)
        self.store.import_envelope(rec_envelope)

        # Record a known export and backup for preview tracking
        export_file = self.temp_path / "report.json"
        self.store.record_known_export("synthetic-dom-001", export_file, "private_report")
        backup_file = self.temp_path / "session_purge_backup.sqlite"
        self.store.create_backup(backup_file)

        # Preview purge
        preview = self.store.preview_session_purge("synthetic-dom-001")
        self.assertEqual(preview.session_id, "synthetic-dom-001")
        self.assertEqual(preview.observation_count, 6)
        self.assertEqual(preview.canonical_posts_to_delete_count, 5)
        self.assertIn(str(export_file.resolve()), preview.known_exports)
        self.assertIn(str(backup_file.resolve()), preview.known_backups)
        self.assertIn("Local purge completed under configured SQLite controls", preview.caveats)
        self.assertNotIn("cryptographically erased", preview.caveats)

        # Execute purge
        result = self.store.purge_session("synthetic-dom-001", run_vacuum=True)
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.deleted_observations_count, 6)
        self.assertEqual(result.deleted_canonical_posts_count, 5)
        self.assertIn("Local purge completed under configured SQLite controls", result.caveats)
        self.assertNotIn("cryptographically erased", result.caveats)

        # Verify purged session is completely gone
        self.assertIsNone(self.store.get_session("synthetic-dom-001"))
        self.assertEqual(len(self.store.list_canonical_posts("synthetic-dom-001")), 0)

        # Verify recording session is preserved untouched
        self.assertIsNotNone(self.store.get_session("synthetic-recording-001"))
        self.assertEqual(len(self.store.list_canonical_posts("synthetic-recording-001")), 3)

    # -------------------------------------------------------------------------
    # 13. Regression tests for repair items
    # -------------------------------------------------------------------------
    def test_purge_session_busy_wal_yields_purge_incomplete(self) -> None:
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        self.store.import_envelope(dom_envelope)

        # Open concurrent connection and hold an active read lock to block checkpoint truncate
        reader_conn = sqlite3.connect(str(self.db_path))
        reader_cursor = reader_conn.cursor()
        reader_cursor.execute("BEGIN;")
        reader_cursor.execute("SELECT COUNT(*) FROM sessions;")

        try:
            with self.assertRaises(StoreError) as ctx:
                self.store.purge_session("synthetic-dom-001")
            self.assertEqual(ctx.exception.category, PURGE_INCOMPLETE)
            self.assertIn("close active readers", ctx.exception.detail)
        finally:
            reader_conn.rollback()
            reader_conn.close()

    def test_restore_backup_rejects_oversized_and_incompatible_version(self) -> None:
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        self.store.import_envelope(dom_envelope)
        backup_file = self.temp_path / "valid_backup.sqlite"
        self.store.create_backup(backup_file)

        # 1. Reject incompatible schema version before target modification
        incompatible_backup = self.temp_path / "incompatible_backup.sqlite"
        shutil.copyfile(backup_file, incompatible_backup)
        mod_conn = sqlite3.connect(str(incompatible_backup))
        mod_conn.execute("PRAGMA user_version = 99;")
        mod_conn.commit()
        mod_conn.close()

        target_db_path = self.temp_path / "target_db.sqlite"
        with CanonicalStore(target_db_path, schemas_dir=SCHEMAS) as target_store:
            # Populate target_store with sentinel session
            rec_envelope = load_json(FIXTURES / "recording-session.json")
            target_store.import_envelope(rec_envelope)
            initial_sessions = target_store.list_sessions()
            self.assertEqual(len(initial_sessions), 1)

            with self.assertRaises(StoreError) as ctx:
                target_store.restore_backup(incompatible_backup)
            self.assertEqual(ctx.exception.category, "BACKUP_ERROR")
            self.assertEqual(ctx.exception.detail, "Unsupported backup schema version")
            # Live target database must remain completely unmodified
            self.assertEqual(target_store.list_sessions(), initial_sessions)

            # 2. Reject oversized backup file before target modification
            oversized_backup = self.temp_path / "oversized_backup.sqlite"
            with open(oversized_backup, "wb") as fp:
                fp.seek(MAX_BACKUP_BYTES)
                fp.write(b"x")

            with self.assertRaises(StoreError) as ctx:
                target_store.restore_backup(oversized_backup)
            self.assertEqual(ctx.exception.category, "BACKUP_ERROR")
            self.assertEqual(
                ctx.exception.detail,
                "Backup file size is invalid or exceeds maximum allowed boundary",
            )
            # Live target database must remain completely unmodified
            self.assertEqual(target_store.list_sessions(), initial_sessions)

    def test_purge_reporting_canonical_post_retained_by_recommendation(self) -> None:
        dom_envelope = copy.deepcopy(load_json(FIXTURES / "dom-session.json"))
        # Restrict observations to only the first one (single canonical post)
        dom_envelope["observations"] = [dom_envelope["observations"][0]]
        dom_envelope["content_digest"] = digest_without_field(dom_envelope)

        single_store_path = self.temp_path / "single_post_store.sqlite"
        with CanonicalStore(single_store_path, schemas_dir=SCHEMAS) as single_store:
            res = single_store.import_envelope(dom_envelope)
            self.assertEqual(res["canonical_posts_count"], 1)
            posts = single_store.list_canonical_posts("synthetic-dom-001")
            self.assertEqual(len(posts), 1)
            retained_post_id = posts[0]["local_post_id"]

            # Add an analysis recommendation referencing this post
            cur = single_store.connection.cursor()
            cur.execute("BEGIN IMMEDIATE;")
            cur.execute(
                """
                INSERT INTO post_analyses (
                    analysis_id, local_post_id, session_id, classification, manual_action,
                    score_relevance, score_credibility, score_information_value, score_actionability,
                    score_risk, score_priority, created_at
                ) VALUES (?, ?, ?, 'organic', 'none', 5, 5, 5, 5, 1, 3, '2030-01-01T00:00:00Z');
                """,
                ("test-analysis-1", retained_post_id, None),
            )
            cur.execute(
                """
                INSERT INTO analysis_recommendations (
                    analysis_id, recommendation_id, target_type, target_local_id, action,
                    evidence_post_ids_json, qualifying_original_post_count, confidence, performed
                ) VALUES (?, ?, 'post', ?, 'bookmark', '[]', 1, 1.0, 0);
                """,
                ("test-analysis-1", "rec-001", retained_post_id),
            )
            cur.execute("COMMIT;")

            # Preview purge: canonical_posts_to_delete_count must be 0
            preview = single_store.preview_session_purge("synthetic-dom-001")
            self.assertEqual(preview.canonical_posts_to_delete_count, 0)
            self.assertEqual(preview.observation_count, 1)

            # Purge session: deleted_canonical_posts_count must be 0
            purge_res = single_store.purge_session("synthetic-dom-001")
            self.assertEqual(purge_res.deleted_canonical_posts_count, 0)
            self.assertEqual(purge_res.deleted_observations_count, 1)

            # Canonical post must remain in store
            self.assertIsNotNone(single_store.get_canonical_post(retained_post_id))
            # Session and observation are purged
            self.assertIsNone(single_store.get_session("synthetic-dom-001"))

    def test_two_session_shared_canonical_post_child_counts_idempotent(self) -> None:
        dom_envelope = load_json(FIXTURES / "dom-session.json")
        shared_obs = dom_envelope["observations"][2]

        env_a = copy.deepcopy(dom_envelope)
        env_a["session"]["session_id"] = "session-shared-a"
        env_a["observations"] = [copy.deepcopy(shared_obs)]
        env_a["observations"][0]["session_id"] = "session-shared-a"
        env_a["content_digest"] = digest_without_field(env_a)

        env_b = copy.deepcopy(dom_envelope)
        env_b["session"]["session_id"] = "session-shared-b"
        env_b["session"]["started_at"] = "2030-01-02T11:00:00Z"
        env_b["session"]["ended_at"] = "2030-01-02T11:05:00Z"
        env_b["observations"] = [copy.deepcopy(shared_obs)]
        env_b["observations"][0]["session_id"] = "session-shared-b"
        env_b["observations"][0]["observation_id"] = "obs-b-shared-001"
        env_b["content_digest"] = digest_without_field(env_b)

        # Import Session A
        self.store.import_envelope(env_a)
        posts_a = self.store.list_canonical_posts("session-shared-a")
        self.assertEqual(len(posts_a), 1)
        post_id = posts_a[0]["local_post_id"]
        post_after_a = self.store.get_canonical_post(post_id)
        self.assertIsNotNone(post_after_a)
        author_count_a = len(post_after_a["authors"])
        rel_count_a = len(post_after_a["relationships"])
        media_count_a = len(post_after_a["media"])
        unc_count_a = len(post_after_a["uncertainty"])
        self.assertGreater(author_count_a, 0)

        # Import Session B (shares the same canonical post)
        self.store.import_envelope(env_b)
        post_after_b = self.store.get_canonical_post(post_id)
        self.assertIsNotNone(post_after_b)

        # Child counts must remain strictly identical
        self.assertEqual(len(post_after_b["authors"]), author_count_a)
        self.assertEqual(len(post_after_b["relationships"]), rel_count_a)
        self.assertEqual(len(post_after_b["media"]), media_count_a)
        self.assertEqual(len(post_after_b["uncertainty"]), unc_count_a)
        self.assertEqual(len(post_after_b["observation_ids"]), 2)


if __name__ == "__main__":
    unittest.main()
