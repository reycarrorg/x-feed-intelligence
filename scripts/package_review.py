#!/usr/bin/env python3
"""Build and verify the deterministic private production-MVP source package."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXED_TIME = (2026, 9, 12, 0, 0, 0)
BASE_FILES = ["README.md", "LICENSE.md", "NOTICE", "THIRD_PARTY_NOTICES.md", "DEPENDENCIES.lock.json", "docs/gate2/PACKAGE_BOUNDARY.md"]
GLOBS = ["schemas/v1/*.json", "src/xfi/*.py", "native/recording-helper/main.swift", "scripts/build_recording_helper.sh"]
EXCLUDED = {"src/xfi/browser.py", "sbom/cyclonedx.cdx.json"}
FORBIDDEN_BYTES = [b"https://fixture.example.invalid", b"TEST ONLY", b"NON-DISTRIBUTABLE"]


def package_files() -> list[Path]:
    paths = [ROOT / item for item in BASE_FILES]
    for pattern in GLOBS:
        paths.extend(ROOT.glob(pattern))
    # WindowsPath ordering is case-insensitive; sort by portable archive names.
    return sorted(
        {path for path in paths if path.relative_to(ROOT).as_posix() not in EXCLUDED},
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )


def package_entries(paths: list[Path]) -> list[tuple[str, bytes, bool]]:
    entries = []
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        # All package inputs are UTF-8 text. Normalize checkout-specific line
        # endings before hashing and packaging so Windows and Unix agree.
        data = path.read_text(encoding="utf-8").encode("utf-8")
        if relative == "schemas/v1/session.schema.json":
            schema = json.loads(data)
            schema["title"] = "Recording-only packaged collection session v1"
            schema["description"] = "Deterministic stricter package projection; the immutable repository schema remains authoritative."
            schema["properties"]["source"]["enum"] = ["synthetic_recording", "user_supplied_recording"]
            schema["properties"]["origin"]["enum"] = [None]
            schema["oneOf"] = [branch for branch in schema["oneOf"] if branch["properties"]["source"]["const"] != "synthetic_dom"]
            data = (json.dumps(schema, indent=2) + "\n").encode()
        entries.append((relative, data, bool(path.stat().st_mode & stat.S_IXUSR)))
    return entries


def source_digest(entries: list[tuple[str, bytes, bool]]) -> str:
    h = hashlib.sha256()
    for relative_name, data, _executable in entries:
        relative = relative_name.encode()
        h.update(len(relative).to_bytes(4, "big")); h.update(relative)
        h.update(len(data).to_bytes(8, "big")); h.update(data)
    return h.hexdigest()


def expected_sbom(entries: list[tuple[str, bytes, bool]]) -> dict:
    sbom = json.loads((ROOT / "sbom/cyclonedx.cdx.json").read_text())
    sbom["metadata"]["component"]["hashes"][0]["content"] = source_digest(entries)
    return sbom


def load_sbom() -> dict:
    return json.loads((ROOT / "sbom/cyclonedx.cdx.json").read_text())


def check_inputs(paths: list[Path], entries: list[tuple[str, bytes, bool]], sbom: dict) -> None:
    lock = json.loads((ROOT / "DEPENDENCIES.lock.json").read_text())
    if lock["product_dependencies"] != [] or [item.get("name") for item in lock["ci_dependencies"]] != ["actions/checkout", "actions/setup-node"]:
        raise SystemExit("dependency lock scope mismatch")
    if [item.get("name") for item in lock.get("extension_dependencies", [])] != ["WXT", "TypeScript", "@types/chrome", "Vitest", "Happy DOM"]:
        raise SystemExit("extension dependency inventory mismatch")
    if [item.get("name") for item in lock.get("test_dependencies", [])] != ["playwright-core", "Chrome for Testing"]:
        raise SystemExit("test-only browser dependency inventory mismatch")
    if sbom["metadata"]["component"]["hashes"][0]["content"] != source_digest(entries):
        raise SystemExit("SBOM source digest mismatch; run --update-sbom")
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"unsafe package input: {path.relative_to(ROOT)}")
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(("harness/", "fixtures/")) or relative == "src/xfi/browser.py":
            raise SystemExit(f"test capability leaked into package: {relative}")
    for relative, data, _executable in entries:
        if any(marker in data for marker in FORBIDDEN_BYTES):
            raise SystemExit(f"test marker leaked into package: {relative}")
    prohibited_names = {"package.json", ".npmrc", "pnpm-lock.yaml"}
    if any(Path(relative).name in prohibited_names or "node_modules" in Path(relative).parts or "browser-runtime" in relative for relative, _data, _executable in entries):
        raise SystemExit("test-only browser stack leaked into package")
    proposal = json.loads((ROOT / "contracts/v1/manifest.proposal.json").read_text())
    if proposal.get("permissions") != ["storage", "scripting"] or proposal.get("optional_host_permissions") != ["https://x.com/*"] or "host_permissions" in proposal:
        raise SystemExit("static production proposal permission drift")


def build(destination: Path, *, replace: bool = False) -> dict:
    paths = package_files()
    entries = package_entries(paths)
    sbom = load_sbom()
    check_inputs(paths, entries, sbom)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not replace: raise SystemExit("package destination exists; choose a new path or pass --replace")
        destination.unlink()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, data, executable in entries:
            info = zipfile.ZipInfo("x-feed-intelligence/" + relative, FIXED_TIME)
            info.external_attr = ((0o755 if executable else 0o644) & 0xFFFF) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
        info = zipfile.ZipInfo("x-feed-intelligence/sbom/cyclonedx.cdx.json", FIXED_TIME)
        info.external_attr = (0o644 & 0xFFFF) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, (json.dumps(sbom, indent=2) + "\n").encode())
    value = hashlib.sha256(destination.read_bytes()).hexdigest()
    return {"path": str(destination), "sha256": value, "file_count": len(entries) + 1, "source_digest": source_digest(entries), "product_dependency_count": 0, "ci_dependency_count": 2}


def verify_reproducible() -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        one, two = Path(temporary) / "one.zip", Path(temporary) / "two.zip"
        first, second = build(one), build(two)
        if first["sha256"] != second["sha256"]:
            raise SystemExit("package is not reproducible")
        with zipfile.ZipFile(one) as archive:
            names = archive.namelist()
            if any("harness" in name or "fixture" in name or name.endswith("browser.py") or name.endswith(("package.json", "pnpm-lock.yaml", ".npmrc")) or "node_modules" in name or "browser-runtime" in name for name in names):
                raise SystemExit("promotion guard failed")
        return {**first, "path": "temporary verification artifact", "reproducible": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "dist/private-review/xfi-gate2-production-mvp.zip")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--update-sbom", action="store_true")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    paths = package_files()
    entries = package_entries(paths)
    if args.update_sbom:
        value = expected_sbom(entries)
        (ROOT / "sbom/cyclonedx.cdx.json").write_text(json.dumps(value, indent=2) + "\n")
        print(json.dumps({"status": "SBOM_UPDATED", "source_digest": value["metadata"]["component"]["hashes"][0]["content"]}, sort_keys=True))
        return 0
    result = verify_reproducible() if args.check else build(args.output.resolve(), replace=args.replace)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
