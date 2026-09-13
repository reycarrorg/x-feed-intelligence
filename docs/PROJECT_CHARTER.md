# Project Charter

## Mission

Build a local-first feed-intelligence tool that separates useful technical, AI, security, community, opportunity, and deal information from hype, slop, scams, and unsafe material without handing account credentials or personalized feed history to an unknown service.

## Product principles

1. User-supplied screen recording remains a fully supported, account-safe input.
2. Browser capture is passive, origin-scoped, visible, locally stored, and inactive when no approved X tab exists.
3. No private API replay, cookie extraction, stealth, automated scrolling in the initial product, CAPTCHA solving, proxy rotation, or anti-bot evasion.
4. No automatic likes, follows, reposts, replies, messages, or other account mutations.
5. Every post and linked resource is untrusted until independently reviewed.
6. Consequential claims are verified outside X using primary sources when practical.
7. Partial or unreadable material is marked uncertain rather than reconstructed.
8. Raw personalized data stays out of Git, diagnostics, and remote telemetry.

## Required report behavior

- Deduplicate posts across frames or repeated feed appearances.
- Distinguish original author, reposter, quoting account, and mentioned accounts.
- Exclude promoted posts from the organic count while separately noting unusual risks or value.
- Classify every legible unique organic post as high signal, promising/verify, community/light value, low-signal/slop, scam/manipulative/unsafe, or insufficient information.
- Score relevance, credibility, originality/information value, actionability, and risk.
- Surface top facts, opportunities, safe next actions, accounts to consider following, and accounts/signals to ignore or mute.
- Preserve uncertainty and source provenance.

## Hands-off authority and stop conditions

Research, documentation, local repository work, synthetic fixtures, implementation, tests, packaging, CI, and private GitHub synchronization may continue without repeated confirmation. Stop for the user before:

- signing into X or accessing an authenticated X tab;
- installing an extension into the user's normal browser profile;
- capturing a real personalized feed;
- changing account settings or performing any social interaction;
- spending money or using a paid API;
- making the repository public;
- shipping a release represented as accepted on the live X site.

