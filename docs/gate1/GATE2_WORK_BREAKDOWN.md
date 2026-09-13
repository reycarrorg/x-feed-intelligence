# Reviewed Gate 2 Work Breakdown

## Entry criteria

Gate 2 may begin only after this Gate 1 pull request is reviewed and merged, every Gate 1 repository/acceptance check is green on `main`, the schemas and fixture manifest are unchanged or deliberately versioned, and no unresolved critical/high security or privacy finding remains. `THIRD_PARTY_NOTICES.md` must predate any dependency adoption.

Gate 2 inputs are limited to synthetic and explicitly user-supplied data. Live X access, an authenticated browser profile, extension installation in the user's normal profile, paid APIs/credits, private web interfaces, remote telemetry, account actions, public release, and scheduled account activity remain outside Gate 2.

## Ordered work packages

### G2.1 — Core validator and canonical store

Implement schema and semantic validation, canonical JSON/digest handling, deterministic deduplication, migrations, parameterized SQLite persistence, review decisions, and content-free diagnostics. Test malformed/deep/oversized input, idempotent import, rollback, foreign keys, WAL, backup and purge with temporary synthetic databases.

Exit: both synthetic envelopes import transactionally; every oracle relationship/count matches; purge and backup caveats have executable evidence; no rejected value is echoed.

### G2.2 — Analysis and safe rendering

Implement classification/score/action records, verification log, author evidence aggregation, private Markdown/JSON reports, static escaped HTML only if needed, and allowlisted sanitized export. Keep model integration optional and capability-free behind the handoff schema.

Exit: every legible organic fixture is complete; score and follow/watchlist gates hold; sanitizer matches the golden file byte-for-byte; injection, HTML/Markdown and formula canaries render only as data.

### G2.3 — Recording ingestion on authored and user-supplied data

Implement metadata preflight, explicit crop selection, bounded candidate-frame extraction, Apple Vision OCR on macOS, field provenance/confidence, card tracking and review. A separately installed FFmpeg may be invoked only after its adoption/preflight gate. Raw recordings remain in place; derived files are ephemeral.

Exit: generated synthetic recording fixtures meet 0.95 precision, 0.90 recall and 1.00 unambiguous relationship/ad separation; worker/disk/time limits stop safely; supplied recordings require explicit user selection and never enter Git/CI.

### G2.4 — Passive extension against local synthetic pages only

Implement the exact MV3 proposal, user-driven lifecycle, isolated parser, visibility/mutation behavior, bounded queue and explicit JSON export. Adopt WXT/Playwright only through the dependency gate. Tests use a fresh isolated profile and local fixture server with outbound network denied; they must never navigate to X.

Exit: generated manifest equals the approved capability set; every hard-stop fixture is 1.00; forbidden effect count is zero; post-stop references/events are zero; DOM precision/recall meet 0.99/0.98; accessibility controls pass automated and manual review.

### G2.5 — Integration, resource measurement, package candidate

Run one normalized corpus through both inputs, reconcile provenance and expected differences, record documented hardware/runtime metrics, generate notices/SBOM, inspect bundle contents and permissions, and create a private review artifact only. Do not install it in the user's normal profile or represent it as live accepted.

Exit: all checks pass from a clean checkout; build hashes reproduce under the documented environment or deviations are explained; mean/max resource data is recorded; security/privacy review has no unresolved critical/high finding; Gate 3 residual-risk packet is drafted but not accepted.

## Review and stop conditions

Each package is a separate reviewable change. Stop and return to architecture review if implementation requires a new host/extension permission, native messaging, localhost service, network or model API, hidden DOM/private endpoint, remote synchronization, automated browser input, retained raw frames by default, a nonlocal database, a rejected dependency, or weaker privacy/metric thresholds.

Gate 2 completion does not authorize Gate 3. The earliest live test still requires explicit user-supervised authorization, current X policy recheck, accepted residual account risk, exact signed/reviewable build, ordinary user sign-in, and immediate stop on any challenge or drift.
