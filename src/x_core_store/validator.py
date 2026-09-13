"""Schema and semantic validator with content-free diagnostics and privacy controls."""

from __future__ import annotations

import copy
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from x_core_store.canonical import compact_bytes, digest_without_field
from x_core_store.exceptions import (
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
    SecurityError,
    ValidationError,
)

SENSITIVE_KEYS = re.compile(
    r"(?i)(authorization|auth[_-]?token|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"private[_-]?key|bearer|cookie|csrf|password|session[_-]?(?:token|storage)|"
    r"local[_-]?storage|browser[_-]?profile|direct[_-]?messages?|notifications?|payment|har)"
)
SECRET_VALUES = re.compile(
    r"(?i)(?:bearer\s+[a-z0-9._-]{12,}|-----BEGIN(?: [A-Z]+)* PRIVATE KEY-----)"
)

HARD_STOP_CODES = {
    "LOGIN_SURFACE",
    "SIGN_OUT_STATE",
    "ACCOUNT_LOCK",
    "CAPTCHA_OR_TURNSTILE",
    "VERIFICATION_CHALLENGE",
    "UNUSUAL_ACTIVITY",
    "CONSENT_SURFACE",
    "RATE_LIMIT",
    "WRONG_ORIGIN",
    "IFRAME_BOUNDARY",
    "PERMISSION_DRIFT",
    "PARSER_VERSION_MISMATCH",
    "UNKNOWN_TOPOLOGY",
    "AMBIGUITY_LIMIT",
    "QUEUE_LIMIT",
    "DURATION_LIMIT",
    "PACKET_LIMIT",
    "DISK_OR_MEMORY_LIMIT",
    "RETENTION_FAILURE",
    "SCHEMA_MISMATCH",
    "EXCLUDED_PERMISSION_REQUEST",
    "ACCOUNT_ACTION_REQUEST",
    "INJECTION_CONTENT",
}

