"""Canonical JSON, digests, and relation-aware deterministic deduplication."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from .errors import ValidationError

NEGATIONS = {"no", "not", "never", "without"}


def canonical_bytes(value: object, trailing_newline: bool = False) -> bytes:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return data + (b"\n" if trailing_newline else b"")


def pretty_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(value: dict, field: str = "content_digest") -> str:
    clone = copy.deepcopy(value)
    clone.pop(field, None)
    return "sha256:" + hashlib.sha256(canonical_bytes(clone)).hexdigest()


def normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(unicodedata.normalize("NFC", value.replace("\r\n", "\n")).split())


def canonical_permalink(raw: str | None) -> str | None:
    if raw is None:
        return None
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or host not in {"x.com", "example.invalid"}:
        raise ValidationError("REJECTED_ORIGIN")
    if parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443}:
        raise ValidationError("REJECTED_ORIGIN")
    return urlunsplit(("https", host, parsed.path.rstrip("/") or "/", "", ""))


def primary_author(observation: dict) -> str | None:
    kinds = {item["kind"] for item in observation["relationships"]}
    roles = ("quoting", "presenting") if "quotes" in kinds else (("original",) if "repost_of" in kinds else ("presenting", "original", "quoting", "reposting", "unknown"))
    for role in roles:
        for author in observation["authors"]:
            if author["role"] == role:
                return author.get("platform_author_id") or author.get("handle") or author.get("local_author_id")
    return None


def media_key(observation: dict) -> tuple:
    return tuple((item["kind"], item.get("perceptual_fingerprint"), normalized_text(item.get("alt_text")), normalized_text(item.get("visible_description"))) for item in observation["media"])


def observation_key(observation: dict) -> tuple[str, str]:
    if observation.get("platform_post_id"):
        return "platform_id", observation["platform_post_id"]
    permalink = canonical_permalink(observation.get("canonical_permalink"))
    if permalink:
        return "canonical_permalink", permalink
    author = primary_author(observation)
    text = normalized_text(observation.get("visible_text"))
    timestamp = observation.get("displayed_timestamp")
    if author and text and timestamp:
        material = canonical_bytes([author, text, media_key(observation), timestamp])
        return "exact_content_tuple", hashlib.sha256(material).hexdigest()
    return "singleton", observation["observation_id"]


def local_post_id(method: str, value: str) -> str:
    stable = hashlib.sha256(canonical_bytes([method, value])).hexdigest()[:16]
    return f"local-{stable}"


def relationship_target_ids(observations: list[dict]) -> dict[str, str]:
    platform_targets = {
        observation["platform_post_id"]: local_post_id("platform_id", observation["platform_post_id"])
        for observation in observations if observation.get("platform_post_id")
    }
    generated_ids = {local_post_id(*observation_key(observation)) for observation in observations}
    for observation in observations:
        for relationship in observation["relationships"]:
            source_platform = relationship.get("source_platform_post_id")
            source_local = relationship["source_local_post_id"]
            if source_platform is not None:
                expected = platform_targets.get(source_platform)
                if expected is None:
                    raise ValidationError("REJECTED_REFERENCE")
                if source_local in generated_ids and source_local != expected:
                    raise ValidationError("REJECTED_REFERENCE")
            elif source_local not in generated_ids:
                raise ValidationError("REJECTED_REFERENCE")
    return platform_targets


def _relationship_signature(observation: dict) -> tuple:
    return tuple(sorted((item["kind"], item.get("source_platform_post_id") or item["source_local_post_id"]) for item in observation["relationships"]))


def _tokens(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return tuple(re.findall(r"\d+(?:\.\d+)?", text)), tuple(sorted(set(re.findall(r"[A-Za-z]+", text.lower())) & NEGATIONS))


def _semantic_tokens(observation: dict) -> tuple[tuple[str, ...], tuple[str, ...]]:
    text = normalized_text(observation.get("visible_text")) or ""
    structured = [
        value
        for author in observation["authors"]
        for value in (author.get("display_name"), author.get("handle"))
        if value
    ]
    structured.extend(
        value
        for relationship in observation["relationships"]
        for value in (relationship.get("source_platform_post_id"), relationship.get("source_local_post_id"))
        if value
    )
    structured.extend(["review required", observation["promotion"]["status"]])
    for value in sorted(structured, key=len, reverse=True):
        normalized = normalized_text(value)
        if normalized:
            text = re.sub(r"(?<!\w)" + re.escape(normalized) + r"(?!\w)", " ", text, flags=re.IGNORECASE)
    return _tokens(normalized_text(text) or "")


def has_merge_conflict(existing: list[dict], candidate: dict, method: str | None = None) -> bool:
    values = [*existing, candidate]
    sets = [
        {item.get("platform_post_id") for item in values if item.get("platform_post_id")},
        {item["promotion"]["status"] for item in values},
        {media_key(item) for item in values if item["media"]},
        {_relationship_signature(item) for item in values},
        {_semantic_tokens(item)[0] for item in values},
        {_semantic_tokens(item)[1] for item in values},
    ]
    if method != "platform_id":
        sets.extend([
            {primary_author(item) for item in values if primary_author(item)},
            {item.get("displayed_timestamp") for item in values if item.get("displayed_timestamp")},
        ])
    return any(len(group) > 1 for group in sets)


def levenshtein(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, lchar in enumerate(left, 1):
        current = [i]
        for j, rchar in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (lchar != rchar)))
        previous = current
    return previous[-1]


def temporal_review_candidate(left: dict, right: dict) -> bool:
    ltext, rtext = normalized_text(left.get("visible_text")) or "", normalized_text(right.get("visible_text")) or ""
    if min(len(ltext), len(rtext)) < 80 or left["session_id"] != right["session_id"]:
        return False
    if primary_author(left) != primary_author(right) or media_key(left) != media_key(right) or left.get("displayed_timestamp") != right.get("displayed_timestamp"):
        return False
    if {p["modality"] for p in left["provenance"]} != {p["modality"] for p in right["provenance"]}:
        return False
    ltime, rtime = left["input_location"].get("video_time_ms"), right["input_location"].get("video_time_ms")
    if ltime is None or rtime is None or abs(ltime - rtime) > 2000 or _tokens(ltext) != _tokens(rtext):
        return False
    return 1 - levenshtein(ltext, rtext) / max(len(ltext), len(rtext)) >= 0.98


def canonicalize(observations: list[dict]) -> list[dict]:
    platform_targets = relationship_target_ids(observations)
    groups: dict[tuple[str, str], list[dict]] = {}
    ordered = sorted(observations, key=lambda o: (o["session_id"], o["appearance_index"], o["observation_id"]))
    for observation in ordered:
        key = observation_key(observation)
        if key in groups and has_merge_conflict(groups[key], observation, key[0]):
            key = "singleton", observation["observation_id"]
        groups.setdefault(key, []).append(observation)

    output: list[dict] = []
    for (method, value), items in sorted(groups.items()):
        first = items[0]
        relationships: dict[tuple[str, str], dict] = {}
        for item in items:
            for relationship in item["relationships"]:
                source_platform = relationship.get("source_platform_post_id")
                target = platform_targets[source_platform] if source_platform is not None else relationship["source_local_post_id"]
                key = relationship["kind"], target
                if key not in relationships:
                    relationships[key] = {**relationship, "source_local_post_id": target, "provenance_ids": []}
                relationships[key]["confidence"] = min(relationships[key]["confidence"], relationship["confidence"])
                relationships[key]["provenance_ids"] = sorted(set(relationships[key]["provenance_ids"]) | set(relationship.get("provenance_ids", [])))
        authors = {canonical_bytes(author): author for item in items for author in item["authors"]}
        media: dict[str, dict] = {}
        for item in items:
            for entry in item["media"]:
                if entry["local_media_id"] not in media:
                    media[entry["local_media_id"]] = {**entry, "provenance_ids": []}
                media[entry["local_media_id"]]["confidence"] = min(media[entry["local_media_id"]]["confidence"], entry["confidence"])
                media[entry["local_media_id"]]["provenance_ids"] = sorted(set(media[entry["local_media_id"]]["provenance_ids"]) | set(entry.get("provenance_ids", [])))
        uncertainty = {canonical_bytes(entry): entry for item in items for entry in item["uncertainty"]}
        modalities = {provenance["modality"] for item in items for provenance in item["provenance"]}
        visible_variants = {normalized_text(item.get("visible_text")) for item in items}
        if len(modalities) > 1 and (len(visible_variants) > 1 or len(authors) > len(first["authors"])):
            variant = {"code": "CROSS_MODALITY_VARIANT", "field": "canonical_record", "severity": "review", "requires_review": True, "safe_detail": "Modalities agree on stable identity and invariants but retain distinct observation evidence."}
            uncertainty[canonical_bytes(variant)] = variant
        promotion_evidence = sorted({evidence for item in items for evidence in item["promotion"]["evidence"]})
        output.append({
            "local_post_id": local_post_id(method, value),
            "platform_post_id": first.get("platform_post_id"),
            "canonical_permalink": canonical_permalink(first.get("canonical_permalink")),
            "observation_ids": sorted(item["observation_id"] for item in items),
            "authors": sorted(authors.values(), key=lambda a: (a["role"], a["local_author_id"])),
            "relationships": [relationships[key] for key in sorted(relationships)],
            "media": [media[key] for key in sorted(media)],
            "promotion": {"status": first["promotion"]["status"], "evidence": promotion_evidence, "confidence": min(item["promotion"]["confidence"] for item in items)},
            "visible_text": first.get("visible_text"),
            "deduplication": {
                "method": method if len(items) > 1 else "singleton",
                "confidence": 1.0 if method != "singleton" else 0.5,
                "review_required": False,
                "evidence_observation_ids": sorted(item["observation_id"] for item in items),
            },
            "uncertainty": sorted(uncertainty.values(), key=lambda u: (u["code"], u["field"])),
        })
    return sorted(output, key=lambda post: post["local_post_id"])
