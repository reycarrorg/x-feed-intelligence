# User-Supervised Live Acceptance Protocol

This protocol defines full acceptance; the [September 16 limited Brave smoke test](BRAVE_SMOKE_TEST_2026-09-16.md) did not complete every condition. This document does not authorize installation, account access, or publication by itself.

## Preconditions

1. Recheck current X terms, browser-extension policy, and account-enforcement risk from primary sources.
2. Review the exact commit, dependency lock, generated manifest, build output, and third-party notices.
3. Confirm the manifest has only `optional_host_permissions: ["https://x.com/*"]` plus `downloads` and `storage` for local Save As and verified retention. Chromium additionally needs `offscreen` to hold the export Blob while its transient popup closes. A narrow background context handles exports; it must make no X or external network requests. There is no always-on host permission.
4. Use a dedicated ordinary browser profile. The user performs login, MFA, consent, CAPTCHA, and recovery personally; credentials are never supplied to the extension or recorded in the repository.
5. Prepare a simultaneous user-controlled screen recording if one-to-one recall measurement is desired.

## One bounded session

1. Load the exact reviewed unpacked build.
2. Open an ordinary `https://x.com` feed page and grant the exact optional site permission.
3. Reload once if the browser requires it. Confirm the collector says ARMED and has collected zero posts.
4. Press Start. For the first sample, scroll manually at an ordinary reading pace. In a separate bounded sample, use the popup's opt-in careful auto-scroll and verify it slows for loading cards, stops on no progress, and stops when the tab is hidden or a challenge appears. Do not use another automation tool.
5. For the first supervised smoke test, stop after at most 100 visible candidate cards or 15 minutes, even though the new Firefox collector can hold up to 10,000 distinct visible cards for a longer manual session. Stop immediately on login, challenge, unusual-activity, rate-limit, permission drift, unexpected surface, or account warning.
6. Export the private JSON once. Choose Documents in the browser Save dialog; the extension cannot force that folder. Validate it locally and compare it with the screen recording if captured. Separately test retention with synthetic exports before trusting automatic recycling of real files.
7. Revoke X access and remove the unpacked extension after the test unless the user explicitly chooses to retain the reviewed build.

## Pass conditions

- No page action except explicitly enabled bounded auto-scroll occurs: no click, hover, playback, expansion, navigation, retry, link opening, media download, network request, request interception, or account action.
- Only cards that were at least 50% visible while the document was visible are accepted.
- Promotion separation and hard-stop behavior have no known false negatives in the reviewed sample.
- DOM precision is at least 0.99 and recall at least 0.98 against the user-controlled recording.
- The exported packet validates, imports idempotently, and produces only non-performed recommendations.
- No credential, cookie, token, direct-message, notification, or unrelated private field appears in the export.

Any prerequisite or pass-condition failure ends the test. It does not authorize retries using broadened access, alternate accounts, private interfaces, proxies, stealth, or automation.
