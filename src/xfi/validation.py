"""Strict, dependency-free schema, semantic, resource, digest, and privacy validation."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from .canonical import canonical_bytes, digest
from .errors import ValidationError

MAX_PACKET_BYTES = 5_242_880
MAX_DEPTH = 64
SENSITIVE_KEYS = re.compile(r"(?i)(authorization|auth[_-]?token|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|bearer|cookie|csrf|password|session[_-]?(?:token|storage)|local[_-]?storage|browser[_-]?profile|direct[_-]?messages?|notifications?|payment|har)")
SECRET_VALUES = re.compile(r"(?i)(?:bearer\s+[a-z0-9._-]{12,}|-----BEGIN(?: [A-Z]+)* PRIVATE KEY-----)")


def nested_depth(value: object) -> int:
    if isinstance(value, dict):
        return 1 + max((nested_depth(item) for item in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((nested_depth(item) for item in value), default=0)
    return 0


def sensitive_category(value: object) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if SENSITIVE_KEYS.search(key):
                return "REJECTED_PRIVATE_SURFACE" if re.search(r"(?i)(direct|notification|payment)", key) else "REJECTED_CREDENTIAL_FIELD"
            result = sensitive_category(child)
            if result:
                return result
    elif isinstance(value, list):
        for child in value:
            result = sensitive_category(child)
            if result:
                return result
    elif isinstance(value, str) and SECRET_VALUES.search(value):
        return "REJECTED_CREDENTIAL_VALUE"
    return None


class SchemaValidator:
    def __init__(self, schema_root: Path):
        self.schema_root = schema_root

    def _load_ref(self, current: Path, reference: str) -> tuple[dict, Path]:
        name, _, fragment = reference.partition("#")
        path = current if not name else current.parent / name
        target = json.loads(path.read_text(encoding="utf-8"))
        if fragment:
            if not fragment.startswith("/"):
                raise ValidationError()
            for part in fragment[1:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
        return target, path

    @staticmethod
    def _type(value: object, expected: str) -> bool:
        return {"null": value is None, "object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str), "boolean": isinstance(value, bool), "integer": isinstance(value, int) and not isinstance(value, bool), "number": isinstance(value, (int, float)) and not isinstance(value, bool)}[expected]

    def validate(self, value: object, schema: dict, path: Path) -> None:
        try:
            self._validate(value, schema, path)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise ValidationError() from None

    def _validate(self, value: object, schema: dict, path: Path) -> None:
        if "$ref" in schema:
            target, target_path = self._load_ref(path, schema["$ref"])
            self._validate(value, target, target_path)
            return
        if "oneOf" in schema:
            matches = 0
            for branch in schema["oneOf"]:
                try:
                    self._validate(value, branch, path)
                    matches += 1
                except ValidationError:
                    pass
            if matches != 1:
                raise ValidationError()
        if "const" in schema and value != schema["const"]:
            raise ValidationError()
        if "enum" in schema and value not in schema["enum"]:
            raise ValidationError()
        expected = schema.get("type")
        if expected is not None and not any(self._type(value, item) for item in ([expected] if isinstance(expected, str) else expected)):
            raise ValidationError()
        if isinstance(value, dict):
            if not set(schema.get("required", [])) <= set(value):
                raise ValidationError()
            properties = schema.get("properties", {})
            if schema.get("additionalProperties") is False and not set(value) <= set(properties):
                raise ValidationError()
            for key, child in value.items():
                if key in properties:
                    self._validate(child, properties[key], path)
        elif isinstance(value, list):
            if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", len(value)):
                raise ValidationError("REJECTED_COUNT_LIMIT")
            if schema.get("uniqueItems") and len({canonical_bytes(item) for item in value}) != len(value):
                raise ValidationError()
            for index, child_schema in enumerate(schema.get("prefixItems", [])):
                if index < len(value):
                    self._validate(value[index], child_schema, path)
            if "items" in schema:
                for child in value:
                    self._validate(child, schema["items"], path)
        elif isinstance(value, str):
            if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", len(value)):
                raise ValidationError("REJECTED_FIELD_LIMIT")
            if "pattern" in schema and not re.search(schema["pattern"], value):
                raise ValidationError()
            try:
                if schema.get("format") == "date": date.fromisoformat(value)
                if schema.get("format") == "date-time": datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                raise ValidationError() from None
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if value < schema.get("minimum", value) or value > schema.get("maximum", value):
                raise ValidationError()

    def validate_file(self, value: object, name: str) -> None:
        path = self.schema_root / name
        self.validate(value, json.loads(path.read_text(encoding="utf-8")), path)


def load_and_validate_envelope(raw: bytes, schema_root: Path) -> dict:
    if len(raw) > MAX_PACKET_BYTES:
        raise ValidationError("REJECTED_PACKET_LIMIT")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValidationError("REJECTED_SCHEMA") from None
    if nested_depth(value) > MAX_DEPTH:
        raise ValidationError("REJECTED_DEPTH")
    privacy = sensitive_category(value)
    if privacy:
        raise ValidationError(privacy)
    if not isinstance(value, dict) or "schema_version" not in value:
        raise ValidationError("REJECTED_SCHEMA")
    if value["schema_version"] != "1.0.0":
        raise ValidationError("REJECTED_VERSION")
    SchemaValidator(schema_root).validate_file(value, "envelope.schema.json")
    if value["content_digest"] != digest(value):
        raise ValidationError("REJECTED_DIGEST")
    session = value["session"]
    ids: set[str] = set()
    provenance: set[str] = set()
    for observation in value["observations"]:
        if observation["session_id"] != session["session_id"]:
            raise ValidationError("REJECTED_REFERENCE")
        if observation["observation_id"] in ids:
            raise ValidationError("REJECTED_DUPLICATE_ID")
        ids.add(observation["observation_id"])
        for item in observation["provenance"]:
            if item["provenance_id"] in provenance:
                raise ValidationError("REJECTED_DUPLICATE_ID")
            provenance.add(item["provenance_id"])
        for relationship in observation["relationships"]:
            if not set(relationship.get("provenance_ids", [])) <= provenance | {p["provenance_id"] for p in observation["provenance"]}:
                raise ValidationError("REJECTED_REFERENCE")
    return value
