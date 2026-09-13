# Deterministic Metrics, Thresholds, and Test Oracles

## Corpus and provenance

The frozen Gate 1 corpus is listed in [`fixtures/synthetic/v1/manifest.json`](../../fixtures/synthetic/v1/manifest.json). Every source and expected-output file is authored for this repository, uses invented identities and reserved domains, and has a SHA-256 recorded over its exact bytes. The acceptance runner recomputes every digest before using a fixture. Changing a fixture or oracle requires an intentional manifest update and review.

Session provenance is a cross-field invariant, not two independent labels: `synthetic_dom` requires origin `https://fixture.example.invalid`; `synthetic_recording` and `user_supplied_recording` require origin `null`. Negative controls reject the former `synthetic_dom` plus `https://x.com` pairing, recordings carrying a DOM origin, and any unversioned live source.

Expected labels are independent oracle fields, never derived from the system output under test. The runner sorts all unordered output explicitly and executes deduplication across multiple input orders to prove determinism.

## Exact formulas

For a set of expected canonical units `E`, predicted canonical units `P`, and one-to-one matches `M`:

- `unique_precision = |M| / |P|`; define as `1.0` when both sets are empty and `0.0` when `P` is empty but `E` is not.
- `unique_recall = |M| / |E|`; define as `1.0` when both sets are empty and `0.0` when `E` is empty but `P` is not.
- `relationship_accuracy = correct unambiguous relationship edges / expected unambiguous relationship edges`; `1.0` when the oracle contains no relationship edge.
- `promoted_separation = correct unambiguous promoted/organic labels / all unambiguous promotion labels`; ambiguous labels are excluded and must enter review.
- `classification_completeness = legible organic canonical units with exactly one valid class, five integer factors, one valid action and confidence / all legible organic canonical units`.
- `stop_rate = hard-stop fixtures producing the exact fail-closed state/code and no later observation / all hard-stop fixtures`.
- `forbidden_effect_count = network requests + account actions + automated input events + cookie/header/page-storage reads + hidden-data reads + page-world injections`.
- `secret_echo_count = occurrences of any complete synthetic secret canary in logs, errors, reports, snapshots, or exports`.
- `sanitizer_match = 1` only when canonical UTF-8 JSON bytes, including the trailing newline, exactly equal the golden file.
- `priority = relevance + credibility + information_value + actionability - risk`.

All ratios are computed from integer counts and compared without rounded display values. A result report includes numerator, denominator, exact fraction, decimal to six places, threshold, and pass/fail.

## Gate 1 and Gate 2 thresholds

| Metric | Synthetic DOM | Synthetic recording | Failure/privacy |
| --- | ---: | ---: | ---: |
| Unique precision | at least 0.99 | at least 0.95 | — |
| Unique recall | at least 0.98 | at least 0.90 | — |
| Relationship accuracy, unambiguous | 1.00 | 1.00 | — |
| Promoted separation, unambiguous | 1.00 | 1.00 | — |
| Classification completeness, legible organic | 1.00 | 1.00 | — |
| Required hard-stop behavior | — | — | 1.00 |
| Forbidden collector effects | — | — | exactly 0 |
| Secret echoes | — | — | exactly 0 |
| Sanitizer golden match | — | — | exactly 1 |

Resource invariants are exact: no more than 250 candidates, no more than 1,800 seconds, no packet larger than 5,242,880 bytes, no field larger than its schema cap, and no observer/timer/DOM reference or new collection event after a stop. The 0.50 visibility ratio is inclusive. The 5% ambiguity threshold is inclusive; a higher ratio stops.

Performance targets—under 2% mean idle CPU, bounded peak memory, and one OCR worker—cannot be honestly proven at Gate 1 because there is no implementation. Gate 2 must measure them on documented hardware, OS, browser/runtime, fixture size, sample count, interval, mean, maximum, and failure path. They are not release claims until measured.

## Gate 1 acceptance runner

Run `python3 tests/gate1_acceptance.py`. It uses only the Python standard library and proves:

- every JSON document parses; schema IDs/versions and cross-file references resolve;
- canonical examples contain required role, relationship, media, provenance, promotion, uncertainty, score, verification, recommendation, and redaction structures;
- fixture digests and authored-synthetic declarations match;
- exact-ID, permalink, relation-aware exact-tuple and conservative-review deduplication invariants are stable across input order;
- conflicting identity/number/negation/media evidence does not auto-merge; two quote authors sharing one embedded original remain distinct, while repost fallback attributes the original source;
- topology and organic/promoted counts reconcile;
- score arithmetic and follow/watchlist evidence thresholds hold;
- injection records have no tool authority;
- the credential/private-surface table rejects authorization, API/access/refresh/client-secret, private-key-like, bearer-value, and direct-message cases without echoing complete canaries, while a benign negative control passes;
- sanitized output matches byte-for-byte, explicitly neutralizes a formula canary in a retained summary, and contains no prohibited identity, media, query, secret, or active formula prefix;
- wrong-origin, login, challenge, rate-limit, permission and resource cases stop with exact codes;
- collector events contain zero network/account/input/credential/hidden-data effects;
- production and synthetic-test manifest permissions match their separate reviewed contracts, and negative promotion controls reject test origin/files/markers from production candidates.

Gate 1 proves the specification and reference oracle, not a production collector, OCR engine, database, browser extension, or model integration.
