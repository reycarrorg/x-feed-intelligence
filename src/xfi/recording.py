"""Bounded recording preflight and Apple Vision ingestion."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .canonical import digest
from .errors import XFIError

MAX_FILE_BYTES = 2_147_483_648
MAX_DURATION_SECONDS = 1_800
MAX_DIMENSION_PIXELS = 7_680 * 4_320
MAX_CANDIDATES = 250
SUPPORTED_CODECS = {"avc1", "hvc1", "hev1", "mp4v", "ap4h", "ap4x"}


def _run(helper: Path, arguments: list[str], timeout: int = 120) -> dict:
    try:
        result = subprocess.run([str(helper), *arguments], capture_output=True, check=False, timeout=timeout, env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
    except (OSError, subprocess.TimeoutExpired):
        raise XFIError("PLATFORM_HELPER_UNAVAILABLE") from None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise XFIError("NATIVE_RECORDING_FAILURE") from None
    if result.returncode != 0 or value.get("status") != "OK":
        raise XFIError(value.get("code", "NATIVE_RECORDING_FAILURE"))
    return value


def find_helper(explicit: Path | None = None) -> Path:
    if sys.platform != "darwin":
        raise XFIError("PLATFORM_UNAVAILABLE_APPLE_VISION")
    path = explicit or (Path(os.environ["XFI_RECORDING_HELPER"]) if "XFI_RECORDING_HELPER" in os.environ else Path(__file__).resolve().parents[2] / "build" / "native" / "xfi-recording-helper")
    if not path.is_file() or not os.access(path, os.X_OK):
        raise XFIError("PLATFORM_HELPER_UNAVAILABLE")
    return path.resolve()


def preflight(path: Path, crop: tuple[int, int, int, int], *, helper: Path | None = None, interval_ms: int = 1_000) -> dict:
    try:
        metadata = path.lstat()
    except OSError:
        raise XFIError("RECORDING_FILE_REJECTED") from None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise XFIError("RECORDING_FILE_REJECTED")
    if metadata.st_size <= 0 or metadata.st_size > MAX_FILE_BYTES:
        raise XFIError("RECORDING_FILE_LIMIT")
    if not isinstance(interval_ms, int) or isinstance(interval_ms, bool) or interval_ms <= 0 or interval_ms > MAX_DURATION_SECONDS * 1000:
        raise XFIError("RECORDING_INTERVAL_REJECTED")
    source = path.resolve()
    if source.suffix.lower() not in {".mov", ".mp4", ".m4v"}:
        raise XFIError("RECORDING_CONTAINER_REJECTED")
    info = _run(find_helper(helper), ["metadata", str(source)])
    x, y, width, height = crop
    if min(x, y) < 0 or min(width, height) <= 0 or x + width > info["width"] or y + height > info["height"]:
        raise XFIError("CROP_OUT_OF_BOUNDS")
    if info["file_bytes"] <= 0 or info["file_bytes"] > MAX_FILE_BYTES:
        raise XFIError("RECORDING_FILE_LIMIT")
    if info["duration_seconds"] <= 0 or info["duration_seconds"] > MAX_DURATION_SECONDS:
        raise XFIError("RECORDING_DURATION_LIMIT")
    if info["width"] * info["height"] > MAX_DIMENSION_PIXELS:
        raise XFIError("RECORDING_DIMENSION_LIMIT")
    if info["codec"] not in SUPPORTED_CODECS:
        raise XFIError("RECORDING_CODEC_REJECTED")
    candidate_count = int((info["duration_seconds"] * 1000 + interval_ms - 1) // interval_ms)
    if candidate_count > MAX_CANDIDATES:
        raise XFIError("RECORDING_CANDIDATE_LIMIT")
    required_temp = width * height * 4
    if shutil.disk_usage(source.parent).free < required_temp * 2:
        raise XFIError("RECORDING_DISK_LIMIT")
    return {**info, "source_path": str(source), "crop_xywh": list(crop), "candidate_frame_limit": MAX_CANDIDATES, "candidate_frame_count": candidate_count, "worker_limit": 1, "raw_recording_copied": False, "derived_files_retained": False}


def ingest(path: Path, crop: tuple[int, int, int, int], *, helper: Path | None = None, interval_ms: int = 1_000, synthetic: bool = False) -> dict:
    helper_path = find_helper(helper)
    info = preflight(path, crop, helper=helper_path, interval_ms=interval_ms)
    output = _run(helper_path, ["ocr", str(path.resolve()), *map(str, crop), str(interval_ms)], timeout=300)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    session_id = "synthetic-recording-native-001" if synthetic else "recording-" + now.replace(":", "").replace("-", "")
    observations = []
    for index, frame in enumerate(output["frames"]):
        lines = [item for item in frame["text"] if item.get("text")]
        text = "\n".join(item["text"] for item in lines) or None
        confidence = sum(float(item["confidence"]) for item in lines) / len(lines) if lines else 0.0
        promoted = bool(text and "promoted" in text.lower())
        ambiguous = not text or bool(text and "review required" in text.lower())
        author_label = lines[0]["text"] if lines else "unknown"
        author_id = "ocr-author-" + hashlib.sha256(author_label.casefold().encode()).hexdigest()[:12]
        synthetic_identity = None
        if synthetic and text:
            identity_by_text = {
                "deterministic local workshop on day 7": "shared-source-001",
                "useful context quoting the workshop": "shared-quote-001",
                "invented notebook offer": "shared-promoted-001",
                "partial evidence": "shared-ambiguous-001",
            }
            synthetic_identity = next((identity for marker, identity in identity_by_text.items() if marker in text.casefold()), None)
        provenance_id = f"{session_id}-provenance-{index:03d}"
        is_quote = synthetic_identity == "shared-quote-001"
        relationships = [{"kind": "quotes", "source_local_post_id": "synthetic-source-shared-source-001", "source_platform_post_id": "shared-source-001", "confidence": confidence, "provenance_ids": [provenance_id]}] if is_quote else []
        observations.append({
            "observation_id": f"{session_id}-observation-{index:03d}", "session_id": session_id, "appearance_index": index, "top_level": True, "visibility_ratio": 1.0, "document_visible": True,
            "platform_post_id": synthetic_identity, "canonical_permalink": None, "visible_text": text, "displayed_timestamp": "recording-visible-card",
            "authors": [{"local_author_id": author_id, "platform_author_id": None, "display_name": author_label if lines else None, "handle": None, "role": "quoting" if is_quote else "original", "identity_confidence": confidence, "uncertainty_codes": [] if lines else ["OCR_AUTHOR_UNREADABLE"]}],
            "relationships": relationships, "media": [], "promotion": {"status": "promoted" if promoted else ("ambiguous" if ambiguous else "organic"), "evidence": ["visible_label"] if promoted else (["layout_marker"] if ambiguous else ["none"]), "confidence": confidence},
            "provenance": [{"provenance_id": provenance_id, "modality": "synthetic_recording" if synthetic else "manual", "collector_version": "recording-ingest-1", "parser_or_ocr_version": "apple-vision-platform", "field": "visible_text", "observed_at": now, "video_time_ms": frame["video_time_ms"], "crop_xywh": list(crop), "confidence": confidence}],
            "uncertainty": [] if not ambiguous else [{"code": "OCR_PARTIAL", "field": "visible_text", "severity": "blocking", "requires_review": True, "safe_detail": "OCR evidence requires human review."}],
            "input_location": {"viewport_time_ms": None, "video_time_ms": frame["video_time_ms"], "crop_xywh": list(crop)},
        })
    envelope = {"schema_version": "1.0.0", "session": {"session_id": session_id, "schema_version": "1.0.0", "source": "synthetic_recording" if synthetic else "user_supplied_recording", "started_at": now, "ended_at": now, "origin": None, "collector_version": "recording-ingest-1", "privacy_profile": "default_local", "limits": {"max_candidates": 250, "max_duration_seconds": 1800, "max_packet_bytes": 5242880}}, "observations": observations, "collection_events": [{"event_code": "SESSION_STARTED", "at": now, "safe_detail_code": None}, {"event_code": "STOPPED_USER", "at": now, "safe_detail_code": None}], "content_digest": ""}
    envelope["content_digest"] = digest(envelope)
    return {"preflight": info, "ocr": {"engine": output["ocr_engine"], "worker_count": output["worker_count"], "candidate_frame_count": output["candidate_frame_count"]}, "envelope": envelope}
