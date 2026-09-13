# Roadmap

## Gate 0 — Research and platform decision

**Complete on `research/platform-reuse-gate`; pending review and merge.**

- Revalidated the private Analyze Twitter Feed chat as untrusted product evidence without copying its post corpus or opening its attachments.
- Compared recording/OCR, passive WebExtension, browser automation, private web interfaces, official API, native capture, local CLI, and hybrid architectures.
- Inspected candidate upstream versions, maintenance, permissions, security posture, licenses, and distribution constraints.
- Defined account-risk, privacy, prompt-injection, activation, deactivation, and hard-stop boundaries.
- Accepted ADR 0001 for Gate 1 planning: recording-first local hybrid, with passive extension live use separately gated.
- Added deterministic repository, Markdown-link, footnote, matrix-arithmetic, and sensitive-artifact validation.

## Gate 1 — Threat model, schemas, and evaluation contracts

**Next; not started by Gate 0.** Exact exit criteria are in the [activation and synthetic-test plan](research/activation-data-flow-and-synthetic-tests.md).

- Define post, author, media, provenance, deduplication, classification, verification, and recommendation schemas.
- Define prompt-injection and sensitive-data redaction contracts.
- Specify deterministic classifier evaluation and human-review thresholds.
- Specify browser lifecycle, stop conditions, local retention, deletion, and export.
- Build synthetic fixtures and acceptance tests.

## Gate 2 — Production MVP on synthetic and supplied data

**Not started.**

- Build local screen-recording ingestion and candidate-frame extraction.
- Build passive origin-scoped browser capture against synthetic fixtures.
- Produce a normalized local analysis packet and shareable report.
- Add deterministic tests, CI, packaging, and privacy/security validation.
- Do not access an authenticated X account.

## Gate 3 — User-supervised acceptance

**Not authorized or started.** This is the earliest gate that may include an explicitly approved live X session.

- Install a review build only with user approval.
- Test passive capture on an ordinary X feed session with the user signed in.
- Stop on challenges, rate limits, or unexpected permissions.
- Compare captured-post count and report fidelity against a screen recording.

## Gate 4 — Optional public release

**Not authorized or started.**

Requires explicit public-release authorization, dependency-license verification, removal of real feed data, reproducible packages, checksums, and documented live acceptance limits.
