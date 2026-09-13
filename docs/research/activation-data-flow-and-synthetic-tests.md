# Activation, Data Flow, and Synthetic Test Plan

## Scope

This is a Gate 0 design, not implemented behavior. It defines the smallest account-aware architecture that can accept user-supplied recordings now and a passive visible-DOM packet later without sharing storage, credentials, or execution authority with X content.

## Components and trust zones

| Component | Trust zone | Allowed responsibility | Explicit exclusions |
| --- | --- | --- | --- |
| User-supplied recording | Private input | Evidence of what was visible in a bounded session | Never committed, uploaded, or silently copied |
| Recording ingester | Local untrusted-input boundary | Probe, crop, sample changed regions, OCR, attach provenance | No X access, URL traversal, command execution, or full-frame logging |
| Passive MV3 extension | Browser origin boundary | Observe visibly intersecting top-level cards after explicit activation; bounded export | No scrolling, clicks, fetch, cookies, request interception, private API, hidden data, or social actions |
| Import validator | Local schema boundary | Reject malformed, oversized, credential-like, executable, or wrong-origin packets | No best-effort coercion of unsafe inputs |
| Analysis core | Local trusted code | Normalize, deduplicate, store, review, classify, redact, and report | Captured content cannot choose tools or change policy |
| SQLite store | Private local data | Transactional observations, canonical units, provenance, review history | No cloud sync or live DB copying by default |
| Verification worker | Separately authorized research boundary | Follow a trusted analyst plan to primary public sources | Never auto-open a captured URL, authenticate, purchase, install, or execute |
| Sanitized exporter | Release boundary | Produce minimized Markdown/JSON with a redaction manifest | No raw media, private corpus, credentials, or stable account identifiers by default |

## Common envelope

Both inputs produce a versioned envelope before persistence:

```json
{
  "schema_version": "0.1",
  "session": {
    "id": "synthetic-session-001",
    "source": "recording-or-passive-extension",
    "started_at": "coarse-or-local-timestamp",
    "ended_at": "coarse-or-local-timestamp",
    "origin": "https://fixture.example.invalid-or-null",
    "collector_version": "fixture-version",
    "privacy_profile": "default-local"
  },
  "observations": [],
  "collection_events": [],
  "redaction_manifest": []
}
```

Gate 1 refines this Gate 0 sketch with a deterministic source/origin invariant: authored synthetic DOM sessions use the reserved `https://fixture.example.invalid` origin, while recording sessions use `null`. Live `https://x.com` is not a valid schema-v1 session origin and requires a separately gated future source/schema version.

Each observation carries a session-scoped ID, input location (video time and crop coordinates, or DOM viewport time), source modality, visible structural fields, field-level confidence, promoted status, original/repost/quote relationships, media descriptors, parser/OCR version, and warnings. Raw HTML, scripts, cookies, headers, page storage, media binaries, and browser-profile material are not envelope fields.

## Recording data flow

1. The user chooses a local recording and confirms the intended feed crop.
2. The ingester reads metadata and enforces configured duration, dimensions, codecs, file size, and disk-budget limits.
3. A bounded sampler identifies changed regions; it does not OCR every frame by default.
4. Apple Vision performs on-device OCR on candidate feed regions. Text, boxes, confidence, frame time, and crop coordinates remain linked.
5. A card tracker groups adjacent evidence. Ambiguous splits/merges enter review.
6. The normalized envelope passes through size, type, secret, and schema validation.
7. A transaction writes observations and candidate canonical units to SQLite.
8. Derived frames/crops are deleted after accepted import unless the user explicitly selects diagnostic retention. The original recording stays in place.

FFmpeg should initially be invoked as a separately installed local executable with its version/configuration recorded. Bundling requires a distinct license/package decision. OpenCV or PySceneDetect enters only after benchmarks show that simpler change detection misses the target.

## Passive-extension lifecycle

This section describes a future production proposal. Through Gate 2 that proposal is statically inspected but never granted or run. Browser integration instead uses a distinct, conspicuously non-distributable manifest limited to `https://fixture.example.invalid`, mapped to an ephemeral loopback fixture server in an isolated profile with outbound access denied. A deterministic promotion guard rejects all test origins, markers, harness files, and fixtures from any production candidate.

### Installation and inactive state

The initial manifest includes ordinary extension storage and scripting capability but no persistent X host access. It contains no remote code, analytics, update channel outside the browser's normal extension mechanism, X/API/model-provider hosts, localhost access, cookies, request interception, debugger, native messaging, or account-action permission.

After installation the extension is inactive. It does not inject, enumerate X tabs, or retain browsing history.

### Explicit arm

1. The user opens the extension control and chooses `Enable on x.com`.
2. The browser displays its native request for optional `https://x.com/*` host permission.
3. On grant, the extension registers the isolated content script and displays a persistent `armed` state.
4. Revoking the host permission unregisters the script and clears its bounded unsaved queue after a confirmation local to the extension.

