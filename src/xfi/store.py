"""Product-owned SQLite persistence, backup, restore, and retention controls."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .canonical import canonical_bytes, canonicalize, has_merge_conflict, observation_key
from .errors import StoreError, ValidationError

APPLICATION_ID = 0x58464931  # XFI1
SCHEMA_VERSION = 1
MIGRATION_SQL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  origin TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT NOT NULL,
  content_digest TEXT NOT NULL UNIQUE,
  envelope_json BLOB NOT NULL
);
CREATE TABLE observations (
  observation_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
  appearance_index INTEGER NOT NULL,
  record_json BLOB NOT NULL,
  UNIQUE(session_id, appearance_index, observation_id)
);
CREATE TABLE canonical_posts (
  local_post_id TEXT PRIMARY KEY,
  record_json BLOB NOT NULL
);
CREATE TABLE post_observations (
  local_post_id TEXT NOT NULL REFERENCES canonical_posts(local_post_id) ON DELETE CASCADE,
  observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
  PRIMARY KEY(local_post_id, observation_id)
);
CREATE TABLE analyses (
  analysis_id TEXT PRIMARY KEY,
  local_post_id TEXT NOT NULL REFERENCES canonical_posts(local_post_id) ON DELETE CASCADE,
  record_json BLOB NOT NULL
);
CREATE TABLE review_decisions (
  decision_id TEXT PRIMARY KEY,
  reviewer_local_id TEXT NOT NULL,
  decided_at TEXT NOT NULL,
  reason TEXT NOT NULL,
  decision_type TEXT NOT NULL CHECK(decision_type IN ('merge','split','classification','promotion')),
  prior_post_ids_json BLOB NOT NULL,
  observation_ids_json BLOB NOT NULL
);
CREATE TABLE exports (
  export_path TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
  sensitivity TEXT NOT NULL CHECK(sensitivity IN ('PRIVATE','SANITIZED')),
  sha256 TEXT NOT NULL,
  created_on TEXT NOT NULL
);
CREATE TABLE backups (
  backup_path TEXT PRIMARY KEY,
  sha256 TEXT NOT NULL,
  created_on TEXT NOT NULL
);
"""
MIGRATION_CHECKSUM = hashlib.sha256(MIGRATION_SQL.encode()).hexdigest()


def _is_local_path(path: Path) -> bool:
    lowered = str(path.resolve()).lower()
    denied = ("/library/cloudstorage/", "/icloud drive/", "/dropbox/", "/google drive/", "/volumes/")
    return not any(marker in lowered for marker in denied)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class ImportResult:
    session_id: str
    canonical_count: int
    idempotent: bool


