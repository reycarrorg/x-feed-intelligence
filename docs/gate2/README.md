# Gate 2 Production MVP Implementation and Evidence

## Status and boundaries

Gate 2 is implemented on `gate2/production-mvp` from required base `9f961e5b9758884bcb5aff6ad2b8e85ca1bf0396`. This is a private, unmerged review candidate. It uses only authored synthetic fixtures and platform facilities. No user-supplied recording was present, no live X origin was opened, no authenticated profile or ordinary browser profile was used, and no remote model, API, telemetry, sync, paid resource, account action, publication, signing, notarization, merge, or deployment was performed.

The merged v1 schemas, contracts, and frozen synthetic fixture manifest remain unchanged. Gate 2 adds one separate authored shared corpus under `fixtures/gate2` without altering the Gate 1 fixture set.

## Architecture delivered

- `src/xfi/validation.py` implements byte, depth, version, schema, semantic, digest, duplicate-ID, reference, secret, private-surface, and resource validation before persistence. Errors expose category codes only.
- `src/xfi/canonical.py` implements canonical UTF-8 JSON, SHA-256 digests, permalink normalization, relation-aware author selection, conflict gates, conservative temporal review eligibility, and deterministic deduplication.
- `src/xfi/store.py` owns SQLite files, migrations, application/schema identity, foreign keys, secure deletion configuration, WAL, idempotent transactional imports, parameterized persistence, auditable review decisions, export/backup inventory, online backup, isolated restore, scoped temporary cleanup, checkpointing, purge verification, and honest vacuum outcomes.
- `src/xfi/analysis.py` implements deterministic organic classification, five-factor scores, manual-only recommendations, verification records, author aggregation, follow/watchlist gates, and a typed capability-free model handoff. Captured content never gains authority.
- `src/xfi/render.py` creates distinct private JSON/Markdown artifacts, contextually escapes Markdown/HTML, neutralizes spreadsheet formulas, applies the allowlisted sanitizer, reconciles redaction entries, and writes through a flushed atomic temporary file without silent overwrite.
- `native/recording-helper/main.swift` uses AVFoundation and Apple Vision sequentially. `src/xfi/recording.py` requires an explicit crop, validates file/container/codec/duration/dimensions/candidate/disk limits, leaves the source unchanged, keeps frames in memory, records field provenance/confidence, and returns review-required ambiguity honestly.
- `harness/synthetic` is a separate marked non-distributable MV3 harness. It implements explicit user lifecycle messages, isolated visible-card parsing, IntersectionObserver collection at the inclusive 0.50 boundary, MutationObserver updates and virtualized-node identity changes, queue/duration/packet/ambiguity limits, all 23 normative hard stops, synchronous teardown, explicit export, and all-zero forbidden-effect accounting.
- `scripts/package_review.py` builds a deterministic recording-only private source package. It mechanically narrows the packaged session schema, excludes every harness/test capability, enforces static production-proposal permissions, and embeds the matching CycloneDX SBOM.

The production extension proposal remains static and ungranted. The analyzer bridge remains explicit JSON export/import; there is no listener, native messaging, product localhost service, or automated input.

## Deterministic verification

`bash tests/check_repo.sh` runs the complete clean-checkout suite. On the measured Mac it passed:

- 9 frozen Gate 1 acceptance groups;
- 15 Gate 2 core/store/render tests;
- 5 browser-harness boundary tests;
- 2 Apple Vision recording tests;
- 2 shared-corpus integration tests;
- direct changed-file security/privacy coverage; and
- byte-identical two-build package verification.

The shared authored corpus produced 3 expected, 3 DOM-harness, and 3 recording canonical units. Both input paths measured unique precision `3/3 = 1.000000` and recall `3/3 = 1.000000`; unambiguous promotion separation was `2/2 = 1.000000`; the no-edge relationship oracle was `1/1 = 1.000000`. All 23 hard stops produced the exact error state with zero post-stop observations, observers, timers, or DOM references. Forbidden effects, secret echoes, and performed account actions were all zero. The frozen sanitizer still matched its golden bytes exactly with 16 reconciled redactions.

The synthetic browser data carries reserved-origin DOM provenance; recording data carries null-origin, video-time, crop, Apple Vision, and confidence provenance. OCR includes visible label text and can require review; the DOM harness preserves structured fixture identity. Those expected modality differences are retained rather than normalized away.

## Measured resources

Measurement command: `python3 scripts/measure_gate2.py`. Hardware/runtime: Apple M1, arm64, 16 GiB physical memory, macOS 27.0, Python 3.9.6, SQLite 3.54.0, Apple Swift 6.4.

| Measurement | Samples | Mean | Maximum |
| --- | ---: | ---: | ---: |
| Idle process CPU | 10 | 0.051949% | 0.070847% |
| Core validate/import/analyze wall time | 20 | 8.991473 ms | 18.768583 ms |
| Core CPU time | 20 | 6.372200 ms | 14.150000 ms |
| Capability-denied harness VM wall time | 10 | 12.642787 ms | 53.555541 ms |
| Four-frame Apple Vision recording run | 3 | 229.692528 ms | 244.142333 ms |

Core Python traced peak was 131,101 bytes; process maximum resident size was 18,907,136 bytes. Native child maximum resident size was 291,799,040 bytes. Recording used one worker and four candidate frames, within the exact one-worker and 250-candidate bounds. The idle mean is below the 2% target. These are measurements on the stated host and authored corpus, not universal performance claims.

## Dependency, SBOM, and package evidence

Product third-party component count is zero. Python standard library, platform SQLite, AVFoundation, Vision, and JavaScriptCore are environment facilities and are not redistributed. FFmpeg, WXT, Playwright, and a browser binary were not adopted, downloaded, or executed.

The existing CI-only `actions/checkout` dependency is pinned to v4.4.0 revision `11d5960a326750d5838078e36cf38b85af677262`, runs with `contents: read` and `persist-credentials: false`, is recorded in `DEPENDENCIES.lock.json`, and is excluded from the product package. Its official repository was active and unarchived; its official security-advisory list returned zero entries on 2026-09-12. That result is not proof of safety.

`sbom/cyclonedx.cdx.json` is CycloneDX 1.5 and records zero product dependencies plus the excluded CI-only action. Packaging refuses fixture origin values, test markers, synthetic harness paths, fixture trees, the browser preflight module, symlinks, permission drift, stale SBOM source hashes, and silent destination overwrite. The exact final package SHA-256 is recorded in the pull request after the final-head build.

## Honest limitations

- No user recording was supplied, so no real recording result is claimed.
- No reviewed isolated MV3 browser binary exists on the measured host. Harness logic executed only in a fresh JavaScriptCore context with `fetch`, XHR, WebSocket, document, browser storage, cookies, page-world, and input capabilities absent. Reserved-host loopback mapping and actual MV3 profile execution remain unavailable, not passed.
- The private package is recording-only and source-based. It contains no runnable extension, browser binary, precompiled native helper, signing identity, notarization ticket, or distribution claim.
- Primary-source verification records are supported, but automatic external verification is absent by design. Model handoff is optional, local-file-only, and has no tool or navigation capability.
- SQLite purge cannot promise cryptographic erasure from SSD remapping, snapshots, older backups, synchronized copies, or prior exports.
- Gate 2 synthetic success does not authorize Gate 3 or reduce the documented Terms/account-enforcement risk.
