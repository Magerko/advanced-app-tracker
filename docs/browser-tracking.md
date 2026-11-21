# Browser tab tracking

Advanced App Tracker can record which website you have open in Firefox, not
just that `firefox.exe` is running. Everything stays on your computer.

## How it works

```text
Firefox extension  ->  http://127.0.0.1:8765  ->  app_tracker/browser  ->  SQLite
```

1. The extension (`extension/`) watches the active tab and sends three kinds
   of events to a local API: `start`, `update-title` and `stop`.
2. The API (`app_tracker/browser/api.py`) only listens on `127.0.0.1`.
3. Sessions are stored in the `browser_activity` table of `app_tracker.db`.
4. Each session gets a category (study, code, social, entertainment, other)
   from the site and the page title (`categorizer.py`).

## Requirements

The local API needs `fastapi` and `uvicorn` (both are in `requirements.txt`).
Without them the app still starts; only browser tracking is switched off and
a warning is written to the log.

## Install the extension

1. Start Advanced App Tracker and open the **Браузер** tab.
2. Click **Установить расширение в Firefox**.
3. Firefox opens and asks "Add Advanced App Tracker?". Click **Add**.

That's all: the extension is signed by Mozilla, so it stays installed after
Firefox restarts. You can also drag `signed-extension/advanced-app-tracker.xpi`
into a Firefox window yourself.

### For developers

- While changing the extension, load it without signing: open
  `about:debugging#/runtime/this-firefox` → **Load Temporary Add-on…** →
  `extension/manifest.json` (removed when Firefox closes), or run
  `web-ext run` inside `extension/` to get auto-reload.
- After a change, raise `"version"` in `extension/manifest.json` and sign a
  new file (keys from https://addons.mozilla.org/developers/addon/api/key/):

  ```powershell
  npm install --global web-ext
  $env:WEB_EXT_API_KEY = "user:12345:678"
  $env:WEB_EXT_API_SECRET = "your-secret"
  python tools/sign_extension.py
  ```

  The script writes `signed-extension/advanced-app-tracker.xpi`; commit it.
  The extension is signed as *unlisted*: it is not shown in the add-ons
  catalogue.

Click the extension icon to see whether the app is running and which site is
being recorded right now.

## Privacy

- The API binds to `127.0.0.1` only; nothing is sent to the internet.
- Query strings and fragments are never stored (they often contain tokens).
- Private windows are not tracked.
- Time when you are away is not counted: after 60 seconds without mouse or
  keyboard input (or when the screen is locked) the session stops. A tab that
  is playing sound (a video lecture) keeps counting.
- Tracking can be turned off in the **Браузер** tab (setting
  `browser_tracking_enabled`).
- Domains listed in `browser_ignored_domains` (comma separated, subdomains
  included) are not recorded.

## Report in the app

The **Браузер** tab shows the time per category and per site for today, the
last 7 days or the last 30 days. It refreshes every 30 seconds. At the bottom
you can switch recording on or off and edit the list of ignored sites; both
take effect immediately, no restart needed.

## Settings (table `settings`)

| Key | Meaning | Default |
|---|---|---|
| `browser_tracking_enabled` | `True` / `False` | `True` |
| `browser_api_port` | port of the local API | `8765` |
| `browser_ignored_domains` | e.g. `bank.example,mail.example` | empty |

If you change the port, also change `API_BASE` in `extension/background.js`
and `host_permissions` in `extension/manifest.json`.

## API

| Method and path | Purpose |
|---|---|
| `GET /health` | check that the app is running |
| `POST /browser-event/start` | a tab became active |
| `POST /browser-event/update-title` | the tab title changed |
| `POST /browser-event/stop` | the session ended |

## Reliability

Once a minute the extension re-sends `start` for the open session. The app
ignores a session it already knows, so this is safe. If the app was restarted
in the middle of a session, the session is restored with its original start
time instead of being lost.

## Known limitations

- Only Firefox is supported by the bundled extension.
- A silent video watched without touching the mouse stops counting after
  60 seconds.
