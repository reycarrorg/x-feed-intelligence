## 2024-03-24 - CI checks depend on upstream commit
**Learning:** `tests/gate2_security.py` checks changes against a specific hardcoded `BASE` commit (`9f961e5b9758884bcb5aff6ad2b8e85ca1bf0396`). If this commit is not in the local checkout, the test fails with git error 128.
**Action:** Do NOT modify the `BASE` variable to bypass the security check. Instead, fetch the missing commit directly using `git fetch origin <commit_hash>` to allow the check to run properly.

## 2024-03-24 - Repository pollution causes CI failures
**Learning:** Temporary scratchpad scripts added to the repository cause security gate failures and repository pollution.
**Action:** Ensure all temporary benchmarking or testing scripts are deleted and un-staged before running pre-commit steps or submitting a PR.
