"""Content-free diagnostics, caveats, and exception types for G2.1."""

from __future__ import annotations

# Platform SQLite Application ID: ASCII 'XFI1' (0x58464931)
APPLICATION_ID: int = 0x58464931

# Documented retention and purge caveats
PURGE_CAVEATS: str = (
    "Local purge completed under configured SQLite controls. "
    "secure_delete=ON overwrites deleted database payload in ordinary pages, but does not prove "
    "erasure from WAL files, free-list history created under a prior setting, OS snapshots, "
    "SSD wear leveling / remapping, backup files, synchronized copies, or exports. "
    "VACUUM rebuilds the database pages but cannot promise cryptographic erasure from underlying storage. "
    "Purging the live database does not alter older backups or separately exported files."
)

BACKUP_CAVEATS: str = (
    "Backups are created through SQLite online backup API after checkpointing. "
    "Never copy a live .sqlite, -wal, or -shm file directly. "
    "Purging the live database does not alter older backups. "
    "The product maintains a local backup inventory only for backups it created and lists those paths during purge. "
    "It cannot discover filesystem snapshots, Time Machine snapshots, manually copied files, cloud sync versions, "
    "or previously shared exports."
)

# Standardized content-free diagnostic category codes
REJECTED_SCHEMA: str = "REJECTED_SCHEMA"
REJECTED_VERSION: str = "REJECTED_VERSION"
REJECTED_DEPTH: str = "REJECTED_DEPTH"
REJECTED_FIELD_LIMIT: str = "REJECTED_FIELD_LIMIT"
REJECTED_COUNT_LIMIT: str = "REJECTED_COUNT_LIMIT"
REJECTED_PACKET_LIMIT: str = "REJECTED_PACKET_LIMIT"
REJECTED_DIGEST_MISMATCH: str = "REJECTED_DIGEST_MISMATCH"
REJECTED_STOP_VIOLATION: str = "REJECTED_STOP_VIOLATION"
REJECTED_CREDENTIAL_FIELD: str = "REJECTED_CREDENTIAL_FIELD"
REJECTED_CREDENTIAL_VALUE: str = "REJECTED_CREDENTIAL_VALUE"
REJECTED_PRIVATE_SURFACE: str = "REJECTED_PRIVATE_SURFACE"
SESSION_ID_COLLISION: str = "SESSION_ID_COLLISION"
PRAGMA_FAILURE: str = "PRAGMA_FAILURE"
UNSUPPORTED_APPLICATION_ID: str = "UNSUPPORTED_APPLICATION_ID"
MIGRATION_ERROR: str = "MIGRATION_ERROR"
PURGE_INCOMPLETE: str = "PURGE_INCOMPLETE"
BACKUP_ERROR: str = "BACKUP_ERROR"


class CoreStoreError(Exception):
    """Base exception for core store. Guarantees content-free diagnostic messages."""

    def __init__(self, category: str, detail: str = "") -> None:
        super().__init__(category)
        self.category: str = category
        self.detail: str = detail

    def __str__(self) -> str:
        if self.detail:
            return f"{self.category}: {self.detail}"
        return self.category

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(category={self.category!r})"


class ValidationError(CoreStoreError):
    """Raised when an import payload fails schema, resource limit, or structural constraints."""
    pass


class SecurityError(CoreStoreError):
    """Raised when an import payload contains credentials, tokens, or forbidden private surfaces."""
    pass


class StoreError(CoreStoreError):
    """Raised when a database, transaction, pragma, or persistence operation fails."""
    pass


class MigrationError(CoreStoreError):
    """Raised when migration application or checksum verification fails."""
    pass
