#!/usr/bin/env python3
"""Fail closed on generated extension manifest or bundle capability drift."""

from __future__ import annotations

import json
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument("--browser", choices=("chrome", "firefox"), default="chrome")
args = parser.parse_args()
BUILD = ROOT / "extension" / ".output" / f"{args.browser}-mv3"
MANIFEST = BUILD / "manifest.json"

if not MANIFEST.is_file():
    raise SystemExit(f"missing generated {args.browser} Manifest V3 build")

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
if args.browser == "firefox":
    gecko = manifest.get("browser_specific_settings", {}).get("gecko", {})
    if gecko.get("id") != "{3bca689a-468a-4cd7-aa08-d61a8a83ed39}":
        errors.append("Firefox extension ID drift")
    if gecko.get("strict_min_version") != "140.0":
        errors.append("Firefox minimum version drift")
    if manifest.get("browser_specific_settings", {}).get("gecko_android", {}).get("strict_min_version") != "142.0":
        errors.append("Firefox Android minimum version drift")
    expected_data = ["websiteContent", "personallyIdentifyingInfo", "personalCommunications"]
    if gecko.get("data_collection_permissions") != {"required": expected_data}:
        errors.append("Firefox local-export data disclosure drift")
elif manifest.get("browser_specific_settings"):
    errors.append("Firefox-only settings leaked into Chrome manifest")

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

print(f"Gate 3 {args.browser} generated manifest and bundle boundaries passed")
