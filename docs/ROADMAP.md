# Roadmap

## Gate 0 — Research and platform decision

**Complete and merged to `main` in merge commit `9124a7b`.**

- Revalidated the private Analyze Twitter Feed chat as untrusted product evidence without copying its post corpus or opening its attachments.
- Compared recording/OCR, passive WebExtension, browser automation, private web interfaces, official API, native capture, local CLI, and hybrid architectures.
- Inspected candidate upstream versions, maintenance, permissions, security posture, licenses, and distribution constraints.
- Defined account-risk, privacy, prompt-injection, activation, deactivation, and hard-stop boundaries.
- Accepted ADR 0001 for Gate 1 planning: recording-first local hybrid, with passive extension live use separately gated.
- Added deterministic repository, Markdown-link, footnote, matrix-arithmetic, and sensitive-artifact validation.

## Gate 1 — Threat model, schemas, and evaluation contracts

**Complete and merged.** The [Gate 1 index](gate1/README.md) maps every exit criterion to its contract and deterministic evidence.

- Define post, author, media, provenance, deduplication, classification, verification, and recommendation schemas.
- Define prompt-injection and sensitive-data redaction contracts.
- Specify deterministic classifier evaluation and human-review thresholds.
- Specify browser lifecycle, stop conditions, local retention, deletion, and export.
- Build synthetic fixtures and acceptance tests.

Gate 1 uses only authored synthetic data and standard-library validation. Passing it proves contract consistency, not a production collector, OCR pipeline, database, live extension, or package.

## Gate 2 — Production MVP on synthetic and supplied data

**Complete and merged.**

- Build local screen-recording ingestion and candidate-frame extraction.
- Build passive origin-scoped browser capture against synthetic fixtures.
- Produce a normalized local analysis packet and shareable report.
- Add deterministic tests, CI, packaging, and privacy/security validation.
- Do not access an authenticated X account.

The reviewed work packages and exact entry criteria are in the [Gate 2 work breakdown](gate1/GATE2_WORK_BREAKDOWN.md).

## Gate 3 — User-supervised acceptance

**Review extension implemented on `gate3/hybrid-extension`; authenticated acceptance not started.** The branch adds the separately versioned live-DOM contract and a buildable manual-scroll Manifest V3 collector. Static, unit, compile, generated-manifest, and existing-core integration checks are complete locally. Installation and live authenticated testing remain separate user-supervised gates.

- Install a review build only with user approval.
- Test passive capture on an ordinary X feed session with the user signed in.
- Stop on challenges, rate limits, or unexpected permissions.
- Compare captured-post count and report fidelity against a screen recording.
- Do not add automatic scrolling, private X interfaces, network interception, or account actions.

## Gate 4 — Optional public release

**Not authorized or started.**

Requires explicit public-release authorization, dependency-license verification, removal of real feed data, reproducible packages, checksums, and documented live acceptance limits.
