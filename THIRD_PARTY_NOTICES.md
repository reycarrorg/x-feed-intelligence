# Third-Party Notices

No third-party package is adopted or distributed in the Gate 1 or Gate 2 product. No third-party source file, binary, model, font, icon, codec, browser, or test framework enters the product package.

The executable product and tests use the Python standard library, platform SQLite, and Apple SDK frameworks. Environment-provided tools and platform SDKs are not redistributed. FFmpeg, WXT, Playwright, and a browser binary remain unadopted and are not downloaded, invoked, or packaged.

## CI-only dependency

`actions/checkout` v7.0.1 at immutable revision `3d3c42e5aac5ba805825da76410c181273ba90b1` is used only on GitHub-hosted CI to fetch this repository with `contents: read`, `persist-credentials: false`, and full history for base-to-head review. It is copyright GitHub, Inc. and contributors and licensed under the MIT License. Upstream source and license: <https://github.com/actions/checkout> and <https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/LICENSE>. It is not included in the private package candidate.

Exact scope, network behavior, maintenance, advisory review, and the conditional allow decision are recorded in [`DEPENDENCIES.lock.json`](DEPENDENCIES.lock.json). Candidate components remain governed by [the dependency and SBOM plan](docs/gate1/DEPENDENCY_AND_SBOM_PLAN.md).
