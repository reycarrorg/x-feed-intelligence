"""Explicit versioned SQLite migrations with SHA-256 checksums."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone

from x_core_store.exceptions import MigrationError

INITIAL_SCHEMA_V1_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backup_inventory (
    backup_id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    schema_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS known_exports (
    export_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    export_path TEXT NOT NULL UNIQUE,
    export_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    origin TEXT,
    collector_version TEXT NOT NULL,
    privacy_profile TEXT NOT NULL,
    limits_json TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    imported_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    event_code TEXT NOT NULL,
    at TEXT NOT NULL,
    safe_detail_code TEXT
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    appearance_index INTEGER NOT NULL,
    top_level INTEGER NOT NULL DEFAULT 1,
    visibility_ratio REAL NOT NULL,
    document_visible INTEGER NOT NULL,
    platform_post_id TEXT,
    canonical_permalink TEXT,
    visible_text TEXT,
    displayed_timestamp TEXT,
    input_location_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_authors (
    author_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
    local_author_id TEXT NOT NULL,
    platform_author_id TEXT,
    display_name TEXT,
    handle TEXT,
    role TEXT NOT NULL,
    identity_confidence REAL NOT NULL,
    uncertainty_codes_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_relationships (
    relationship_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    source_local_post_id TEXT NOT NULL,
    source_platform_post_id TEXT,
    confidence REAL NOT NULL,
    provenance_ids_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_media (
    media_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
    local_media_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    alt_text TEXT,
    visible_description TEXT,
    perceptual_fingerprint TEXT,
    binary_collected INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL,
    provenance_ids_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_promotions (
    observation_id TEXT PRIMARY KEY REFERENCES observations(observation_id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    confidence REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_provenance (
    provenance_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
    provenance_id TEXT NOT NULL,
    modality TEXT NOT NULL,
    collector_version TEXT NOT NULL,
    parser_or_ocr_version TEXT NOT NULL,
    field TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    video_time_ms INTEGER,
    crop_xywh_json TEXT,
    confidence REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS observation_uncertainties (
    uncertainty_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    field TEXT NOT NULL,
    severity TEXT NOT NULL,
    requires_review INTEGER NOT NULL,
    safe_detail TEXT
);

CREATE TABLE IF NOT EXISTS canonical_posts (
    local_post_id TEXT PRIMARY KEY,
    platform_post_id TEXT,
    canonical_permalink TEXT,
    visible_text TEXT,
    promotion_status TEXT NOT NULL,
    promotion_confidence REAL NOT NULL,
    promotion_evidence_json TEXT NOT NULL,
    dedup_method TEXT NOT NULL,
    dedup_confidence REAL NOT NULL,
    dedup_review_required INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_post_observations (
    local_post_id TEXT NOT NULL REFERENCES canonical_posts(local_post_id) ON DELETE CASCADE,
    observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
    PRIMARY KEY (local_post_id, observation_id)
);

CREATE TABLE IF NOT EXISTS canonical_post_authors (
    author_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_post_id TEXT NOT NULL REFERENCES canonical_posts(local_post_id) ON DELETE CASCADE,
    local_author_id TEXT NOT NULL,
    platform_author_id TEXT,
    display_name TEXT,
    handle TEXT,
    role TEXT NOT NULL,
    identity_confidence REAL NOT NULL,
    uncertainty_codes_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_post_relationships (
    relationship_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_post_id TEXT NOT NULL REFERENCES canonical_posts(local_post_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    source_local_post_id TEXT NOT NULL,
    source_platform_post_id TEXT,
    confidence REAL NOT NULL,
    provenance_ids_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_post_media (
    media_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_post_id TEXT NOT NULL REFERENCES canonical_posts(local_post_id) ON DELETE CASCADE,
    local_media_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    alt_text TEXT,
    visible_description TEXT,
    perceptual_fingerprint TEXT,
    binary_collected INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL,
    provenance_ids_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS canonical_post_uncertainties (
    uncertainty_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_post_id TEXT NOT NULL REFERENCES canonical_posts(local_post_id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    field TEXT NOT NULL,
    severity TEXT NOT NULL,
    requires_review INTEGER NOT NULL,
    safe_detail TEXT
);

CREATE TABLE IF NOT EXISTS review_decisions (
    decision_id TEXT PRIMARY KEY,
    decision_type TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    target_canonical_id TEXT,
    source_canonical_ids_json TEXT NOT NULL,
    observation_ids_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS post_analyses (
    analysis_id TEXT PRIMARY KEY,
    local_post_id TEXT NOT NULL REFERENCES canonical_posts(local_post_id) ON DELETE CASCADE,
    session_id TEXT REFERENCES sessions(session_id) ON DELETE CASCADE,
    classification TEXT NOT NULL,
    manual_action TEXT NOT NULL,
    score_relevance INTEGER NOT NULL,
    score_credibility INTEGER NOT NULL,
    score_information_value INTEGER NOT NULL,
    score_actionability INTEGER NOT NULL,
    score_risk INTEGER NOT NULL,
    score_priority INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_verifications (
    verification_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id TEXT NOT NULL REFERENCES post_analyses(analysis_id) ON DELETE CASCADE,
    verification_id TEXT NOT NULL,
    claim_summary TEXT NOT NULL,
    required INTEGER NOT NULL,
    reason_code TEXT,
    result TEXT NOT NULL,
    not_checked_reason TEXT,
    sources_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_recommendations (
    rec_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id TEXT NOT NULL REFERENCES post_analyses(analysis_id) ON DELETE CASCADE,
    recommendation_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_local_id TEXT NOT NULL,
    action TEXT NOT NULL,
    evidence_post_ids_json TEXT NOT NULL,
    qualifying_original_post_count INTEGER,
    confidence REAL NOT NULL,
    performed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS analysis_redactions (
    redaction_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    analysis_id TEXT NOT NULL REFERENCES post_analyses(analysis_id) ON DELETE CASCADE,
    json_pointer TEXT NOT NULL,
    action TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    replacement TEXT
);

CREATE INDEX IF NOT EXISTS idx_observations_session_id ON observations(session_id);
CREATE INDEX IF NOT EXISTS idx_observations_platform_post_id ON observations(platform_post_id);
CREATE INDEX IF NOT EXISTS idx_cpo_observation_id ON canonical_post_observations(observation_id);
CREATE INDEX IF NOT EXISTS idx_cpo_local_post_id ON canonical_post_observations(local_post_id);
CREATE INDEX IF NOT EXISTS idx_review_decisions_target ON review_decisions(target_canonical_id);
"""

