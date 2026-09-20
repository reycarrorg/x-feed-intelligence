# Limited Brave smoke test — September 16, 2026

This is a bounded developer-assisted runtime check, not full Gate 3 acceptance. The user granted the extension's exact optional `https://x.com/*` access in their existing Brave profile and asked for active testing. No credentials or real post content are recorded in this repository.

## Result observed

- The initial popup could identify an active tab but Brave withheld its URL. The popup now confirms the active X tab by requesting status from its own X-only content script; it does not need a new permission.
- The content script displayed `XFI ARMED` but the popup received no response because the listener returned a value rather than calling Chromium's `sendResponse` callback. The listener now replies synchronously for status/start/stop/discard and retains the channel for asynchronous export.
- After reloading the exact local unpacked build and X tab, the popup displayed `ARMED` with an enabled Start control.
- Start changed the state to `CAPTURING`. One developer-assisted PageDown input in the ordinary feed increased the visible-card count to 5. Stop changed the state to `STOPPED` and preserved the count.
- The local JSON export was created and passed the repository's strict `xfi.cli validate` command as schema `2.0.0`. Its metadata reported `source: live_dom`, `collection_mode: manual_scroll`, five top-level observations, and a minimum visibility ratio above 0.5.
- The private packet stayed outside the repository. No post text, account identifiers, or session file are committed.

## Not established

This test did not measure precision/recall against a user-controlled recording, independently adjudicate advertisement classification, exercise challenge and rate-limit hard stops live, prove long-session reliability, or establish that use is permitted by X or safe from account enforcement. The extension was not signed, store-published, or merged into `main`. The [full acceptance protocol](USER_SUPERVISED_TEST.md) remains open.
