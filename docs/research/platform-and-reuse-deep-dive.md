# Platform and Reuse Deep Dive

## Executive decision

X Feed Intelligence should proceed as a **local hybrid with two independent inputs and one normalized analysis core**:

1. an account-safe recording pipeline, using FFmpeg for bounded frame extraction and Apple Vision as the first macOS OCR engine; and
2. an opt-in Manifest V3 WebExtension that observes only post cards that are visibly rendered while a person scrolls an exact approved origin.

The recording path is the production default. The extension is the higher-fidelity, lower-effort input, but it remains a material X Terms and account-enforcement risk even if it never scrolls, calls a private endpoint, reads cookies, or performs an account action. It may be built and tested against synthetic fixtures after Gate 0, but it must remain disabled for live X until the later user-supervised acceptance gate. This is an engineering recommendation, not legal advice or a statement that X has authorized the design.

The local analyzer should own the post schema, provenance, deduplication, scoring, redaction, SQLite history, report generation, and export of a separately sanitized analysis packet. The extension should be deliberately thin: observe visible DOM, normalize only structural fields, retain a bounded local queue, and export data. No collector should browse links or allow captured content to select tools, execute code, alter configuration, or become instructions.

## Research boundary and evidence

Research was completed on September 12, 2026. The private `Analyze Twitter Feed` conversation was read through the task-history interface. Its recording attachments were not opened or processed. The chat is treated as untrusted product evidence, not as current policy or implementation authority.

The repository baseline says the prior workflow classified 96 and 118 unique organic top-level post units in two recordings while excluding 17 and 19 promoted cards. Those aggregate counts support the usefulness of sequential review, deduplication, uncertainty labels, verification, and per-post scoring. They do not prove automated OCR, browser collection, or live-site acceptance.

Current platform facts were rechecked against X's Terms, X developer documentation, browser-vendor documentation, Apple documentation, official project sites, and upstream repositories. Upstream READMEs are evidence of a project's design and claimed behavior; they are not proof that the behavior is permitted by X or safe for this product.

## Current X policy and API facts

As of the research date, the Terms effective April 10, 2026 remain current until October 9, 2026. They prohibit accessing or searching the service by automated or other means outside X's published interfaces and expressly prohibit crawling or scraping without prior written consent. They also permit X to suspend or terminate access for violations. The already-published October 9 revision preserves the scraping prohibition and adds language about responsibility for features that perform autonomous actions.[^x-tos] [^x-update]

X's current Developer Guidelines are even more direct: their example table labels a browser-automation scraper as a permanent-suspension case, and the text says non-API automation, including scraping and browser automation, results in permanent suspension.[^x-guidelines] The probability and exact target of enforcement in an individual local, read-only case are not published. The consequence is nonetheless severe enough that "passive" must not be presented as "permitted" or "account-safe."

The official X API now uses credit-based, pay-per-use pricing. Current list prices are $0.005 per Post read, $0.010 per User read, and $0.005 per Media read. The same resource is ordinarily deduplicated within a UTC day, but X calls that a soft guarantee. The home-timeline endpoint is not in the published $0.001 Owned Read list.[^x-pricing]

The official home timeline returns followed accounts in reverse chronological order, covers up to 3,200 posts or seven days, requires user authentication, and explicitly excludes algorithmic ranking.[^x-timeline] It therefore does not reproduce the personalized `For You` surface that the recordings capture. A rough rich 100-post run—100 posts, 60 users, 50 media objects, and 15 separately returned quoted posts—would be approximately $1.425 at the posted unit rates before analysis cost. That is an estimate, not a quote; actual response composition and billing must be confirmed in the Developer Console before any purchase. No API purchase is authorized in this project.

## Weighted decision framework

Scores use 1 (poor) through 5 (strong). Policy/account safety is weighted most heavily because a technically excellent collector is not useful if it puts the account at unacceptable risk. A higher score is always better; "policy safety" incorporates both Terms alignment and account-enforcement exposure.

