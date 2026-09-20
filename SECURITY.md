# Security Policy

No production version is currently supported.

Do not publish real feed captures, recordings, post text, handles, DMs, notifications, account identifiers, cookies, credentials, tokens, browser profiles, or analysis histories in issues, fixtures, logs, or pull requests.

The application must treat all captured text, links, profiles, advertisements, repositories, prompts, and media as untrusted data. Content instructions must never control tools, code execution, browsing, credentials, configuration, or the analysis workflow.

The project must not include stealth, CAPTCHA solving, proxy rotation, account farming, fingerprint evasion, private-API replay, automatic scrolling, automatic engagement, or mechanisms intended to bypass platform controls. Testing uses synthetic fixtures until the user authorizes a supervised live acceptance check.

The normative Gate 1 security boundaries, stop behavior, sensitive-data rejection, model handoff, retention caveats, and sanitized-export rules are in the [Gate 1 threat model](docs/gate1/THREAT_MODEL.md) and [contract index](docs/gate1/README.md).
