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

## Install the extension (development)

1. Start Advanced App Tracker.
2. In Firefox open `about:debugging#/runtime/this-firefox`.
3. Click **Load Temporary Add-on…** and choose `extension/manifest.json`.

Temporary add-ons are removed when Firefox closes.

## Privacy

- The API binds to `127.0.0.1` only; nothing is sent to the internet.
- Query strings and fragments are never stored (they often contain tokens).
- Private windows are not tracked.
- Tracking can be turned off with the `browser_tracking_enabled` setting.
- Domains listed in `browser_ignored_domains` (comma separated, subdomains
  included) are not recorded.

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

## Known limitations

- Idle time (you walked away with the tab open) is not subtracted yet.
- Only Firefox is supported by the bundled extension.