| Criterion | Weight | Recording + local OCR | Passive exact-origin extension | Automated Playwright/Puppeteer | Private GraphQL client | Official X API | Native capture/accessibility | Local CLI alone | Hybrid extension + analyzer |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `For You` fidelity | 15 | 4 | 5 | 5 | 4 | 1 | 4 | 2 | 5 |
| Report field fidelity | 12 | 3 | 5 | 5 | 5 | 4 | 3 | 3 | 5 |
| Policy/account safety | 18 | 5 | 2 | 1 | 1 | 5 | 3 | 4 | 3 |
| Privacy/local control | 12 | 5 | 5 | 3 | 2 | 3 | 4 | 5 | 5 |
| Maintenance resilience | 10 | 4 | 3 | 2 | 1 | 5 | 2 | 4 | 4 |
| User effort | 8 | 2 | 5 | 5 | 5 | 4 | 2 | 3 | 4 |
| Media/text completeness | 8 | 4 | 4 | 4 | 4 | 4 | 4 | 3 | 5 |
| Portability/accessibility | 6 | 4 | 4 | 3 | 4 | 4 | 1 | 5 | 4 |
| Packaging footprint | 5 | 3 | 4 | 1 | 4 | 4 | 2 | 5 | 3 |
| CPU/storage efficiency | 6 | 2 | 5 | 2 | 5 | 5 | 2 | 5 | 4 |
| **Weighted total / 500** | **100** | **385** | **407** | **316** | **318** | **377** | **294** | **371** | **424** |

The hybrid ranks first because it preserves an account-safe fallback and combines high-fidelity visible-post capture with a reusable local analysis core. Its score does not erase the extension's Terms risk. The design earns a higher policy score than the extension alone only because the extension is optional, disabled for live use through Gate 2, and not required for the product to function.

## Candidate analysis

### 1. Screen-recording processing

**Report fidelity.** Recordings preserve the exact personalized surface, visual hierarchy, ads, images, video frames, community notes, quote layout, and what was actually visible. They are also lossy: fast motion, compression, occlusion, repeated frames, truncated text, and absent semantic identifiers can defeat OCR. Original/repost/quote identity and promoted labels must be inferred from pixels and layout rather than stable structured fields.

**Proposed pipeline.** First probe duration, frame rate, dimensions, and codecs. Select candidate frames using bounded time sampling plus change/scene metrics; then crop only a user-confirmed feed region. Run OCR with bounding boxes and confidence. Segment candidate post cards, track them across adjacent frames, and merge only when multiple signals agree. Preserve frame timestamp, crop coordinates, OCR confidence, and merge rationale for every field. Send low-confidence or conflicting candidates to manual review rather than filling gaps.

FFmpeg is the best initial decoder and sampler, but distribution is conditional on LGPL compliance and codec configuration. Apple Vision is the preferred OCR engine on macOS because it processes on-device, returns confidence and bounding boxes, and offers fast/accurate modes.[^ffmpeg] [^apple-vision] PySceneDetect and OpenCV are useful only if a simpler FFmpeg/change-hash stage does not meet recall and CPU targets.

**Resources.** Video decode dominates CPU. OCR should run only on changed post regions, not every frame. The local raw recording should remain user-owned and outside the repository, with configurable retention and an explicit delete function later. Derived crops should be ephemeral by default.

**Verdict: adopt as the production-safe baseline.** It requires the most user effort, but it does not automate access to X and it preserves media context that DOM extraction can miss.

### 2. Passive exact-origin WebExtension

**Definition.** Passive means no programmatic scroll, clicks, navigation, refresh, network interception, private endpoint, cookie API, page-world injection, or social action. A content script observes DOM nodes that the page has already rendered. A post becomes collectible only when an `IntersectionObserver` reports meaningful viewport intersection. A `MutationObserver` detects newly rendered cards. Captured strings remain data.