The host grant is necessary technical authority, not a claim that X authorizes extraction.

### Activation

The content script may collect only when all of these predicates are true:

- top-level document origin is exactly `https://x.com`;
- document is visible and not a challenge, login, consent, lock, error, or rate-limit surface;
- the extension is armed and the current session is explicitly started;
- parser health is within the accepted synthetic fixture contract;
- a candidate top-level post card reaches the configured viewport-intersection threshold;
- queue, age, and local-storage budgets are below their limits.

A visible badge reports `armed`, `capturing`, `paused`, `limit reached`, or `error`. Collection pauses immediately when the document is hidden. The observer and in-memory DOM references are destroyed on navigation away, session stop, host-permission revocation, tab close, or any hard stop.

### Observation behavior

`MutationObserver` may identify candidate cards that the page rendered. `IntersectionObserver` is the collection gate. The extension reads only visible semantic structure required for the envelope. It does not cause a scroll, click, hover, expansion, playback, navigation, refresh, retry, network call, clipboard action, download, or key event. It never asks a page script for hidden state.

Queue capacity is initially 250 unique candidate cards or 30 minutes, whichever comes first. Reaching a limit pauses collection and requires explicit export or discard. These are provisional evaluation limits, not production promises.

### Export and deactivate

The user explicitly chooses `Export session`. The extension serializes the bounded envelope, computes a content digest, and offers a local JSON file. No localhost server or native-messaging bridge is required. Successful export does not imply import. The analyzer validates schema, size, origin, secret patterns, and digest before a transactional import.

Stopping a session detaches observers and clears DOM references. Closing the final approved tab does not run background collection. The extension stores configuration and bounded unsaved session data only; imported history belongs to the local analyzer.

## Fail-closed behavior

The extension records only a non-sensitive event code and stops for:

- login, sign-out, CAPTCHA, Turnstile, verification, unusual activity, lock, consent, or rate-limit surface;
- unexpected origin, iframe boundary, permission change, parser version mismatch, unknown card topology, or excessive ambiguity;
- queue, time, disk, memory, or payload limit;
- any request for an excluded permission or account action;
- captured text that tries to issue instructions, request secrets, or induce execution or navigation.

No recovery path may recommend retries, stealth, headless/headful changes, proxy rotation, fingerprint modification, alternate accounts, copied profiles, CAPTCHA services, or private API replay.

## Analysis and sanitization flow

The import validator treats every string as data and applies depth, length, encoding, enum, and count limits. SQLite writes are parameterized and transactional. HTML and Markdown outputs escape captured content. File names are generated locally rather than accepted from captured content. URLs are stored as strings and never fetched by the ingestion path.

The analysis core produces two distinct outputs:

- a private report packet with local evidence and account/post identities required for review; and
- a sanitized packet with pseudonyms, reduced timestamps, query-free URLs, no media, no raw corpus, no stable platform identifiers unless explicitly retained, and a field-level redaction manifest.

Verification runs separately from ingestion. A trusted analyst selects a claim and independently searches for the official source. Captured links may be recorded as claims but are not opened automatically.

## Synthetic fixture families

All repository fixtures are authored synthetic content with reserved example domains and invented identities. No real post text, media, handles, IDs, or private chat excerpts are permitted.

| Family | Required variants | Acceptance signal |
| --- | --- | --- |
| Topology | Original, repost, quote, reply-as-card, multi-card thread, promoted card, community note | Correct relationship graph and organic/ad count |
| Visibility | 0%, threshold edge, above threshold, partially clipped, recycled virtualized node, background tab | Only eligible visible observations collected once per appearance |
| Mutation | Text/media loaded late, engagement changes, card reused, card removed/reinserted | Stable identity, bounded updates, no duplicate inflation |
| Text | Long text, Unicode, right-to-left, emoji, code-like text, prompt injection, zero-width characters | Safe escaped storage/rendering; no instruction execution |
| Media | Image alt text, video poster, missing alt text, quoted media, media-only card | Media descriptors and uncertainty without binary download |
| Identity | Display-name collision, handle change, repost/quote author conflict, missing ID | No unsafe merge; role-aware confidence |
| Advertising | Clear promoted label, delayed label, ambiguous sponsorship, ordinary product discussion | Ads excluded only with evidence; ambiguity reviewed |
| Failure | Login, challenge, rate limit, unknown markup, oversize payload, malformed schema | Immediate stop or import rejection with non-sensitive code |
| Privacy | Synthetic cookie/token/header/DM/notification/email/account menu | Field omitted or packet rejected; secret never echoed to logs |
| Recording | Slow/fast scroll, compression, occlusion, repeat frames, partial cards, changing video | Sequential ledger, conservative merge, field provenance |
| Sanitization | Synthetic PII, query parameters, stable IDs, free-text identity clues | Expected minimization and complete redaction manifest |
| Accessibility | Keyboard-only controls, screen-reader names, high contrast, zoom, no-color state | All lifecycle controls and report classes perceivable/operable |

