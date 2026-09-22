@echo off
setlocal
set "XFI_FIREFOX=%ProgramFiles%\Mozilla Firefox\firefox.exe"
set "XFI_LOCK=%TEMP%\xfi-firefox-launch.lock"
if not exist "%XFI_FIREFOX%" (
  echo Firefox was not found at "%XFI_FIREFOX%".
  pause
  exit /b 1
)
where pnpm >nul 2>nul
if errorlevel 1 (
  echo pnpm is not available on PATH. Open this reviewed worktree with its existing Node and pnpm setup, then try again.
  pause
  exit /b 1
)
2>nul mkdir "%XFI_LOCK%"
if errorlevel 1 (
  echo XFI Firefox is already running or its previous launcher did not close cleanly.
  echo Close its temporary Firefox window and launcher. If both are closed, remove "%XFI_LOCK%" and try again.
  pause
  exit /b 1
)
cd /d "%~dp0extension"
if errorlevel 1 goto failure
if not exist "node_modules\.bin\wxt.cmd" (
  echo The reviewed extension dependencies are unavailable in this worktree.
  echo This launcher does not download software. Restore the pinned dependencies, then try again.
  goto failure
)
call pnpm run build:firefox
if errorlevel 1 goto failure
echo Starting a separate temporary Firefox profile with XFI. Your normal Firefox profile, cookies, and sessions are not used.
echo X access remains off until you grant it, and capture remains off until you press Start.
set "npm_config_offline=true"
call pnpm dlx web-ext@10.6.0 run --source-dir ".output\firefox-mv3" --firefox "%XFI_FIREFOX%" --no-reload --start-url "https://x.com/" --no-input --boring
if errorlevel 1 goto failure
rd "%XFI_LOCK%" >nul 2>nul
exit /b 0
:failure
rd "%XFI_LOCK%" >nul 2>nul
echo XFI Firefox could not start. Review the error above.
pause
exit /b 1
