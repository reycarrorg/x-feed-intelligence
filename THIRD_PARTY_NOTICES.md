# Third-Party Notices

No third-party package is adopted or distributed in the Gate 1 or Gate 2 product. The test-only browser stack documented below is adopted solely for local verification and never enters the product package. No third-party source file, binary, model, font, icon, codec, browser, or test framework enters that package.

The executable product and most tests use the Python standard library, platform SQLite, and Apple SDK frameworks. Environment-provided tools and platform SDKs are not redistributed. WXT remains unadopted. Playwright Core and one exact Chrome-for-Testing archive are test-only; FFmpeg and the Chromium headless shell were not downloaded or executed.

## CI-only dependency

`actions/checkout` v7.0.1 at immutable revision `3d3c42e5aac5ba805825da76410c181273ba90b1` is used only on GitHub-hosted CI to fetch this repository with `contents: read`, `persist-credentials: false`, and full history for base-to-head review. It is copyright GitHub, Inc. and contributors and licensed under the MIT License. Upstream source and license: <https://github.com/actions/checkout> and <https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/LICENSE>. It is not included in the private package candidate.

Exact scope, network behavior, maintenance, advisory review, and the conditional allow decision are recorded in [`DEPENDENCIES.lock.json`](DEPENDENCIES.lock.json). Candidate components remain governed by [the dependency and SBOM plan](docs/gate1/DEPENDENCY_AND_SBOM_PLAN.md).

## Test-only browser dependency

`playwright-core` 1.63.0 is used only to drive the isolated synthetic MV3 browser test. It is copyright Microsoft Corporation and licensed under the Apache License 2.0. Upstream source and license: <https://github.com/microsoft/playwright/tree/v1.63.0> and <https://github.com/microsoft/playwright/blob/v1.63.0/LICENSE>. The exact npm artifact SHA-256 is `208593d4e1bcd8f8fe5f869cad1cc332dc7f1d70dc1d58c102dc3ac36e30f26c`; registry SHA-512 integrity is recorded in both lockfiles. The package declares no lifecycle scripts; the repository requests script suppression and the reviewed install command explicitly supplies `--ignore-scripts`. The package, its bundled third-party notices, and every browser artifact are excluded from the product package.

## Test-only browser artifact

Chrome for Testing 153.0.8010.36 for macOS arm64 is used only for the isolated MV3 test. The exact official archive URL and SHA-256 (`1f701ef60757c63c6ccf98afaf28291dd0c8d1457d3d738e81fd62201c230ad0`), launcher SHA-256, Chromium revision, test network containment, maintenance/advisory review, and exclusion decision are recorded in [`DEPENDENCIES.lock.json`](DEPENDENCIES.lock.json). The archive identifies Google LLC, the Chromium project, the Chrome Terms of Service, and bundled open-source notices exposed by `chrome://credits`. The outer test app does not pass strict distribution-signature verification, so it is never trusted by name or ambient installation: the test runner accepts only this repository-local ignored artifact after exact hash verification. It is never installed system-wide or packaged. Playwright's disclosed FFmpeg and headless-shell artifacts remain excluded and were not downloaded or executed. The earlier Playwright-pinned 153.0.8010.12 early-stable build was rejected as superseded after the official advisory check and cannot pass the final runner hash gate.
