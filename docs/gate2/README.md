# Gate 2 Production MVP Implementation and Evidence

## Status and boundaries

Gate 2 is implemented on `gate2/production-mvp` from required base `9f961e5b9758884bcb5aff6ad2b8e85ca1bf0396`. This is a private, unmerged review candidate. It uses only authored synthetic fixtures and platform facilities. No user-supplied recording was present, no live X origin was opened, no authenticated profile or ordinary browser profile was used, and no remote model, API, telemetry, sync, paid resource, account action, publication, signing, notarization, merge, or deployment was performed.

The merged v1 schemas and frozen Gate 1 fixture corpus remain unchanged. During this repair pass, the separate test-only manifest was deliberately versioned from 0.1.0 to 0.2.0 and the browser boundary from 1.0.0 to 1.1.0 so the previously inert controls could be wired to a test-only service worker. That correction added no permission and no host: ordinary permissions remain exactly `storage`, and the only host remains `https://fixture.example.invalid/*`. Gate 2 also adds one separate authored shared corpus under `fixtures/gate2` without altering the frozen Gate 1 fixture set.

## Architecture delivered

- `src/xfi/validation.py` implements byte, depth, version, schema, semantic, digest, duplicate-ID, reference, secret, private-surface, and resource validation before persistence. Errors expose category codes only.
- `src/xfi/canonical.py` implements canonical UTF-8 JSON, SHA-256 digests, permalink normalization, relation-aware author selection, conflict gates, conservative temporal review eligibility, and deterministic deduplication.
- `src/xfi/store.py` owns SQLite files, migrations, application/schema identity, foreign keys, secure deletion configuration, WAL, idempotent transactional imports, parameterized persistence, auditable review decisions, export/backup inventory, online backup, isolated restore, scoped temporary cleanup, checkpointing, purge verification, and honest vacuum outcomes.
- `src/xfi/analysis.py` implements deterministic organic classification, five-factor scores, manual-only recommendations, verification records, author aggregation, follow/watchlist gates, and a typed capability-free model handoff. Captured content never gains authority.
- `src/xfi/render.py` creates distinct private JSON/Markdown artifacts, contextually escapes Markdown/HTML, neutralizes spreadsheet formulas, applies the allowlisted sanitizer, reconciles redaction entries, and writes through a flushed atomic temporary file without silent overwrite.
- `native/recording-helper/main.swift` uses AVFoundation and Apple Vision sequentially. `src/xfi/recording.py` requires an explicit crop, validates file/container/codec/duration/dimensions/candidate/disk limits, leaves the source unchanged, keeps frames in memory, records field provenance/confidence, and returns review-required ambiguity honestly.
- `harness/synthetic` is a separate marked non-distributable MV3 harness. Its native buttons drive arm/start/export/stop/discard messages through a sender-checked test service worker. It implements isolated visible-card parsing, descendant-level computed-style and viewport exclusion, IntersectionObserver collection at the inclusive 0.50 boundary, character/attribute/child mutation evidence, same-identity updates, virtualized-node identity changes, a real duration timer, UTF-8 packet accounting, all 23 normative hard stops, synchronous teardown, a normalized v1 export, and all-zero forbidden-effect accounting.
- `scripts/package_review.py` builds a deterministic recording-only private source package. It mechanically narrows the packaged session schema, excludes every harness/test capability, enforces static production-proposal permissions, and embeds the matching CycloneDX SBOM.

The production extension proposal remains static and ungranted. The analyzer bridge remains explicit JSON export/import; there is no listener, native messaging, product localhost service, or automated input.

## Deterministic verification

`bash tests/check_repo.sh` runs the portable clean-checkout suite. The opt-in exact-browser run additionally sets `XFI_RUN_REAL_BROWSER=1` and names the reviewed Node binary. On the measured Mac the combined suites passed:

- 9 frozen Gate 1 acceptance groups;
- 18 Gate 2 core/store/render tests;
- 6 browser-harness tests, including one real MV3 launch;
- 3 Apple Vision recording tests;
- 2 shared-corpus integration tests;
- 2 end-to-end operator CLI tests;
- direct changed-file security/privacy coverage; and
- byte-identical two-build package verification.

The shared authored truth set contains 4 identities: an original source, one quote edge, one promoted card, and one ambiguous card. The real MV3 export contained 5 observations over those exact 4 identities because a non-ASCII same-identity character-data change was preserved rather than overwriting prior evidence. The capability-denied DOM VM likewise produced 5 observations/4 identities; the Apple Vision path produced 5 frames/4 canonical units. Both paths measured identity precision and recall of `4/4 = 1.000000`, promotion separation of `2/2 = 1.000000`, and relationship edge accuracy of `1/1 = 1.000000`. All 23 hard stops produced the exact error state with zero post-stop observations, observers, timers, or DOM references. Forbidden effects, secret echoes, and performed account actions were all zero. The frozen sanitizer still matched its golden bytes exactly with 16 reconciled redactions.

