#!/usr/bin/env python3
"""Deterministic documentation and repository-safety checks through Gate 1."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent.parent

REQUIRED = (
    "README.md",
    "LICENSE.md",
    "NOTICE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "docs/PROJECT_CHARTER.md",
    "docs/ROADMAP.md",
    "docs/research/RESEARCH_PLAN.md",
    "docs/research/EXISTING_CHAT_BASELINE.md",
    "docs/research/platform-and-reuse-deep-dive.md",
    "docs/research/reuse-matrix.md",
    "docs/research/x-account-and-policy-risk.md",
    "docs/research/report-methodology.md",
    "docs/research/activation-data-flow-and-synthetic-tests.md",
    "docs/adr/0001-platform-selection.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/gate1/README.md",
    "docs/gate1/THREAT_MODEL.md",
    "docs/gate1/ANALYSIS_CONTRACTS.md",
    "docs/gate1/RETENTION_AND_EXPORT.md",
    "docs/gate1/EXTENSION_LIFECYCLE.md",
    "docs/gate1/MODEL_HANDOFF.md",
    "docs/gate1/METRICS_AND_ORACLES.md",
    "docs/gate1/DEPENDENCY_AND_SBOM_PLAN.md",
    "docs/gate1/GATE2_WORK_BREAKDOWN.md",
    "docs/gate1/REVIEW_RECORD.md",
    "docs/gate1/POLICY_RECHECK.md",
)

FORBIDDEN_SUFFIXES = {
    ".mp4", ".mov", ".m4v", ".webm", ".sqlite", ".sqlite3", ".db",
    ".pem", ".key", ".p12", ".har",
}

REQUIRED_PHRASES = {
    "docs/adr/0001-platform-selection.md": (
        "Status: Accepted; implemented by the Gate 1 contract baseline",
        "No real-account access",
        "recording",
        "passive",
    ),
    "docs/research/report-methodology.md": (
        "High Signal",
        "Promising — Verify",
        "Community / Light Value",
        "Low Signal / Slop",
        "Scam / Manipulative / Unsafe",
        "Insufficient Information",
        "CONSIDER FOLLOWING AUTHOR",
        "Promoted cards",
    ),
    "docs/research/activation-data-flow-and-synthetic-tests.md": (
        "Gate 1 entry and exit criteria",
        "IntersectionObserver",
        "MutationObserver",
        "No real-account access",
    ),
    "docs/research/x-account-and-policy-risk.md": (
        "permanent suspension",
        "Synthetic-only through Gate 2",
        "Hard-stop states",
    ),
    "docs/gate1/THREAT_MODEL.md": (
        "Browser extension",
        "Recording selection",
        "SQLite database",
        "Model handoff",
        "Sanitized export",
        "Packaging",
    ),
    "docs/gate1/ANALYSIS_CONTRACTS.md": (
        "Deterministic deduplication",
        "Primary-source verification",
        "Prompt injection and tool authority",
        "Sensitive-data rejection",
        "Sanitized export",
    ),
    "docs/gate1/EXTENSION_LIFECYCLE.md": (
        "https://x.com/*",
        "PERMISSION_PROMPT",
        "CAPTURING",
        "Fail closed",
    ),
    "docs/gate1/GATE2_WORK_BREAKDOWN.md": (
        "synthetic and explicitly user-supplied data",
        "Live X access",
        "Gate 2 completion does not authorize Gate 3",
    ),
    "docs/gate1/REVIEW_RECORD.md": (
        "no security finding",
        "zero complete-canary echoes",
        "not proof of a production implementation",
        "Gate 2 is ready for review, not automatically activated",
    ),
    "docs/gate1/POLICY_RECHECK.md": (
        "did not open X",
        "No Gate 0 premise changed",
        "synthetic-only extension work",
        "before Gate 3",
    ),
}

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
FOOTNOTE_RE = re.compile(r"\[\^([^\]]+)\]")
FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]]+)\]:", re.MULTILINE)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def markdown_files() -> list[Path]:
    return sorted(path for path in ROOT.rglob("*.md") if ".git" not in path.parts)


def check_required(errors: list[str]) -> None:
    for relative in REQUIRED:
        path = ROOT / relative
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            fail(errors, f"missing or empty required file: {relative}")


def check_repository_artifacts(errors: list[str]) -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(ROOT)
        if path.suffix.lower() in FORBIDDEN_SUFFIXES or path.name == ".env":
            fail(errors, f"private capture, database, or credential-like file: {relative}")


def split_destination(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("<") and ">" in raw:
        return raw[1 : raw.index(">")]
    return raw.split(maxsplit=1)[0]


def check_links_and_footnotes(errors: list[str]) -> None:
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)

        destinations = [*LINK_RE.findall(text), *IMAGE_RE.findall(text)]
        for raw in destinations:
            destination = split_destination(raw)
            if not destination or destination.startswith("#"):
                continue
            parsed = urlparse(destination)
            if parsed.scheme:
                if parsed.scheme not in {"https", "mailto"}:
                    fail(errors, f"unsupported external link scheme in {relative}: {destination}")
                if parsed.scheme == "https" and not parsed.netloc:
                    fail(errors, f"invalid HTTPS link in {relative}: {destination}")
                continue

            target_text = unquote(destination.split("#", 1)[0])
            target = (path.parent / target_text).resolve()
            try:
                target.relative_to(ROOT)
            except ValueError:
                fail(errors, f"relative link escapes repository in {relative}: {destination}")
                continue
            if target_text and not target.exists():
                fail(errors, f"broken relative link in {relative}: {destination}")

        references = set(FOOTNOTE_RE.findall(text))
        definitions = set(FOOTNOTE_DEF_RE.findall(text))
        missing = sorted(references - definitions)
        unused = sorted(definitions - references)
        if missing:
            fail(errors, f"missing footnote definitions in {relative}: {', '.join(missing)}")
        if unused:
            fail(errors, f"unused footnote definitions in {relative}: {', '.join(unused)}")


def check_required_content(errors: list[str]) -> None:
    for relative, phrases in REQUIRED_PHRASES.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for phrase in phrases:
            if phrase not in text:
                fail(errors, f"required decision content missing from {relative}: {phrase}")


def check_sensitive_text(errors: list[str]) -> None:
    local_path = re.compile(r"(?:/Users/|[A-Za-z]:\\\\Users\\\\)\S+")
    real_post_url = re.compile(r"https://(?:www\.)?x\.com/[A-Za-z0-9_]+/status/[0-9]+")
    secret_assignment = re.compile(
        r"(?i)(?:auth[_-]?token|api[_-]?key|password|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9_./+-]{12,}"
    )
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT)
        if local_path.search(text):
            fail(errors, f"local absolute path found in {relative}")
        if real_post_url.search(text):
            fail(errors, f"real X post URL found in {relative}")
        if secret_assignment.search(text):
            fail(errors, f"credential-like assignment found in {relative}")


def check_decision_matrix(errors: list[str]) -> None:
    path = ROOT / "docs/research/platform-and-reuse-deep-dive.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    table = [line for line in lines if line.startswith("|")]
    header_index = next(
        (index for index, line in enumerate(table) if line.startswith("| Criterion | Weight |")),
        None,
    )
    if header_index is None:
        fail(errors, "weighted decision table not found")
        return
    rows = []
    for line in table[header_index + 2 :]:
        cells = [cell.strip().strip("*").strip("`") for cell in line.strip("|").split("|")]
        if not cells or cells[0] == "Weighted total / 500":
            totals = [int(cell) for cell in cells[2:]]
            break
        try:
            rows.append((int(cells[1]), [int(cell) for cell in cells[2:]]))
        except (ValueError, IndexError):
            break
    else:
        fail(errors, "weighted decision totals row not found")
        return

    if not rows:
        fail(errors, "weighted decision score rows not found")
        return
    calculated = [
        sum(weight * scores[column] for weight, scores in rows)
        for column in range(len(rows[0][1]))
    ]
    if calculated != totals:
        fail(errors, f"weighted decision totals mismatch: expected {calculated}, found {totals}")
    if sum(weight for weight, _ in rows) != 100:
        fail(errors, "weighted decision weights do not sum to 100")


def main() -> int:
    errors: list[str] = []
    check_required(errors)
    if not errors:
        check_repository_artifacts(errors)
        check_links_and_footnotes(errors)
        check_required_content(errors)
        check_sensitive_text(errors)
        check_decision_matrix(errors)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("documentation, decision, link, footnote, matrix, and safety checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
