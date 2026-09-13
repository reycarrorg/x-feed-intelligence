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
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return data + (b"\n" if trailing_newline else b"")


def pretty_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


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


def _tokens(text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return tuple(re.findall(r"\d+(?:\.\d+)?", text)), tuple(sorted(set(re.findall(r"[A-Za-z]+", text.lower())) & NEGATIONS))


def has_merge_conflict(existing: list[dict], candidate: dict) -> bool:
    values = [*existing, candidate]
    sets = [
        {item.get("platform_post_id") for item in values if item.get("platform_post_id")},
        {primary_author(item) for item in values if primary_author(item)},
        {item.get("displayed_timestamp") for item in values if item.get("displayed_timestamp")},
        {item["promotion"]["status"] for item in values},
        {media_key(item) for item in values if item["media"]},
        {_tokens(normalized_text(item.get("visible_text")) or "")[0] for item in values},
        {_tokens(normalized_text(item.get("visible_text")) or "")[1] for item in values},
    ]
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
    groups: dict[tuple[str, str], list[dict]] = {}
    ordered = sorted(observations, key=lambda o: (o["session_id"], o["appearance_index"], o["observation_id"]))
    for observation in ordered:
        key = observation_key(observation)
        if key in groups and has_merge_conflict(groups[key], observation):
            key = "singleton", observation["observation_id"]
        groups.setdefault(key, []).append(observation)

    output: list[dict] = []
    for (method, value), items in sorted(groups.items()):
        stable = hashlib.sha256(canonical_bytes([method, value])).hexdigest()[:16]
        first = items[0]
        output.append({
            "local_post_id": f"local-{stable}",
            "platform_post_id": first.get("platform_post_id"),
            "canonical_permalink": canonical_permalink(first.get("canonical_permalink")),
            "observation_ids": sorted(item["observation_id"] for item in items),
            "authors": first["authors"],
            "relationships": sorted(first["relationships"], key=lambda r: (r["kind"], r["source_local_post_id"])),
            "media": first["media"],
            "promotion": first["promotion"],
            "visible_text": first.get("visible_text"),
            "deduplication": {
                "method": method if len(items) > 1 else "singleton",
                "confidence": 1.0 if method != "singleton" else 0.5,
                "review_required": False,
                "evidence_observation_ids": sorted(item["observation_id"] for item in items),
            },
            "uncertainty": sorted(first["uncertainty"], key=lambda u: (u["code"], u["field"])),
        })
    return sorted(output, key=lambda post: post["local_post_id"])
