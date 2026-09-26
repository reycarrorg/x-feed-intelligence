## 2024-05-19 - Replace O(N^2) list comprehensions with O(N) dict hash maps
**Learning:** Found a nested list comprehension calculating promoted post counts per author inside `aggregate_authors`. In worst cases, this performs a linear search over thousands of posts for every grouped author, leading to exponential performance degradation on large datasets.
**Action:** Replace nested loops querying whole list variables with pre-computed dictionary hash maps populated in a single O(N) initial pass over the list.
