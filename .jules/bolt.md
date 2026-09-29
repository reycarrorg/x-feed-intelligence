## 2024-05-18 - Caching expensive semantic tokens

**Learning:** Re-computing `_semantic_tokens` repeatedly within `has_merge_conflict` causes massive CPU spikes during canonical index rebuilding because of regex string manipulation on large lists of authors and interactions. The problem is exacerbated during deduplication because conflicts iterate through items $O(n^2)$ relative to the items grouping.
**Action:** Always memoize computationally expensive, string-based dictionary transformation logic like `_semantic_tokens` into the `observation` dictionary itself when it operates purely functionally and the underlying JSON doesn't mutate during the loop.

## 2024-05-18 - Early return pattern in `has_merge_conflict`

**Learning:** `has_merge_conflict` builds a huge array of sets for all possible conflicting states at once, then checks them using `any()`. For conflicts, especially expensive ones involving text normalization, this forces calculation of worst-case complexity even if an earlier conflict constraint fails.
**Action:** When validating multi-step conditions in hot paths (like DB import and indexing), convert `any()` list comprehensions into discrete `if` statements with early returns. Put computationally cheap checks (like ID existence) before computationally expensive text normalizations or regular expressions.
