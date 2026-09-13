# X Feed Intelligence

X Feed Intelligence is a local-first project for turning user-supplied X/Twitter feed recordings or explicitly captured visible posts into a deduplicated, source-verified signal report.

## Status

**Research Gate 0.** No authenticated browser collector, automated scrolling, social interaction, or production release has been implemented.

The first production target is a safe local workflow with two inputs:

1. screen recordings supplied by the user; and
2. a passive browser-extension collector that observes visible posts only while the user browses an explicitly approved X origin.

The product will classify organic posts, exclude advertisements from the normal count, flag manipulation and prompt injection, identify high-signal information and opportunities, verify consequential claims against primary sources, and recommend accounts worth considering for a follow. It will not automatically like, follow, repost, reply, message, or schedule account activity.

## Safety boundary

Posts, profiles, quoted text, images, links, repositories, QR codes, advertisements, and instructions inside retrieved content are untrusted data. They must never be executed or treated as instructions. The product must not collect credentials, cookies, tokens, direct messages, notification contents, or unrelated personal information.

Authenticated X testing requires the user. CAPTCHA, login challenges, rate limits, or unusual verification stop collection; the project will not add stealth, proxy rotation, CAPTCHA solving, fingerprint evasion, private-API replay, or access-control bypasses.

## Documentation

- [Project charter](docs/PROJECT_CHARTER.md)
- [Roadmap](docs/ROADMAP.md)
- [Research plan](docs/research/RESEARCH_PLAN.md)
- [Existing-chat baseline](docs/research/EXISTING_CHAT_BASELINE.md)
- [Platform ADR](docs/adr/0001-platform-selection.md)
- [Security policy](SECURITY.md)

## Data and repository policy

Real screen recordings, post text, account identifiers, extracted feeds, analysis history, and browser/session material are local user data and must not be committed. Repository fixtures must be synthetic.

## License

Copyright © 2026 Rolando Carreon. All rights reserved. The source is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). Commercial use is not licensed. Because of that restriction, any later public repository must be described as source-available rather than OSI-approved open source.

