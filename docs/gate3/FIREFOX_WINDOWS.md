# Windows Firefox development run

> Historical Gate 3 test instructions. The current review build uses the
> extension action popup and an explicitly opened in-page control panel; former
> sidebar instructions do not apply. The current build has not yet been loaded
> in the user's Firefox client.

This is a local Gate 3 review build, not a signed Firefox release or a completed
live-X acceptance test. It does not require Chrome or Brave. Firefox 140 or
newer is required on desktop; the checked Windows PC has Firefox 156.

Use the `X Feed Intelligence Firefox` shortcut on the current Windows Desktop,
or double-click `Start XFI Firefox.cmd` in the worktree. The launcher rebuilds
the Firefox Manifest V3 extension and uses the already cached Mozilla
`web-ext` 10.6.0 runner to install it temporarily in a **new Firefox profile**.
It opens `https://x.com/`, so no `about:debugging` step is required. Leave the
launcher window open while using this temporary build. The normal Firefox
profile, cookies, and X login are not copied or modified. Closing the temporary
Firefox session removes the add-on; use the shortcut again to rebuild and
relaunch it. The launcher deliberately does not download dependencies.

The launcher uses only the installed **standard Firefox Release** application
binary (on this PC, `C:\Program Files\Mozilla Firefox\firefox.exe`, Firefox
156). It explicitly does not fall back to Firefox Developer Edition. This
selects the normal Firefox application binary while `web-ext` still creates a
separate temporary profile; it does not open, replace, or reuse the user's
everyday Firefox profile or session.

Only one launcher session may run at a time. If it reports a stale launcher
lock after both its temporary Firefox window and launcher have closed, remove
`%TEMP%\xfi-firefox-launch.lock` and retry.

The launcher first looks for a normal user or system `pnpm` installation. On
this Windows setup it can also discover the existing Codex-managed runtime
without relying on Explorer's PATH. To rebuild and verify that resolution
without starting Firefox, run `Start XFI Firefox.cmd --verify` from a Command
Prompt in the worktree. If the launcher names a missing `pnpm.cmd`, restore the
named runtime or install a supported Node and pnpm runtime; it does not install
or download either automatically.

To validate the exact `web-ext run` arguments without starting Firefox, run
`Start XFI Firefox.cmd --argv-check`. This checks the pinned local runner's
option parser after rebuilding the Firefox bundle and reports the pinned
standard Firefox Release binary it passed as `--firefox`.

If an older temporary XFI session is still open, export any unsaved capture
before closing it. Rebuilding files on disk does not automatically reload that
running add-on; launch a fresh temporary session to use the current reviewed build.

The Firefox manifest has one optional site permission, `https://x.com/*`, and
no always-on host permission, background worker, or network API permission.
Firefox also displays a data-use disclosure because an explicit local JSON
export can contain visible website content, author identifiers, and social
posts. The extension does not transmit that packet to a server. The user must
separately grant X access and press **Start** before collection. Do not log in
to X, grant access, or begin a live collection just to verify installation;
follow [the user-supervised protocol](USER_SUPERVISED_TEST.md) when ready.

The action popup has a **Keep controls on this X page** button. It opens an
explicit, removable floating control panel inside the current X page; it is not
a Firefox sidebar or an OS-level always-on-top window. Capture stays in the X
tab if the panel closes, and the controls reappear only when you explicitly
open them again. The review build can accumulate up to 10,000 distinct cards
that each become at least 50% visible, with an 8-hour and 15-MiB safety ceiling
(with a separate 9-MiB refresh-safe cap). Stop and export
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