The actual browser output—not a hand-shaped surrogate—passed the shared v1 validator and digest check, imported transactionally into the shared SQLite store, canonicalized to 4 posts, and produced 2 organic analyses; the promoted and ambiguous units remained outside organic analysis. The browser run used a fresh temporary profile, exact reserved-host HTTPS mapping, and a deny-by-default proxy. It allowed only reserved-host tunnels and denied every other browser request. No ordinary or authenticated profile was opened.

The synthetic browser data carries reserved-origin DOM provenance; recording data carries null-origin, video-time, crop, Apple Vision, and confidence provenance. OCR includes visible label text and can require review; the DOM harness preserves structured fixture identity. Those expected modality differences are retained rather than normalized away.

## Measured resources

Measurement command: `python3 scripts/measure_gate2.py`. Hardware/runtime: Apple M1, arm64, 16 GiB physical memory, macOS 27.0, Python 3.9.6, SQLite 3.54.0, Apple Swift 6.4.

| Measurement | Samples | Mean | Maximum |
| --- | ---: | ---: | ---: |
| Idle process CPU | 10 | 0.063271% | 0.082906% |
| Core validate/import/analyze wall time | 20 | 8.601983 ms | 19.171958 ms |
| Core CPU time | 20 | 6.247450 ms | 14.174000 ms |
| Capability-denied harness VM wall time | 10 | 24.919838 ms | 154.605083 ms |
| Five-frame Apple Vision recording run | 3 | 275.662819 ms | 283.697541 ms |

Core Python traced peak was 131,173 bytes; process maximum resident size was 19,120,128 bytes. Native child maximum resident size was 292,569,088 bytes. Recording used one worker and five candidate frames, within the exact one-worker and 250-candidate bounds. The idle mean is below the 2% target. These are measurements on the stated host and authored corpus, not universal performance claims.

## Dependency, SBOM, and package evidence

Product third-party component count is zero. Python standard library, platform SQLite, AVFoundation, Vision, and JavaScriptCore are environment facilities and are not redistributed. WXT, FFmpeg, and the Chromium headless shell were not adopted, downloaded, or executed.

The test-only stack adopts `playwright-core` 1.63.0 from the exact npm artifact SHA-256 `208593d4e1bcd8f8fe5f869cad1cc332dc7f1d70dc1d58c102dc3ac36e30f26c` and current-Stable Chrome for Testing 153.0.8010.36/mac-arm64 from the exact official archive SHA-256 `1f701ef60757c63c6ccf98afaf28291dd0c8d1457d3d738e81fd62201c230ad0`. The initially disclosed Playwright-pinned 153.0.8010.12 build was rejected as superseded after the official release/advisory check; it cannot pass the final runner hash gate. Package lifecycle scripts are disabled. The browser runner rechecks both archive and launcher hashes before every execution, uses a fresh temporary profile, disables background update/metrics/sync features, and forces network traffic through a local deny proxy. The Chrome test app does not pass strict distribution-signature verification, so its use is conditional on the pinned artifact hashes and limited to local testing. Both components, `node_modules`, the browser archives/runtime, package metadata, and the browser runner are excluded from the product package.

The existing CI-only `actions/checkout` dependency is pinned to v7.0.1 revision `3d3c42e5aac5ba805825da76410c181273ba90b1`, runs on Node 24 with `contents: read`, `persist-credentials: false`, and full history for base-to-head review, is recorded in `DEPENDENCIES.lock.json`, and is excluded from the product package. Its official repository was active and unarchived; its official security-advisory list returned zero entries on 2026-09-12. That result is not proof of safety.

`sbom/cyclonedx.cdx.json` is CycloneDX 1.5 and records zero product dependencies plus the excluded CI action and excluded test-only browser stack. Packaging refuses fixture origin values, test markers, synthetic harness paths, fixture trees, package/lock metadata, Node modules, browser artifacts, the browser preflight module, symlinks, permission drift, stale SBOM source hashes, and silent destination overwrite. The exact final package SHA-256 is recorded in the pull request after the final-head build.

## Honest limitations

- No user recording was supplied, so no real recording result is claimed.
- Actual isolated MV3 execution is verified only for the exact macOS arm64 Chrome-for-Testing artifact and authored fixture. The browser is not distribution-signed, and Linux/Windows/browser-store behavior remains unverified. This does not verify the static production proposal or live-origin compatibility.
- The private package is recording-only and source-based. It contains no runnable extension, browser binary, precompiled native helper, signing identity, notarization ticket, or distribution claim.
- Primary-source verification records are supported, but automatic external verification is absent by design. Model handoff is optional, local-file-only, and has no tool or navigation capability.
- SQLite purge cannot promise cryptographic erasure from SSD remapping, snapshots, older backups, synchronized copies, or prior exports.
- Gate 2 synthetic success does not authorize Gate 3 or reduce the documented Terms/account-enforcement risk.