DEFAULT_SCHEMAS_DIR = Path(__file__).resolve().parent.parent.parent / "schemas" / "v1"
RFC3339_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RFC3339_DATETIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def parse_rfc3339(value: str) -> datetime:
    """Parse a timezone-aware RFC 3339 timestamp or raise a content-free error."""
    if RFC3339_DATETIME.fullmatch(value) is None:
        raise ValueError("invalid RFC 3339 timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)


def sensitive_category(value) -> str | None:
    """Inspect data structure for credential names, private surfaces, and token patterns."""
    def visit(node) -> str | None:
        if isinstance(node, dict):
            for key, child in node.items():
                if SENSITIVE_KEYS.search(key):
                    if re.search(r"(?i)(direct|notification|payment)", key):
                        return REJECTED_PRIVATE_SURFACE
                    return REJECTED_CREDENTIAL_FIELD
                result = visit(child)
                if result:
                    return result
        elif isinstance(node, list):
            for child in node:
                result = visit(child)
                if result:
                    return result
        elif isinstance(node, str) and SECRET_VALUES.search(node):
            return REJECTED_CREDENTIAL_VALUE
        return None

    return visit(value)


def nested_depth(value) -> int:
    """Compute nesting depth of JSON structures."""
    if isinstance(value, dict):
        return 1 + max((nested_depth(child) for child in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((nested_depth(child) for child in value), default=0)
    return 0


def json_type_matches(value, expected: str) -> bool:
    """Verify JSON schema data type match."""
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


class EnvelopeValidator:
    """Validates import envelopes against JSON schemas and semantic integrity rules."""

    def __init__(self, schemas_dir: Path | None = None) -> None:
        self.schemas_dir = Path(schemas_dir) if schemas_dir else DEFAULT_SCHEMAS_DIR
        self._schema_cache: dict[str, dict] = {}

    def _load_schema(self, filename: str) -> dict:
        if filename not in self._schema_cache:
            path = self.schemas_dir / filename
            if not path.is_file():
                raise ValidationError(REJECTED_SCHEMA, f"Schema file not found: {filename}")
            self._schema_cache[filename] = json.loads(path.read_text(encoding="utf-8"))
        return self._schema_cache[filename]

    def _resolve_ref(self, current_file: str, ref: str) -> tuple[dict, str]:
        target_name, _, fragment = ref.partition("#")
        file_to_load = target_name if target_name else current_file
        target = self._load_schema(file_to_load)
        if fragment:
            if not fragment.startswith("/"):
                raise ValidationError(REJECTED_SCHEMA, f"Unsupported schema fragment: {ref}")
            for part in fragment[1:].split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                if part not in target:
                    raise ValidationError(REJECTED_SCHEMA, f"Reference fragment not found: {part}")
                target = target[part]
        return target, file_to_load

    def _validate_instance(self, value, schema: dict, current_file: str, location: str = "$") -> None:
        if "$ref" in schema:
            target, target_file = self._resolve_ref(current_file, schema["$ref"])
            self._validate_instance(value, target, target_file, location)
            return

        if "oneOf" in schema:
            matches = 0
            for branch in schema["oneOf"]:
                try:
                    self._validate_instance(value, branch, current_file, location)
                except ValidationError:
                    continue
                matches += 1
            if matches != 1:
                raise ValidationError(REJECTED_SCHEMA, f"{location}: expected exactly one matching variant, got {matches}")

        if "const" in schema:
            if value != schema["const"]:
                raise ValidationError(REJECTED_SCHEMA, f"{location}: const mismatch")

        if "enum" in schema:
            if value not in schema["enum"]:
                raise ValidationError(REJECTED_SCHEMA, f"{location}: value outside allowed enumeration")

        expected = schema.get("type")
        if expected is not None:
            expected_types = [expected] if isinstance(expected, str) else expected
            if not any(json_type_matches(value, item) for item in expected_types):
                raise ValidationError(REJECTED_SCHEMA, f"{location}: type mismatch")

        if isinstance(value, dict):
            required = schema.get("required", [])
            for req in required:
                if req not in value:
                    raise ValidationError(REJECTED_SCHEMA, f"{location}: missing required property '{req}'")
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                additional = set(value) - set(properties)
                if additional:
                    raise ValidationError(REJECTED_SCHEMA, f"{location}: disallowed additional property")
            for key, child in value.items():
                if key in properties:
                    self._validate_instance(child, properties[key], current_file, f"{location}/{key}")

        if isinstance(value, list):
            if len(value) < schema.get("minItems", 0):
                raise ValidationError(REJECTED_SCHEMA, f"{location}: too few items")
            if len(value) > schema.get("maxItems", len(value)):
                raise ValidationError(REJECTED_SCHEMA, f"{location}: too many items")
            if schema.get("uniqueItems"):
                unique_set = {compact_bytes(item) for item in value}
                if len(unique_set) != len(value):
                    raise ValidationError(REJECTED_SCHEMA, f"{location}: duplicate array items")
            prefix = schema.get("prefixItems", [])
            for index, child_schema in enumerate(prefix):
                if index < len(value):
                    self._validate_instance(value[index], child_schema, current_file, f"{location}/{index}")
            if "items" in schema:
                for index, child in enumerate(value):
                    self._validate_instance(child, schema["items"], current_file, f"{location}/{index}")

        if isinstance(value, str):
            if len(value) < schema.get("minLength", 0):
                raise ValidationError(REJECTED_SCHEMA, f"{location}: string shorter than minimum length")
            if len(value) > schema.get("maxLength", len(value)):
                raise ValidationError(REJECTED_SCHEMA, f"{location}: string exceeds maximum length")
            if "pattern" in schema:
                if re.search(schema["pattern"], value) is None:
                    raise ValidationError(REJECTED_SCHEMA, f"{location}: string fails required pattern")
            if schema.get("format") == "date":
                try:
                    if RFC3339_DATE.fullmatch(value) is None:
                        raise ValueError("invalid RFC 3339 date")
                    date.fromisoformat(value)
                except ValueError as error:
                    raise ValidationError(REJECTED_SCHEMA, f"{location}: invalid ISO date format") from error
            if schema.get("format") == "date-time":
                try:
                    parse_rfc3339(value)
                except ValueError as error:
                    raise ValidationError(REJECTED_SCHEMA, f"{location}: invalid RFC 3339 date-time format") from error

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value < schema.get("minimum", value):
                raise ValidationError(REJECTED_SCHEMA, f"{location}: number below minimum")
            if value > schema.get("maximum", value):
                raise ValidationError(REJECTED_SCHEMA, f"{location}: number above maximum")

    def _check_depth_and_fields(self, value, current_depth: int = 0) -> None:
        if current_depth > 64:
            raise ValidationError(REJECTED_DEPTH, "Input nesting exceeds maximum depth limit of 64")
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(k, str) and len(k) > 10000:
                    raise ValidationError(REJECTED_FIELD_LIMIT, "Object key exceeds maximum field length of 10000")
                self._check_depth_and_fields(v, current_depth + 1)
        elif isinstance(value, list):
            for item in value:
                self._check_depth_and_fields(item, current_depth + 1)
        elif isinstance(value, str):
            if len(value) > 10000:
                raise ValidationError(REJECTED_FIELD_LIMIT, "String field exceeds maximum length of 10000")

    def validate_packet_bytes(self, raw_bytes: bytes) -> None:
        """Validate raw byte size against maximum 5 MiB packet limit."""
        if len(raw_bytes) > 5242880:
            raise ValidationError(REJECTED_PACKET_LIMIT, "Packet exceeds maximum size of 5242880 bytes")

    def validate_envelope(self, envelope: dict, raw_bytes: bytes | None = None) -> None:
        """Validate complete envelope against privacy, resource, schema, and semantic invariants."""
        if not isinstance(envelope, dict):
            raise ValidationError(REJECTED_SCHEMA, "Envelope must be a JSON object")

        if raw_bytes is not None:
            self.validate_packet_bytes(raw_bytes)
        else:
            compact = compact_bytes(envelope)
            self.validate_packet_bytes(compact)

        # 1. Depth and field limits
        self._check_depth_and_fields(envelope)

        # 2. Sensitive data inspection (rejects before persisting or detailed parsing)
        cat = sensitive_category(envelope)
        if cat:
            raise SecurityError(cat, "Input rejected by sensitive data scanner")

        # 3. Schema version preflight
        if "schema_version" not in envelope:
            raise ValidationError(REJECTED_SCHEMA, "Missing schema_version property")
        if envelope["schema_version"] != "1.0.0":
            raise ValidationError(REJECTED_VERSION, "Unsupported schema version")

        # 4. Observation count limit
        observations = envelope.get("observations")
        if observations is not None:
            if not isinstance(observations, list):
                raise ValidationError(REJECTED_SCHEMA, "observations must be an array")
            if len(observations) > 250:
                raise ValidationError(REJECTED_COUNT_LIMIT, f"Observation count exceeds limit of 250 (got {len(observations)})")

        # 5. Schema validation against envelope.schema.json
        envelope_schema = self._load_schema("envelope.schema.json")
        self._validate_instance(envelope, envelope_schema, "envelope.schema.json")

        # 6. Content digest validation
        expected_digest = digest_without_field(envelope, "content_digest")
        if envelope.get("content_digest") != expected_digest:
            raise ValidationError(REJECTED_DIGEST_MISMATCH, "Envelope content digest does not match recomputed SHA-256")

        # 7. Session semantic invariants
        session = envelope["session"]
        source = session["source"]
        origin = session["origin"]
        if source == "synthetic_dom" and origin != "https://fixture.example.invalid":
            raise ValidationError(REJECTED_SCHEMA, "synthetic_dom session requires origin 'https://fixture.example.invalid'")
        if source in {"synthetic_recording", "user_supplied_recording"} and origin is not None:
            raise ValidationError(REJECTED_SCHEMA, "recording session requires null origin")
        if parse_rfc3339(session["ended_at"]) < parse_rfc3339(session["started_at"]):
            raise ValidationError(REJECTED_SCHEMA, "Session end precedes session start")

        # 8. Observation session consistency and uniqueness
        session_id = session["session_id"]
        seen_obs_ids = set()
        for obs in envelope["observations"]:
            if obs["session_id"] != session_id:
                raise ValidationError(REJECTED_SCHEMA, "Observation session_id does not match session")
            if obs["observation_id"] in seen_obs_ids:
                raise ValidationError(REJECTED_SCHEMA, "Duplicate observation_id in envelope")
            seen_obs_ids.add(obs["observation_id"])

        # 9. Stop event constraint: no observation after a stop event
        stop_events = [
            event for event in envelope.get("collection_events", [])
            if event["event_code"].startswith("STOPPED_") or event["event_code"] in HARD_STOP_CODES
        ]
        if stop_events:
            first_stop = min(parse_rfc3339(event["at"]) for event in stop_events)
            for obs in envelope["observations"]:
                for prov in obs.get("provenance", []):
                    observed_at = prov.get("observed_at")
                    if observed_at and parse_rfc3339(observed_at) > first_stop:
                        raise ValidationError(
                            REJECTED_STOP_VIOLATION,
                            "Observation observed_at occurs after collection stop event"
                        )

    def validate_canonical_post(self, canonical_post: dict) -> None:
        """Validate a derived canonical post against the same closed Gate 1 contract."""
        if not isinstance(canonical_post, dict):
            raise ValidationError(REJECTED_SCHEMA, "Canonical post must be a JSON object")
        self._check_depth_and_fields(canonical_post)
        category = sensitive_category(canonical_post)
        if category:
            raise SecurityError(category, "Derived post rejected by sensitive data scanner")
        schema = self._load_schema("canonical-post.schema.json")
        self._validate_instance(canonical_post, schema, "canonical-post.schema.json")
