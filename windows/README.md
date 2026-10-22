# Spyhop for Windows (community preview)

A side port of the Spyhop browser board for Windows. It lives only in this folder and shares no code with the macOS app: `board.py` here is a copy of `legacy/mac-browser/board.py` with Windows support added, so changes on one side do not reach the other. There is no installer and no automatic update.

## Get started

You need Windows 10 or 11, Python 3.9+ (`winget install Python.Python.3.12`), and a logged-in `claude` or `codex` CLI.

```powershell
git clone https://github.com/leeleelee3264/spyhop
.\spyhop\windows\spyhop.cmd
```

Or download the repository as a ZIP from GitHub, unzip it, and run `windows\spyhop.cmd`. To update, run `git pull` (or download the ZIP again).

The board opens in your default browser at `http://127.0.0.1:47613/`. `spyhop.cmd doctor` explains how each session was found, or why it was not.

A **tray icon** appears next to the clock. It shows how many sessions are waiting for you (gray when the board is off). Click it to open the small board panel; right-click it to see every session and jump to one. It also restarts the board when Claude or Codex runs. Choose **Hide tray icon** at the bottom of its right-click menu to remove it; `spyhop.cmd` brings it back.

## What works

- Sessions in Windows Terminal, VS Code, PowerShell or cmd are grouped by folder and terminal. Sessions the **Claude desktop app** runs show up under `folder · Claude app`.
- **Claude app Code tab sessions** used in the last 12 hours show up even when the app has put them to sleep, read from the app's own session records. Archived ones are left out.
- **Codex desktop app** threads (Codex inside the ChatGPT app, or the IDE extension) used in the last 12 hours show up under `folder · Codex app`, read from Codex's `state_N.sqlite`. Only threads you started are shown.
- **Cowork** sessions show up only when the app keeps their records on your computer (`local-agent-mode-sessions`). Recent Cowork versions keep sessions inside the Cowork virtual machine's disk, so those cannot be shown.
- **Go to session** brings that terminal or app window to the front. It cannot pick the exact tab.
- **End session** force-closes the AI program (Windows has no SIGTERM). The terminal tab stays.
- Summaries, AI topic grouping and **Start at login** (a `Spyhop` entry under `HKCU\...\CurrentVersion\Run`) work as on macOS.
- Not on Windows: Orca, moving sessions, and automatic updates.
- DeepSeek reads its key from the `DEEPSEEK_API_KEY` environment variable instead of the Keychain.

## Tests

```powershell
cd windows
python -X utf8 -m unittest discover -s tests
```

CI runs these on `windows-latest` for every pull request that touches `windows/` (see `.github/workflows/windows.yml`). The tray icon and window focus cannot be tested there.
