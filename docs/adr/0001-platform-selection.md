# ADR 0001: Local Hybrid Platform with Recording-First Delivery

- Status: Accepted; implemented by the Gate 1 contract baseline
- Decision date: 2026-09-12
- Scope: Architecture selection only; no live X collector is approved

## Context

The product must turn a user's personalized X feed into a complete, deduplicated, source-verified signal report. The proven input is a user-supplied screen recording. A lower-friction visible-post collector is desirable, but the project will not export credentials, replay private endpoints, automate scrolling, perform social actions, evade controls, use paid services without authority, or place personalized data in Git or remote telemetry.

Current X Terms broadly prohibit automated or other access outside published interfaces and prohibit scraping without prior written consent. X Developer Guidelines describe non-API scraping/browser automation as a permanent-suspension case. The documented API is policy-favored but its home timeline is reverse chronological and excludes algorithmic ranking, so it does not reproduce the observed `For You` surface. A passive content script has materially less behavior and credential exposure than browser automation or private GraphQL, but its extraction can still be treated as scraping.

Eight candidates were compared using weighted fidelity, policy/account safety, privacy, resilience, effort, completeness, portability, footprint, and resource criteria. The detailed evidence is in the [platform deep dive](../research/platform-and-reuse-deep-dive.md), [reuse matrix](../research/reuse-matrix.md), and [account-risk assessment](../research/x-account-and-policy-risk.md).

## Decision

Adopt a **local hybrid with two independent inputs and one normalized analysis core**:

1. **Production-safe baseline:** user-supplied recording ingestion using bounded FFmpeg sampling and Apple Vision OCR on macOS, with conservative card tracking and human review.
2. **Conditional low-friction input:** a thin Manifest V3 extension that observes only visibly intersecting top-level cards on an explicitly granted exact X origin while the person scrolls normally.
3. **Shared local core:** a CLI-first analyzer that validates versioned packets, records provenance and uncertainty in SQLite, deduplicates, supports review, scores and verifies claims, and exports private and separately sanitized reports.

The recording path must remain independently useful. The extension may be implemented and tested against synthetic local fixtures in Gate 2, but it is disabled for live X through Gate 2. Any Gate 3 live test is a separate, explicit, user-supervised risk acceptance after a current policy recheck. This ADR is an engineering decision, not legal advice or written permission from X.

The initial bridge from extension to analyzer is an explicit bounded JSON export/import. Do not add localhost listeners or native messaging until a later decision demonstrates a need and analyzes the enlarged permission boundary.

## Extension constraints

- Manifest V3, packaged code only, isolated content script.
- Exact optional host permission `https://x.com/*`; no `<all_urls>`, legacy domains, X API hosts, model-provider hosts, or localhost.
- No cookies, authorization headers, request interception, page-world injection, private APIs, browser-profile copy, hidden state, or media download.
- No scrolling, clicks, navigation, hover, expansion, playback, refresh, retries, or account mutations.
- Explicit arm/start/export/stop controls and an always-visible lifecycle state.
- Collect only cards meeting a viewport-intersection threshold in a visible document.
- Bounded queue and duration; fail closed on login, challenge, rate limit, wrong origin, permission drift, parser drift, ambiguity, or resource limit.
- Captured content is escaped untrusted data and has no tool or execution authority.

These controls reduce behavior and privacy scope; they do not remove X Terms or enforcement risk.

## Reuse decisions

Adopt or conditionally adopt only narrow, well-maintained components after Gate 1 lockfile and notice review:

- Apple Vision for the first macOS OCR path;
- platform SQLite for local transactional storage;
- WXT as the leading extension build framework, conditional on dependency/permission audit;
- Playwright for synthetic local browser tests only;
- FFmpeg as a user-installed executable first, with any bundled distribution requiring a separate LGPL/configuration decision;
- OpenCV, PySceneDetect, and GRDB.swift only if benchmarks or platform selection demonstrate need.

Hold Tesseract until a supported release resolves the reviewed advisories. Treat Plasmo, Puppeteer, PaddleOCR, Mozilla Readability, and XClipper only as references. Do not copy private-interface/session logic from XClipper, XActions, Twikit, or tweetkit-x. Reject stealth plugins, anti-detection patches, undetected drivers, CAPTCHA services, proxies, account farms, and fingerprint profiles.

`THIRD_PARTY_NOTICES.md`, exact versions, lockfiles, source/license provenance, and an SBOM are required before the first dependency is accepted into implementation.

## Consequences

### Positive

- A useful recording workflow can ship without automating access to X.
- Both inputs share one report methodology, schema, local store, and privacy boundary.
- The extension has a narrow, inspectable capability set and no credential requirement.
- Synthetic testing can validate most lifecycle, parser, security, privacy, and performance behavior without touching a real account.
- Explicit provenance and confidence allow OCR and DOM evidence to coexist without pretending they are equally reliable.

### Costs and limitations

- Recording ingestion has higher user effort and imperfect text/identity fidelity.
- A passive extension still carries material residual Terms and account risk; enforcement probability is unknown and potential consequence is high.
- X markup changes can break the extension, so parser health and fail-closed behavior are product requirements.
- The official API is not an equivalent fallback for `For You` and would require separate paid authority.
- Two input paths increase test and packaging surface even with one shared core.
- Local-only processing makes backup, retention, deletion, and model/runtime packaging the project's responsibility.

## Alternatives rejected

- **Automated Playwright/Puppeteer on live X:** explicit non-API automation, authenticated profile exposure, browser cost, and challenge pressure. Playwright remains synthetic-test-only.
- **Private GraphQL/web clients:** credential/session exposure, undocumented endpoints, write-capable surfaces, high breakage, and policy risk.
- **Official API as the primary input:** documented and safer but does not reproduce algorithmic `For You`; also requires paid credits and app authorization.
- **Native screen/accessibility collector:** broader system permissions and incidental-data risk without better exact-feed semantics. A native analyzer UI remains optional later.
- **CLI alone:** suitable for analysis but cannot provide lower-friction in-browser collection.
- **Passive extension alone:** leaves no account-safe production path and loses recording-only media context.
- **Stealth, CAPTCHA, proxy, fingerprint, or account-farm methods:** incompatible with the product's safety boundary and explicitly prohibited.

## Gate implications

Gate 1 is limited to threat modeling, schemas, lifecycle/permission contracts, privacy and retention design, dependency notices, and deterministic synthetic evaluation. Its exact exit criteria are in the [activation and synthetic-test plan](../research/activation-data-flow-and-synthetic-tests.md).

No real-account access, extension installation into the user's normal profile, paid API use, or social action is approved by this ADR.

The Gate 1 baseline is indexed in the [Gate 1 contract set](../gate1/README.md). It preserves this ADR without adding a live collector or dependency. Gate 2 entry remains contingent on review and merge of those contracts and is limited to synthetic and explicitly user-supplied data.
