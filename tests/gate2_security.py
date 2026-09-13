#!/usr/bin/env python3
"""Direct deterministic security/privacy coverage for the Gate 2 change."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "9f961e5b9758884bcb5aff6ad2b8e85ca1bf0396"


def changed_files() -> list[Path]:
    committed = subprocess.run(["git", "diff", "--name-only", BASE, "--"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
    return sorted({ROOT / name for name in [*committed, *untracked] if name})


def main() -> int:
    errors: list[str] = []
    files = changed_files()
    source_prefixes = (".github/", "src/", "native/", "harness/", "scripts/", "tests/")
    source_names = {"DEPENDENCIES.lock.json", "THIRD_PARTY_NOTICES.md", "sbom/cyclonedx.cdx.json", "package.json", "pnpm-lock.yaml", ".npmrc"}
    covered = [path for path in files if path.relative_to(ROOT).as_posix().startswith(source_prefixes) or path.relative_to(ROOT).as_posix() in source_names]
    if not covered:
        errors.append("changed source/build/packaging inventory is empty")
    forbidden_python = re.compile(r"(?:shell\s*=\s*True|\bos\.system\s*\(|\beval\s*\(|\bexec\s*\(|urllib\.request|http\.client|(?:from|import)\s+requests)")
    forbidden_shell = re.compile(r"\b(?:curl|wget|npm|npx|pip|brew)\b")
    forbidden_harness = re.compile(r"(?:fetch\s*\(|new\s+XMLHttpRequest|new\s+WebSocket|\.cookie\b|\blocalStorage\b|\bsessionStorage\b|\.click\s*\(|\.scroll(?:To|By|IntoView)?\s*\(|URLSession)")
    local_path = re.compile("/" + "Users" + "/|[A-Za-z]:\\\\" + "Users" + "\\\\")
    for path in covered:
        relative = path.relative_to(ROOT).as_posix()
        if not path.is_file() or path.is_symlink():
            errors.append(f"missing or symlinked reviewed file: {relative}")
            continue
        if path.suffix.lower() in {".mov", ".mp4", ".sqlite", ".db", ".pem", ".key", ".har"}:
            errors.append(f"private/binary artifact in review scope: {relative}")
            continue
        if path.suffix.lower() not in {".py", ".swift", ".js", ".sh", ".json", ".yml", ".yaml", ".md", ".html"}:
            continue
        text = path.read_text(encoding="utf-8")
        if local_path.search(text):
            errors.append(f"local absolute path in {relative}")
        if path.suffix == ".py" and path.name != "gate2_security.py" and forbidden_python.search(text):
            errors.append(f"unsafe Python capability in {relative}")
        if path.suffix == ".sh" and forbidden_shell.search(text):
            errors.append(f"download/package-manager command in {relative}")
        if relative.startswith(("harness/", "native/")) and forbidden_harness.search(text):
            errors.append(f"forbidden browser/network/input capability in {relative}")
    proposal = json.loads((ROOT / "contracts/v1/manifest.proposal.json").read_text())
    synthetic = json.loads((ROOT / "harness/synthetic/manifest.json").read_text())
    if proposal.get("permissions") != ["storage", "scripting"] or proposal.get("optional_host_permissions") != ["https://x.com/*"] or "host_permissions" in proposal:
        errors.append("production proposal capability drift")
    if synthetic.get("permissions") != ["storage"] or synthetic.get("host_permissions") != ["https://fixture.example.invalid/*"] or "optional_host_permissions" in synthetic:
        errors.append("synthetic manifest capability drift")
    lock = json.loads((ROOT / "DEPENDENCIES.lock.json").read_text())
    if lock.get("product_dependencies") != [] or [item.get("name") for item in lock.get("test_dependencies", [])] != ["playwright-core", "Chrome for Testing"]:
        errors.append("test dependency adoption scope drift")
    if lock["test_dependencies"][0].get("sha256") != "208593d4e1bcd8f8fe5f869cad1cc332dc7f1d70dc1d58c102dc3ac36e30f26c" or lock["test_dependencies"][1].get("archive_sha256") != "1f701ef60757c63c6ccf98afaf28291dd0c8d1457d3d738e81fd62201c230ad0":
        errors.append("test dependency artifact integrity drift")
    revision = lock["ci_dependencies"][0]["revision"]
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    if workflow.count("actions/checkout@" + revision) != 2 or "persist-credentials: false" not in workflow:
        errors.append("CI lock/revision or credential persistence drift")
    if errors:
        for error in errors: print("SECURITY REVIEW ERROR: " + error, file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "changed_files": len(files), "reviewed_source_build_packaging_files": len(covered), "critical_findings": 0, "high_findings": 0, "network_product_dependencies": 0, "subagents": 0}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
