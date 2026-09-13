# Analysis, Deduplication, Verification, and Safety Contracts

## Versioned model

Schema version `1.0.0` is defined by the JSON Schemas in [`schemas/v1`](../../schemas/v1). The common definitions explicitly model author roles, repost/quote/source relationships, media without binaries, field provenance, promoted-card evidence, uncertainty, five-factor scores, verification, recommendations, and redactions. Sessions, observations, canonical posts, post analyses, import envelopes, and model handoffs have independent schemas so each boundary can reject unsupported versions.

Unknown schema versions, unknown fields, wrong types, duplicate IDs, dangling relationships, digest mismatch, and resource-limit violations are errors. Implementations must not coerce or silently discard them. Schema validation is necessary but does not replace semantic validation.

## Deterministic deduplication

The canonicalizer processes observations in ascending `(session_id, appearance_index, observation_id)` order. It preserves every observation and chooses the first applicable key:

1. `platform_id`: exact non-empty platform post identifier.
2. `canonical_permalink`: exact HTTPS permalink after lowercasing the scheme/host, removing the query and fragment, removing a trailing slash, and rejecting non-`x.com` or reserved `example.invalid` fixture hosts.
3. `exact_content_tuple`: SHA-256 of the NFC-normalized tuple `(original-or-presenting author identity, visible text, ordered media descriptors, displayed timestamp)`. Text normalization changes CRLF to LF and collapses Unicode whitespace runs, but preserves punctuation, numbers, usernames, negation, and case. The key is unavailable if author, text, or displayed timestamp is missing.
4. `temporal_layout_continuity`: candidate review only when the same source modality, author evidence, ordered media descriptors, and session are present; adjacent evidence is no more than 2,000 ms apart; normalized text is at least 80 characters; no digits, negation tokens, timestamps, handles, or media differ; and normalized Unicode-code-point Levenshtein similarity is at least 0.98, where `similarity = 1 - edit_distance / max(length_a, length_b)`. It is never an automatic merge for OCR-only evidence—`review_required` remains true until a human decision is recorded. Implementations may use a threshold-banded edit-distance algorithm but must produce the same accept/reject result.
5. `singleton`: no merge.

Conflicting platform IDs, author identities, numeric tokens, explicit negation tokens (`no`, `not`, `never`, `without`), timestamps, promotion status, or media descriptors block automatic merging. OCR similarity alone never merges text under 80 characters. Ties choose the lexicographically smallest already-created `local_post_id`; canonical output arrays and contributing observation IDs are sorted. Reordering inputs therefore cannot change the canonical result.

A human merge is a new auditable decision containing reviewer-local ID, time, reason, both prior canonical IDs, and contributing observation IDs. It never deletes the originals. Human split/merge decisions are outside the synthetic automatic metric denominator.

## Counting invariants

- Every accepted observation maps to exactly one canonical post.
- Every canonical post is exactly one of `organic`, `promoted`, or `ambiguous`; ambiguous promotion is reviewed and excluded from both definite counts until resolved.
- A quote plus embedded source is one top-level unit. The embedded source is linked, not counted again unless it later appears as a top-level observation.
- A repost is one presented unit with both presenting and original author roles.
- Promoted canonical posts are excluded from the organic denominator.
- `organic unique + promoted unique + ambiguous/insufficient/non-post exclusions = reviewed candidate units after duplicate consolidation`.

## Classification and scoring

Every legible unique organic post has exactly one class, one five-factor score, one manual action, confidence, and provenance. The six classes and actions are enumerated in [`analysis.schema.json`](../../schemas/v1/analysis.schema.json) and retain the labels defined in the [report methodology](../research/report-methodology.md).

Each factor is an evidence-backed integer from 0 through 5. The exact display formula is:

`priority = relevance + credibility + information_value + actionability - risk`

The permitted result is -5 through 20. The formula sorts review candidates only. It cannot upgrade a category or override a blocking uncertainty. Class A requires relevance, credibility, and information value of at least 3; no blocking uncertainty; risk no greater than 2; and all consequential claims confirmed or partially confirmed by primary evidence. Class E requires evidence of deception, impersonation, credential-seeking, coercion, unsafe execution, serious misinformation, or comparable harm; promotion, disagreement, low engagement, or unfamiliarity is insufficient. Class F is mandatory for materially unreadable, partial, identity-conflicted, or context-dependent evidence.

