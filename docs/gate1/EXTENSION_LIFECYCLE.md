# Passive MV3 Permission and Lifecycle Contract

## Exact manifest proposal

The machine-readable proposal is [`contracts/v1/manifest.proposal.json`](../../contracts/v1/manifest.proposal.json). It contains exactly two ordinary permissions—`storage` and `scripting`—and one optional host permission, `https://x.com/*`.

- `storage` holds configuration and a bounded unsaved synthetic/session queue. It does not authorize X page storage or browser history access.
- `scripting` permits registration and removal of the packaged isolated content script only after the optional host grant.
- `https://x.com/*` is optional and must be requested from the extension control on the user's explicit arm action. It is not present in `host_permissions` and must never be broadened silently.
- The toolbar `action` supplies the visible control and badge without another permission.
- The service worker coordinates explicit lifecycle actions. It has no network authority, remote code, native-messaging bridge, localhost listener, or scheduled collection.
- The extension CSP permits packaged scripts from `self` and prohibits objects and base-URL rewriting.

The proposal intentionally omits `activeTab`, `tabs`, `downloads`, `cookies`, `webRequest`, `declarativeNetRequest`, `debugger`, `clipboardRead`, `clipboardWrite`, `notifications`, `alarms`, `unlimitedStorage`, `nativeMessaging`, static `content_scripts`, all required host permissions, X API hosts, legacy Twitter hosts, localhost, and model-provider hosts.

## Machine state

[`contracts/v1/extension-lifecycle.json`](../../contracts/v1/extension-lifecycle.json) is the normative transition table. The toolbar must present the current state as text and an icon/badge; color is supplementary.

```text
INACTIVE -> PERMISSION_PROMPT -> ARMED -> CAPTURING
   ^              | denied         |          |
   |              v                |          +-> PAUSED_HIDDEN -> CAPTURING
   +----------- INACTIVE           |          +-> LIMIT_REACHED -> STOPPED
                                  +----------+-> STOPPED
Any armed/capture state -- hard stop --> ERROR -- acknowledge --> INACTIVE
```

Only the user can request arm, start, export/discard, stop, disarm, or acknowledge an error. The extension never starts merely because an approved tab opens. Granting host permission produces `ARMED`, not `CAPTURING`.

## Capture predicates

An observation is eligible only when all predicates hold simultaneously:

1. the top-level document origin is exactly `https://x.com`;
2. the content script is in the top-level frame and its execution world is isolated;
3. the document is visible and no login, sign-out, lock, CAPTCHA, Turnstile, verification, unusual-activity, consent, error, or rate-limit surface is detected;
4. state is `CAPTURING` after a user start action;
5. parser version and topology match the reviewed synthetic contract, with ambiguity at or below 5%;
6. a top-level candidate card reaches a 0.50 viewport intersection ratio;
7. the queue is below 250 candidate cards, elapsed duration is below 1,800 seconds, and serialized packet size is below 5,242,880 bytes.

`MutationObserver` may locate newly rendered candidate cards. `IntersectionObserver` is the only collection gate. A virtualized node reuse creates a new observation only when its stable evidence changes and it later crosses the visibility gate. Mutation updates attach provenance to the same appearance until identity changes; they do not erase earlier values.

## Fail closed

All hard-stop codes are enumerated in the machine contract. A stop must synchronously detach observers, cancel timers, clear DOM references, block further observation events, and retain only the code and coarse local time. Captured content must not appear in the error. Recovery is a user acknowledgement to `INACTIVE`; there is no automatic retry.

No failure path may suggest another account, alternate IP, retry loop, headless/headful mode, copied profile, proxy, fingerprint change, stealth patch, CAPTCHA service, private endpoint, or relaxed permission.

## Export and deactivation

Export is a deliberate user action that serializes the bounded envelope and computes a SHA-256 digest locally. It does not imply a successful analyzer import. Stop detaches runtime objects. Disarm unregisters the script; host-permission revocation is separately respected. Clearing unsaved data after revocation needs an extension-local confirmation so a permission change does not silently destroy a user draft.

Through Gate 2, any implementation of this proposal may run only against local authored synthetic pages in an isolated test profile. The exact optional X permission may be represented in the build for manifest inspection, but it must not be granted or exercised on the live origin.
