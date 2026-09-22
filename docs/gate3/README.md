# Gate 3 Hybrid Review Extension

## Current evidence

The branch implements Chrome/Chromium and Firefox Manifest V3 review builds and a live-DOM v2 packet contract. It is source-reviewed, compiled, unit-tested, built, and checked against the existing local analysis core. The generated manifest is also inspected deterministically. This does **not** prove compatibility with current authenticated X markup, extension-store acceptance, long-session reliability, or account safety.

The review build was locally installed in Brave and passed one bounded authenticated-X smoke test on September 16, 2026. See the [test record](BRAVE_SMOKE_TEST_2026-09-16.md). A separate temporary Windows Firefox build is described in [FIREFOX_WINDOWS.md](FIREFOX_WINDOWS.md); it has not run an authenticated-X acceptance session. The extension remains unsigned and store-unpublished. These checks do not establish the full user-supervised acceptance conditions, current-X classification accuracy, long-session reliability, or account safety.

## Fixed behavior

- Access is optional and limited to `https://x.com/*`.
- Permission grant and collection start are distinct user actions.
- All controls remain in the extension action popup. A count-only bubble on X shows the total committed cards across a continuous capture; it has no buttons and does not intercept input.
- Collection observes top-level cards only after they reach at least 50% viewport visibility.
- The user can scroll normally or enable careful hands-free scrolling in Settings. Assisted scrolling waits for DOM settling and storage acknowledgment, moves 80–160 pixels per step in the visible feed container, slows when no new cards are captured, and stops on trusted mouse/keyboard input, hidden-tab, challenge, rate-limit, or no-progress conditions. It does not synthesize a real middle click or control the system pointer.
- The tab becoming hidden pauses collection.
- Each part is bounded at 10,000 distinct visible cards, 8 hours, and 15 MiB. The effective automatic rollover threshold is the conservative 9-MiB `storage.session` refresh-recovery ceiling; XFI pauses capture, verifies that part's download completed, and then starts a new part. On failed or interrupted saving it stops and retains the old recoverable packet. Refresh during rollover also stops with an exportable packet rather than risk silent loss. This is not browser-restart persistence. Older 5-MiB and 128-MiB review packets remain importable.
- Exports use a configurable subfolder under the browser's existing download location, without changing Firefox's global setting. Firefox may still prompt if the user has configured it to ask for every download. The extension cannot force an absolute Documents path. All automatically saved continuous parts are retained. It tracks only its own completed, unrenamed standalone exports and recycles the oldest verified standalone file after ten. If verification or removal fails, it keeps the older file. It does not upload, browse links, or analyze through a remote model.
- Promoted cards are labeled and excluded by the downstream organic analysis.
- Preview grades are conservative routing hints, not factual verdicts.

## Deliberately absent

The extension has a narrow export background context so downloads do not depend on the transient popup document. Chromium uses an offscreen extension document solely to hold a local Blob URL; Firefox uses its extension background event page. The exact download lifecycle in the user's Firefox client remains unverified. Neither context requests X or other network data. The extension has no network fetch/XHR/WebSocket, request interception, cookie read, private API, media download, synthetic input event, or account action. Assisted scrolling is the only new page action and is opt-in.

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

The extension emits schema `2.0.0` with `source: live_dom` and `collection_mode: manual_scroll` or `assisted_scroll`. The same strict validator, canonicalizer, product-owned SQLite store, analysis core, reports, purge controls, and capability-denied model handoff used by Gate 2 accept the new packet type. Schema v1 remains unchanged for synthetic DOM and recording inputs.
