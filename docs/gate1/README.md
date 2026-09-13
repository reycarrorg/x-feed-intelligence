# Gate 1 Contract Set

Gate 1 freezes the security, data, lifecycle, privacy, evaluation, and dependency contracts needed before production implementation. It contains no live collector, OCR pipeline, database, extension build, remote model integration, or X access.

## Requirement map

| Gate 1 requirement | Normative artifact | Deterministic evidence |
| --- | --- | --- |
| Threat model across browser, recording, parser/OCR, database, rendering, dependencies, injection, export, build and packaging | [Threat Model](THREAT_MODEL.md) | Repository safety, lifecycle and privacy groups |
| Sessions, observations, canonical posts, author roles, relationships, media, provenance, ads, scores, verification, recommendations, uncertainty and redactions | [`schemas/v1`](../../schemas/v1) and [Analysis Contracts](ANALYSIS_CONTRACTS.md) | Schema/reference and fixture-example checks |
| Conservative relation-aware deduplication and counting invariants | [Analysis Contracts](ANALYSIS_CONTRACTS.md#deterministic-deduplication) | DOM/recording counts, quote/repost collision fixtures and 42 reordered runs |
| Classification, five factors, manual actions, follow/watchlist thresholds | [Analysis Contracts](ANALYSIS_CONTRACTS.md#classification-and-scoring) | Four analysis records and seven boundary cases |
| Primary-source verification | [Analysis Contracts](ANALYSIS_CONTRACTS.md#primary-source-verification) | Required verification/result/source structures |
| Prompt injection and tool authority | [Analysis Contracts](ANALYSIS_CONTRACTS.md#prompt-injection-and-tool-authority) | Injection handoff with empty tool authority |
| Sensitive-data rejection and sanitized export | [Analysis Contracts](ANALYSIS_CONTRACTS.md#sensitive-data-rejection) | Credential rejection/non-echo and byte-exact golden export |
| Retention, SQLite deletion/WAL/backup caveats, purge and exports | [Retention and Export](RETENTION_AND_EXPORT.md) | Gate 2 transactional test requirements |
| Separate static production proposal and non-distributable synthetic MV3 harness, plus fail-closed state machine | [Extension Lifecycle](EXTENSION_LIFECYCLE.md) and [`contracts/v1`](../../contracts/v1) | Exact capabilities, non-promotion controls, transitions, limits and stop checks |
| Structurally separated model handoff | [Model Handoff](MODEL_HANDOFF.md) and [handoff schema](../../schemas/v1/model-handoff.schema.json) | Trusted producer, quoted records and all-false authority checks |
| Authored synthetic corpus | [fixture manifest](../../fixtures/synthetic/v1/manifest.json) | Ten SHA-256 checks and complete coverage inventory |
| Exact metrics, thresholds and oracles | [Metrics and Oracles](METRICS_AND_ORACLES.md) | Standard-library acceptance runner |
| Lock, notice and SBOM plan before dependency adoption | [Dependency and SBOM Plan](DEPENDENCY_AND_SBOM_PLAN.md) and [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) | Empty-dependency-set and undeclared-lock checks |
| Synthetic/user-supplied-only Gate 2 plan | [Gate 2 Work Breakdown](GATE2_WORK_BREAKDOWN.md) | Exact entry/exit and architecture stop conditions |
| Security, privacy, safety and residual-risk review | [Review Record](REVIEW_RECORD.md) | No confirmed findings; exact checks and unverified runtime gates |
| Current policy and live-access boundary recheck | [Policy Recheck](POLICY_RECHECK.md) | Same-day Gate 0 evidence remains controlling; no X access in Gate 1 |

## Run acceptance

```sh
bash tests/check_repo.sh
```

This runs documentation/link/footnote/sensitive-artifact checks followed by `python3 tests/gate1_acceptance.py`. The oracle uses no third-party dependency or network access.

Passing Gate 1 proves that the contracts and authored evidence are internally consistent. It does not prove production behavior, performance, live X compatibility, SQLite purge behavior, package integrity, signing, notarization, or account safety.