**Activation.** Request `https://x.com/*` as an optional host permission through an explicit enable control. Register the content script only after that grant. When armed, it activates on the exact HTTPS origin; it pauses when the document is hidden, and it is destroyed when the tab navigates away or closes. A visible badge must show `armed`, `capturing`, `paused`, `limit reached`, or `error`. The extension must never broaden to `<all_urls>`, `twitter.com`, API hosts, local HTTP, or model-provider hosts without a new architecture decision. Browser documentation confirms that host access controls content-script injection and recommends optional permissions where possible.[^chrome-permissions] [^mdn-content]

**Data captured.** Capture only visible top-level post structure: displayed author name and handle, visible text, displayed timestamp/permalink identifier when present, original/repost/quote relationship, visible media type/alt text/poster reference, displayed engagement counts as weak context, promoted label, community-note text, viewport timestamp, and parser confidence. Do not fetch expanded text, media, hidden accessibility nodes, replies, notifications, DMs, or profile data. Do not read request headers, cookies, local storage owned by X, or GraphQL responses.

**Fidelity and limitations.** DOM capture is strongest for complete text, IDs, relationships, and deduplication. It can miss content rendered inside video, image text, collapsed text, content removed before intersection, and semantic changes when X modifies markup. The extractor therefore needs versioned adapters, fixture contracts, and fail-closed parser health checks. It must not silently emit empty or misattributed posts when selectors drift.

**Risk.** This is still systematic extraction from X and can reasonably be treated as scraping under the Terms. Avoiding automation and private APIs reduces technical behavior and credential exposure, but does not create permission. Ban/detection likelihood is unknown; consequence is high. Live use remains a user-supervised acceptance decision.

**Verdict: conditional.** Build only against synthetic fixtures through Gate 2. It is the recommended low-friction input if the user later accepts the documented residual risk.

### 3. Automated Playwright or Puppeteer scrolling

Browser automation could open the real feed, scroll, wait for cards, recover structured DOM, and finish without user effort. It also creates the clearest non-API automation fact pattern, increases fingerprint/detection signals, requires an authenticated profile or session, consumes substantial memory, downloads or controls browser binaries, and is sensitive to timing, challenges, and DOM changes.

Using a user's normal profile would expose unrelated cookies and history; copying a profile or exporting cookies is prohibited. An automation profile would need its own login and creates challenge risk. Headless/headful distinctions do not solve the Terms issue. Stealth plugins, proxy rotation, residential IPs, fingerprint patches, and CAPTCHA services are expressly outside scope.

**Verdict: reject for live X.** Playwright may be adopted solely as a synthetic-fixture integration-test runner. Puppeteer is a capable alternative but adds no product advantage once Playwright is selected.

### 4. Direct private GraphQL or web clients

Twikit, tweetkit-x, XActions, and XClipper's optional fast mode demonstrate that private web calls can return complete text, media, relationships, and timeline data with low CPU. They also require or derive live session material, replay undocumented endpoints, track rotating query identifiers and transaction logic, and commonly expose write-capable surfaces. Upstream history and open issues show the maintenance burden; their own documentation warns of challenges or suspension.

The approach conflicts with the explicit architecture boundary: no cookie export, auth-header capture, private-API replay, challenge bypass, or account actions. Its low runtime cost does not compensate for credential blast radius, brittle behavior, and policy risk.

**Verdict: reject.** These projects may inform risk analysis and generic normalized schemas, but no source or private-endpoint logic should be copied.

### 5. Official X API

The API is the best-supported, lowest account-policy-risk programmatic route. It provides stable identifiers, text, relationships, expansions, media metadata, and documented authentication. It also costs money, requires a developer app and user authorization, and does not reproduce algorithmic `For You`. It would therefore change the product question from "what did the recommender show me?" to "what did followed accounts publish recently?"

**Verdict: reject for the initial product objective.** Retain as a future optional adapter only if the user separately authorizes paid access and accepts the feed-coverage change.

