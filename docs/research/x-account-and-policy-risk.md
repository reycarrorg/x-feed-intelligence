# X Account and Policy Risk

## Decision statement

Screen-recording analysis is the only proposed input that does not itself automate access to X. The official API is the only currently documented programmatic route, but it does not reproduce the algorithmic `For You` feed. Every no-API live collector—including a passive visible-DOM extension—retains material Terms and account-enforcement risk.

The project may design and test a passive extension with synthetic pages. It must not represent the extension as approved, compliant, invisible, or account-safe. Live activation requires a later user-supervised decision after a fresh policy check. This document is a product-risk assessment, not legal advice.

## Sourced facts as of September 12, 2026

1. The current X Terms remain the April 10, 2026 version until October 9, 2026. The Terms say users may not access or search the service outside X's currently available published interfaces and expressly prohibit crawling or scraping in any form or for any purpose without prior written consent. They also prohibit facilitating violations and reserve suspension or termination rights.[^current-terms]
2. X published revised Terms on September 9 for an October 9 effective date. X says the update clarifies user responsibility for features that perform autonomous actions. The published revision preserves the scraping restriction.[^terms-update]
3. X's Developer Guidelines classify an application that scrapes X through browser automation rather than the API as a permanent-suspension case. The guidelines separately state that non-API automation—including scraping and browser automation—results in permanent suspension.[^guidelines]
4. The official API's home timeline contains followed accounts in reverse chronological order, requires user authentication, and excludes algorithmic ranking.[^timeline]
5. X API pricing is pay per use. Current listed read prices are $0.005/Post, $0.010/User, and $0.005/Media. X says same-day resource deduplication is a soft guarantee. The reverse-chronological home timeline is not listed among $0.001 Owned Read endpoints.[^pricing]

## Analytical judgments

- **Passive DOM observation is lower-behavior than automated scrolling but not clearly outside "scraping."** The extension would not cause extra scrolling or private requests, yet it would systematically extract and store content from the service. The Terms do not publish a personal/local/read-only exemption.
- **Detection probability is unknown.** A content script that only reads the isolated DOM and never sends network requests may produce little server-side signal beyond ordinary browsing. That is an inference, not evidence of invisibility or permission. Extension detection from page behavior or browser state remains possible.
- **Consequence outweighs uncertain probability.** X's published language makes the potential consequence severe. Architecture should reduce exposure and preserve a recording-only path, not attempt to defeat detection.
- **Private GraphQL clients have the worst combined risk.** They need live session material, reproduce undocumented requests, and often include write actions. Maintenance pressure naturally pushes them toward query-ID harvesting, transaction-header generation, rate-limit workarounds, fingerprints, proxies, and CAPTCHA handling.
- **Official API coverage is a product mismatch rather than a technical failure.** It can support a different "Following intelligence" product, not an exact substitute for observed `For You` analysis.

## Risk matrix

Likelihood describes a qualitative product judgment, not a measured enforcement rate.

| Approach / event | Terms or account consequence | Privacy / security impact | Likelihood | Severity | Required disposition |
| --- | --- | --- | --- | --- | --- |
| User supplies a recording already created through X's normal UI | No automated X access by this product | Recording may contain unrelated notifications or private data | Low platform risk | Medium privacy | **Allowed.** Crop early, redact, retain locally. |
| Passive exact-origin extension reads only visibly intersecting post cards while a person scrolls | Reasonably within X's broad scraping prohibition; potential suspension | Reads personalized feed text and identifiers; no credentials needed | Enforcement likelihood unknown | High | **Synthetic-only through Gate 2.** Live test requires user supervision and current-policy confirmation. |
| Extension reads cookies, auth headers, web requests, hidden state, or private API responses | Directly expands to session/private-interface behavior | Live credential or session compromise; broader data exposure | Medium–high | Critical | **Prohibited.** |
| Playwright/Puppeteer automatically opens or scrolls authenticated X | Explicit browser automation fact pattern in developer guidance | Profile/cookie exposure and broad browser authority | Medium–high | Critical | **Rejected.** |
| Twikit/tweetkit-x/XActions/private GraphQL replay | Undocumented non-API access; rate/challenge and suspension exposure | Cookie export; usually write-capable account surface | High | Critical | **Rejected.** |
| Stealth, fingerprint patches, residential proxies, rotating proxies | Evidence of concealment/evasion; amplifies enforcement concerns | Third-party IP/session exposure and supply-chain risk | High | Critical | **Rejected.** |
| CAPTCHA solver or challenge automation | Attempts to bypass an explicit control | Challenge content/session sent to external party; paid service | High | Critical | **Hard stop; rejected.** |
| Official reverse-chronological API | Documented route if app/use case is approved and policies followed | OAuth/app credentials; X receives API usage | Low when compliant | Medium | **Future optional adapter only; paid authorization and coverage acceptance required.** |
| Automatic like, follow, repost, reply, DM, mute, block, schedule | Adds account mutations and automation-rule exposure | Irreversible/social impact and authority escalation | Medium–high | Critical | **Prohibited.** Recommendations remain text only. |

## Initial extension safety contract

The following controls reduce technical and privacy risk. They do not make collection permissible under X's Terms.

