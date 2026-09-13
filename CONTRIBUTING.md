# Contributing

Contributions must use synthetic feed fixtures and preserve the project charter, security policy, noncommercial license, and account-safety boundaries.

Do not include real posts, recordings, usernames, account data, credentials, tokens, cookies, scraped datasets, copyrighted media, stealth behavior, CAPTCHA handling, automatic engagement, or private-API replay. Record every dependency's source, version, license, permissions, and data behavior.

Run `bash tests/check_repo.sh` before proposing a change. Gate 1 fixtures must remain authored synthetic, hash-listed in the fixture manifest, and covered by deterministic expected output. No dependency may be used before its lock, provenance, license/notice entry, security review, and SBOM plan land in the same reviewed change.
