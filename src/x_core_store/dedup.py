"""Deterministic relation-aware deduplication and canonical post construction."""

from __future__ import annotations

import copy
import hashlib
import re

from x_core_store.canonical import (
    canonical_permalink,
    compact_bytes,
    levenshtein_distance,
    normalized_text,
)

NEGATIONS = {"no", "not", "never", "without"}


def primary_author(observation: dict) -> str | None:
    """Select relation-aware primary author identity according to contract rules."""
    relationship_kinds = {item["kind"] for item in observation.get("relationships", [])}
    if "quotes" in relationship_kinds:
        priority = ("quoting", "presenting")
    elif "repost_of" in relationship_kinds:
        priority = ("original",)
    else:
        priority = ("presenting", "original", "quoting", "reposting", "unknown")

    authors = observation.get("authors", [])
    for role in priority:
        for author in authors:
            if author.get("role") == role:
                return (
                    author.get("platform_author_id")
                    or author.get("handle")
                    or author.get("local_author_id")
                )
    return None


def media_key(observation: dict) -> tuple:
    """Extract comparable media descriptors."""
    return tuple(
        (
            item["kind"],
            item.get("perceptual_fingerprint"),
            normalized_text(item.get("alt_text")),
            normalized_text(item.get("visible_description")),
        )
        for item in observation.get("media", [])
    )


def observation_key(observation: dict) -> tuple[str, str]:
    """Select first applicable key from the 5-step deduplication ladder."""
    platform_id = observation.get("platform_post_id")
    if platform_id:
        return "platform_id", platform_id

    raw_permalink = observation.get("canonical_permalink")
    if raw_permalink:
        try:
            permalink = canonical_permalink(raw_permalink)
            if permalink:
                return "canonical_permalink", permalink
        except Exception:
            pass

    author = primary_author(observation)
    text = normalized_text(observation.get("visible_text"))
    timestamp = observation.get("displayed_timestamp")
    if author and text and timestamp:
        material = compact_bytes([author, text, media_key(observation), timestamp])
        return "exact_content_tuple", hashlib.sha256(material).hexdigest()

    return "singleton", observation["observation_id"]


def has_merge_conflict(existing: list[dict], candidate: dict) -> bool:
    """Check if merging candidate into existing group violates any consistency constraint."""
    all_items = [*existing, candidate]
    platform_ids = {item.get("platform_post_id") for item in all_items if item.get("platform_post_id")}
    authors = {primary_author(item) for item in all_items if primary_author(item)}
    timestamps = {item.get("displayed_timestamp") for item in all_items if item.get("displayed_timestamp")}
    promotions = {item["promotion"]["status"] for item in all_items if "promotion" in item}
    media = {media_key(item) for item in all_items if item.get("media")}
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


def temporal_review_candidate(left: dict, right: dict) -> bool:
    """Evaluate whether two OCR candidates qualify for human temporal continuity review."""
    left_text = normalized_text(left.get("visible_text")) or ""
    right_text = normalized_text(right.get("visible_text")) or ""
    if min(len(left_text), len(right_text)) < 80:
        return False
    if left.get("session_id") != right.get("session_id") or primary_author(left) != primary_author(right):
        return False
    if media_key(left) != media_key(right) or left.get("displayed_timestamp") != right.get("displayed_timestamp"):
        return False
    left_modality = {item["modality"] for item in left.get("provenance", [])}
    right_modality = {item["modality"] for item in right.get("provenance", [])}
    if left_modality != right_modality:
        return False
    left_time = left.get("input_location", {}).get("video_time_ms")
    right_time = right.get("input_location", {}).get("video_time_ms")
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


def canonicalize(observations: list[dict]) -> list[dict]:
    """Canonicalize observations into sorted canonical posts with deduplication metadata."""
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
        local_post_id = f"local-{stable}"
        evidence_ids = sorted(item["observation_id"] for item in items)
        dedup_method = method if len(items) > 1 else "singleton"

        # Extract first non-null platform_post_id, canonical_permalink, visible_text
        platform_post_id = next((item.get("platform_post_id") for item in items if item.get("platform_post_id")), None)
        raw_permalink = next((item.get("canonical_permalink") for item in items if item.get("canonical_permalink")), None)
        canon_permalink = None
        if raw_permalink:
            try:
                canon_permalink = canonical_permalink(raw_permalink)
            except Exception:
                canon_permalink = raw_permalink
        visible_text = next((item.get("visible_text") for item in items if item.get("visible_text") is not None), None)

        # Aggregate authors (deduplicate by local_author_id and role)
        seen_authors = set()
        aggregated_authors = []
        for item in items:
            for auth in item.get("authors", []):
                key_auth = (auth["local_author_id"], auth["role"])
                if key_auth not in seen_authors:
                    seen_authors.add(key_auth)
                    aggregated_authors.append(copy.deepcopy(auth))

        # Aggregate relationships (deduplicate by kind and source_local_post_id)
        seen_rels = set()
        aggregated_rels = []
        for item in items:
            for rel in item.get("relationships", []):
                key_rel = (rel["kind"], rel["source_local_post_id"])
                if key_rel not in seen_rels:
                    seen_rels.add(key_rel)
                    aggregated_rels.append(copy.deepcopy(rel))

        # Aggregate media (deduplicate by local_media_id)
        seen_media = set()
        aggregated_media = []
        for item in items:
            for med in item.get("media", []):
                if med["local_media_id"] not in seen_media:
                    seen_media.add(med["local_media_id"])
                    aggregated_media.append(copy.deepcopy(med))

        # Promotion from primary observation
        promotion = copy.deepcopy(items[0]["promotion"])

        # Deduplication record
        deduplication = {
            "method": dedup_method,
            "confidence": 1.0,
            "review_required": False,
            "evidence_observation_ids": evidence_ids,
        }

        # Aggregate uncertainties (deduplicate by code and field)
        seen_unc = set()
        aggregated_unc = []
        for item in items:
            for unc in item.get("uncertainty", []):
                key_unc = (unc["code"], unc["field"])
                if key_unc not in seen_unc:
                    seen_unc.add(key_unc)
                    aggregated_unc.append(copy.deepcopy(unc))

        canonical_post = {
            "local_post_id": local_post_id,
            "platform_post_id": platform_post_id,
            "canonical_permalink": canon_permalink,
            "observation_ids": evidence_ids,
            "authors": aggregated_authors,
            "relationships": aggregated_rels,
            "media": aggregated_media,
            "promotion": promotion,
            "visible_text": visible_text,
            "deduplication": deduplication,
            "uncertainty": aggregated_unc,
        }
        output.append(canonical_post)

    return sorted(output, key=lambda item: item["local_post_id"])