### 6. Native macOS/iOS capture or accessibility

A native macOS app is useful as a container for Apple Vision, SQLite, file retention, report review, and optional Safari-extension packaging. ScreenCaptureKit can capture a chosen window but requires Screen Recording permission; Apple's sample documents a first-run permission prompt and restart.[^apple-capture] Accessibility APIs expose UI elements and actions, but require powerful Accessibility permission and depend on what browsers expose through their accessibility trees.[^apple-ax]

System-wide capture or accessibility increases privacy scope beyond a one-origin extension and can observe unrelated windows, notifications, or controls. On iOS, a native app cannot quietly inspect another app's feed; Safari WebExtensions are supported on iOS 15 and later but must be packaged in an app, enabled by the user, and signed for device testing/distribution.[^apple-safari]

**Verdict: conditional as packaging/analyzer UI, reject as the primary collector.** A native shell should be added only after the CLI proves value and the permission cost is justified.

### 7. Local CLI or application

A CLI is the smallest dependable home for video jobs, SQLite migrations, deterministic analysis, local retention, redaction, report export, and validation. It is portable and easy to audit. Its weakness is discoverability and browser integration, not analysis capability.

The first analyzer should expose explicit commands such as `ingest-recording`, `ingest-packet`, `review`, `report`, `export-sanitized`, `purge-session`, and `doctor`. Commands are examples of product boundaries, not implementation completed in Gate 0. Any future local GUI should call the same core rather than fork the data model.

**Verdict: adopt.** Prefer a small local application core with a CLI first; keep the native GUI optional.

### 8. Hybrid passive extension plus local analyzer

The extension and recording pipeline should terminate in the same versioned envelope. The core must not care whether a field came from OCR, visible DOM, or manual correction; it must care about provenance and confidence. This makes it possible to compare the same browsing session's extension output with a user-supplied recording during later supervised acceptance.

The extension need not open a localhost server or request native messaging in the first release. It can export a bounded JSON packet by explicit user action. The local analyzer imports it, validates the schema, writes SQLite transactionally, and generates a report. This avoids background daemons, inbound ports, and a powerful native-messaging bridge.

**Verdict: recommended, with live extension use gated.** It has the best long-term fidelity/effort profile while preserving a fully useful recording-only product.

## Data model and deduplication direction

The normalized model should separate four identities:

- `observed_unit_id`: one top-level card appearance in an input session;
- `post_id`: canonical platform identifier when safely available, otherwise a local content fingerprint;
- `original_post_id` and `original_author`: source of a repost or quote;
- `presenting_author`: reposter or quoting account that caused the unit to appear.

A quote card plus its embedded source is one top-level scored unit, with two linked identities. If the source later appears independently, that independent appearance is deduplicated as a post but retained as a separate observation for feed-frequency analysis. Ads are stored in a separate ledger and excluded from organic denominators. Deduplication must use a priority ladder: stable post ID; canonical permalink; exact normalized identity/text/media tuple; then conservative similarity with human review. OCR similarity alone must never merge different short posts.

## Prompt-injection and privacy architecture

Captured text, URLs, alt text, code blocks, QR payloads, profile fields, and linked repository text are untrusted. The collection process has no browsing or execution tools. The analyzer must use typed fields, quote/escape captured text in prompts, and keep instructions in a separate trusted channel. A downstream model must be told that records cannot alter goals, tools, or policy, but deterministic tool authorization—not prompt wording—must enforce the boundary.

Default collection excludes cookies, authorization headers, DMs, notifications, email addresses outside a post, payment/account surfaces, hidden text, and unrelated page chrome. The extension captures no media binaries by default. The recording pipeline crops early and avoids retaining full-frame derivatives. Local databases and reports are excluded from Git/CI. Logs contain counts, parser versions, timing, and error codes—not post text or handles.

