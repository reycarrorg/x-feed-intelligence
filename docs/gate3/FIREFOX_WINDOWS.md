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

If an older temporary XFI session is still open, export any unsaved capture
before closing it. Rebuilding files on disk does not automatically reload that
running add-on; launch a fresh temporary session to use version 0.4.0.

The Firefox manifest has one optional site permission, `https://x.com/*`, and
no always-on host permission, background worker, or network API permission.
Firefox also displays a data-use disclosure because an explicit local JSON
export can contain visible website content, author identifiers, and social
posts. The extension does not transmit that packet to a server. The user must
separately grant X access and press **Start** before collection. Do not log in
to X, grant access, or begin a live collection just to verify installation;
follow [the user-supervised protocol](USER_SUPERVISED_TEST.md) when ready.

The popup has a **Keep open in Firefox sidebar** button. The sidebar remains
beside the X tab while you scroll and refreshes its counts about once per
second; it is not an OS-level always-on-top window. Capture stays in the X tab
if you close the sidebar, but the counters reappear when you reopen it. The
review build can accumulate up to 10,000 distinct cards that each become at
least 50% visible, with an 8-hour and 128-MiB safety ceiling. Stop and export
from the same X tab before reloading or closing it; a reload discards the
in-memory session. Large JSON exports are transferred from the collector in
bounded chunks and may take time. Export periodically during a long run if
you want recoverable checkpoints; each export contains the session so far.
The first live supervised test should still
be small, as described in the protocol; 10,000-card live reliability is not
yet proven.

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
