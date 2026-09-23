## 2026-09-12 - Avoid O(N^2) Aggregations
**Learning:** In the canonical analysis path, calculating author density across the entire list of posts recursively for every aggregated author scales poorly O(N^2).
**Action:** Pre-calculate properties across the full posts array into O(N) hash maps when needing to check conditions on large arrays within aggregated item loops.
