# Roadmap

## Gate 0 — Research and platform decision

- Revalidate the existing Analyze Twitter Feed chat and its source claims.
- Compare video/OCR, passive WebExtension, browser automation, private web interfaces, official API, native application, and hybrid architectures.
- Inspect legitimate open-source components, licenses, maintenance, permissions, and security posture.
- Define account-risk and data-protection boundaries.
- Accept an architecture ADR.

## Gate 1 — Threat model, schemas, and evaluation contracts

- Define post, author, media, provenance, deduplication, classification, verification, and recommendation schemas.
- Define prompt-injection and sensitive-data redaction contracts.
- Specify deterministic classifier evaluation and human-review thresholds.
- Specify browser lifecycle, stop conditions, local retention, deletion, and export.
- Build synthetic fixtures and acceptance tests.

## Gate 2 — Production MVP on synthetic and supplied data

- Build local screen-recording ingestion and candidate-frame extraction.
- Build passive origin-scoped browser capture against synthetic fixtures.
- Produce a normalized local analysis packet and shareable report.
- Add deterministic tests, CI, packaging, and privacy/security validation.
- Do not access an authenticated X account.

## Gate 3 — User-supervised acceptance

- Install a review build only with user approval.
- Test passive capture on an ordinary X feed session with the user signed in.
- Stop on challenges, rate limits, or unexpected permissions.
- Compare captured-post count and report fidelity against a screen recording.

## Gate 4 — Optional public release

Requires explicit public-release authorization, dependency-license verification, removal of real feed data, reproducible packages, checksums, and documented live acceptance limits.

