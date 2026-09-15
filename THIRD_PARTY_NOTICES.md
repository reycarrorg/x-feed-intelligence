# Third-Party Notices

No third-party package is adopted or distributed in the Gate 1 or Gate 2 recording-only package. Gate 3 adds the separately gated extension reuse and build dependencies documented below. The test-only browser stack remains solely for local verification and never enters the recording-only package.

The recording product and most tests use the Python standard library, platform SQLite, and Apple SDK frameworks. Environment-provided tools and platform SDKs are not redistributed. Playwright Core and one exact Chrome-for-Testing archive are test-only; FFmpeg and the Chromium headless shell were not downloaded or executed.

## Gate 3 extension reuse

Selected visible-DOM selector, author, timestamp, status-ID, and quoted-card parsing methods in `extension/lib/parser.ts` are adapted from XClipper 2.8.2 at commit `3f7c6caa2e6f02bf37d140b989cbbdf4485275a5`, by Ali Zendegani, under the PolyForm Noncommercial License 1.0.0. Required Notice: Copyright © 2026 Ali Zendegani (<https://github.com/zendegani/XClipper>). Fast/Auto/Super modes, automatic navigation, private GraphQL interfaces, request/header interception, media downloads, and account actions are not adopted.

WXT 0.21.4, copyright its contributors and licensed under MIT, is used as the extension build framework. It is a development dependency and no WXT-hosted service is used at runtime. Exact direct and transitive artifacts are pinned in `extension/pnpm-lock.yaml`. TypeScript and `@types/chrome` are compile-time dependencies; Vitest and Happy DOM are test-only. Their inclusion in the dependency graph is not permission to import unrelated capabilities into the product.

Feed Cleaner and XRAI informed user-visible explanation and local-analysis concepts only. No source from either project is copied into Gate 3. The inspected Feed Cleaner revision lacked a complete root license file, so its package-metadata license declaration was not treated as sufficient for source reuse.

## CI-only dependency

`actions/checkout` v7.0.1 at immutable revision `3d3c42e5aac5ba805825da76410c181273ba90b1` is used only on GitHub-hosted CI to fetch this repository with `contents: read`, `persist-credentials: false`, and full history for base-to-head review. It is copyright GitHub, Inc. and contributors and licensed under the MIT License. Upstream source and license: <https://github.com/actions/checkout> and <https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/LICENSE>. It is not included in the private package candidate.

`actions/setup-node` v7.0.0 at immutable revision `820762786026740c76f36085b0efc47a31fe5020` is used only on GitHub-hosted CI to provide Node.js 24.19.0 for extension compilation, tests, and packaging. It is copyright GitHub, Inc. and contributors and licensed under the MIT License. Upstream source and license: <https://github.com/actions/setup-node> and <https://github.com/actions/setup-node/blob/820762786026740c76f36085b0efc47a31fe5020/LICENSE>. It is not included in the generated extension.

Exact scope, network behavior, maintenance, advisory review, and the conditional allow decision are recorded in [`DEPENDENCIES.lock.json`](DEPENDENCIES.lock.json). Candidate components remain governed by [the dependency and SBOM plan](docs/gate1/DEPENDENCY_AND_SBOM_PLAN.md).

## Test-only browser dependency

`playwright-core` 1.63.0 is used only to drive the isolated synthetic MV3 browser test. It is copyright Microsoft Corporation and licensed under the Apache License 2.0. Upstream source and license: <https://github.com/microsoft/playwright/tree/v1.63.0> and <https://github.com/microsoft/playwright/blob/v1.63.0/LICENSE>. The exact npm artifact SHA-256 is `208593d4e1bcd8f8fe5f869cad1cc332dc7f1d70dc1d58c102dc3ac36e30f26c`; registry SHA-512 integrity is recorded in both lockfiles. The package declares no lifecycle scripts; the repository requests script suppression and the reviewed install command explicitly supplies `--ignore-scripts`. The package, its bundled third-party notices, and every browser artifact are excluded from the product package.

## Test-only browser artifact

Chrome for Testing 153.0.8010.36 for macOS arm64 is used only for the isolated MV3 test. The exact official archive URL and SHA-256 (`1f701ef60757c63c6ccf98afaf28291dd0c8d1457d3d738e81fd62201c230ad0`), launcher SHA-256, Chromium revision, test network containment, maintenance/advisory review, and exclusion decision are recorded in [`DEPENDENCIES.lock.json`](DEPENDENCIES.lock.json). The archive identifies Google LLC, the Chromium project, the Chrome Terms of Service, and bundled open-source notices exposed by `chrome://credits`. The outer test app does not pass strict distribution-signature verification, so it is never trusted by name or ambient installation: the test runner accepts only this repository-local ignored artifact after exact hash verification. It is never installed system-wide or packaged. Playwright's disclosed FFmpeg and headless-shell artifacts remain excluded and were not downloaded or executed. The earlier Playwright-pinned 153.0.8010.12 early-stable build was rejected as superseded after the official advisory check and cannot pass the final runner hash gate.
