@echo off
setlocal
set "XFI_FIREFOX=%ProgramFiles%\Mozilla Firefox\firefox.exe"
if not exist "%XFI_FIREFOX%" (
  echo Firefox was not found at "%XFI_FIREFOX%".
  pause
  exit /b 1
)
where pnpm >nul 2>nul
if errorlevel 1 (
  echo pnpm is not available on PATH. Install the pinned package manager before launching XFI.
  pause
  exit /b 1
)
cd /d "%~dp0extension"
if errorlevel 1 exit /b 1
call pnpm install --frozen-lockfile --ignore-scripts
if errorlevel 1 goto failure
call pnpm run build:firefox
if errorlevel 1 goto failure
echo Starting a separate temporary Firefox profile with XFI. X access remains off until you grant it.
call pnpm dlx web-ext@10.6.0 run --source-dir ".output\firefox-mv3" --firefox "%XFI_FIREFOX%" --no-reload --start-url "about:debugging#/runtime/this-firefox" --no-input
if errorlevel 1 goto failure
exit /b 0
:failure
echo XFI Firefox could not start. Review the error above.
pause
exit /b 1
