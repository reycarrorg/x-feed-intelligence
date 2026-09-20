# Gate 3 Hybrid Review Extension

## Current evidence

The branch implements a Chrome/Chromium Manifest V3 review extension and a live-DOM v2 packet contract. It is source-reviewed, compiled, unit-tested, built, and checked against the existing local analysis core. The generated manifest is also inspected deterministically. This does **not** prove compatibility with current authenticated X markup, extension-store acceptance, long-session reliability, or account safety.

The review build was locally installed in Brave and passed one bounded authenticated-X smoke test on September 16, 2026. See the [test record](BRAVE_SMOKE_TEST_2026-09-16.md). A separate temporary Windows Firefox build is described in [FIREFOX_WINDOWS.md](FIREFOX_WINDOWS.md); it has not run an authenticated-X acceptance session. The extension remains unsigned and store-unpublished. These checks do not establish the full user-supervised acceptance conditions, current-X classification accuracy, long-session reliability, or account safety.

## Fixed behavior

- Access is optional and limited to `https://x.com/*`.
- Permission grant and collection start are distinct user actions.
- Collection observes top-level cards only after they reach at least 50% viewport visibility.
- The user scrolls normally. There is no automatic scrolling.
- The tab becoming hidden pauses collection.
- The current review build stops at 10,000 distinct visible cards, 8 hours, 128 MiB, excessive ambiguity, login/challenge/rate-limit surfaces, or prompt-injection-like content. Older review packets with the 100-card/15-minute/5-MiB limits remain importable.
- Export is a local JSON download. The extension does not upload, browse links, or analyze through a remote model.
- Promoted cards are labeled and excluded by the downstream organic analysis.
- Preview grades are conservative routing hints, not factual verdicts.

## Deliberately absent

The extension has no background service worker, network fetch/XHR/WebSocket, request interception, cookie read, private API, media download, auto-scroll, synthetic input event, account action, or automatic retry path.

## Local review commands

From `extension/`, use the repository-pinned package manager version:

```sh
pnpm install --frozen-lockfile --ignore-scripts
pnpm run prepare:wxt
pnpm run compile
pnpm run test
pnpm run build
python3 ../tests/check_gate3_manifest.py
```

The unpacked review build is generated at `extension/.output/chrome-mv3/`. Loading it into a browser is a separate acceptance action and must follow the [user-supervised protocol](USER_SUPERVISED_TEST.md).

## Core integration

The extension emits schema `2.0.0` with `source: live_dom` and `collection_mode: manual_scroll`. The same strict validator, canonicalizer, product-owned SQLite store, analysis core, reports, purge controls, and capability-denied model handoff used by Gate 2 accept the new packet type. Schema v1 remains unchanged for synthetic DOM and recording inputs.