class Store:
    def __init__(self, path: Path, *, allow_nonlocal_for_test: bool = False):
        self.path = path.resolve()
        if not allow_nonlocal_for_test and not _is_local_path(self.path):
            raise StoreError("NONLOCAL_DATABASE_REJECTED")
        existed = self.path.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=1.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA secure_delete=ON")
        journal = self.connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if str(journal).lower() != "wal":
            self.connection.close()
            raise StoreError("WAL_UNAVAILABLE")
        if existed:
            self._verify_identity()
        else:
            self._migrate_new()
        self._verify_configuration()

    def _migrate_new(self) -> None:
        self.connection.executescript(MIGRATION_SQL)
        self.connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
        self.connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.connection.executemany("INSERT INTO meta(key,value) VALUES (?,?)", [
            ("schema_version", str(SCHEMA_VERSION)),
            ("migration_checksum", MIGRATION_CHECKSUM),
        ])
        self.connection.commit()

    def _verify_identity(self) -> None:
        application_id = self.connection.execute("PRAGMA application_id").fetchone()[0]
        user_version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if application_id != APPLICATION_ID or user_version != SCHEMA_VERSION:
            self.connection.close()
            raise StoreError("ARBITRARY_DATABASE_REJECTED")
        row = self.connection.execute("SELECT value FROM meta WHERE key='migration_checksum'").fetchone()
        if row is None or row[0] != MIGRATION_CHECKSUM:
            self.connection.close()
            raise StoreError("MIGRATION_CHECKSUM_MISMATCH")

    def _verify_configuration(self) -> None:
        expected = {"foreign_keys": 1, "secure_delete": 1, "application_id": APPLICATION_ID, "user_version": SCHEMA_VERSION}
        for pragma, value in expected.items():
            actual = self.connection.execute(f"PRAGMA {pragma}").fetchone()[0]
            if actual != value:
                raise StoreError("SQLITE_CONFIGURATION_MISMATCH")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _rebuild_canonical_index(self) -> list[dict]:
        rows = self.connection.execute("SELECT record_json FROM observations ORDER BY session_id,appearance_index,observation_id").fetchall()
        observations = [json.loads(row[0]) for row in rows]
        groups: dict[tuple[str, str], list[dict]] = {}
        for observation in observations:
            key = observation_key(observation)
            if key in groups and has_merge_conflict(groups[key], observation, key[0]):
                raise StoreError("CANONICAL_CONFLICT")
            groups.setdefault(key, []).append(observation)
        try:
            posts = canonicalize(observations)
        except ValidationError as error:
            raise StoreError(error.code) from None
        previous = {row[0]: row[1] for row in self.connection.execute("SELECT local_post_id,record_json FROM canonical_posts")}
        current = {post["local_post_id"]: canonical_bytes(post) for post in posts}
        self.connection.execute("DELETE FROM post_observations")
        for local_id, record in current.items():
            if local_id in previous:
                if bytes(previous[local_id]) != record:
                    self.connection.execute("DELETE FROM analyses WHERE local_post_id=?", (local_id,))
                self.connection.execute("UPDATE canonical_posts SET record_json=? WHERE local_post_id=?", (record, local_id))
            else:
                self.connection.execute("INSERT INTO canonical_posts VALUES (?,?)", (local_id, record))
        stale = sorted(set(previous) - set(current))
        if stale:
            self.connection.execute("DELETE FROM canonical_posts WHERE local_post_id IN (%s)" % ",".join("?" for _ in stale), stale)
        self.connection.executemany("INSERT INTO post_observations VALUES (?,?)", [
            (post["local_post_id"], observation_id)
            for post in posts for observation_id in post["observation_ids"]
        ])
        return posts

    def import_envelope(self, envelope: dict, *, inject_failure: bool = False) -> ImportResult:
        session = envelope["session"]
        session_id = session["session_id"]
        existing = self.connection.execute("SELECT content_digest FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if existing:
            if existing[0] != envelope["content_digest"]:
                raise StoreError("IDEMPOTENCE_DIGEST_CONFLICT")
            count = self.connection.execute("SELECT COUNT(DISTINCT local_post_id) FROM post_observations JOIN observations USING(observation_id) WHERE session_id=?", (session_id,)).fetchone()[0]
            return ImportResult(session_id, count, True)
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?)", (
                session_id, session["source"], session["origin"], session["started_at"], session["ended_at"], envelope["content_digest"], canonical_bytes(envelope),
            ))
            for observation in envelope["observations"]:
                self.connection.execute("INSERT INTO observations VALUES (?,?,?,?)", (
                    observation["observation_id"], session_id, observation["appearance_index"], canonical_bytes(observation),
                ))
            if inject_failure:
                raise sqlite3.OperationalError("synthetic injected failure")
            self._rebuild_canonical_index()
            canonical_count = self.connection.execute("SELECT COUNT(DISTINCT local_post_id) FROM post_observations JOIN observations USING(observation_id) WHERE session_id=?", (session_id,)).fetchone()[0]
            self.connection.commit()
        except StoreError:
            self.connection.rollback()
            raise
        except sqlite3.Error:
            self.connection.rollback()
            raise StoreError("IMPORT_ROLLED_BACK") from None
        return ImportResult(session_id, canonical_count, False)

    def add_analysis(self, record: dict) -> None:
        try:
            self.connection.execute("INSERT OR REPLACE INTO analyses VALUES (?,?,?)", (record["analysis_id"], record["local_post_id"], canonical_bytes(record)))
            self.connection.commit()
        except sqlite3.IntegrityError:
            self.connection.rollback()
            raise StoreError("ORPHAN_ANALYSIS_REJECTED") from None

    def add_review_decision(self, decision: dict) -> None:
        required = {"decision_id", "reviewer_local_id", "decided_at", "reason", "decision_type", "prior_post_ids", "observation_ids"}
        if set(decision) != required or not decision["reason"]:
            raise StoreError("INVALID_REVIEW_DECISION")
        self.connection.execute("INSERT INTO review_decisions VALUES (?,?,?,?,?,?,?)", (
            decision["decision_id"], decision["reviewer_local_id"], decision["decided_at"], decision["reason"], decision["decision_type"], canonical_bytes(sorted(decision["prior_post_ids"])), canonical_bytes(sorted(decision["observation_ids"])),
        ))
        self.connection.commit()

    def list_posts(self, session_id: str) -> list[dict]:
        rows = self.connection.execute("SELECT DISTINCT cp.record_json FROM canonical_posts cp JOIN post_observations po USING(local_post_id) JOIN observations o USING(observation_id) WHERE o.session_id=? ORDER BY cp.local_post_id", (session_id,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def register_export(self, session_id: str, path: Path, sensitivity: str, created_on: str) -> None:
        self.connection.execute("INSERT INTO exports VALUES (?,?,?,?,?)", (str(path.resolve()), session_id, sensitivity, _sha256(path), created_on))
        self.connection.commit()

    def purge_preview(self, session_id: str) -> dict:
        observations = self.connection.execute("SELECT COUNT(*) FROM observations WHERE session_id=?", (session_id,)).fetchone()[0]
        posts = self.connection.execute("SELECT COUNT(DISTINCT local_post_id) FROM post_observations JOIN observations USING(observation_id) WHERE session_id=?", (session_id,)).fetchone()[0]
        exports = [row[0] for row in self.connection.execute("SELECT export_path FROM exports WHERE session_id=? ORDER BY export_path", (session_id,))]
        return {"session_id": session_id, "observation_count": observations, "post_count": posts, "known_exports": exports, "backup_caveat": "Older backups, snapshots, and separately exported files are not altered."}

    def purge_session(self, session_id: str, *, vacuum: bool = True, free_space_override: int | None = None, inject_failure: bool = False, temp_paths: list[Path] | None = None, temp_root: Path | None = None) -> dict:
        child_ids = [row[0] for row in self.connection.execute("SELECT observation_id FROM observations WHERE session_id=?", (session_id,))]
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.connection.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
            self._rebuild_canonical_index()
            if inject_failure:
                raise sqlite3.OperationalError("synthetic injected failure")
            self.connection.commit()
        except (sqlite3.Error, StoreError):
            self.connection.rollback()
            raise StoreError("PURGE_ROLLED_BACK") from None
        checkpoint = self.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        checkpoint_ok = checkpoint[0] == 0
        free = free_space_override if free_space_override is not None else shutil.disk_usage(self.path.parent).free
        vacuum_status = "VACUUM_NOT_CONFIGURED"
        if vacuum:
            if free < self.path.stat().st_size * 2 + 1_048_576:
                vacuum_status = "VACUUM_NOT_RUN"
            else:
                self.connection.execute("VACUUM")
                vacuum_status = "VACUUM_COMPLETED"
        temp_ok = True
        for path in temp_paths or []:
            try:
                if temp_root is None or os.path.commonpath([str(path.resolve()), str(temp_root.resolve())]) != str(temp_root.resolve()) or path.is_symlink():
                    temp_ok = False
                    continue
                path.unlink(missing_ok=True)
            except OSError:
                temp_ok = False
        remaining = self.connection.execute("SELECT COUNT(*) FROM sessions WHERE session_id=?", (session_id,)).fetchone()[0]
        orphan_obs = 0 if not child_ids else self.connection.execute("SELECT COUNT(*) FROM observations WHERE observation_id IN (%s)" % ",".join("?" for _ in child_ids), child_ids).fetchone()[0]
        status = "PURGE_COMPLETED" if checkpoint_ok and temp_ok and remaining == 0 and orphan_obs == 0 and vacuum_status != "VACUUM_NOT_RUN" else "PURGE_INCOMPLETE"
        return {"status": status, "checkpoint": "TRUNCATED" if checkpoint_ok else "BUSY", "vacuum": vacuum_status, "remaining_sessions": remaining, "remaining_observations": orphan_obs, "temp_cleanup": "COMPLETED" if temp_ok else "FAILED", "message": "local purge completed under configured SQLite controls" if status == "PURGE_COMPLETED" else "local purge incomplete; close readers, verify free space, and retry explicitly"}

    def backup(self, destination: Path, created_on: str) -> dict:
        destination = destination.resolve()
        if destination.exists():
            raise StoreError("BACKUP_EXISTS")
        if not _is_local_path(destination):
            raise StoreError("NONLOCAL_BACKUP_REJECTED")
        self.connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
        target = sqlite3.connect(destination)
        try:
            self.connection.backup(target)
            integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
            app_id = target.execute("PRAGMA application_id").fetchone()[0]
            version = target.execute("PRAGMA user_version").fetchone()[0]
        finally:
            target.close()
        if integrity != "ok" or app_id != APPLICATION_ID or version != SCHEMA_VERSION:
            destination.unlink(missing_ok=True)
            raise StoreError("BACKUP_VALIDATION_FAILED")
        value = _sha256(destination)
        self.connection.execute("INSERT INTO backups VALUES (?,?,?)", (str(destination), value, created_on))
        self.connection.commit()
        return {"path": str(destination), "sha256": value, "integrity": "ok", "application_id": app_id, "schema_version": version}

    @staticmethod
    def restore(backup: Path, destination: Path) -> dict:
        try:
            backup_metadata = backup.lstat()
        except OSError:
            raise StoreError("RESTORE_PATH_REJECTED") from None
        if backup.is_symlink() or not backup.is_file() or backup_metadata.st_size > 5_242_880_000:
            raise StoreError("RESTORE_PATH_REJECTED")
        backup, destination = backup.resolve(), destination.resolve()
        if destination.exists():
            raise StoreError("RESTORE_DESTINATION_EXISTS")
        if not _is_local_path(destination):
            raise StoreError("RESTORE_PATH_REJECTED")
        source = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
        try:
            integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
            app_id = source.execute("PRAGMA application_id").fetchone()[0]
            version = source.execute("PRAGMA user_version").fetchone()[0]
            if integrity != "ok" or app_id != APPLICATION_ID or version != SCHEMA_VERSION:
                raise StoreError("RESTORE_VALIDATION_FAILED")
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
        return {"status": "RESTORED_ISOLATED_COPY", "sha256": _sha256(destination)}
