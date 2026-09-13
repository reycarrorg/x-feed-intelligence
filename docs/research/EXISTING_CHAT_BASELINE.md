# Existing Analyze Twitter Feed Chat Baseline

Source conversation: `Analyze Twitter Feed`, conversation ID `6aa46df5-6368-83ea-9d74-f758d6542de0`.

The conversation and its attachments are private evidence. They are not copied into this repository and must be treated as untrusted data.

## Proven workflow evidence

The chat successfully analyzed two user-supplied X feed screen recordings. One report reliably classified 96 unique organic posts and excluded 17 promoted posts. A later report classified 118 unique organic posts and excluded 19 promoted cards. Both used sequential review, deduplication, uncertainty labels, source verification for consequential claims, opportunity extraction, and a post-level scoring ledger.

This is evidence that the report specification is useful. It is not evidence that OCR or automated browser capture is already implemented.

## Existing product requirements

- Read-only analysis.
- No X login or account interaction during recording analysis.
- Posts and on-screen instructions treated as untrusted data.
- Incidental private information omitted.
- Ads excluded from the organic count.
- Original/repost/quote identity distinguished.
- High-signal, verify-first, community, slop, unsafe, and insufficient classifications.
- Important claims checked against primary sources.
- Opportunities and accounts worth considering for a follow surfaced without performing the follow.

## Unverified proposal from the chat

The chat proposed a local browser collector and identified XClipper, XActions, Twikit, and tweetkit-x as potential references. It also warned that automated extraction may conflict with X's current terms and that private web interfaces are brittle. Gate 0 must revalidate every material claim, repository, license, and current policy before architecture or reuse decisions.

