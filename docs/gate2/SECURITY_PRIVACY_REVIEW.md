# Gate 2 Direct Security and Privacy Review

## Method and scope

The sole implementing agent reviewed the complete diff from base `9f961e5b9758884bcb5aff6ad2b8e85ca1bf0396` directly. No subagent, worker, delegated scanner, remote scanner, or model/API service was used. The worker-based security-scan workflow was intentionally not invoked because it conflicts with the explicit no-worker boundary.

Coverage includes every changed Python, Swift, JavaScript, shell, HTML, workflow, dependency-lock, notice, SBOM, packaging, and test file. The review followed data from packet bytes through validation, canonicalization, parameterized SQLite operations, analysis, rendering, explicit exports, recording metadata/frame/OCR handling, synthetic DOM parsing, lifecycle teardown, package contents, and CI. `tests/gate2_security.py` independently inventories the changed diff and checks local paths, private/binary artifacts, unsafe Python execution/network surfaces, shell downloads/package managers, browser network/input/storage capabilities, exact manifests, the pinned CI revision, and credential persistence.

The direct review also inspected every dynamic SQL construction. Values are bound parameters; the only constructed SQL fragments are placeholder counts derived from in-memory ID-list length, not captured data. The native helpers accept argument vectors without a shell. The recording helper emits content only as explicit private product output and emits category-only errors. The harness contains no network API, account input, cookie/header/page-storage read, page-world injection, navigation, or retry capability.

## Findings and remediation

Three material issues were found and fixed before delivery:

1. **Production promotion leakage — fixed.** The first package design copied the full frozen session schema, which contains the reserved synthetic origin. Packaging now deterministically emits a stricter recording-only session-schema projection, excludes all browser/harness/fixture capability, and fails on test origin values, markers, files, stale SBOM hashes, or permission drift.
2. **Unscoped purge cleanup — fixed.** The first purge helper could unlink any caller-supplied temporary path. It now requires containment under an explicit temporary root, refuses symlinks and out-of-scope paths, preserves the file on rejection, and returns `PURGE_INCOMPLETE`.
3. **Incomplete hard-stop enumeration — fixed.** The first runnable harness covered the 12 authored fixture stops but not all normative machine-contract codes. It now enumerates and tears down on all 23 codes; tests reconcile the executable list with the contract and require zero post-stop state.

No unresolved critical or high security/privacy finding remains. No medium or low confirmed vulnerability remains. Product network dependency count, remote-code count, credential-read count, account-action count, automated-input count, secret-echo count, and live-origin execution count are all zero.

## Residual risk and unverified tiers

Actual isolated-browser MV3 execution is unavailable because no reviewed browser binary is installed and downloading one would require a dependency adoption decision. The production proposal was never loaded or granted. Apple Vision exercised only an authored temporary movie. The source package is reproducible, but a compiled universal binary, signing, notarization, browser-store review, public distribution, live X compatibility, real-recording accuracy, filesystem snapshot erasure, and physical interoperability are not verified.