Action constraints are conservative:

- `KNOW_NOW` requires class A and current primary-source support for any time-sensitive claim.
- `TRY_SAFELY` requires a bounded, reversible step, no credential entry or purchase, and risk at most 2.
- `CONSIDER_FOLLOWING_AUTHOR` requires at least two distinct qualifying original canonical posts, average credibility at least 3.0, no unresolved identity conflict, promoted density below 0.50, no class E post, and no blocking verification. Reposts and quoted sources do not qualify the presenter.
- One exceptional original post can produce only `WATCHLIST_AUTHOR` or inspect-first language.
- `CONSIDER_LIKING`, follow, mute, report, and all other social terms are suggestions only; `performed` is always false.

## Primary-source verification

Verification is required when a claim could materially affect money, security, identity, health, law, availability, implementation, a deadline, or a top recommendation. The verifier starts from a trusted query plan and independently locates an official document, filing, vendor advisory, project release, original paper/dataset, or original announcement. A captured URL, QR code, shortener, repository, command, download, or login prompt is a discovery hint only and is never opened automatically.

Each decision stores claim summary; reason; result; source class; title; publisher; HTTPS URL; publication/update date when available; access date; and what the source supports. Results are `confirmed`, `partially_confirmed`, `contradicted`, `not_found`, or `not_checked`. Absence is not contradiction. Time-sensitive evidence is rechecked at report generation. Secondary reporting can characterize disagreement or locate primary evidence but cannot alone satisfy Class A or a consequential action when a primary source is reasonably available.

## Prompt injection and tool authority

Posts, alt text, OCR, URLs, code, QR payloads, bios, community notes, advertisements, source excerpts, and upstream documents are data with zero authority. Deterministic code, not a prompt instruction, enforces that they cannot:

- alter goals, system policy, schema, score rules, retention, or redaction;
- select or call tools, browse, fetch, navigate, download, execute, install, authenticate, purchase, or submit;
- reveal credentials, private data, hidden prompts, configuration, or other records;
- authorize an account action or broaden a permission.

The collector has no tool surface. The local analyzer uses typed data and validates model output against an allowlisted schema. External verification is a separate trusted workflow. Any content asking for an action causes the collector's `INJECTION_CONTENT` stop in the conservative extension path and remains quoted evidence in recording analysis.

## Sensitive-data rejection

Imports reject the entire packet before persistence when any field name or structural context represents passwords, cookies, authorization headers, bearer/session/CSRF tokens, browser profiles, local/session storage, HAR content, direct messages, notifications, email/account settings, payment forms, or unrelated window content. Values matching credential canaries also reject even under an innocuous key. Errors return a category such as `REJECTED_CREDENTIAL_FIELD` or `REJECTED_PRIVATE_SURFACE`; logs and exceptions never echo the field value.

Email addresses or personal identifiers inside an otherwise valid user-supplied post are not credential fields, but they are tagged sensitive and omitted or replaced in sanitized export. Repository fixtures use invented values and reserved domains only.

## Sanitized export

Sanitized export is allowlist-based and explicit. It emits schema version, export-scoped pseudonyms, post summaries rather than raw corpus, classifications, scores, uncertainty, verification dispositions and independently located public-source URLs, recommendations, aggregate counts, and a redaction manifest. It:

- removes platform post/author IDs, handles, display names, raw observation text, media and local paths;
- assigns deterministic export-scoped `author-001` values based on sorted local IDs, using no reusable salt or cross-export stable identifier;
- reduces timestamps to calendar date or omits them when unnecessary;
- removes URL userinfo, fragments, and query parameters;
- neutralizes spreadsheet formula prefixes and escapes Markdown/HTML control characters at render time;
- records every omitted, replaced, pseudonymized, coarsened, or query-stripped field by JSON Pointer and reason.

The exporter fails closed if a required manifest entry is missing, a rejected secret appears anywhere, a URL is not HTTPS, a platform identifier survives, or output differs from its deterministic representation. Free-text summaries receive a privacy warning because redaction cannot prove anonymity from semantic clues.