## Deterministic acceptance metrics

Gate 1 must freeze a labeled synthetic corpus and exact measurement script before thresholds become release claims. Initial target criteria are:

- 100% stop behavior for every challenge, login, rate-limit, permission, wrong-origin, and oversize fixture;
- 0 network requests, account actions, automated input events, cookie/header reads, or hidden-data reads by collector tests;
- 100% promoted-card separation on unambiguous fixtures;
- at least 99% unique-unit precision and 98% recall on synthetic DOM fixtures;
- at least 95% unique-unit precision and 90% recall on supplied synthetic recording fixtures, with every miss attributable in the review ledger;
- 100% relationship accuracy for unambiguous original/repost/quote fixtures;
- 100% classification/action schema completeness for legible units;
- no secret value appears in logs, reports, snapshots, exceptions, or exports;
- sanitizer expected-output tests pass byte-for-byte;
- extension queue never exceeds 250 candidates and stops at the configured age limit;
- after stop/navigation, no observers, timers, DOM references, or collection events remain;
- provisional idle overhead below 2% mean CPU, bounded peak memory, and one OCR worker unless benchmarks justify a change.

Performance must be measured on documented hardware, browser/runtime versions, fixture sizes, and sampling intervals. Averages without worst-case and failure-path results are insufficient.

## Test layers

1. Schema and migration tests: canonical examples, boundary sizes, invalid types, unknown versions, idempotent imports, and rollback.
2. Pure parser tests: frozen synthetic HTML fragments with no browser network.
3. Browser integration: the test-only manifest and reserved synthetic origin under Playwright; the hostname maps to an ephemeral loopback server, outbound network is denied, and test scrolling is limited to the synthetic page. The production proposal is inspected only and is never loaded.
4. Recording golden tests: generated synthetic video with expected frames, cards, OCR fields, counts, and uncertainty.
5. Deduplication/property tests: randomized observation order, repeats, near collisions, and stable results.
6. Security tests: injection strings, path traversal, spreadsheet formulas, HTML/Markdown escaping, decompression/size limits, secret canaries, and malicious SQLite/input rejection.
7. Privacy tests: telemetry absence, network-deny assertions, log capture, retention expiration, transactional purge, backup behavior, and sanitizer golden files.
8. Accessibility tests: automated semantics plus keyboard and screen-reader manual checks.
9. Packaging/license tests: locked dependencies, notices, SBOM, separate production/test manifest diffs, negative promotion controls, no remote code, reproducible artifact hashes.

Playwright is allowed only for local synthetic-fixture tests. It must never open X or import a real browser profile.

## Gate 1 entry and exit criteria

Gate 1 may start when Gate 0's ADR, reuse matrix, policy risk, methodology, and this plan are accepted. It exits only when all of the following are reviewed and committed:

1. versioned schemas for sessions, observations, canonical posts, author roles, media, provenance, scores, verification, recommendations, ads, uncertainty, and redactions;
2. a threat model covering browser, recording, parser/OCR, database, report rendering, dependency/update, prompt injection, and sanitized export trust boundaries;
3. exact extension permission manifest and lifecycle state machine, with every permission justified;
4. local retention/deletion and backup semantics, including tested SQLite deletion limitations;
5. deterministic synthetic fixture corpus and licensed/provenance manifest;
6. metric formulas, baselines, thresholds, and failure reporting for DOM and recording paths;
7. dependency lock/notice/SBOM plan and approval of every adopted component;
8. current X policy recheck and a documented statement that live extension access remains outside Gate 1;
9. privacy/secret/redaction test plan with synthetic canaries;
10. a reviewed Gate 2 work breakdown that implements synthetic and supplied-data paths only.

No real-account access, extension installation into the user's normal profile, paid API use, or social action is a Gate 1 acceptance activity.

## Gate 3 live-test prerequisites

A later live X test requires all of these, not merely a working build:

- explicit user-supervised authorization for that test session;
- fresh X Terms, Developer Agreement/Policy/Guidelines, and API-capability review;
- accepted residual-risk statement acknowledging that passive extraction may still be prohibited and suspension is possible;
- signed/reviewable build with exact manifest and no unexpected permission or network capability;
- passed synthetic security, privacy, lifecycle, parser-health, and sanitizer tests;
- recording-only fallback proven independently;
- ordinary user sign-in performed by the user, with no secret handling by the product;
- immediate stop on any challenge, warning, restriction, parser drift, or permission mismatch;
- no mutation, evasion, retry loop, profile copy, proxy, CAPTCHA handling, or private API use;
- post-test local evidence reconciliation and user decision before any further live session.