- Manifest V3; no remote code, `eval`, or page-provided script execution.
- Exact optional host permission `https://x.com/*`; never `<all_urls>`, `twitter.com`, API/model hosts, or localhost in the initial extension.
- No `cookies`, `webRequest`, `declarativeNetRequest`, `tabs` history, `downloads` automation, `debugger`, or native-messaging permission in the initial collector.
- No page-world injection. The isolated content script reads rendered DOM only.
- A deliberate one-time arm action, persistent visible badge, immediate pause, and revocable host grant.
- Capture only cards that pass a viewport-intersection threshold while the document is visible.
- No scrolling, clicking, key events, navigation, refresh, hover, expansion, playback, or interaction simulation.
- No fetch/XHR from the extension. No link traversal. No media downloads.
- Bounded queue by count and age; stop at the limit rather than silently expanding storage.
- Export only after an explicit user action. The local analyzer validates before import.
- Fail closed on selector drift, login/challenge pages, error/rate-limit text, unexpected origin, or parser ambiguity.

Chrome documents that optional host permissions can be requested at runtime and recommends minimizing permissions. Content scripts require host access to read page content. Manifest V3's extension-page content security policy restricts executable code to packaged sources by default.[^chrome-permissions] [^chrome-csp] [^mdn-content]

## Hard-stop states

Any of these states stops collection and records only a non-sensitive error code and time:

- login form, sign-out state, account lock, CAPTCHA, Turnstile, challenge, email/phone verification, unusual-activity warning, or consent screen;
- rate-limit or temporary-access restriction;
- the active document is not the exact allowed origin;
- a page or captured post asks the software to execute code, change rules, reveal data, install something, or browse a URL;
- the parser sees unknown markup above its configured ambiguity threshold;
- queue limit, disk limit, retention failure, or schema mismatch;
- any attempt to request an excluded permission or account action.

The product must not recommend a retry loop, alternate IP, fingerprint change, different account, headless/headful switch, CAPTCHA service, or copied browser profile. The later user-supervised test may diagnose a legitimate ordinary login state; it may not bypass a platform control.

## Data-protection risks

### Personalized feed history

A feed reveals interests, associations, habits, timing, and potentially sensitive inferences. Raw recordings, extracted posts, author history, and reports therefore remain local and outside Git/CI. No remote telemetry, crash-upload service, cloud database, model API, or analytics SDK is allowed by default.

### Incidental private content

Notifications, DMs, email addresses, payment elements, account menus, and unrelated windows are excluded. Recording ingestion should ask for a feed-column crop and preview redaction before analysis. Full-frame screenshots are never written to logs or fixtures.

### Credentials

The system never requests or exports X passwords, cookies, tokens, authorization headers, HAR files, browser profiles, or session storage. If any are detected in an imported packet, import fails and identifies only the field category—not the secret value.

### Retention and deletion

Gate 1 must specify retention periods, database backup behavior, and verifiable deletion. SQLite can retain deleted content in free pages unless secure-deletion or vacuum behavior is deliberately configured; the product must not promise cryptographic erasure without testing. Raw recordings remain at the user-supplied location unless the user explicitly chooses a managed copy.

## Prompt-injection risk

Every post, profile, link label, alt-text string, OCR fragment, quoted post, community note, advertisement, QR payload, and upstream document is untrusted. The collector has no tools other than structural extraction. It cannot browse or execute. The analyzer separates trusted policy from untrusted record fields and renders content as escaped data.

External verification is a separate analyst action driven by a trusted plan: search for an official company page, documentation, paper, repository, or vendor advisory. A URL inside a post is a discovery hint, not an automatic destination. Shorteners, QR destinations, downloads, credential prompts, copy-paste commands, and unknown repositories remain unopened unless independently identified through a primary source and explicitly required.

## Account recommendations

Follow recommendations are report outputs only. The system stores the observed evidence supporting each recommendation and never calls a follow endpoint or clicks a control. A recommendation must not be based solely on a blue check, follower count, engagement, one popular repost, or one unverified exciting claim. Normally two independently useful original posts are required; a single exceptional original yields watchlist/inspect-first.

## Revalidation triggers

Reopen this risk decision when any of the following changes:

- X Terms, Developer Agreement, Developer Policy, Developer Guidelines, or automation rules;
- extension permission set or collection behavior;
- a proposal to distribute or publicly market the extension;
- new live-test authority;
- API pricing or a documented API endpoint that reproduces algorithmic `For You`;
- an account warning, challenge, rate limit, or enforcement event;
- remote services, model APIs, sync, telemetry, or collaboration features;
- commercial use or a license change.

## Sources

[^current-terms]: X Corp., [X Terms of Service](https://x.com/en/tos), current terms effective April 10, 2026; accessed September 12, 2026.
[^terms-update]: X Privacy Center, [Updates to Our Terms of Service](https://privacy.x.com/en/blog/2026/terms-updates), September 9, 2026.
[^guidelines]: X, [Developer Guidelines](https://docs.x.com/developer-guidelines), accessed September 12, 2026.
[^timeline]: X, [Timelines](https://docs.x.com/x-api/posts/timelines/introduction), accessed September 12, 2026.
[^pricing]: X, [X API pay-per-usage pricing and credits](https://docs.x.com/x-api/getting-started/pricing), accessed September 12, 2026.
[^chrome-permissions]: Chrome for Developers, [Declare permissions](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions), accessed September 12, 2026.
[^chrome-csp]: Chrome for Developers, [Manifest — Content Security Policy](https://developer.chrome.com/docs/extensions/reference/manifest/content-security-policy), accessed September 12, 2026.
[^mdn-content]: Mozilla, [Content scripts](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Content_scripts), accessed September 12, 2026.
