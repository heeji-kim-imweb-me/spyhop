@echo off
rem Spyhop (Windows): start the board and open it in the default browser.
rem   spyhop            start the board (or reuse the running one) and open it
rem   spyhop doctor     explain how each session was found, or why it was not (add --titles to show titles)
setlocal
set "d=%~dp0"
set "PY=python"
where py >nul 2>nul && set "PY=py -3"

if /i "%~1"=="doctor" (
  %PY% -X utf8 "%d%board.py" --doctor %2 %3
  exit /b %errorlevel%
)

%PY% -X utf8 "%d%board.py" --ensure >nul || exit /b 1
rem The loader page waits for the board server and shows the board as soon as it is up.
start "" "%USERPROFILE%\.spyhop\open.html"
echo opened: browser %USERPROFILE%\.spyhop\open.html
