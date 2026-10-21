@echo off
rem Spyhop (Windows): start the board, the tray icon, and open the board in the default browser.
rem   spyhop            start the board (or reuse the running one), show the tray icon and open the board
rem   spyhop doctor     explain how each session was found, or why it was not (add --titles to show titles)
setlocal
set "d=%~dp0"
set "PY=python"
set "PYW=pythonw"
where py >nul 2>nul && set "PY=py -3"
where pyw >nul 2>nul && set "PYW=pyw -3"

if /i "%~1"=="doctor" (
  %PY% -X utf8 "%d%board.py" --doctor %2 %3
  exit /b %errorlevel%
)

%PY% -X utf8 "%d%board.py" --ensure >nul || exit /b 1
rem Tray icon (only one runs; a second start exits at once).
start "" %PYW% -X utf8 "%d%tray.py"
rem The loader page waits for the board server and shows the board as soon as it is up.
start "" "%USERPROFILE%\.spyhop\open.html"
echo opened: browser %USERPROFILE%\.spyhop\open.html
