"""Synthetic browser-harness safety preflight and promotion guard."""

from __future__ import annotations

import json
import os
from pathlib import Path

FORBIDDEN_ORIGIN_VALUES = ("https://fixture.example.invalid", "TEST ONLY", "NON-DISTRIBUTABLE")
FORBIDDEN_BUNDLE_PATHS = ("manifest.synthetic-test-only.json", "synthetic-harness.js", "fixtures/synthetic/")


def promotion_safe(manifest: dict, bundle_paths: list[str]) -> bool:
    rendered = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return not any(value in rendered for value in FORBIDDEN_ORIGIN_VALUES) and not any(forbidden in path for path in bundle_paths for forbidden in FORBIDDEN_BUNDLE_PATHS)


def browser_runtime_preflight() -> dict:
    explicit = os.environ.get("XFI_REVIEWED_ISOLATED_BROWSER")
    if explicit and Path(explicit).is_file() and os.access(explicit, os.X_OK):
        return {"status": "REVIEWED_BROWSER_DECLARED", "executable": str(Path(explicit).resolve()), "execution_authorized": False, "reason": "Declaration alone does not satisfy dependency review or authorize execution."}
    return {"status": "BROWSER_RUNTIME_UNAVAILABLE", "executable": None, "execution_authorized": False, "reason": "No reviewed isolated MV3 browser runtime is present; no browser was downloaded or ordinary profile used."}

