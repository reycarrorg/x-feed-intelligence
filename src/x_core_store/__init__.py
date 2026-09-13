"""X Feed Intelligence - Core Validator and Canonical Store (Gate 2 work package G2.1)."""

from __future__ import annotations

from x_core_store.canonical import (
    canonical_json,
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
    CoreStoreError,
    MigrationError,
    SecurityError,
    StoreError,
    ValidationError,
)
from x_core_store.store import (
    BackupRecord,
    CanonicalStore,
    ExportRecord,
    PurgePreview,
    PurgeResult,
    ReviewDecision,
)
from x_core_store.validator import (
    EnvelopeValidator,
    sensitive_category,
)

__all__ = [
    "APPLICATION_ID",
    "BACKUP_CAVEATS",
    "PURGE_CAVEATS",
    "BackupRecord",
    "CanonicalStore",
    "CoreStoreError",
    "EnvelopeValidator",
    "ExportRecord",
    "MigrationError",
    "PurgePreview",
    "PurgeResult",
    "ReviewDecision",
    "SecurityError",
    "StoreError",
    "ValidationError",
    "canonical_json",
    "canonical_permalink",
    "canonicalize",
    "compact_bytes",
    "digest_without_field",
    "has_merge_conflict",
    "levenshtein_distance",
    "media_key",
    "normalized_text",
    "observation_key",
    "primary_author",
    "sensitive_category",
    "sha256_digest",
    "temporal_review_candidate",
]
