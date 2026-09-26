## 2024-06-25 - Python O(n*m) String Comparison Bottleneck

**Learning:** Pure Python implementations of O(n*m) distance checks (like Levenshtein distance) in hot paths are a significant performance bottleneck due to Python's loop overhead. However, when comparing primarily large text blobs that are usually identical or share mostly identical prefixes/suffixes (like temporal review deduplication), the matrix calculation time can be trivially bypassed.

**Action:** Whenever identifying string/text matching algorithms (like distance checks) that process mostly matching data, add simple prefix/suffix trimming before running the core O(n*m) algorithm to skip unnecessary looping and gain huge performance wins.
