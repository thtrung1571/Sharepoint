# AGENTS.md

## Project Overview

PySide6 Qt desktop app that automates Microsoft SharePoint/OneDrive login (with POP3-based 2FA), browses folder trees, downloads selected files, and sends them via SMTP email.

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point (`python main.py` / `python main.py --check`) |
| `config.py` | Load/save `config.json` + env overrides (`AMS_*`) |
| `paths.py` | Pure path helpers (`get_base_path`, `get_config_path`, ...) |
| `models/sent_log.py` | Thread-safe JSON send log, keyed by full path |
| `models/pop3_client.py` | POP3 fetcher for Microsoft 2FA codes (testable) |
| `services/browser_worker.py` | `BrowserThread` QThread driving Playwright |
| `services/email_worker.py` | `EmailThread` QThread for download + send |
| `services/email_sender.py` | Pure SMTP logic (no Qt), retry + SSL/STARTTLS switch |
| `services/sharepoint/` | SharePoint subpackage: `selectors.py` (DOM selectors, TARGET_URL, BASE_ID), `auth.py` (login + POP3 2FA), `navigation.py` (URL/path helpers), `browsing.py` (list/folder/checkbox), `download.py`. `__init__.py` re-exports the old flat API |
| `ui/main_window.py` | `MainWindow` QMainWindow |
| `ui/dialogs.py` | `SettingsDialog`, `SendMailDialog` |
| `config.json` | Runtime config (SMTP, defaults, headless flag) |
| `.env` | POP3 credentials for 2FA code fetching (do not commit) |
| `tests/` | `unittest` suite for pure logic (no browser needed) |
| `build.bat` / `build_dir.bat` | PyInstaller packaging (entry = `main.py`) |

## Architecture

Layered by responsibility, dependencies point one way (`ui` -> `services` -> `models`):

- `models/`: pure data + persistence. No Qt, no Playwright imports. Everything here must stay unit-testable without a display or a browser.
- `services/`: talks to the outside world. `email_sender.py` must remain Qt-free so it can be tested and reused standalone. `browser_worker.py` / `email_worker.py` are thin QThread wrappers; real logic lives in `sharepoint/` subpackage / `email_sender.py`.
- `ui/`: Qt widgets only. The UI never calls Playwright directly; it talks to the browser exclusively through `BrowserThread.send()` command dicts.

Never import Qt inside `models/` or `services/email_sender.py`.

## Config

- `config.json` holds runtime settings (SMTP, defaults, `headless`, `target_url`). Missing file is created with defaults by `config.py`.
- Any key can be overridden by an env var prefixed `AMS_` (e.g. `AMS_SMTP_PASS`, `AMS_TARGET_URL`). Env wins over file.
- POP3 credentials come from `.env` (`POP3_HOST`, `POP3_PORT`, `POP3_USER`, `POP3_PASS`), loaded by `config.py` at startup. Do not commit `.env`.
- `config.json` currently stores the SMTP password in plaintext. Prefer not setting `smtp_pass` in the file and using `AMS_SMTP_PASS` instead.

## Security

- **Zip-slip guard**: `email_sender.get_attachments` validates every zip entry before extraction. Entries whose resolved path escapes `<downloads>/_extracted` (e.g. `../evil`) raise `ValueError` and nothing is extracted. Never call `zf.extractall()` without this check if the zip source is untrusted.

## Critical Quirks

