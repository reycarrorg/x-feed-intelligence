# Windows Firefox development run

This is a local Gate 3 review build, not a signed Firefox release or a completed
live-X acceptance test. It does not require Chrome or Brave. Firefox 140 or
newer is required on desktop; the checked Windows PC has Firefox 156.

From the Windows worktree, double-click `Start XFI Firefox.cmd`. The launcher
uses the pinned `pnpm` lockfile with package scripts disabled, builds the
Firefox Manifest V3 extension, and uses Mozilla `web-ext` 10.6.0 to
install it temporarily in a **new Firefox profile**. It opens
`about:debugging#/runtime/this-firefox`. Leave the launcher window open while
using this temporary build. The normal Firefox profile, cookies, and X login
are not copied. Closing the temporary Firefox session removes the add-on;
double-click the launcher again to rebuild and relaunch it. The first launcher
run may fetch this pinned test runner from npm; it is not shipped with the
extension or the recording-only product package.

The Firefox manifest has one optional site permission, `https://x.com/*`, and
no always-on host permission, background worker, or network API permission.
Firefox also displays a data-use disclosure because an explicit local JSON
export can contain visible website content, author identifiers, and social
posts. The extension does not transmit that packet to a server. The user must
separately grant X access and press **Start** before collection. Do not log in
to X, grant access, or begin a live collection just to verify installation;
follow [the user-supervised protocol](USER_SUPERVISED_TEST.md) when ready.

For a local rebuild and static check from `extension/`:

```powershell
pnpm install --frozen-lockfile --ignore-scripts
pnpm run prepare:wxt
pnpm run compile
pnpm run test
pnpm run build:firefox
python ..\tests\check_gate3_manifest.py --browser firefox
```

If `python` is not on `PATH`, use an installed or bundled Python runtime for
the final script; the double-click launcher does not require Python.
Mozilla's `web-ext lint` on the generated Firefox build must report zero
errors and warnings. This static evidence is not proof of current X DOM
compatibility, classification accuracy, account safety, or durable installation.
Persistent everyday Firefox installation requires a separately reviewed and
signed add-on; it is not performed by this launcher.
