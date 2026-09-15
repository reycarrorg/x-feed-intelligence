"""Platform SQLite canonical store with WAL, foreign keys, migrations, backup, and purge."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from x_core_store.canonical import compact_bytes
from x_core_store.dedup import canonicalize
from x_core_store.exceptions import (
    APPLICATION_ID,
    BACKUP_CAVEATS,
    PURGE_CAVEATS,
    PRAGMA_FAILURE,
    PURGE_INCOMPLETE,
    REJECTED_SCHEMA,
    SESSION_ID_COLLISION,
    UNSUPPORTED_APPLICATION_ID,
    StoreError,
    ValidationError,
)
from x_core_store.migrations import MIGRATIONS, apply_migrations
from x_core_store.validator import EnvelopeValidator

MAX_BACKUP_BYTES: int = 104857600  # 100 MiB maximum supported backup size


@dataclass(frozen=True)
class ReviewDecision:
    decision_id: str
    decision_type: str
    reviewer_id: str
    created_at: str
    reason: str
    target_canonical_id: str | None
    source_canonical_ids: list[str]
    observation_ids: list[str]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class BackupRecord:
    backup_id: int
    backup_path: str
    created_at: str
    sha256: str
    schema_version: str


@dataclass(frozen=True)
class ExportRecord:
    export_id: int
    session_id: str
    export_path: str
    export_type: str
    created_at: str


@dataclass(frozen=True)
class PurgePreview:
    session_id: str
    observation_count: int
    canonical_posts_to_delete_count: int
    shared_canonical_posts_count: int
    known_exports: list[str]
    known_backups: list[str]
    caveats: str


@dataclass(frozen=True)
class PurgeResult:
    status: str
    session_id: str
    deleted_observations_count: int
    deleted_canonical_posts_count: int
    wal_checkpoint_status: tuple[int, int, int]
    vacuum_status: str
    caveats: str
    known_backups: list[str]
    known_exports: list[str]


class CanonicalStore:
    """Production-quality transactional SQLite store for canonical posts, sessions, and review decisions."""

    def __init__(self, database_path: str | Path, schemas_dir: Path | None = None) -> None:
        self.db_path = Path(database_path).resolve()
        self.schemas_dir = schemas_dir
        self.validator = EnvelopeValidator(schemas_dir=schemas_dir)
        self._conn: sqlite3.Connection | None = None
        self._open_and_configure()

    def _open_and_configure(self) -> None:
        """Open database and enforce PRAGMA invariants: foreign keys, secure delete, WAL, application ID."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. Foreign keys
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA foreign_keys;")
        row = cursor.fetchone()
        if not row or row[0] != 1:
            conn.close()
            raise StoreError(PRAGMA_FAILURE, "Foreign keys could not be enabled")

        # 2. Secure delete
        cursor.execute("PRAGMA secure_delete = ON;")
        cursor.execute("PRAGMA secure_delete;")
        row = cursor.fetchone()
        if not row or row[0] != 1:
            conn.close()
            raise StoreError(PRAGMA_FAILURE, "Secure delete could not be enabled")

        # 3. Journal mode WAL
        cursor.execute("PRAGMA journal_mode = WAL;")
        row = cursor.fetchone()
        if not row or row[0].upper() != "WAL":
            conn.close()
            raise StoreError(PRAGMA_FAILURE, f"WAL journal mode could not be enabled (got {row[0] if row else 'None'})")

        # 4. Application ID validation
        cursor.execute("PRAGMA application_id;")
        app_id_row = cursor.fetchone()
        current_app_id = app_id_row[0] if app_id_row else 0
        if current_app_id == 0:
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table';")
            table_count = cursor.fetchone()[0]
            if table_count > 0:
                conn.close()
                raise StoreError(UNSUPPORTED_APPLICATION_ID, "Existing database lacks supported application ID")
            cursor.execute(f"PRAGMA application_id = {APPLICATION_ID};")
        elif current_app_id != APPLICATION_ID:
            conn.close()
            raise StoreError(UNSUPPORTED_APPLICATION_ID, "Database has an unsupported application ID")

        self._conn = conn
        apply_migrations(self._conn)

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise StoreError("STORE_CLOSED", "Database connection is closed")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> CanonicalStore:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def import_envelope(self, envelope_or_bytes: dict | bytes | str) -> dict[str, Any]:
        """Validate and transactionally import an envelope, storing sessions, observations, and canonical posts."""
        raw_bytes = None
        if isinstance(envelope_or_bytes, bytes):
            raw_bytes = envelope_or_bytes
            self.validator.validate_packet_bytes(raw_bytes)
            try:
                envelope = json.loads(raw_bytes.decode("utf-8"))
            except Exception as error:
                raise ValidationError(REJECTED_SCHEMA, "Payload failed JSON decoding") from error
        elif isinstance(envelope_or_bytes, str):
            raw_bytes = envelope_or_bytes.encode("utf-8")
            self.validator.validate_packet_bytes(raw_bytes)
            try:
                envelope = json.loads(envelope_or_bytes)
            except Exception as error:
                raise ValidationError(REJECTED_SCHEMA, "Payload failed JSON decoding") from error
        else:
            envelope = envelope_or_bytes

        # Validate envelope against schema and semantic contracts
        self.validator.validate_envelope(envelope, raw_bytes=raw_bytes)

        session = envelope["session"]
        session_id = session["session_id"]
        content_digest = envelope["content_digest"]

        # Run deduplication
        canonical_posts = canonicalize(envelope["observations"])
        for canonical_post in canonical_posts:
            self.validator.validate_canonical_post(canonical_post)

        cursor = self.connection.cursor()
        now_utc = datetime.now(timezone.utc).isoformat()

        # Begin immediate transaction
        cursor.execute("BEGIN IMMEDIATE;")
        try:
            cursor.execute("SELECT content_digest FROM sessions WHERE session_id = ?;", (session_id,))
            existing_session = cursor.fetchone()
            if existing_session:
                if existing_session[0] == content_digest:
                    cursor.execute("COMMIT;")
                    return {
                        "status": "ALREADY_IMPORTED",
                        "session_id": session_id,
                        "content_digest": content_digest,
                        "observations_count": len(envelope["observations"]),
                        "canonical_posts_count": len(canonical_posts),
                    }
                else:
                    raise StoreError(
                        SESSION_ID_COLLISION,
                        "Session already exists with different content digest"
                    )

            # Insert session
            cursor.execute(
                """
                INSERT INTO sessions (
                    session_id, schema_version, source, started_at, ended_at, origin,
                    collector_version, privacy_profile, limits_json, content_digest, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    session_id,
                    session["schema_version"],
                    session["source"],
                    session["started_at"],
                    session["ended_at"],
                    session["origin"],
                    session["collector_version"],
                    session["privacy_profile"],
                    compact_bytes(session["limits"]).decode("utf-8"),
                    content_digest,
                    now_utc,
                ),
            )

            # Insert collection events
            for event in envelope.get("collection_events", []):
                cursor.execute(
                    """
                    INSERT INTO collection_events (session_id, event_code, at, safe_detail_code)
                    VALUES (?, ?, ?, ?);
                    """,
                    (session_id, event["event_code"], event["at"], event.get("safe_detail_code")),
                )

            # Insert observations and child evidence
            for obs in envelope["observations"]:
                obs_id = obs["observation_id"]
                cursor.execute(
                    """
                    INSERT INTO observations (
                        observation_id, session_id, appearance_index, top_level, visibility_ratio,
                        document_visible, platform_post_id, canonical_permalink, visible_text,
                        displayed_timestamp, input_location_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        obs_id,
                        session_id,
                        obs["appearance_index"],
                        1 if obs.get("top_level", True) else 0,
                        obs["visibility_ratio"],
                        1 if obs["document_visible"] else 0,
                        obs.get("platform_post_id"),
                        obs.get("canonical_permalink"),
                        obs.get("visible_text"),
                        obs.get("displayed_timestamp"),
                        compact_bytes(obs["input_location"]).decode("utf-8"),
                    ),
                )

                for auth in obs.get("authors", []):
                    cursor.execute(
                        """
                        INSERT INTO observation_authors (
                            observation_id, local_author_id, platform_author_id, display_name,
                            handle, role, identity_confidence, uncertainty_codes_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            obs_id,
                            auth["local_author_id"],
                            auth.get("platform_author_id"),
                            auth.get("display_name"),
                            auth.get("handle"),
                            auth["role"],
                            auth["identity_confidence"],
                            compact_bytes(auth.get("uncertainty_codes", [])).decode("utf-8"),
                        ),
                    )

                for rel in obs.get("relationships", []):
                    cursor.execute(
                        """
                        INSERT INTO observation_relationships (
                            observation_id, kind, source_local_post_id, source_platform_post_id,
                            confidence, provenance_ids_json
                        ) VALUES (?, ?, ?, ?, ?, ?);
                        """,
                        (
                            obs_id,
                            rel["kind"],
                            rel["source_local_post_id"],
                            rel.get("source_platform_post_id"),
                            rel["confidence"],
                            compact_bytes(rel.get("provenance_ids", [])).decode("utf-8"),
                        ),
                    )

                for med in obs.get("media", []):
                    cursor.execute(
                        """
                        INSERT INTO observation_media (
                            observation_id, local_media_id, kind, alt_text, visible_description,
                            perceptual_fingerprint, binary_collected, confidence, provenance_ids_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            obs_id,
                            med["local_media_id"],
                            med["kind"],
                            med.get("alt_text"),
                            med.get("visible_description"),
                            med.get("perceptual_fingerprint"),
                            0,
                            med["confidence"],
                            compact_bytes(med.get("provenance_ids", [])).decode("utf-8"),
                        ),
                    )

                prom = obs["promotion"]
                cursor.execute(
                    """
                    INSERT INTO observation_promotions (observation_id, status, evidence_json, confidence)
                    VALUES (?, ?, ?, ?);
                    """,
                    (
                        obs_id,
                        prom["status"],
                        compact_bytes(prom.get("evidence", [])).decode("utf-8"),
                        prom["confidence"],
                    ),
                )

                for prov in obs.get("provenance", []):
                    cursor.execute(
                        """
                        INSERT INTO observation_provenance (
                            observation_id, provenance_id, modality, collector_version,
                            parser_or_ocr_version, field, observed_at, video_time_ms,
                            crop_xywh_json, confidence
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            obs_id,
                            prov["provenance_id"],
                            prov["modality"],
                            prov["collector_version"],
                            prov["parser_or_ocr_version"],
                            prov["field"],
                            prov["observed_at"],
                            prov.get("video_time_ms"),
                            compact_bytes(prov.get("crop_xywh")).decode("utf-8") if prov.get("crop_xywh") is not None else None,
                            prov["confidence"],
                        ),
                    )

                for unc in obs.get("uncertainty", []):
                    cursor.execute(
                        """
                        INSERT INTO observation_uncertainties (
                            observation_id, code, field, severity, requires_review, safe_detail
                        ) VALUES (?, ?, ?, ?, ?, ?);
                        """,
                        (
                            obs_id,
                            unc["code"],
                            unc["field"],
                            unc["severity"],
                            1 if unc.get("requires_review", False) else 0,
                            unc.get("safe_detail"),
                        ),
                    )

            # Insert canonical posts and linkage
            for post in canonical_posts:
                post_id = post["local_post_id"]
                dedup = post["deduplication"]
                prom = post["promotion"]

                cursor.execute(
                    """
                    INSERT INTO canonical_posts (
                        local_post_id, platform_post_id, canonical_permalink, visible_text,
                        promotion_status, promotion_confidence, promotion_evidence_json,
                        dedup_method, dedup_confidence, dedup_review_required, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(local_post_id) DO UPDATE SET
                        platform_post_id = COALESCE(excluded.platform_post_id, canonical_posts.platform_post_id),
                        canonical_permalink = COALESCE(excluded.canonical_permalink, canonical_posts.canonical_permalink),
                        visible_text = COALESCE(excluded.visible_text, canonical_posts.visible_text);
                    """,
                    (
                        post_id,
                        post.get("platform_post_id"),
                        post.get("canonical_permalink"),
                        post.get("visible_text"),
                        prom["status"],
                        prom["confidence"],
                        compact_bytes(prom.get("evidence", [])).decode("utf-8"),
                        dedup["method"],
                        dedup["confidence"],
                        1 if dedup.get("review_required", False) else 0,
                        now_utc,
                    ),
                )

                for obs_id in post["observation_ids"]:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO canonical_post_observations (local_post_id, observation_id)
                        VALUES (?, ?);
                        """,
                        (post_id, obs_id),
                    )

                cursor.execute(
                    "SELECT local_author_id, role FROM canonical_post_authors WHERE local_post_id = ?;",
                    (post_id,),
                )
                existing_authors = {(r[0], r[1]) for r in cursor.fetchall()}

                for auth in post.get("authors", []):
                    key_auth = (auth["local_author_id"], auth["role"])
                    if key_auth not in existing_authors:
                        existing_authors.add(key_auth)
                        cursor.execute(
                            """
                            INSERT INTO canonical_post_authors (
                                local_post_id, local_author_id, platform_author_id, display_name,
                                handle, role, identity_confidence, uncertainty_codes_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                            """,
                            (
                                post_id,
                                auth["local_author_id"],
                                auth.get("platform_author_id"),
                                auth.get("display_name"),
                                auth.get("handle"),
                                auth["role"],
                                auth["identity_confidence"],
                                compact_bytes(auth.get("uncertainty_codes", [])).decode("utf-8"),
                            ),
                        )

                cursor.execute(
                    "SELECT kind, source_local_post_id FROM canonical_post_relationships WHERE local_post_id = ?;",
                    (post_id,),
                )
                existing_rels = {(r[0], r[1]) for r in cursor.fetchall()}

                for rel in post.get("relationships", []):
                    key_rel = (rel["kind"], rel["source_local_post_id"])
                    if key_rel not in existing_rels:
                        existing_rels.add(key_rel)
                        cursor.execute(
                            """
                            INSERT INTO canonical_post_relationships (
                                local_post_id, kind, source_local_post_id, source_platform_post_id,
                                confidence, provenance_ids_json
                            ) VALUES (?, ?, ?, ?, ?, ?);
                            """,
                            (
                                post_id,
                                rel["kind"],
                                rel["source_local_post_id"],
                                rel.get("source_platform_post_id"),
                                rel["confidence"],
                                compact_bytes(rel.get("provenance_ids", [])).decode("utf-8"),
                            ),
                        )

                cursor.execute(
                    "SELECT local_media_id FROM canonical_post_media WHERE local_post_id = ?;",
                    (post_id,),
                )
                existing_media = {r[0] for r in cursor.fetchall()}

                for med in post.get("media", []):
                    key_med = med["local_media_id"]
                    if key_med not in existing_media:
                        existing_media.add(key_med)
                        cursor.execute(
                            """
                            INSERT INTO canonical_post_media (
                                local_post_id, local_media_id, kind, alt_text, visible_description,
                                perceptual_fingerprint, binary_collected, confidence, provenance_ids_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                            """,
                            (
                                post_id,
                                med["local_media_id"],
                                med["kind"],
                                med.get("alt_text"),
                                med.get("visible_description"),
                                med.get("perceptual_fingerprint"),
                                0,
                                med["confidence"],
                                compact_bytes(med.get("provenance_ids", [])).decode("utf-8"),
                            ),
                        )

                cursor.execute(
                    "SELECT code, field FROM canonical_post_uncertainties WHERE local_post_id = ?;",
                    (post_id,),
                )
                existing_unc = {(r[0], r[1]) for r in cursor.fetchall()}

                for unc in post.get("uncertainty", []):
                    key_unc = (unc["code"], unc["field"])
                    if key_unc not in existing_unc:
                        existing_unc.add(key_unc)
                        cursor.execute(
                            """
                            INSERT INTO canonical_post_uncertainties (
                                local_post_id, code, field, severity, requires_review, safe_detail
                            ) VALUES (?, ?, ?, ?, ?, ?);
                            """,
                            (
                                post_id,
                                unc["code"],
                                unc["field"],
                                unc["severity"],
                                1 if unc.get("requires_review", False) else 0,
                                unc.get("safe_detail"),
                            ),
                        )

            cursor.execute("COMMIT;")
        except Exception:
            cursor.execute("ROLLBACK;")
            raise

        organic_count = sum(p["promotion"]["status"] == "organic" for p in canonical_posts)
        promoted_count = sum(p["promotion"]["status"] == "promoted" for p in canonical_posts)
        ambiguous_count = sum(p["promotion"]["status"] == "ambiguous" for p in canonical_posts)

        return {
            "status": "IMPORTED",
            "session_id": session_id,
            "content_digest": content_digest,
            "observations_count": len(envelope["observations"]),
            "canonical_posts_count": len(canonical_posts),
            "organic_count": organic_count,
            "promoted_count": promoted_count,
            "ambiguous_count": ambiguous_count,
        }

    def record_review_decision(self, decision: ReviewDecision) -> str:
        """Persist an auditable human review decision (e.g., merge or split)."""
        cursor = self.connection.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        try:
            # If human_merge with a target_canonical_id, ensure target exists in canonical_posts
            if decision.decision_type == "human_merge" and decision.target_canonical_id:
                cursor.execute(
                    "SELECT COUNT(*) FROM canonical_posts WHERE local_post_id = ?;",
                    (decision.target_canonical_id,),
                )
                if cursor.fetchone()[0] == 0:
                    cursor.execute(
                        """
                        INSERT INTO canonical_posts (
                            local_post_id, platform_post_id, canonical_permalink, visible_text,
                            promotion_status, promotion_confidence, promotion_evidence_json,
                            dedup_method, dedup_confidence, dedup_review_required, created_at
                        ) VALUES (?, NULL, NULL, NULL, 'organic', 1.0, '["manual_review"]', 'human_review', 1.0, 0, ?);
                        """,
                        (decision.target_canonical_id, decision.created_at),
                    )

                for obs_id in decision.observation_ids:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO canonical_post_observations (local_post_id, observation_id)
                        VALUES (?, ?);
                        """,
                        (decision.target_canonical_id, obs_id),
                    )

            cursor.execute(
                """
                INSERT INTO review_decisions (
                    decision_id, decision_type, reviewer_id, created_at, reason,
                    target_canonical_id, source_canonical_ids_json, observation_ids_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    decision.decision_id,
                    decision.decision_type,
                    decision.reviewer_id,
                    decision.created_at,
                    decision.reason,
                    decision.target_canonical_id,
                    compact_bytes(decision.source_canonical_ids).decode("utf-8"),
                    compact_bytes(decision.observation_ids).decode("utf-8"),
                    compact_bytes(decision.metadata).decode("utf-8"),
                ),
            )

            cursor.execute("COMMIT;")
        except Exception:
            cursor.execute("ROLLBACK;")
            raise

        return decision.decision_id

    def list_review_decisions(self, target_canonical_id: str | None = None) -> list[ReviewDecision]:
        """List review decisions, optionally filtered by target canonical post ID."""
        cursor = self.connection.cursor()
        if target_canonical_id:
            cursor.execute(
                "SELECT * FROM review_decisions WHERE target_canonical_id = ? ORDER BY created_at ASC;",
                (target_canonical_id,),
            )
        else:
            cursor.execute("SELECT * FROM review_decisions ORDER BY created_at ASC;")

        results = []
        for row in cursor.fetchall():
            results.append(
                ReviewDecision(
                    decision_id=row["decision_id"],
                    decision_type=row["decision_type"],
                    reviewer_id=row["reviewer_id"],
                    created_at=row["created_at"],
                    reason=row["reason"],
                    target_canonical_id=row["target_canonical_id"],
                    source_canonical_ids=json.loads(row["source_canonical_ids_json"]),
                    observation_ids=json.loads(row["observation_ids_json"]),
                    metadata=json.loads(row["metadata_json"]),
                )
            )
        return results

    def create_backup(self, backup_path: str | Path, overwrite: bool = False) -> BackupRecord:
        """Create a consistent online SQLite backup, verify integrity, and record inventory."""
        target = Path(backup_path).resolve()
        if target.exists() and not overwrite:
            raise StoreError("BACKUP_ERROR", "Backup file already exists and overwrite is False")

        target.parent.mkdir(parents=True, exist_ok=True)

        # Checkpoint WAL before backup
        cursor = self.connection.cursor()
        cursor.execute("PRAGMA wal_checkpoint(PASSIVE);")

        dest_conn = sqlite3.connect(str(target))
        try:
            self.connection.backup(dest_conn)
            dest_cursor = dest_conn.cursor()
            dest_cursor.execute("PRAGMA integrity_check;")
            check = dest_cursor.fetchone()[0]
            if check != "ok":
                raise StoreError("BACKUP_ERROR", f"Backup failed integrity check: {check}")
            dest_cursor.execute("PRAGMA application_id;")
            app_id = dest_cursor.fetchone()[0]
            if app_id != APPLICATION_ID:
                raise StoreError("BACKUP_ERROR", "Backup file application ID mismatch")
        finally:
            dest_conn.close()

        file_bytes = target.read_bytes()
        digest = hashlib.sha256(file_bytes).hexdigest()
        now_utc = datetime.now(timezone.utc).isoformat()
        schema_ver = "1.0.0"

        cursor.execute("BEGIN IMMEDIATE;")
        try:
            cursor.execute(
                """
                INSERT INTO backup_inventory (backup_path, created_at, sha256, schema_version)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(backup_path) DO UPDATE SET
                    created_at = excluded.created_at,
                    sha256 = excluded.sha256,
                    schema_version = excluded.schema_version;
                """,
                (str(target), now_utc, digest, schema_ver),
            )
            cursor.execute("SELECT backup_id FROM backup_inventory WHERE backup_path = ?;", (str(target),))
            backup_id = cursor.fetchone()[0]
            cursor.execute("COMMIT;")
        except Exception:
            cursor.execute("ROLLBACK;")
            raise

        return BackupRecord(
            backup_id=backup_id,
            backup_path=str(target),
            created_at=now_utc,
            sha256=digest,
            schema_version=schema_ver,
        )

    def restore_backup(self, backup_path: str | Path) -> None:
        """Restore database from a verified product backup file."""
        target = Path(backup_path).resolve()
        if not target.is_file():
            raise StoreError("BACKUP_ERROR", "Backup file does not exist")

        file_size = target.stat().st_size
        if file_size == 0 or file_size > MAX_BACKUP_BYTES:
            raise StoreError(
                "BACKUP_ERROR",
                "Backup file size is invalid or exceeds maximum allowed boundary",
            )

        backup_conn = sqlite3.connect(str(target))
        try:
            b_cursor = backup_conn.cursor()
            b_cursor.execute("PRAGMA integrity_check;")
            if b_cursor.fetchone()[0] != "ok":
                raise StoreError("BACKUP_ERROR", "Backup integrity check failed")
            b_cursor.execute("PRAGMA application_id;")
            if b_cursor.fetchone()[0] != APPLICATION_ID:
                raise StoreError("BACKUP_ERROR", "Backup application ID mismatch")

            # Verify schema version matches current/latest supported migration version
            b_cursor.execute("PRAGMA user_version;")
            ver_row = b_cursor.fetchone()
            backup_version = ver_row[0] if ver_row else 0
            latest_version = max(m["version"] for m in MIGRATIONS)
            if backup_version != latest_version:
                raise StoreError(
                    "BACKUP_ERROR",
                    "Unsupported backup schema version",
                )

            # Restore into current database
            backup_conn.backup(self.connection)
        finally:
            backup_conn.close()

        # Re-verify pragmas and integrity
        cursor = self.connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA secure_delete = ON;")
        cursor.execute("PRAGMA integrity_check;")
        if cursor.fetchone()[0] != "ok":
            raise StoreError("BACKUP_ERROR", "Restored database failed integrity check")

    def list_backups(self) -> list[BackupRecord]:
        """List all tracked backups from the local database inventory."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM backup_inventory ORDER BY created_at ASC;")
        return [
            BackupRecord(
                backup_id=row["backup_id"],
                backup_path=row["backup_path"],
                created_at=row["created_at"],
                sha256=row["sha256"],
                schema_version=row["schema_version"],
            )
            for row in cursor.fetchall()
        ]

    def record_known_export(self, session_id: str, export_path: str | Path, export_type: str) -> None:
        """Record an exported report or dataset path for purge preview tracking."""
        target = str(Path(export_path).resolve())
        cursor = self.connection.cursor()
        now_utc = datetime.now(timezone.utc).isoformat()
        cursor.execute("BEGIN IMMEDIATE;")
        try:
            cursor.execute(
                """
                INSERT INTO known_exports (session_id, export_path, export_type, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(export_path) DO UPDATE SET
                    created_at = excluded.created_at,
                    export_type = excluded.export_type;
                """,
                (session_id, target, export_type, now_utc),
            )
            cursor.execute("COMMIT;")
        except Exception:
            cursor.execute("ROLLBACK;")
            raise

    def list_known_exports(self, session_id: str | None = None) -> list[ExportRecord]:
        """List known exports, optionally filtered by session ID."""
        cursor = self.connection.cursor()
        if session_id:
            cursor.execute("SELECT * FROM known_exports WHERE session_id = ? ORDER BY created_at ASC;", (session_id,))
        else:
            cursor.execute("SELECT * FROM known_exports ORDER BY created_at ASC;")
        return [
            ExportRecord(
                export_id=row["export_id"],
                session_id=row["session_id"],
                export_path=row["export_path"],
                export_type=row["export_type"],
                created_at=row["created_at"],
            )
            for row in cursor.fetchall()
        ]

    def preview_session_purge(self, session_id: str) -> PurgePreview:
        """Preview counts, known exports, and documented caveats before purging a session."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM observations WHERE session_id = ?;", (session_id,))
        obs_count = cursor.fetchone()[0]

        # Canonical posts linked to this session
        cursor.execute(
            """
            SELECT DISTINCT local_post_id FROM canonical_post_observations
            WHERE observation_id IN (SELECT observation_id FROM observations WHERE session_id = ?);
            """,
            (session_id,),
        )
        linked_post_ids = {row[0] for row in cursor.fetchall()}

        # Check which of these have observations from OTHER sessions or are retained by recommendations
        posts_to_delete = 0
        shared_posts = 0
        for post_id in linked_post_ids:
            cursor.execute(
                """
                SELECT COUNT(*) FROM canonical_post_observations cpo
                JOIN observations o ON cpo.observation_id = o.observation_id
                WHERE cpo.local_post_id = ? AND o.session_id != ?;
                """,
                (post_id, session_id),
            )
            other_obs_count = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(*) FROM analysis_recommendations
                WHERE target_type = 'post' AND target_local_id = ?;
                """,
                (post_id,),
            )
            recs_count = cursor.fetchone()[0]

            if other_obs_count == 0 and recs_count == 0:
                posts_to_delete += 1
            else:
                shared_posts += 1

        exports = [e.export_path for e in self.list_known_exports(session_id)]
        backups = [b.backup_path for b in self.list_backups()]

        return PurgePreview(
            session_id=session_id,
            observation_count=obs_count,
            canonical_posts_to_delete_count=posts_to_delete,
            shared_canonical_posts_count=shared_posts,
            known_exports=exports,
            known_backups=backups,
            caveats=PURGE_CAVEATS,
        )

    def purge_session(self, session_id: str, run_vacuum: bool = True) -> PurgeResult:
        """Transactionally purge a session, delete orphaned canonical posts, truncate WAL, and run optional vacuum."""
        preview = self.preview_session_purge(session_id)
        cursor = self.connection.cursor()

        cursor.execute("BEGIN IMMEDIATE;")
        try:
            # Delete session-owned analyses
            cursor.execute("DELETE FROM post_analyses WHERE session_id = ?;", (session_id,))

            # Delete observations belonging to session (cascades to observation authors/media/provenance/uncertainties/cpo)
            cursor.execute("DELETE FROM observations WHERE session_id = ?;", (session_id,))
            deleted_observations_count = cursor.rowcount

            # Delete session row (cascades to collection events)
            cursor.execute("DELETE FROM sessions WHERE session_id = ?;", (session_id,))

            # Delete canonical posts that have NO remaining observations and NO remaining analysis recommendations
            cursor.execute(
                """
                DELETE FROM canonical_posts
                WHERE local_post_id NOT IN (SELECT DISTINCT local_post_id FROM canonical_post_observations)
                  AND local_post_id NOT IN (
                      SELECT DISTINCT target_local_id FROM analysis_recommendations WHERE target_type = 'post'
                  );
                """
            )
            deleted_canonical_posts_count = cursor.rowcount

            cursor.execute("COMMIT;")
        except Exception:
            cursor.execute("ROLLBACK;")
            raise

        # Checkpoint WAL with TRUNCATE
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        wal_status = cursor.fetchone()
        wal_checkpoint_status = (wal_status[0], wal_status[1], wal_status[2]) if wal_status else (0, 0, 0)
        if wal_checkpoint_status[0] != 0:
            raise StoreError(
                PURGE_INCOMPLETE,
                "WAL checkpoint could not complete (busy lock); close active readers and retry purge",
            )

        vacuum_status = "VACUUM_NOT_RUN"
        if run_vacuum and self.db_path.is_file():
            try:
                db_size = self.db_path.stat().st_size
                free_disk = shutil.disk_usage(self.db_path.parent).free
                if free_disk >= db_size * 2:
                    cursor.execute("VACUUM;")
                    vacuum_status = "VACUUM_RUN"
                else:
                    vacuum_status = "VACUUM_NOT_RUN"
            except Exception:
                vacuum_status = "VACUUM_NOT_RUN"

        # Verification check: session must be completely absent
        cursor.execute("SELECT COUNT(*) FROM sessions WHERE session_id = ?;", (session_id,))
        if cursor.fetchone()[0] != 0:
            raise StoreError("PURGE_INCOMPLETE", "Session row remains after purge execution")
        cursor.execute("SELECT COUNT(*) FROM observations WHERE session_id = ?;", (session_id,))
        if cursor.fetchone()[0] != 0:
            raise StoreError("PURGE_INCOMPLETE", "Observations remain after purge execution")

        return PurgeResult(
            status="COMPLETED",
            session_id=session_id,
            deleted_observations_count=max(deleted_observations_count, 0),
            deleted_canonical_posts_count=max(deleted_canonical_posts_count, 0),
            wal_checkpoint_status=wal_checkpoint_status,
            vacuum_status=vacuum_status,
            caveats=PURGE_CAVEATS,
            known_backups=preview.known_backups,
            known_exports=preview.known_exports,
        )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Fetch session metadata by session ID."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM sessions WHERE session_id = ?;", (session_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return dict(row)

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all stored sessions."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM sessions ORDER BY started_at ASC;")
        return [dict(row) for row in cursor.fetchall()]

    def get_canonical_post(self, local_post_id: str) -> dict[str, Any] | None:
        """Fetch full canonical post entity by local post ID."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM canonical_posts WHERE local_post_id = ?;", (local_post_id,))
        row = cursor.fetchone()
        if not row:
            return None

        post = dict(row)
        cursor.execute("SELECT observation_id FROM canonical_post_observations WHERE local_post_id = ? ORDER BY observation_id ASC;", (local_post_id,))
        post["observation_ids"] = [r[0] for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM canonical_post_authors WHERE local_post_id = ? ORDER BY author_row_id ASC;", (local_post_id,))
        post["authors"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM canonical_post_relationships WHERE local_post_id = ? ORDER BY relationship_row_id ASC;", (local_post_id,))
        post["relationships"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM canonical_post_media WHERE local_post_id = ? ORDER BY media_row_id ASC;", (local_post_id,))
        post["media"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM canonical_post_uncertainties WHERE local_post_id = ? ORDER BY uncertainty_row_id ASC;", (local_post_id,))
        post["uncertainty"] = [dict(r) for r in cursor.fetchall()]

        return post

    def list_canonical_posts(self, session_id: str | None = None) -> list[dict[str, Any]]:
        """List canonical posts, optionally filtered by session ID."""
        cursor = self.connection.cursor()
        if session_id:
            cursor.execute(
                """
                SELECT DISTINCT cp.local_post_id FROM canonical_posts cp
                JOIN canonical_post_observations cpo ON cp.local_post_id = cpo.local_post_id
                JOIN observations o ON cpo.observation_id = o.observation_id
                WHERE o.session_id = ?
                ORDER BY cp.local_post_id ASC;
                """,
                (session_id,),
            )
        else:
            cursor.execute("SELECT local_post_id FROM canonical_posts ORDER BY local_post_id ASC;")

        ids = [row[0] for row in cursor.fetchall()]
        posts = []
        for pid in ids:
            p = self.get_canonical_post(pid)
            if p:
                posts.append(p)
        return posts

    def get_observation(self, observation_id: str) -> dict[str, Any] | None:
        """Fetch raw observation by observation ID."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM observations WHERE observation_id = ?;", (observation_id,))
        row = cursor.fetchone()
        if not row:
            return None
        obs = dict(row)

        cursor.execute("SELECT * FROM observation_authors WHERE observation_id = ? ORDER BY author_row_id ASC;", (observation_id,))
        obs["authors"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM observation_relationships WHERE observation_id = ? ORDER BY relationship_row_id ASC;", (observation_id,))
        obs["relationships"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM observation_media WHERE observation_id = ? ORDER BY media_row_id ASC;", (observation_id,))
        obs["media"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM observation_promotions WHERE observation_id = ?;", (observation_id,))
        prom = cursor.fetchone()
        obs["promotion"] = dict(prom) if prom else None

        cursor.execute("SELECT * FROM observation_provenance WHERE observation_id = ? ORDER BY provenance_row_id ASC;", (observation_id,))
        obs["provenance"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM observation_uncertainties WHERE observation_id = ? ORDER BY uncertainty_row_id ASC;", (observation_id,))
        obs["uncertainty"] = [dict(r) for r in cursor.fetchall()]

        return obs
