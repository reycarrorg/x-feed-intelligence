# Dependency Lock, Notice, and SBOM Plan

## Gate 1 decision and Gate 2 test adoption

Gate 1 adopted no third-party package. Its executable acceptance logic uses the Python standard library and platform shell tools already required by the repository. [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) existed before dependency adoption. Gate 2 now adopts exactly two excluded test components: `playwright-core` 1.63.0 and one pinned Chrome-for-Testing 153.0.8010.36/mac-arm64 archive. Neither is a product dependency or package input; the exact artifacts, hashes, licenses, lifecycle/network/telemetry behavior, maintenance/advisory review, signature boundary, and allow decision are recorded in the dependency lock, notices, SBOM, and Gate 2 evidence.

Platform facilities such as Python's standard library, SQLite supplied by the selected runtime, and Apple SDK frameworks are environment prerequisites rather than vendored packages; their runtime versions still belong in build/test evidence. FFmpeg remains a user-installed executable proposal, not an adopted or bundled dependency.

## Adoption gate

Before the first commit that imports, bundles, downloads, links, executes, or generates code/assets from a component, the same reviewed change must include:

1. exact package name, owner, upstream HTTPS source, version/tag and immutable revision or artifact SHA-256;
2. direct/transitive dependency lockfile with integrity fields and package-manager version;
3. license SPDX identifier, full license location, copyright/NOTICE text, source-offer/relinking obligations, and modification status in `THIRD_PARTY_NOTICES.md`;
4. lifecycle/install/build scripts, network access, telemetry, update behavior, executable downloads, generated code, permissions, bundled models/data/codecs/fonts/icons, and binary contents;
5. maintainer activity, security policy, advisories and known-vulnerability review dated at adoption;
6. an allow/conditional/reject decision tied to the Gate 0 reuse matrix;
7. a generated CycloneDX JSON SBOM for the exact locked graph and packaged artifact, with hashes when supported;
8. deterministic build/test commands and a generated-permission/bundle diff;
9. CI checks that fail on unlocked dependencies, missing notices, unexpected packages, remote code, license-policy conflicts, lifecycle-script drift, or SBOM mismatch.

No floating versions, git branches, curl-pipe-shell installers, remote scripts, runtime CDN code, silent model downloads, automatic paid service fallback, or unreviewed browser binaries are permitted.

## Candidate-specific decisions for Gate 2

- Start the analyzer and schema validator with the standard library and platform SQLite. Do not add an ORM until measured complexity justifies it.
- Invoke a separately installed FFmpeg only after version/configuration probing, resource sandboxing, malicious-media tests, and user-facing availability diagnostics. Bundling requires a distinct LGPL/GPL/nonfree review.
- Use Apple Vision through the platform SDK on macOS; record deployment target and API availability.
- WXT remains deferred. The synthetic extension slice adopted Playwright Core without the wrapper, with an exact one-package lock and lifecycle scripts disabled. The browser installer was dry-run only; it disclosed Chrome, FFmpeg, and a headless shell. Only the exact Chrome archive was directly downloaded and hash-pinned, while FFmpeg and the headless shell remained excluded. The production proposal is static-only through Gate 2; packaging fails if the reserved test origin, test-only markers, harness/control/service-worker files, package metadata, Node modules, browser artifacts, browser runner, or fixture tree appears in a production candidate.
- OpenCV, PySceneDetect and GRDB.swift require benchmark evidence. Tesseract remains on hold. All rejected Gate 0 projects remain prohibited.

## CI evidence

The dependency job must emit an exact lockfile digest, notice-entry count, SBOM component count, vulnerability-source/date record, separate production/test manifest findings, and promotion-guard results including negative controls. An advisory scan with no findings is not proof of safety. CI must not upload raw fixtures beyond the authored synthetic corpus or any local report/database.
