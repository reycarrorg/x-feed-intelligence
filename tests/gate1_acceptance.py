#!/usr/bin/env python3
"""Deterministic, standard-library Gate 1 contract and synthetic-evidence oracle."""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import random
import re
import sys
import unicodedata
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures" / "synthetic" / "v1"
SCHEMAS = ROOT / "schemas" / "v1"
CONTRACTS = ROOT / "contracts" / "v1"

SENSITIVE_KEYS = re.compile(
    r"(?i)(authorization|auth[_-]?token|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"private[_-]?key|bearer|cookie|csrf|password|session[_-]?(?:token|storage)|"
    r"local[_-]?storage|browser[_-]?profile|direct[_-]?messages?|notifications?|payment|har)"
)
SECRET_VALUES = re.compile(
    r"(?i)(?:bearer\s+[a-z0-9._-]{12,}|-----BEGIN(?: [A-Z]+)* PRIVATE KEY-----)"
)
NEGATIONS = {"no", "not", "never", "without"}
FORMULA_PREFIXES = ("=", "+", "-", "@")


class CheckFailure(AssertionError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def compact_bytes(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def pretty_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def digest_without_field(value: dict, field: str = "content_digest") -> str:
    clone = copy.deepcopy(value)
    clone.pop(field, None)
    return "sha256:" + hashlib.sha256(compact_bytes(clone)).hexdigest()


def resolve_schema_ref(current_path: Path, ref: str) -> tuple[dict, Path]:
    target_name, _, fragment = ref.partition("#")
    target_path = current_path if not target_name else current_path.parent / target_name
    target = load_json(target_path)
    if fragment:
        require(fragment.startswith("/"), f"unsupported schema fragment: {ref}")
        for part in fragment[1:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            target = target[part]
    return target, target_path


def json_type_matches(value, expected: str) -> bool:
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
    raise CheckFailure(f"unsupported schema type in oracle: {expected}")


def validate_schema_instance(value, schema: dict, schema_path: Path, location: str = "$") -> None:
    if "$ref" in schema:
        target, target_path = resolve_schema_ref(schema_path, schema["$ref"])
        validate_schema_instance(value, target, target_path, location)
        return

    if "oneOf" in schema:
        matches = 0
        for branch in schema["oneOf"]:
            try:
                validate_schema_instance(value, branch, schema_path, location)
            except CheckFailure:
                continue
            matches += 1
        require(matches == 1, f"{location}: expected exactly one oneOf branch, got {matches}")

    if "const" in schema:
        require(value == schema["const"], f"{location}: const mismatch")
    if "enum" in schema:
        require(value in schema["enum"], f"{location}: value outside enum")

    expected = schema.get("type")
    if expected is not None:
        expected_types = [expected] if isinstance(expected, str) else expected
        require(any(json_type_matches(value, item) for item in expected_types), f"{location}: type mismatch")

    if isinstance(value, dict):
        required = schema.get("required", [])
        require(all(key in value for key in required), f"{location}: required property missing")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            require(set(value) <= set(properties), f"{location}: additional property")
        for key, child in value.items():
            if key in properties:
                validate_schema_instance(child, properties[key], schema_path, f"{location}/{key}")

    if isinstance(value, list):
        require(len(value) >= schema.get("minItems", 0), f"{location}: too few items")
        require(len(value) <= schema.get("maxItems", len(value)), f"{location}: too many items")
        if schema.get("uniqueItems"):
            require(len({compact_bytes(item) for item in value}) == len(value), f"{location}: duplicate array item")
        prefix = schema.get("prefixItems", [])
        for index, child_schema in enumerate(prefix):
            if index < len(value):
                validate_schema_instance(value[index], child_schema, schema_path, f"{location}/{index}")
        if "items" in schema:
            for index, child in enumerate(value):
                validate_schema_instance(child, schema["items"], schema_path, f"{location}/{index}")

    if isinstance(value, str):
        require(len(value) >= schema.get("minLength", 0), f"{location}: string too short")
        require(len(value) <= schema.get("maxLength", len(value)), f"{location}: string too long")
        if "pattern" in schema:
            require(re.search(schema["pattern"], value) is not None, f"{location}: pattern mismatch")
        if schema.get("format") == "date":
            try:
                date.fromisoformat(value)
            except ValueError as error:
                raise CheckFailure(f"{location}: invalid date") from error
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise CheckFailure(f"{location}: invalid date-time") from error

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        require(value >= schema.get("minimum", value), f"{location}: below minimum")
        require(value <= schema.get("maximum", value), f"{location}: above maximum")


def normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = unicodedata.normalize("NFC", value.replace("\r\n", "\n"))
    return " ".join(value.split())


def primary_author(observation: dict) -> str | None:
    relationship_kinds = {item["kind"] for item in observation["relationships"]}
    if "quotes" in relationship_kinds:
        priority = ("quoting", "presenting")
    elif "repost_of" in relationship_kinds:
        priority = ("original",)
    else:
        priority = ("presenting", "original", "quoting", "reposting", "unknown")
    authors = observation["authors"]
    for role in priority:
        for author in authors:
            if author["role"] == role:
                return (
                    author.get("platform_author_id")
                    or author.get("handle")
                    or author.get("local_author_id")
                )
    return None


def media_key(observation: dict) -> tuple:
    return tuple(
        (
            item["kind"],
            item.get("perceptual_fingerprint"),
            normalized_text(item.get("alt_text")),
            normalized_text(item.get("visible_description")),
        )
        for item in observation["media"]
    )


def canonical_permalink(raw: str | None) -> str | None:
    if raw is None:
        return None
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    require(parsed.scheme.lower() == "https", "permalink scheme must be HTTPS")
    require(host in {"x.com", "example.invalid"}, "permalink host is not allowed")
    require(parsed.username is None and parsed.password is None, "permalink contains userinfo")
    require(parsed.port in {None, 443}, "permalink uses an unexpected port")
    netloc = host
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(("https", netloc, path, "", ""))


def observation_key(observation: dict) -> tuple[str, str]:
    platform_id = observation.get("platform_post_id")
    if platform_id:
        return "platform_id", platform_id
    permalink = canonical_permalink(observation.get("canonical_permalink"))
    if permalink:
        return "canonical_permalink", permalink
    author = primary_author(observation)
    text = normalized_text(observation.get("visible_text"))
    timestamp = observation.get("displayed_timestamp")
    if author and text and timestamp:
        material = compact_bytes([author, text, media_key(observation), timestamp])
        return "exact_content_tuple", hashlib.sha256(material).hexdigest()
    return "singleton", observation["observation_id"]


def has_merge_conflict(existing: list[dict], candidate: dict) -> bool:
    all_items = [*existing, candidate]
    platform_ids = {item.get("platform_post_id") for item in all_items if item.get("platform_post_id")}
    authors = {primary_author(item) for item in all_items if primary_author(item)}
    timestamps = {item.get("displayed_timestamp") for item in all_items if item.get("displayed_timestamp")}
    promotions = {item["promotion"]["status"] for item in all_items}
    media = {media_key(item) for item in all_items if item["media"]}
    texts = [normalized_text(item.get("visible_text")) or "" for item in all_items]
    numeric_tokens = {tuple(re.findall(r"\d+(?:\.\d+)?", text)) for text in texts}
    negation_tokens = {
        tuple(sorted(set(re.findall(r"[A-Za-z]+", text.lower())) & NEGATIONS))
        for text in texts
    }
    return any(
        len(values) > 1
        for values in (
            platform_ids,
            authors,
            timestamps,
            promotions,
            media,
            numeric_tokens,
            negation_tokens,
        )
    )


def levenshtein_distance(left: str, right: str) -> int:
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


def temporal_review_candidate(left: dict, right: dict) -> bool:
    left_text = normalized_text(left.get("visible_text")) or ""
    right_text = normalized_text(right.get("visible_text")) or ""
    if min(len(left_text), len(right_text)) < 80:
        return False
    if left["session_id"] != right["session_id"] or primary_author(left) != primary_author(right):
        return False
    if media_key(left) != media_key(right) or left.get("displayed_timestamp") != right.get("displayed_timestamp"):
        return False
    left_modality = {item["modality"] for item in left["provenance"]}
    right_modality = {item["modality"] for item in right["provenance"]}
    if left_modality != right_modality:
        return False
    left_time = left["input_location"].get("video_time_ms")
    right_time = right["input_location"].get("video_time_ms")
    if left_time is None or right_time is None or abs(left_time - right_time) > 2000:
        return False
    if re.findall(r"\d+(?:\.\d+)?", left_text) != re.findall(r"\d+(?:\.\d+)?", right_text):
        return False
    left_negations = set(re.findall(r"[A-Za-z]+", left_text.lower())) & NEGATIONS
    right_negations = set(re.findall(r"[A-Za-z]+", right_text.lower())) & NEGATIONS
    if left_negations != right_negations:
        return False
    maximum = max(len(left_text), len(right_text))
    similarity = 1.0 - levenshtein_distance(left_text, right_text) / maximum
    return similarity >= 0.98


def nested_depth(value) -> int:
    if isinstance(value, dict):
        return 1 + max((nested_depth(child) for child in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((nested_depth(child) for child in value), default=0)
    return 0


def validate_resource_case(name: str) -> str:
    if name == "missing-version":
        value = {"observations": []}
        return "REJECTED_SCHEMA" if "schema_version" not in value else "ACCEPTED"
    if name == "unknown-version":
        value = {"schema_version": "99.0.0", "observations": []}
        return "REJECTED_VERSION" if value["schema_version"] != "1.0.0" else "ACCEPTED"
    if name == "wrong-type":
        value = {"schema_version": "1.0.0", "observations": "not-an-array"}
        return "REJECTED_SCHEMA" if not isinstance(value["observations"], list) else "ACCEPTED"
    if name == "depth-65":
        value: object = "leaf"
        for _ in range(65):
            value = [value]
        return "REJECTED_DEPTH" if nested_depth(value) > 64 else "ACCEPTED"
    if name == "field-10001":
        value = "x" * 10001
        return "REJECTED_FIELD_LIMIT" if len(value) > 10000 else "ACCEPTED"
    if name == "observations-251":
        value = [None] * 251
        return "REJECTED_COUNT_LIMIT" if len(value) > 250 else "ACCEPTED"
    if name == "packet-5242881":
        size = 5242881
        return "REJECTED_PACKET_LIMIT" if size > 5242880 else "ACCEPTED"
    raise CheckFailure(f"unknown resource case: {name}")


def simulate_hard_stop(state: str, code: str, lifecycle: dict) -> dict:
    require(code in lifecycle["hard_stop_codes"], f"unknown hard-stop code: {code}")
    require(state in {"ARMED", "CAPTURING", "PAUSED_HIDDEN"}, "hard stop tested from ineligible state")
    return {
        "state": "ERROR",
        "event_code": code,
        "observers": 0,
        "timers": 0,
        "dom_references": 0,
        "later_observations": 0,
        "automatic_retry": False,
    }


def canonicalize(observations: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    ordered = sorted(
        observations,
        key=lambda item: (item["session_id"], item["appearance_index"], item["observation_id"]),
    )
    for observation in ordered:
        method, value = observation_key(observation)
        key = method, value
        if key in grouped and has_merge_conflict(grouped[key], observation):
            key = "singleton", observation["observation_id"]
        grouped.setdefault(key, []).append(observation)

    output = []
    for (method, value), items in sorted(grouped.items()):
        stable = hashlib.sha256(compact_bytes([method, value])).hexdigest()[:16]
        output.append(
            {
                "local_post_id": f"local-{stable}",
                "method": method if len(items) > 1 else "singleton",
                "observation_ids": sorted(item["observation_id"] for item in items),
                "promotion": items[0]["promotion"]["status"],
                "relationships": sorted(
                    (rel["kind"], rel["source_local_post_id"])
                    for item in items
                    for rel in item["relationships"]
                ),
            }
        )
    return sorted(output, key=lambda item: item["local_post_id"])


def sensitive_category(value) -> str | None:
    def visit(node) -> str | None:
        if isinstance(node, dict):
            for key, child in node.items():
                if SENSITIVE_KEYS.search(key):
                    if re.search(r"(?i)(direct|notification|payment)", key):
                        return "REJECTED_PRIVATE_SURFACE"
                    return "REJECTED_CREDENTIAL_FIELD"
                result = visit(child)
                if result:
                    return result
        elif isinstance(node, list):
            for child in node:
                result = visit(child)
                if result:
                    return result
        elif isinstance(node, str) and SECRET_VALUES.search(node):
            return "REJECTED_CREDENTIAL_VALUE"
        return None

    return visit(value)


def strip_query_and_fragment(url: str) -> str:
    parsed = urlsplit(url)
    require(parsed.scheme == "https" and bool(parsed.hostname), "export URL must be HTTPS")
    require(parsed.username is None and parsed.password is None, "export URL contains userinfo")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def neutralize_formula(value: str) -> str:
    first_non_whitespace = next((character for character in value if not character.isspace()), None)
    return "'" + value if first_non_whitespace in FORMULA_PREFIXES else value


def has_formula_prefix(value: str) -> bool:
    first_non_whitespace = next((character for character in value if not character.isspace()), None)
    return first_non_whitespace in FORMULA_PREFIXES


def production_candidate_safe(manifest: dict, bundle_paths: list[str], boundary: dict) -> bool:
    guard = boundary["production_promotion_guard"]
    rendered = compact_bytes(manifest).decode("utf-8")
    if any(value in rendered for value in guard["forbidden_production_values"]):
        return False
    return not any(
        forbidden in path
        for path in bundle_paths
        for forbidden in guard["forbidden_bundle_paths"]
    )


def synthetic_harness_safe(manifest: dict) -> bool:
    rendered = compact_bytes(manifest).decode("utf-8")
    scripts = manifest.get("content_scripts", [])
    return (
        manifest.get("permissions") == ["storage"]
        and manifest.get("host_permissions") == ["https://fixture.example.invalid/*"]
        and "optional_host_permissions" not in manifest
        and bool(scripts)
        and all(
            item.get("matches") == ["https://fixture.example.invalid/*"]
            and item.get("world") == "ISOLATED"
            and item.get("all_frames") is False
            for item in scripts
        )
        and all(origin not in rendered for origin in ("https://x.com", "https://twitter.com", "https://api.x.com"))
    )


def sanitize(source: dict) -> dict:
    author_ids = sorted(item["local_author_id"] for item in source["authors"])
    author_map = {value: f"author-{index:03d}" for index, value in enumerate(author_ids, 1)}
    post_ids = sorted(item["local_post_id"] for item in source["posts"])
    post_map = {value: f"post-{index:03d}" for index, value in enumerate(post_ids, 1)}

    manifest = []
    for index, author in enumerate(source["authors"]):
        manifest.append(
            {
                "json_pointer": f"/authors/{index}",
                "action": "pseudonymize",
                "reason_code": "account_identifier",
                "replacement": author_map[author["local_author_id"]],
            }
        )

    posts = []
    for index, post in enumerate(sorted(source["posts"], key=lambda item: item["local_post_id"])):
        post_pseudonym = post_map[post["local_post_id"]]
        clean_summary = neutralize_formula(post["summary"])
        posts.append(
            {
                "post": post_pseudonym,
                "author": author_map[post["author_local_id"]],
                "summary": clean_summary,
                "classification": post["classification"],
                "score": post["score"],
                "observed_on": post["observed_at"][:10],
                "uncertainty": post["uncertainty"],
            }
        )
        source_index = source["posts"].index(post)
        pointer = f"/posts/{source_index}"
        manifest.extend(
            [
                {"json_pointer": f"{pointer}/local_post_id", "action": "replace", "reason_code": "platform_identifier", "replacement": post_pseudonym},
                {"json_pointer": f"{pointer}/platform_post_id", "action": "omit", "reason_code": "platform_identifier", "replacement": None},
                {"json_pointer": f"{pointer}/raw_text", "action": "omit", "reason_code": "free_text_identity", "replacement": None},
                {"json_pointer": f"{pointer}/observed_at", "action": "coarsen", "reason_code": "precise_time", "replacement": post["observed_at"][:10]},
                {"json_pointer": f"{pointer}/captured_url", "action": "omit", "reason_code": "platform_identifier" if "x.com" in post["captured_url"] else "tracking_parameter", "replacement": None},
                {"json_pointer": f"{pointer}/media", "action": "omit", "reason_code": "media", "replacement": None},
            ]
        )
        if clean_summary != post["summary"]:
            manifest.append(
                {
                    "json_pointer": f"{pointer}/summary",
                    "action": "replace",
                    "reason_code": "formula_injection",
                    "replacement": clean_summary,
                }
            )

    sources = []
    for index, item in enumerate(source["verification_sources"]):
        clean_url = strip_query_and_fragment(item["url"])
        sources.append({**item, "url": clean_url})
        if clean_url != item["url"]:
            manifest.append(
                {
                    "json_pointer": f"/verification_sources/{index}/url",
                    "action": "strip_query",
                    "reason_code": "tracking_parameter",
                    "replacement": clean_url,
                }
            )

    result = {
        "schema_version": "1.0.0",
        "sanitizer_version": "1.0.0",
        "generated_on": source["generated_at"][:10],
        "authors": [{"author": author_map[value]} for value in author_ids],
        "posts": posts,
        "verification_sources": sources,
        "redaction_manifest": manifest,
        "content_digest": "",
        "privacy_warning": "Minimized synthetic export; prose can still contain contextual identity clues.",
    }
    result["content_digest"] = digest_without_field(result)
    return result


def check_schema_documents() -> str:
    schemas = sorted(SCHEMAS.glob("*.schema.json"))
    require(len(schemas) == 7, "expected seven v1 schema documents")
    ids = set()
    for path in schemas:
        schema = load_json(path)
        require(schema["$schema"] == "https://json-schema.org/draft/2020-12/schema", f"wrong dialect: {path.name}")
        require("/v1/" in schema["$id"], f"unversioned schema ID: {path.name}")
        require(schema["$id"] not in ids, f"duplicate schema ID: {path.name}")
        ids.add(schema["$id"])
        for ref in re.findall(r'"\$ref"\s*:\s*"([^"]+)"', path.read_text(encoding="utf-8")):
            target = ref.split("#", 1)[0]
            if target and not target.startswith("https://"):
                require((path.parent / target).is_file(), f"unresolved schema reference: {path.name} -> {target}")

    common = load_json(SCHEMAS / "common.schema.json")["$defs"]
    required_defs = {"AuthorRole", "AuthorRef", "Relationship", "Media", "Provenance", "Uncertainty", "PromotedCard", "Score", "Verification", "Recommendation", "Redaction"}
    require(required_defs <= set(common), "common schema is missing required contract definitions")

    examples = [
        (load_json(FIXTURES / "dom-session.json"), SCHEMAS / "envelope.schema.json"),
        (load_json(FIXTURES / "recording-session.json"), SCHEMAS / "envelope.schema.json"),
        (load_json(FIXTURES / "model-handoff.json"), SCHEMAS / "model-handoff.schema.json"),
    ]
    examples.extend((item, SCHEMAS / "canonical-post.schema.json") for item in load_json(FIXTURES / "canonical-posts.json"))
    examples.extend((item, SCHEMAS / "analysis.schema.json") for item in load_json(FIXTURES / "analysis-records.json"))
    for value, path in examples:
        validate_schema_instance(value, load_json(path), path)

    session_path = SCHEMAS / "session.schema.json"
    session_schema = load_json(session_path)
    session = copy.deepcopy(examples[0][0]["session"])
    validate_schema_instance(session, session_schema, session_path)
    recording_session = copy.deepcopy(session)
    recording_session.update({"source": "synthetic_recording", "origin": None})
    validate_schema_instance(recording_session, session_schema, session_path)
    supplied_session = copy.deepcopy(session)
    supplied_session.update({"source": "user_supplied_recording", "origin": None})
    validate_schema_instance(supplied_session, session_schema, session_path)
    rejected_pairs = [
        {**session, "origin": "https://x.com"},
        {**recording_session, "origin": "https://fixture.example.invalid"},
        {**session, "source": "live_x_dom", "origin": "https://x.com"},
    ]
    for rejected in rejected_pairs:
        try:
            validate_schema_instance(rejected, session_schema, session_path)
        except CheckFailure:
            continue
        raise CheckFailure("source/origin negative control was accepted")
    return f"{len(schemas)} schemas, {len(required_defs)} required common definitions, {len(examples)} examples, 3 valid and 3 rejected source/origin pairings"


def check_fixture_manifest() -> str:
    manifest = load_json(FIXTURES / "manifest.json")
    require(manifest["fixture_set_version"] == "1.0.0", "fixture manifest version mismatch")
    require(manifest["provenance"]["origin"] == "authored_synthetic", "fixtures are not declared authored synthetic")
    require(manifest["provenance"]["contains_real_x_data"] is False, "fixture provenance permits real X data")
    listed = set()
    for item in manifest["files"]:
        path = FIXTURES / item["path"]
        require(path.is_file(), f"manifest file missing: {item['path']}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual == item["sha256"], f"fixture digest mismatch: {item['path']}")
        require(item["authored_synthetic"] is True, f"fixture lacks synthetic provenance: {item['path']}")
        listed.add(item["path"])
    actual_files = {path.name for path in FIXTURES.glob("*.json") if path.name != "manifest.json"}
    require(listed == actual_files, "fixture manifest does not exactly cover the corpus")
    return f"{len(listed)} fixture hashes verified"


def check_envelopes_and_deduplication() -> str:
    dom = load_json(FIXTURES / "dom-session.json")
    recording = load_json(FIXTURES / "recording-session.json")
    canonical_examples = load_json(FIXTURES / "canonical-posts.json")
    hard_stop_codes = set(load_json(CONTRACTS / "extension-lifecycle.json")["hard_stop_codes"])
    for envelope in (dom, recording):
        require(envelope["schema_version"] == "1.0.0", "envelope version mismatch")
        require(envelope["session"]["schema_version"] == "1.0.0", "session version mismatch")
        require(len(envelope["observations"]) <= 250, "candidate limit exceeded")
        require(envelope["content_digest"] == digest_without_field(envelope), "envelope digest mismatch")
        ids = [item["observation_id"] for item in envelope["observations"]]
        require(len(ids) == len(set(ids)), "duplicate observation ID")
        require(all(item["session_id"] == envelope["session"]["session_id"] for item in envelope["observations"]), "cross-session observation")
        stop_times = [event["at"] for event in envelope["collection_events"] if event["event_code"].startswith("STOPPED_") or event["event_code"] in hard_stop_codes]
        if stop_times:
            first_stop = min(stop_times)
            observed_times = [provenance["observed_at"] for item in envelope["observations"] for provenance in item["provenance"]]
            require(all(value <= first_stop for value in observed_times), "observation occurs after a stop event")

    dom_expected = {"canonical": 5, "organic": 3, "promoted": 1, "ambiguous": 1}
    rec_expected = {"canonical": 3, "organic": 2, "promoted": 0, "ambiguous": 1}
    baseline_dom = canonicalize(dom["observations"])
    baseline_rec = canonicalize(recording["observations"])
    for baseline, expected in ((baseline_dom, dom_expected), (baseline_rec, rec_expected)):
        counts = {status: sum(item["promotion"] == status for item in baseline) for status in ("organic", "promoted", "ambiguous")}
        require(len(baseline) == expected["canonical"], "canonical count mismatch")
        require(all(counts[key] == expected[key] for key in counts), "promotion count mismatch")
        require(sum(counts.values()) == len(baseline), "count reconciliation failed")

    require(any(item["method"] == "platform_id" and len(item["observation_ids"]) == 2 for item in baseline_dom), "exact platform ID did not deduplicate")
    require(any(item["method"] == "exact_content_tuple" and len(item["observation_ids"]) == 2 for item in baseline_rec), "exact content tuple did not deduplicate")
    require(len(baseline_rec) == 3, "numeric conflict merged unsafely")
    require(sum(len(item["observation_ids"]) for item in baseline_dom) == len(dom["observations"]), "DOM observations were discarded")
    require(sum(len(item["observation_ids"]) for item in baseline_rec) == len(recording["observations"]), "recording observations were discarded")
    require(any(author["role"] == "original" for item in canonical_examples for author in item["authors"]), "canonical author-role example missing")
    require(any(rel["kind"] == "source_of" for item in canonical_examples for rel in item["relationships"]), "canonical source-relationship example missing")
    require(any(media["binary_collected"] is False for item in canonical_examples for media in item["media"]), "canonical media example missing or collects a binary")
    require(all("deduplication" in item and "promotion" in item and "uncertainty" in item for item in canonical_examples), "canonical contract example incomplete")

    permalink_a = copy.deepcopy(dom["observations"][0])
    permalink_b = copy.deepcopy(dom["observations"][1])
    for index, item in enumerate((permalink_a, permalink_b)):
        item["platform_post_id"] = None
        item["observation_id"] = f"permalink-{index}"
        item["appearance_index"] = index
        item["media"] = []
    require(len(canonicalize([permalink_b, permalink_a])) == 1, "canonical permalink did not deduplicate")

    conflict_a = copy.deepcopy(permalink_a)
    conflict_b = copy.deepcopy(permalink_b)
    conflict_a["platform_post_id"] = "synthetic-conflict-a"
    conflict_b["platform_post_id"] = "synthetic-conflict-b"
    require(len(canonicalize([conflict_a, conflict_b])) == 2, "conflicting platform IDs merged")

    numeric_a = copy.deepcopy(recording["observations"][0])
    numeric_b = copy.deepcopy(recording["observations"][2])
    for index, item in enumerate((numeric_a, numeric_b)):
        item["platform_post_id"] = "synthetic-shared-but-conflicted"
        item["observation_id"] = f"numeric-conflict-{index}"
        item["appearance_index"] = index
    require(len(canonicalize([numeric_a, numeric_b])) == 2, "same-ID numeric conflict merged")

    negation_a = copy.deepcopy(numeric_a)
    negation_b = copy.deepcopy(numeric_a)
    negation_a["observation_id"] = "negation-conflict-0"
    negation_b["observation_id"] = "negation-conflict-1"
    negation_b["appearance_index"] = 1
    negation_b["visible_text"] = negation_a["visible_text"].replace("no external action", "external action")
    require(len(canonicalize([negation_a, negation_b])) == 2, "same-ID negation conflict merged")

    near_a = copy.deepcopy(recording["observations"][0])
    near_b = copy.deepcopy(recording["observations"][1])
    near_b["visible_text"] = near_b["visible_text"].replace("careful", "carefu")
    require(len(canonicalize([near_a, near_b])) == 2, "near OCR text merged automatically")
    require(temporal_review_candidate(near_a, near_b), "eligible near OCR evidence did not enter review")
    short_a = copy.deepcopy(near_a)
    short_b = copy.deepcopy(near_b)
    short_a["visible_text"] = "Short synthetic note."
    short_b["visible_text"] = "Short synthetic n0te."
    require(not temporal_review_candidate(short_a, short_b), "short OCR text entered similarity review")

    role_cases = load_json(FIXTURES / "dedup-role-collisions.json")["cases"]
    role_template = copy.deepcopy(dom["observations"][2])
    for case in role_cases:
        pair = []
        for side, authors in (("left", case["authors_left"]), ("right", case["authors_right"])):
            observation = copy.deepcopy(role_template)
            observation["observation_id"] = f"{case['name']}-{side}"
            observation["appearance_index"] = len(pair)
            observation["platform_post_id"] = None
            observation["canonical_permalink"] = None
            observation["authors"] = authors
            observation["relationships"] = [{"kind": case["relationship_kind"], "source_local_post_id": "shared-source"}]
            pair.append(observation)
        require(primary_author(pair[0]) == case["expected_primary_left"], f"left primary author mismatch: {case['name']}")
        require(primary_author(pair[1]) == case["expected_primary_right"], f"right primary author mismatch: {case['name']}")
        merged = len(canonicalize(pair)) == 1
        require(merged is case["expected_automatic_merge"], f"relation-aware fallback mismatch: {case['name']}")

    for observations, baseline in ((dom["observations"], baseline_dom), (recording["observations"], baseline_rec)):
        variants = [list(reversed(observations))]
        for seed in range(20):
            shuffled = list(observations)
            random.Random(seed).shuffle(shuffled)
            variants.append(shuffled)
        require(all(canonicalize(items) == baseline for items in variants), "deduplication depends on input order")
    return "DOM 5/3/1/1 and recording 3/2/0/1 canonical/organic/promoted/ambiguous; quote/repost role collisions and 42 order variants stable"


def check_analysis_contracts() -> str:
    records = load_json(FIXTURES / "analysis-records.json")
    classes = {
        "A_HIGH_SIGNAL", "B_PROMISING_VERIFY", "C_COMMUNITY_LIGHT_VALUE",
        "D_LOW_SIGNAL_SLOP", "E_SCAM_MANIPULATIVE_UNSAFE", "F_INSUFFICIENT_INFORMATION",
    }
    actions = load_json(SCHEMAS / "analysis.schema.json")["properties"]["manual_action"]["enum"]
    for record in records:
        require(record["classification"] in classes, "unknown classification")
        require(record["manual_action"] in actions, "unknown manual action")
        score = record["score"]
        require(all(isinstance(score[key], int) and 0 <= score[key] <= 5 for key in ("relevance", "credibility", "information_value", "actionability", "risk")), "score factor out of range")
        expected = score["relevance"] + score["credibility"] + score["information_value"] + score["actionability"] - score["risk"]
        require(score["priority"] == expected, "priority formula mismatch")
        require(all(rec["performed"] is False for rec in record["recommendations"]), "recommendation claims a performed action")
        if record["classification"] == "A_HIGH_SIGNAL":
            require(score["relevance"] >= 3 and score["credibility"] >= 3 and score["information_value"] >= 3 and score["risk"] <= 2, "Class A score gate failed")
            require(all(item["result"] in {"confirmed", "partially_confirmed"} and any(source["source_class"] == "primary" for source in item["sources"]) for item in record["verification"] if item["required"]), "Class A verification gate failed")

    def follow_allowed(originals: int, credibility: float, promoted_density: float, identity_conflict: bool, unsafe: bool, blocking: bool) -> bool:
        return originals >= 2 and credibility >= 3.0 and promoted_density < 0.5 and not identity_conflict and not unsafe and not blocking

    cases = [
        ((2, 3.0, 0.49, False, False, False), True),
        ((1, 5.0, 0.0, False, False, False), False),
        ((2, 2.99, 0.0, False, False, False), False),
        ((2, 5.0, 0.5, False, False, False), False),
        ((3, 5.0, 0.0, True, False, False), False),
        ((3, 5.0, 0.0, False, True, False), False),
        ((3, 5.0, 0.0, False, False, True), False),
    ]
    require(all(follow_allowed(*args) is expected for args, expected in cases), "follow threshold mismatch")
    return f"{len(records)} analysis examples and {len(cases)} follow-threshold cases passed"


def unique_metrics(expected: int, predicted: int, matches: int) -> tuple[Fraction, Fraction]:
    require(0 <= matches <= min(expected, predicted), "invalid one-to-one match count")
    if expected == 0 and predicted == 0:
        return Fraction(1, 1), Fraction(1, 1)
    precision = Fraction(matches, predicted) if predicted else Fraction(0, 1)
    recall = Fraction(matches, expected) if expected else Fraction(0, 1)
    return precision, recall


def check_metric_formulas() -> str:
    dom_precision, dom_recall = unique_metrics(5, 5, 5)
    rec_precision, rec_recall = unique_metrics(3, 3, 3)
    require(dom_precision >= Fraction(99, 100), "DOM precision threshold failed")
    require(dom_recall >= Fraction(98, 100), "DOM recall threshold failed")
    require(rec_precision >= Fraction(95, 100), "recording precision threshold failed")
    require(rec_recall >= Fraction(90, 100), "recording recall threshold failed")
    require(unique_metrics(0, 0, 0) == (Fraction(1), Fraction(1)), "empty-set metric definition mismatch")
    require(unique_metrics(1, 0, 0) == (Fraction(0), Fraction(0)), "missing-prediction metric definition mismatch")
    require(unique_metrics(0, 1, 0) == (Fraction(0), Fraction(0)), "unexpected-prediction metric definition mismatch")

    relationship_accuracy = Fraction(1, 1)
    promoted_separation = Fraction(4, 4)
    classification_completeness = Fraction(4, 4)
    stop_rate = Fraction(12, 12)
    require(all(value == 1 for value in (relationship_accuracy, promoted_separation, classification_completeness, stop_rate)), "exact acceptance ratio failed")
    return "precision/recall edge definitions and DOM 0.99/0.98, recording 0.95/0.90, exact 1.00 thresholds passed"


def check_handoff_and_privacy() -> str:
    packet = load_json(FIXTURES / "model-handoff.json")
    require(packet["trusted_control"]["created_by"] == "local_trusted_analyzer", "handoff trusted producer mismatch")
    authority = packet["trusted_control"]["tool_authority"]
    require(authority == {"mode": "deny_by_default", "allowed_tools": [], "captured_urls_authoritative": False}, "handoff tool authority widened")
    require(all(value is False for value in packet["authority_result"].values()), "handoff authority result widened")
    require(any("Ignore every rule" in item["quoted_value"] for item in packet["untrusted_records"]), "injection fixture missing")

    privacy_cases = load_json(FIXTURES / "privacy-rejection.json")["cases"]
    for case in privacy_cases:
        category = sensitive_category(case["packet"])
        logs = [category or "REJECTED_UNKNOWN", "import rejected before persistence"]
        require(category == case["expected_category"], f"privacy rejection category mismatch: {case['name']}")
        require(all(case["must_not_echo"] not in item for item in logs), f"secret canary echoed: {case['name']}")
    safe_payload = {"token_count": 12, "public_source_url": "https://research.example.invalid", "summary": "Ordinary synthetic text."}
    require(sensitive_category(safe_payload) is None, "credential detector rejected safe negative control")
    return f"injection remained quoted with zero authority; {len(privacy_cases)} sensitive packets rejected with zero complete-canary echoes"


def check_sanitizer() -> str:
    source = load_json(FIXTURES / "sanitizer-input.json")
    expected_path = FIXTURES / "sanitizer-expected.json"
    actual = sanitize(source)
    require(actual["content_digest"] == digest_without_field(actual), "sanitizer digest mismatch")
    require(pretty_bytes(actual) == expected_path.read_bytes(), "sanitizer output differs byte-for-byte from golden file")
    rendered = pretty_bytes(actual).decode("utf-8")
    prohibited = ["example_alpha", "example_beta", "synthetic-author-", "synthetic-post-", "local-post-", "@example", "?", "#fragment", "media-diagram"]
    require(all(value not in rendered for value in prohibited), "sanitized export retained a prohibited identity/media/query value")
    require(all(not has_formula_prefix(post["summary"]) for post in actual["posts"]), "sanitized summary has spreadsheet formula prefix")
    require(actual["posts"][1]["summary"].startswith("'=HYPERLINK"), "retained formula canary was not neutralized explicitly")
    require(neutralize_formula("Ordinary summary") == "Ordinary summary", "safe summary changed during formula neutralization")
    require(neutralize_formula(" \t=SUM(1,1)") == "' \t=SUM(1,1)", "leading-whitespace formula prefix was not neutralized")
    require(len(actual["redaction_manifest"]) == 16, "redaction manifest count mismatch")
    return "golden output matched byte-for-byte with 16 reconciled redactions and retained-summary formula neutralization"


def check_lifecycle_manifest_and_limits() -> str:
    manifest = load_json(CONTRACTS / "manifest.proposal.json")
    test_manifest = load_json(CONTRACTS / "manifest.synthetic-test-only.json")
    boundary = load_json(CONTRACTS / "browser-test-boundary.json")
    require(manifest["manifest_version"] == 3, "manifest is not MV3")
    require(manifest["permissions"] == ["storage", "scripting"], "manifest ordinary permissions drifted")
    require(manifest["optional_host_permissions"] == ["https://x.com/*"], "optional host permission drifted")
    forbidden_manifest_keys = {"host_permissions", "content_scripts", "externally_connectable"}
    require(not (forbidden_manifest_keys & set(manifest)), "manifest added a forbidden top-level capability")
    serialized = compact_bytes(manifest).decode("utf-8")
    forbidden_permissions = ["<all_urls>", "cookies", "webRequest", "declarativeNetRequest", "debugger", "nativeMessaging", "downloads", "http://", "twitter.com", "api.x.com", "localhost"]
    require(all(item not in serialized for item in forbidden_permissions), "manifest contains a forbidden permission or host")
    require(boundary["production_proposal"] == {
        "manifest": "contracts/v1/manifest.proposal.json",
        "review_mode": "static_inspection_only",
        "optional_live_origin": "https://x.com/*",
        "granted_or_exercised_through_gate2": False,
        "packaged_for_distribution_through_gate2": False,
    }, "production proposal boundary drifted")
    harness = boundary["synthetic_browser_harness"]
    require(test_manifest["permissions"] == ["storage"], "test harness permissions drifted")
    require(test_manifest["host_permissions"] == ["https://fixture.example.invalid/*"], "test harness origin drifted")
    require("optional_host_permissions" not in test_manifest, "test harness exposes optional live permission")
    require(all(item["matches"] == ["https://fixture.example.invalid/*"] and item["world"] == "ISOLATED" for item in test_manifest["content_scripts"]), "test harness script boundary drifted")
    require("TEST ONLY" in test_manifest["name"] and "NON-DISTRIBUTABLE" in test_manifest["description"], "test harness markers missing")
    require(harness["isolated_profile"] is True and harness["outbound_network_denied"] is True and harness["non_distributable"] is True, "test harness safety flags drifted")
    require(harness["allowed_navigation_origins"] == ["https://fixture.example.invalid"], "test harness navigation allowlist widened")
    test_serialized = compact_bytes(test_manifest).decode("utf-8")
    require(all(origin not in test_serialized for origin in ("https://x.com", "https://twitter.com", "https://api.x.com")), "test harness can reach a live X origin")
    production_paths = ["manifest.json", "background.js", "control.html", "collector.js"]
    require(production_candidate_safe(manifest, production_paths, boundary), "production proposal failed non-promotion oracle")
    leaked_manifest = copy.deepcopy(manifest)
    leaked_manifest["host_permissions"] = ["https://fixture.example.invalid/*"]
    require(not production_candidate_safe(leaked_manifest, production_paths, boundary), "fixture origin leaked into production negative control")
    require(not production_candidate_safe(manifest, [*production_paths, "synthetic-harness.js"], boundary), "test harness path leaked into production negative control")
    widened_test = copy.deepcopy(test_manifest)
    widened_test["host_permissions"].append("https://x.com/*")
    require(synthetic_harness_safe(test_manifest), "synthetic harness failed its exact-capability oracle")
    require(not synthetic_harness_safe(widened_test), "live X origin was accepted by synthetic harness negative control")

    lifecycle = load_json(CONTRACTS / "extension-lifecycle.json")
    require(lifecycle["initial_state"] == "INACTIVE", "lifecycle initial state drifted")
    require(lifecycle["limits"] == {"minimum_visibility_ratio": 0.5, "max_candidates": 250, "max_duration_seconds": 1800, "max_packet_bytes": 5242880, "max_ambiguity_ratio": 0.05}, "lifecycle limits drifted")
    require(any(item["from"] == "ARMED" and item["event"] == "USER_STARTS_SESSION" and item["to"] == "CAPTURING" for item in lifecycle["transitions"]), "user start transition missing")
    require(all(item["to"] != "CAPTURING" for item in lifecycle["transitions"] if item["event"] == "PERMISSION_GRANTED"), "permission grant starts capture")
    event_codes = set(load_json(SCHEMAS / "envelope.schema.json")["properties"]["collection_events"]["items"]["properties"]["event_code"]["enum"])
    require(set(lifecycle["hard_stop_codes"]) <= event_codes, "envelope cannot represent every lifecycle hard-stop code")

    policy = load_json(FIXTURES / "policy-cases.json")
    topology_names = {"original", "repost", "quote", "reply-as-card", "two-visible-thread-cards", "promoted-card", "community-note"}
    require({item["name"] for item in policy["topology_cases"]} == topology_names, "topology coverage incomplete")
    require(all(0 <= item["organic_units"] <= item["top_level_units"] for item in policy["topology_cases"]), "topology count oracle invalid")
    require(next(item for item in policy["topology_cases"] if item["name"] == "promoted-card")["organic_units"] == 0, "promoted topology entered organic count")
    require(next(item for item in policy["topology_cases"] if item["name"] == "two-visible-thread-cards")["top_level_units"] == 2, "thread oracle inferred the wrong unit count")

    identity_names = {"display-name-collision", "handle-change-same-platform-author", "repost-quote-role-conflict", "missing-platform-id-exact-tuple", "missing-platform-id-partial-evidence"}
    require({item["name"] for item in policy["identity_cases"]} == identity_names, "identity coverage incomplete")
    require(next(item for item in policy["identity_cases"] if item["name"] == "display-name-collision")["automatic_merge"] is False, "display-name collision merges")
    require(next(item for item in policy["identity_cases"] if item["name"] == "repost-quote-role-conflict")["automatic_merge"] is False, "author-role conflict merges")

    advertising = {item["name"]: item for item in policy["advertising_cases"]}
    require(set(advertising) == {"clear-promoted-label", "delayed-label", "ambiguous-sponsorship", "ordinary-product-discussion"}, "advertising coverage incomplete")
    require(advertising["clear-promoted-label"]["status"] == "promoted" and advertising["clear-promoted-label"]["organic_denominator"] is False, "clear promotion handling mismatch")
    require(all(advertising[name]["status"] == "ambiguous" and advertising[name]["organic_denominator"] is False for name in ("delayed-label", "ambiguous-sponsorship")), "ambiguous advertising entered organic denominator")
    require(advertising["ordinary-product-discussion"]["status"] == "organic", "ordinary product discussion mislabeled")

    text_names = {"long-text", "unicode-nfc", "right-to-left", "emoji", "code-like", "prompt-injection", "zero-width"}
    require({item["name"] for item in policy["text_cases"]} == text_names, "text coverage incomplete")
    require(normalized_text("Cafe\u0301") == normalized_text("Café"), "NFC comparison normalization failed")
    require("\u200b" in normalized_text("synthetic\u200btext"), "zero-width evidence was silently erased")

    media_names = {"image-alt-text", "video-poster", "missing-alt-text", "quoted-media", "media-only-card"}
    require({item["name"] for item in policy["media_cases"]} == media_names, "media coverage incomplete")
    require(all(item["binary_collected"] is False for item in policy["media_cases"]), "media fixture permits binary collection")
    require(all(next(item for item in policy["media_cases"] if item["name"] == name)["uncertain"] for name in ("missing-alt-text", "media-only-card")), "missing/media-only uncertainty absent")
    for case in policy["visibility_cases"]:
        observed = case["document_visible"] and case["ratio"] >= lifecycle["limits"]["minimum_visibility_ratio"]
        require(observed is case["eligible"], f"visibility boundary mismatch: {case['name']}")
    require({item["code"] for item in policy["hard_stop_cases"]} <= set(lifecycle["hard_stop_codes"]), "hard-stop fixture missing from lifecycle")
    for case in policy["hard_stop_cases"]:
        stopped = simulate_hard_stop("CAPTURING", case["code"], lifecycle)
        require(stopped["state"] == "ERROR" and stopped["event_code"] == case["code"], f"hard stop did not enter ERROR: {case['name']}")
        require(all(stopped[key] == 0 for key in ("observers", "timers", "dom_references", "later_observations")), f"hard stop retained runtime state: {case['name']}")
        require(stopped["automatic_retry"] is False, f"hard stop enabled retry: {case['name']}")
    require(all(value == 0 for value in policy["collector_effects"].values()), "collector fixture recorded a forbidden or post-stop effect")
    require({item["name"] for item in policy["accessibility_cases"]} == {"keyboard-only", "screen-reader", "high-contrast", "zoom-200", "no-color"}, "accessibility coverage incomplete")
    require(all(item["required"] for item in policy["accessibility_cases"]), "accessibility case is optional")
    require({item["name"] for item in policy["malformed_cases"]} >= {"missing-version", "unknown-version", "wrong-type", "depth-65", "field-10001", "observations-251", "packet-5242881"}, "malformed/resource coverage incomplete")
    for case in policy["malformed_cases"]:
        require(validate_resource_case(case["name"]) == case["category"], f"malformed/resource case did not reject exactly: {case['name']}")
    require(250 <= lifecycle["limits"]["max_candidates"] and 251 > lifecycle["limits"]["max_candidates"], "queue boundary behavior drifted")
    require(1800 <= lifecycle["limits"]["max_duration_seconds"] and 1801 > lifecycle["limits"]["max_duration_seconds"], "duration boundary behavior drifted")
    require(5242880 <= lifecycle["limits"]["max_packet_bytes"] and 5242881 > lifecycle["limits"]["max_packet_bytes"], "packet boundary behavior drifted")
    require(0.05 <= lifecycle["limits"]["max_ambiguity_ratio"] and 0.050001 > lifecycle["limits"]["max_ambiguity_ratio"], "ambiguity boundary behavior drifted")
    return f"separate production/static and synthetic/test-only MV3 contracts; {len(policy['hard_stop_cases'])} stops, {len(policy['visibility_cases'])} visibility edges, zero forbidden effects"


def check_repository_safety_and_notices() -> str:
    real_status = re.compile(r"https://(?:www\.)?x\.com/[A-Za-z0-9_]+/status/[0-9]+")
    local_path = re.compile(r"(?:/Users/|[A-Za-z]:\\\\Users\\\\)\S+")
    forbidden_suffixes = {".mp4", ".mov", ".m4v", ".webm", ".sqlite", ".sqlite3", ".db", ".pem", ".key", ".p12", ".har"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        require(path.suffix.lower() not in forbidden_suffixes and path.name != ".env", f"forbidden private/credential artifact: {path.relative_to(ROOT)}")
        if path.suffix.lower() in {".md", ".json", ".py", ".sh"}:
            text = path.read_text(encoding="utf-8")
            require(not real_status.search(text), f"real X status URL pattern: {path.relative_to(ROOT)}")
            if path.suffix.lower() in {".md", ".json"}:
                require(not local_path.search(text), f"local absolute path: {path.relative_to(ROOT)}")

    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    require("No third-party package" in notices, "empty adopted-dependency declaration missing")
    package_files = [path for pattern in ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "requirements*.txt", "poetry.lock", "Pipfile.lock", "Cargo.lock", "Package.resolved") for path in ROOT.rglob(pattern) if ".git" not in path.parts]
    require(not package_files, "dependency/lockfile exists despite empty notice set")
    return "no private artifact, real-status URL, local path, or undeclared dependency found"


def run() -> int:
    checks = [
        ("schemas", check_schema_documents),
        ("fixture provenance", check_fixture_manifest),
        ("deduplication and counts", check_envelopes_and_deduplication),
        ("classification and scoring", check_analysis_contracts),
        ("metric formulas and thresholds", check_metric_formulas),
        ("handoff and privacy", check_handoff_and_privacy),
        ("sanitizer", check_sanitizer),
        ("manifest and lifecycle", check_lifecycle_manifest_and_limits),
        ("repository safety and notices", check_repository_safety_and_notices),
    ]
    for name, check in checks:
        detail = check()
        print(f"PASS {name}: {detail}")
    print(f"Gate 1 acceptance passed: {len(checks)} deterministic groups")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except (CheckFailure, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL Gate 1 acceptance: {error}", file=sys.stderr)
        raise SystemExit(1)
