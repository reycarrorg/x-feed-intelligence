# ADR 0001: Runtime Platform

- Status: Researching
- Decision date: Pending

## Context

The product needs a safe screen-recording path and a lower-friction way to collect visible personalized feed posts without an official API, credentials export, account mutation, stealth, or access-control bypass.

## Current hypothesis

A local hybrid may be smallest overall: a passive WebExtension for explicit visible-post capture plus a local application or CLI for video extraction, durable local storage, analysis-packet generation, and report export. This remains a hypothesis until Gate 0 finishes.

## Non-negotiable constraints

- No remote telemetry or cloud database.
- No credentials, cookies, tokens, DMs, or notification capture.
- No automatic social actions.
- No CAPTCHA solving, proxy rotation, stealth, fingerprint evasion, or private-API replay.
- No authenticated X testing without the user.
- No raw personalized data in Git or CI.
- Stop and disclose rather than bypass a login challenge or rate limit.