- **`.env` required**: POP3 credentials (`POP3_HOST`, `POP3_USER`, `POP3_PASS`) feed the 2FA code fetcher. `config.py` loads `.env` on import.
- **`ROOTFOLDER-BASED XHR MATCHING`**: SharePoint issue one POST `RenderListDataAsStream` per folder display. Predicate must match BOTH the `RootFolder=&lt;expected-path&gt;` and the `View=&lt;guid&gt;` (when known). See `browsing._make_list_stream_matcher`.
- **`TARGET_URL` fallback**: default SharePoint URL lives in `services/sharepoint/selectors.py` (`TARGET_URL`, re-exported); can be overridden by `config.json` key `target_url` or env `AMS_TARGET_URL`.
- **`sent_log.json` at project root** persists send history; keys may include full relative paths (`folder/sub/file.zip`) so same-named files in different folders don't collide.
- **Frozen vs dev paths**: `paths.get_base_path()` switches between `sys.executable` dir (packaged, `sys.frozen`) and this repo dir (dev). Nothing is written at import time.
- **Playwright browser path**: `main.py` sets `PLAYWRIGHT_BROWSERS_PATH` to `<base>/browsers`.
- **POP3 2FA**: verification code fetched via blocking POP3_SSL inside `models/pop3_client.py`, called from `services/sharepoint.wait_for_code` in a thread executor. Timeout 120s.

### Realtime UI Status
- Status bar now shows live progress during login (Clearing, Launching, Mail input, Waiting for OTP input, Fetching verification code, Waiting for code, Entering OTP code, Login success, Items ready). No more hardcoded "Starting browser..." placeholder.
- Headless mode still works but status is visible in UI.
- `BrowserThread` emits a `status` Qt signal at each phase; `sharepoint/` accepts an optional `status_cb` callback (default `None`) so it stays Qt-free. `BrowserThread._try_login` passes `self.status.emit` as the callback.

### Event-driven waits (no hard sleeps in SharePoint flow)
- All previous `wait_for_timeout()` calls were removed. Login: `page.goto(target_url, wait_until="load")` followed by the account-tile / email-input probing. A mid-flow redirect that raises `Execution context was destroyed` is caught in `auth.login` and treated as "no login form detected" (existing session), not as a crash.
- **Folder open/back waits on the list XHR, not on DOM timing.** `click_folder` / `go_back` wrap the click in `page.expect_response(...)` matching a POST to `RenderListDataAsStream` whose decoded `RootFolder=` query param ends with the expected target-folder path. `browsing._make_list_stream_matcher(expected_folder, expected_view)` builds that predicate from the current page URL (`id` → folder path, `viewid` → View GUID). This prevents SharePoint prefetch XHRs for sibling folders from satisfying the wait. On a 15 s timeout both fall back to `wait_for_load_state("domcontentloaded")` + `wait_for_folder_list`. Never re-dispatch the dblclick in the fallback branch.
- URL navigation (`navigate_to_path`, `navigate_to_url`, `reload_url` after send) still relies on callers' `get_items()` which already waits on selectors.
- OTC validation: instead of sleeping 8s and checking for the error element, `validate_code` waits up to 5s for `#idTd_OTCC_Error_OTC` to appear. Error shown → code rejected; timeout → accepted. Faster on both success and failure paths.

## Running

```bash
pip install -r requirements.txt
python main.py
```

Headless sanity check (no UI, no browser):

```bash
python main.py --check
```

## Tests

```bash
python -m unittest discover -s tests -t . -v
```

Stdlib `unittest` only (pytest is not a dependency). Tests cover pure logic: sent-log file handling, POP3 message parsing, attachment/zip logic in `email_sender`, and path helpers. Browser and SMTP network calls are injected/mocked.

## Building

```batch
build.bat        # onefile: dist/AutoMailSender.exe
build_dir.bat    # onedir:  dist/AutoMailSender/AutoMailSender.exe
```

Both scripts install playwright browsers, copy them to `browsers/`, and bundle everything into the PyInstaller output.

## Data Dirs (relative to base path)

| Dir/File | Purpose |
|----------|---------|
| `downloads/` | Temporary download staging, cleared after each send |
| `browser_data/` | Persistent Chromium user profile (login session) |
| `config.json` | Runtime config (auto-created with defaults if missing) |
| `sent_log.json` | Send history (path key -> sent_at, to, subject, files, is_folder) |

The app can be configured to `clear_browser: true` to wipe `browser_data/` on startup.
