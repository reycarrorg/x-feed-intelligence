#!/usr/bin/env python3
"""Fail closed on generated extension manifest or bundle capability drift."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "extension" / ".output" / "chrome-mv3"
MANIFEST = BUILD / "manifest.json"

if not MANIFEST.is_file():
    raise SystemExit("missing generated Chrome Manifest V3 build")

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
errors: list[str] = []

if manifest.get("manifest_version") != 3:
    errors.append("manifest is not MV3")
if manifest.get("optional_host_permissions") != ["https://x.com/*"]:
    errors.append("optional X origin permission drift")
if manifest.get("host_permissions"):
    errors.append("always-on host permission is forbidden")
if manifest.get("permissions"):
    errors.append(f"unexpected extension permissions: {manifest['permissions']}")
if manifest.get("background"):
    errors.append("background execution is forbidden")

scripts = manifest.get("content_scripts", [])
if len(scripts) != 1 or scripts[0].get("matches") != ["https://x.com/*"] or scripts[0].get("all_frames", False):
    errors.append("content script origin/frame boundary drift")

bundle = "\n".join(
    path.read_text(encoding="utf-8", errors="replace")
    for path in sorted(BUILD.rglob("*.js"))
)
for label, pattern in {
    "automatic scrolling": r"\b(?:scrollBy|scrollTo|scrollIntoView)\s*\(",
    "XHR": r"\bXMLHttpRequest\b",
    "web socket": r"\bWebSocket\b",
    "cookie access": r"\bdocument\.cookie\b",
    "network interception": r"\b(?:webRequest|declarativeNetRequest)\b",
}.items():
    if re.search(pattern, bundle, flags=re.IGNORECASE):
        errors.append(f"generated bundle contains forbidden {label} primitive")

if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)

print("Gate 3 generated manifest and bundle boundaries passed")
