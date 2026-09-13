# Gate 1 Threat Model

## Status and scope

This threat model is normative for schema version `1.0.0`. It covers local handling of authored synthetic fixtures and future user-supplied recordings. The passive extension remains synthetic-test-only through Gate 2. No live X access, authenticated profile, account action, remote telemetry, paid service, or automatic external verification is authorized.

Protected assets are account/session secrets; private feed and recording content; author and post identities; local analysis history; report integrity; tool and instruction authority; deletion intent; build integrity; and the user's X account standing. Captured text, links, media, markup, OCR, fixture content, dependencies, and upstream documentation are untrusted.

## Trust boundaries and abuse cases

| Boundary | Untrusted input or threat | Required control | Failure behavior | Residual risk |
| --- | --- | --- | --- | --- |
| Browser extension | Hostile page markup, virtualized node reuse, hidden content, prompt injection, challenge pages, permission drift | Exact optional `https://x.com/*` host; isolated script; visibility gate; parser health; bounded queue; no network, cookies, headers, page storage, page-world injection, automated input, or account APIs | Detach observers and DOM references; record a non-sensitive stop code; require user acknowledgement; never retry automatically | Visible DOM extraction may still violate X Terms and may expose personalized content |
| Recording selection | Wrong window, notifications, DMs, account menus, oversized or malicious media | User-confirmed feed crop; metadata, codec, duration, dimension, file, worker, and disk limits; original remains in place; no full-frame logs | Reject before decode or stop the bounded job; identify category only | Crop may still contain incidental information; media decoder defects remain possible |
| Parser and OCR | Malformed structure, adversarial Unicode, incorrect author relationships, hallucinated text, low confidence | Typed fields, length/depth/count limits, field provenance, confidence, normalization before comparison only, ambiguity threshold, human review | Reject unsafe packets; classify materially unreadable posts as insufficient; never reconstruct missing text | OCR/layout ambiguity cannot be eliminated and may lower recall |
| Import boundary | Malformed JSON, unknown schema, path/formula content, secrets, credential-like fields, oversized or deeply nested data | Byte/depth/count/type/version checks before persistence; sensitive-name and value detectors; generated local filenames; parameterized transactions | Reject atomically with category code; never echo rejected values | Pattern matching cannot identify every sensitive free-text disclosure |
| SQLite database | SQL injection, malicious imported DB, stale WAL/SHM, copied live DB, deleted data in free pages/backups | Create and own the DB; never import arbitrary DB files; parameterized SQL; local filesystem; transactions; `secure_delete=ON`; checkpoint then purge; backup through SQLite backup API | Roll back on failure; preserve a safe error code; mark purge incomplete if checkpoint/vacuum/backup handling fails | SSD wear leveling, filesystem snapshots, cloud/backup copies, and prior unsafe settings prevent cryptographic-erasure promises |
| Report rendering | HTML/Markdown/script injection, formula injection, path traversal, remote resources, identity leakage | Contextual escaping; plain-text classification labels; formula-prefix neutralization; no active remote content; locally generated filenames; sanitized export allowlist | Refuse unsafe render target or escape as data | Human readers can still act on malicious quoted content |
| Verification | Captured URL induces navigation, download, login, purchase, or code execution | Trusted analyst plan; independently locate primary source; captured links are hints only; no auth, install, command, purchase, or submission | `not_checked` with reason; suspicious destination remains unopened | Search results and official pages can be compromised or outdated |
| Model handoff | Post or source text claims authority, asks for tools/secrets, or changes policy | Trusted control and untrusted records in different typed fields; deny-by-default authority; no tools in analysis handoff; output schema validation | Discard nonconforming output; no tool call or navigation | A model may misclassify content; deterministic guards remain authoritative |
| Sanitized export | Stable IDs, handles, exact times, queries, media, secrets, or free-text identity clues escape | Allowlisted output; pseudonyms scoped to export; query stripping; time coarsening; media omission; complete redaction manifest; byte-for-byte golden tests | Fail export if scan or manifest reconciliation fails | Sanitization minimizes risk but cannot guarantee anonymity from prose context |
| Dependencies and updates | Compromised package, lifecycle script, license conflict, remote code, generated permission drift | No dependency before lock, provenance, advisory and license review; checksums; notices; SBOM; generated manifest diff; packaged code only | Block adoption/build/package | Registries, maintainer accounts, compiler/runtime and transitive dependencies remain supply-chain risks |
| Build and CI | Secrets in logs, network-dependent tests, nondeterministic artifacts, real data entering fixtures | Synthetic-only tests; zero-network collector oracle; pinned tools when adopted; secret scan; fixture provenance hashes; reproducible command and environment record | CI fails; no release or artifact acceptance | Hosted CI operator and base-image trust remain outside repository control |
| Packaging | Unexpected permissions, remote code, unsigned/unnotarized claims, bundled codec/license failures | Inspect exact manifest; enumerate bundle contents; notices and SBOM; reproducible hashes; separate signing/notarization evidence | Package rejected; no live installation or release | Browser/store and OS signing ecosystems introduce separate review and policy risk |

## Security properties

1. Content authority is always zero. A captured instruction cannot change policy, select a tool, trigger navigation, disclose data, or authorize a purchase or social action.
2. Collector authority is structural extraction only. The synthetic test oracle must observe zero network requests, account actions, automated input events, credential reads, or hidden-data reads.
3. Imports are all-or-nothing. Schema, size, origin, version, digest, secret, and resource checks occur before a database transaction commits.
4. Provenance is field-level and append-only. Manual corrections add provenance; they do not overwrite original evidence.
5. Deduplication never discards observations and never merges across an explicit conflict.
6. Private and sanitized outputs are different artifacts. Sanitized exports never inherit fields merely because they were safe in a private report.
7. Deletion is accurately described as best-effort local purge with recorded caveats, never cryptographic erasure.
8. Live extension collection stays disabled through Gate 2 regardless of synthetic success.

## Required security tests

The Gate 1 oracle exercises injection strings, secrets, malformed and oversized input, wrong origins, challenges, rate limits, permission drift, parser ambiguity, resource ceilings, deterministic deduplication, output escaping, and sanitizer golden files. Gate 2 must add database transaction/purge tests, static report-rendering tests, synthetic browser instrumentation, synthetic recording decoding/OCR, package inspection, and dependency/SBOM verification before claiming implementation of these properties.

## Review triggers

Re-review this model before any new permission, network listener, native messaging, remote model, telemetry, live X session, official API, sync, automatic verification, account action, bundled binary/model/font, public distribution, license change, or material schema change.
