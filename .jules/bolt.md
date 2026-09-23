## 2026-09-23 - Avoid deepcopy for sha256 digests
**Learning:** `deepcopy` is very slow when computing digests on large dictionaries in `canonical.py`'s `digest` function. Because we immediately discard the cloned dictionary, a shallow copy (`dict.copy()`) is sufficient to avoid modifying the original dictionary when we `pop` the digest field.
**Action:** Use `.copy()` instead of `copy.deepcopy()` in `src/xfi/canonical.py:digest` for a significant speedup.
