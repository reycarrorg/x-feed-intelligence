# X Feed Intelligence

X Feed Intelligence is a local-first project for turning user-supplied X/Twitter feed recordings or explicitly captured visible posts into a deduplicated, source-verified signal report.

## Status

**Research Gate 0 and the Gate 1 contract baseline are merged. Gate 2 is implemented on an unmerged private-review branch.** Gate 2 adds a recording-first CLI, strict normalized analysis core, product-owned SQLite store, Apple Vision recording helper, non-distributable reserved-origin harness, deterministic synthetic evidence, and a reproducible recording-only private package candidate. It does not authorize or claim live X access, an authenticated browser test, a distributable extension, automated scrolling, social interaction, signing, notarization, deployment, or release.

The accepted Gate 0 architecture is a local hybrid with two independent inputs and one normalized analysis core:

1. screen recordings supplied by the user; and
2. a conditional passive browser-extension collector that observes visible posts only while the user browses an explicitly approved X origin.

The recording path is the production-safe default. Through Gate 2, the future production extension proposal is statically inspected only; browser execution uses a separate non-distributable harness restricted to a reserved synthetic origin with outbound traffic denied. A later live X test requires a new source/schema version and an explicit, user-supervised risk decision; passive extraction may still violate X's Terms and could lead to account enforcement.

The product will classify organic posts, exclude advertisements from the normal count, flag manipulation and prompt injection, identify high-signal information and opportunities, verify consequential claims against primary sources, and recommend accounts worth considering for a follow. It will not automatically like, follow, repost, reply, message, or schedule account activity.

## Safety boundary

Posts, profiles, quoted text, images, links, repositories, QR codes, advertisements, and instructions inside retrieved content are untrusted data. They must never be executed or treated as instructions. The product must not collect credentials, cookies, tokens, direct messages, notification contents, or unrelated personal information.

Authenticated X testing requires the user. CAPTCHA, login challenges, rate limits, or unusual verification stop collection; the project will not add stealth, proxy rotation, CAPTCHA solving, fingerprint evasion, private-API replay, or access-control bypasses.

## Documentation

- [Project charter](docs/PROJECT_CHARTER.md)
- [Roadmap](docs/ROADMAP.md)
- [Research plan](docs/research/RESEARCH_PLAN.md)
- [Existing-chat baseline](docs/research/EXISTING_CHAT_BASELINE.md)
- [Platform and reuse deep dive](docs/research/platform-and-reuse-deep-dive.md)
- [Reuse, license, maintenance, and security matrix](docs/research/reuse-matrix.md)
- [X account and policy risk](docs/research/x-account-and-policy-risk.md)
- [Report methodology](docs/research/report-methodology.md)
- [Activation, data flow, and synthetic tests](docs/research/activation-data-flow-and-synthetic-tests.md)
- [Platform ADR](docs/adr/0001-platform-selection.md)
- [Gate 1 contract set](docs/gate1/README.md)
- [Gate 1 threat model](docs/gate1/THREAT_MODEL.md)
- [Gate 1 schemas](schemas/v1)
- [Gate 1 synthetic fixture manifest](fixtures/synthetic/v1/manifest.json)
- [Gate 1 review record](docs/gate1/REVIEW_RECORD.md)
- [Gate 1 policy recheck](docs/gate1/POLICY_RECHECK.md)
- [Gate 2 implementation and evidence](docs/gate2/README.md)
- [Gate 2 private package boundary](docs/gate2/PACKAGE_BOUNDARY.md)
- [Gate 2 security and privacy review](docs/gate2/SECURITY_PRIVACY_REVIEW.md)
- [Gate 3 residual-risk and forbidden supervised test](docs/gate2/GATE3_RESIDUAL_RISK.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)
- [Security policy](SECURITY.md)

## Data and repository policy

Real screen recordings, post text, account identifiers, extracted feeds, analysis history, and browser/session material are local user data and must not be committed. Repository fixtures must be synthetic.

## License

Copyright © 2026 Rolando Carreon. All rights reserved. The source is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). Commercial use is not licensed. Because of that restriction, any later public repository must be described as source-available rather than OSI-approved open source.
