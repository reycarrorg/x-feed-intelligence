## 2024-05-23 - Eager Set Comprehensions in Conflict Resolution
**Learning:** `has_merge_conflict` in this codebase eagerly computed sets over potentially large string arrays, invoking expensive regex operations (`_semantic_tokens`) even when conflicts existed early on cheaper attributes (like IDs or promotion status).
**Action:** When identifying uniqueness or conflicts, apply short-circuit logic (fail-fast) starting with the cheapest checks (O(1) lookups or properties) and deferring expensive text analysis to the end.