MIGRATIONS = [
    {
        "version": 1,
        "name": "001_initial_core_schema",
        "sql": INITIAL_SCHEMA_V1_SQL,
    }
]


def migration_checksum(sql: str) -> str:
    """Compute sha256 checksum over migration SQL text."""
    return hashlib.sha256(sql.strip().encode("utf-8")).hexdigest()


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Ensure schema_migrations table exists, verify applied checksums, and apply pending migrations."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        );
    """)

    cursor.execute("SELECT version, name, checksum FROM schema_migrations ORDER BY version ASC;")
    applied = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

    for migration in MIGRATIONS:
        version = migration["version"]
        name = migration["name"]
        expected_checksum = migration_checksum(migration["sql"])

        if version in applied:
            applied_name, applied_checksum = applied[version]
            if applied_checksum != expected_checksum:
                raise MigrationError(
                    "MIGRATION_ERROR",
                    f"Checksum mismatch for already applied migration {version} ({name})"
                )
        else:
            now_utc = datetime.now(timezone.utc).isoformat()
            quoted_name = "'" + name.replace("'", "''") + "'"
            quoted_checksum = "'" + expected_checksum.replace("'", "''") + "'"
            quoted_time = "'" + now_utc.replace("'", "''") + "'"
            script = f"""
BEGIN IMMEDIATE;
{migration["sql"]}
INSERT INTO schema_migrations (version, name, checksum, applied_at)
VALUES ({int(version)}, {quoted_name}, {quoted_checksum}, {quoted_time});
PRAGMA user_version = {int(version)};
COMMIT;
"""
            try:
                conn.executescript(script)
            except Exception as error:
                if conn.in_transaction:
                    conn.rollback()
                raise MigrationError("MIGRATION_ERROR", "Migration transaction failed") from error