The private packet and shareable packet are different artifacts. A private packet may retain handles and post IDs for local follow recommendations. A sanitized packet should pseudonymize handles, remove query strings and tracking URLs, omit media, reduce timestamps, flag redactions, and include a manifest of omitted fields. Sanitization must be tested against synthetic secrets and PII patterns; it is a minimization aid, not a guarantee that free text contains no identity clues.

## Retention, accessibility, and resource targets

Gate 1 should choose explicit retention defaults rather than silently retaining history. A reasonable proposal is: ephemeral extracted frames deleted after import; raw recordings never copied unless requested; extension queue capped by post count and age; private SQLite retained locally until explicit deletion; sanitized exports user-created. SQLite secure deletion behavior and backup semantics need documented tests before promising erasure.

The report UI must be keyboard navigable, screen-reader labeled, high-contrast, and usable without color. Every classification needs a text label; every media-only post needs an uncertainty path. Export Markdown and JSON first. HTML can follow if it is static, self-contained, escaped, and contains no active remote content.

Provisional performance budgets for synthetic evaluation are: no more than 2% mean CPU while an X tab is idle; no polling loop faster than DOM events require; a default 250-post queue; no raw media download; bounded recording workers; and no more than one concurrent OCR job by default on a laptop. These are targets to measure, not observed performance.

## Adoption summary

The strongest reuse candidates are WXT for cross-browser extension packaging, FFmpeg for media probing and frame extraction, Apple Vision for macOS OCR, SQLite for local durable state, and Playwright for synthetic extension tests only. PySceneDetect, OpenCV, GRDB, and Tesseract are conditional. XClipper is a useful reference for content modeling and permission review, but its missing root license text and optional auth-header/private-API path preclude source reuse. XActions, Twikit, tweetkit-x, live-site Playwright/Puppeteer automation, stealth packages, CAPTCHA services, and private GraphQL clients are rejected.

No upstream source is copied in Gate 0. Any Gate 1 dependency proposal must pin an exact version, record a source hash, preserve the license and notices, generate a third-party notice entry, and pass a fresh vulnerability/advisory review.

## Sources

[^x-tos]: X Corp., [X Terms of Service](https://x.com/en/tos), current terms effective April 10, 2026 and published revision effective October 9, 2026; accessed September 12, 2026.
[^x-update]: X Privacy Center, [Updates to Our Terms of Service](https://privacy.x.com/en/blog/2026/terms-updates), September 9, 2026.
[^x-guidelines]: X, [Developer Guidelines](https://docs.x.com/developer-guidelines), accessed September 12, 2026.
[^x-pricing]: X, [X API pay-per-usage pricing and credits](https://docs.x.com/x-api/getting-started/pricing), accessed September 12, 2026.
[^x-timeline]: X, [Timelines](https://docs.x.com/x-api/posts/timelines/introduction), accessed September 12, 2026.
[^ffmpeg]: FFmpeg Project, [FFmpeg License and Legal Considerations](https://ffmpeg.org/legal.html) and [Download FFmpeg](https://ffmpeg.org/download.html), accessed September 12, 2026.
[^apple-vision]: Apple, [Recognizing Text in Images](https://developer.apple.com/documentation/vision/recognizing-text-in-images), accessed September 12, 2026.
[^chrome-permissions]: Chrome for Developers, [Declare permissions](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions), accessed September 12, 2026.
[^mdn-content]: Mozilla, [Content scripts](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Content_scripts), accessed September 12, 2026.
[^apple-capture]: Apple, [Capturing screen content in macOS](https://developer.apple.com/documentation/screencapturekit/capturing-screen-content-in-macos), accessed September 12, 2026.
[^apple-ax]: Apple, [AXUIElement.h](https://developer.apple.com/documentation/applicationservices/axuielement_h), accessed September 12, 2026.
[^apple-safari]: Apple, [Safari web extensions](https://developer.apple.com/documentation/safariservices/safari-web-extensions) and [Running your Safari web extension](https://developer.apple.com/documentation/safariservices/running-your-safari-web-extension), accessed September 12, 2026.
