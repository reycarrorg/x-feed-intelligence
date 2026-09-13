"""Canonical JSON serialization, SHA-256 digests, and text/URL normalizers."""

from __future__ import annotations

import copy
import hashlib
import json
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from x_core_store.exceptions import ValidationError


def compact_bytes(value) -> bytes:
    """Serialize value to canonical compact UTF-8 JSON bytes (sorted keys, no extra whitespace)."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_json(value) -> str:
    """Return the canonical JSON string representation of value."""
    return compact_bytes(value).decode("utf-8")


def sha256_digest(data: bytes | str) -> str:
    """Compute sha256 hex digest prefixed with 'sha256:'."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def digest_without_field(value: dict, field: str = "content_digest") -> str:
    """Compute sha256 digest over canonical JSON bytes after omitting specified field."""
    clone = copy.deepcopy(value)
    clone.pop(field, None)
    return sha256_digest(compact_bytes(clone))


def normalized_text(value: str | None) -> str | None:
    """NFC normalize text, convert CRLF to LF, and collapse Unicode whitespace runs."""
    if value is None:
        return None
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n"))
    return " ".join(value.split())


def canonical_permalink(raw: str | None) -> str | None:
    """Normalize and validate HTTPS permalink, removing query and fragment."""
    if raw is None:
        return None
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https":
        raise ValidationError("REJECTED_SCHEMA", "Permalink scheme must be HTTPS")
    if host not in {"x.com", "example.invalid"}:
        raise ValidationError("REJECTED_SCHEMA", "Permalink host is not allowed")
    if parsed.username is not None or parsed.password is not None:
        raise ValidationError("REJECTED_SCHEMA", "Permalink contains userinfo")
    if parsed.port not in {None, 443}:
        raise ValidationError("REJECTED_SCHEMA", "Permalink uses an unexpected port")
    netloc = host
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(("https", netloc, path, "", ""))


def levenshtein_distance(left: str, right: str) -> int:
    """Compute exact Levenshtein distance between two strings."""
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, 1):
        current = [left_index]
        for right_index, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]
