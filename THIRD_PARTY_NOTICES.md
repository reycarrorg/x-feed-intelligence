# Third-Party Notices

No third-party package is adopted or distributed in the Gate 1 or Gate 2 product. No third-party source file, binary, model, font, icon, codec, browser, or test framework enters the product package.

The executable product and tests use the Python standard library, platform SQLite, and Apple SDK frameworks. Environment-provided tools and platform SDKs are not redistributed. FFmpeg, WXT, Playwright, and a browser binary remain unadopted and are not downloaded, invoked, or packaged.

## CI-only dependency

`actions/checkout` v4.4.0 at immutable revision `11d5960a326750d5838078e36cf38b85af677262` is used only on GitHub-hosted CI to fetch this repository with `contents: read` and `persist-credentials: false`. It is copyright GitHub, Inc. and contributors and licensed under the MIT License. Upstream source and license: <https://github.com/actions/checkout> and <https://github.com/actions/checkout/blob/11d5960a326750d5838078e36cf38b85af677262/LICENSE>. It is not included in the private package candidate.

Exact scope, network behavior, maintenance, advisory review, and the conditional allow decision are recorded in [`DEPENDENCIES.lock.json`](DEPENDENCIES.lock.json). Candidate components remain governed by [the dependency and SBOM plan](docs/gate1/DEPENDENCY_AND_SBOM_PLAN.md).
