@echo off
setlocal
set "XFI_FIREFOX=%ProgramFiles%\Mozilla Firefox\firefox.exe"
set "XFI_LOCK=%TEMP%\xfi-firefox-launch.lock"
set "XFI_PNPM="
set "XFI_RUNTIME_NODE="
if /i "%~1"=="--verify" set "XFI_VERIFY=1"
if /i "%~1"=="--argv-check" set "XFI_ARGV_CHECK=1"
if not exist "%XFI_FIREFOX%" (
  echo Firefox was not found at "%XFI_FIREFOX%".
  pause
  exit /b 1
)
for %%P in ("%LocalAppData%\pnpm\pnpm.cmd" "%AppData%\npm\pnpm.cmd" "%ProgramFiles%\nodejs\pnpm.cmd" "%ProgramFiles(x86)%\nodejs\pnpm.cmd") do if not defined XFI_PNPM if exist "%%~fP" set "XFI_PNPM=%%~fP"
if not defined XFI_PNPM for /f "delims=" %%P in ('where pnpm 2^>nul') do if not defined XFI_PNPM set "XFI_PNPM=%%P"
if not defined XFI_PNPM for /d %%R in ("%UserProfile%\.cache\codex-runtimes\*") do if not defined XFI_PNPM if exist "%%~fR\dependencies\bin\fallback\pnpm.cmd" if exist "%%~fR\dependencies\node\bin\node.exe" (
  set "XFI_PNPM=%%~fR\dependencies\bin\fallback\pnpm.cmd"
  set "XFI_RUNTIME_NODE=%%~fR\dependencies\node\bin"
)
if not defined XFI_PNPM (
  echo pnpm was not found in the standard user or Node locations, PATH, or the existing Codex runtime cache.
  echo Missing component: pnpm.cmd. Install a supported Node and pnpm runtime, or open Codex once to restore its managed runtime.
  pause
  exit /b 1
)
call "%XFI_PNPM%" --version >nul 2>nul
if errorlevel 1 (
  echo pnpm was found but could not run: "%XFI_PNPM%"
  echo Restore that runtime or install a supported Node and pnpm runtime, then try again.
  pause
  exit /b 1
)
if defined XFI_RUNTIME_NODE set "PATH=%XFI_RUNTIME_NODE%;%PATH%"
where node >nul 2>nul
if errorlevel 1 (
  echo node.exe is unavailable for the pinned extension build after resolving pnpm: "%XFI_PNPM%"
  echo Restore the matching Node runtime or install a supported Node and pnpm runtime, then try again.
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
call "%XFI_PNPM%" run build:firefox
if errorlevel 1 goto failure
if defined XFI_VERIFY (
  echo XFI launcher verification succeeded. Firefox was not started.
  goto cleanup
)
if defined XFI_ARGV_CHECK (
  set "npm_config_offline=true"
  call "%XFI_PNPM%" dlx web-ext@10.6.0 run --source-dir ".output\firefox-mv3" --firefox "%XFI_FIREFOX%" --no-reload --start-url "https://x.com/" --no-input --help
  if errorlevel 1 goto failure
  echo XFI launcher argument check succeeded. Firefox was not started.
  goto cleanup
)
echo Starting a separate temporary Firefox profile with XFI. Your normal Firefox profile, cookies, and sessions are not used.
echo X access remains off until you grant it, and capture remains off until you press Start.
set "npm_config_offline=true"
call "%XFI_PNPM%" dlx web-ext@10.6.0 run --source-dir ".output\firefox-mv3" --firefox "%XFI_FIREFOX%" --no-reload --start-url "https://x.com/" --no-input
if errorlevel 1 goto failure
:cleanup
rd "%XFI_LOCK%" >nul 2>nul
exit /b 0
:failure
rd "%XFI_LOCK%" >nul 2>nul
echo XFI Firefox could not start. Review the error above.
pause
exit /b 1
