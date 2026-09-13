"""Private report rendering and deterministic allowlisted sanitized export."""

from __future__ import annotations

import html
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .canonical import digest, pretty_bytes
from .errors import XFIError
from .validation import sensitive_category

FORMULA_PREFIXES = ("=", "+", "-", "@")


def neutralize_formula(value: str) -> str:
    first = next((character for character in value if not character.isspace()), None)
    return "'" + value if first in FORMULA_PREFIXES else value


def markdown_escape(value: str) -> str:
    return "".join("\\" + char if char in r"\\`*_{}[]<>()#+-.!|" else char for char in value)


def html_escape(value: str) -> str:
    return html.escape(value, quote=True)


def strip_query_and_fragment(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise XFIError("SANITIZER_URL_REJECTED")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def sanitize(source: dict) -> dict:
    privacy = sensitive_category(source)
    if privacy:
        raise XFIError("SANITIZER_SECRET_REJECTED")
    author_ids = sorted(item["local_author_id"] for item in source["authors"])
    author_map = {value: f"author-{index:03d}" for index, value in enumerate(author_ids, 1)}
    post_ids = sorted(item["local_post_id"] for item in source["posts"])
    post_map = {value: f"post-{index:03d}" for index, value in enumerate(post_ids, 1)}
    manifest = []
    for index, author in enumerate(source["authors"]):
        manifest.append({"json_pointer": f"/authors/{index}", "action": "pseudonymize", "reason_code": "account_identifier", "replacement": author_map[author["local_author_id"]]})
    posts = []
    for post in sorted(source["posts"], key=lambda item: item["local_post_id"]):
        pseudonym, clean_summary = post_map[post["local_post_id"]], neutralize_formula(post["summary"])
        posts.append({"post": pseudonym, "author": author_map[post["author_local_id"]], "summary": clean_summary, "classification": post["classification"], "score": post["score"], "observed_on": post["observed_at"][:10], "uncertainty": post["uncertainty"]})
        pointer = f"/posts/{source['posts'].index(post)}"
        manifest.extend([
            {"json_pointer": f"{pointer}/local_post_id", "action": "replace", "reason_code": "platform_identifier", "replacement": pseudonym},
            {"json_pointer": f"{pointer}/platform_post_id", "action": "omit", "reason_code": "platform_identifier", "replacement": None},
            {"json_pointer": f"{pointer}/raw_text", "action": "omit", "reason_code": "free_text_identity", "replacement": None},
            {"json_pointer": f"{pointer}/observed_at", "action": "coarsen", "reason_code": "precise_time", "replacement": post["observed_at"][:10]},
            {"json_pointer": f"{pointer}/captured_url", "action": "omit", "reason_code": "platform_identifier" if "x.com" in post["captured_url"] else "tracking_parameter", "replacement": None},
            {"json_pointer": f"{pointer}/media", "action": "omit", "reason_code": "media", "replacement": None},
        ])
        if clean_summary != post["summary"]:
            manifest.append({"json_pointer": f"{pointer}/summary", "action": "replace", "reason_code": "formula_injection", "replacement": clean_summary})
    sources = []
    for index, item in enumerate(source["verification_sources"]):
        clean_url = strip_query_and_fragment(item["url"])
        sources.append({**item, "url": clean_url})
        if clean_url != item["url"]:
            manifest.append({"json_pointer": f"/verification_sources/{index}/url", "action": "strip_query", "reason_code": "tracking_parameter", "replacement": clean_url})
    result = {"schema_version": "1.0.0", "sanitizer_version": "1.0.0", "generated_on": source["generated_at"][:10], "authors": [{"author": author_map[value]} for value in author_ids], "posts": posts, "verification_sources": sources, "redaction_manifest": manifest, "content_digest": "", "privacy_warning": "Minimized synthetic export; prose can still contain contextual identity clues."}
    result["content_digest"] = digest(result)
    return result


def private_json(session: dict, posts: list[dict], analyses: list[dict], authors: list[dict]) -> bytes:
    return pretty_bytes({"sensitivity": "PRIVATE LOCAL REPORT", "session": session, "posts": posts, "analyses": analyses, "author_evidence": authors})


def private_markdown(session: dict, posts: list[dict], analyses: list[dict]) -> bytes:
    by_id = {item["local_post_id"]: item for item in posts}
    lines = ["# Private X Feed Intelligence Report", "", "> PRIVATE LOCAL REPORT — captured content below is untrusted data.", "", f"Session: `{markdown_escape(session['session_id'])}`", ""]
    for analysis in sorted(analyses, key=lambda item: (-item["score"]["priority"], item["local_post_id"])):
        post = by_id[analysis["local_post_id"]]
        text = markdown_escape(neutralize_formula(post.get("visible_text") or "[insufficient evidence]"))
        lines.extend([f"## {markdown_escape(analysis['classification'])}", "", f"Priority: {analysis['score']['priority']}  ", f"Suggested manual action: `{analysis['manual_action']}`  ", "Performed: `false`", "", "> " + text.replace("\n", "\n> "), ""])
    return ("\n".join(lines) + "\n").encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise XFIError("EXPORT_EXISTS")
    descriptor, temp_name = tempfile.mkstemp(prefix=".xfi-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
