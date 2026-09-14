# Playwright CDP Variant

`autoticket_playwright.py` runs the same AutoTicket UI, parser, Outlook queue, profile, and ServiceNow config, but executes the ServiceNow ready check and form fill through Playwright over QtWebEngine's Chrome DevTools Protocol endpoint.

The original `autoticket.py` entry point still uses `QWebEnginePage.runJavaScript`.

## Install

```powershell
python -m pip install -r requirements-app.txt
```

This variant only attaches to the Chromium runtime bundled with QtWebEngine, so `playwright install` is not required for this flow.

## Run

```powershell
python autoticket_playwright.py
```

By default, the launcher sets:

```powershell
QTWEBENGINE_REMOTE_DEBUGGING=9222
```

and Playwright connects to:

```text
http://127.0.0.1:9222
```

## Change the CDP port

Use **Settings > Playwright Connection** to save a host, port and operation timeout
in the local `settings.ini`, then restart. The dialog shows the active endpoint.
Environment variables below override the saved host and port. An explicitly set
`QTWEBENGINE_REMOTE_DEBUGGING` still controls Qt's listener; keep it consistent
with your selected endpoint port.

If port `9222` is already in use:

```powershell
$env:AUTOTICKET_CDP_PORT = "9333"
python autoticket_playwright.py
```

If you need a different host for the CDP endpoint:

```powershell
$env:AUTOTICKET_CDP_HOST = "127.0.0.1"
$env:AUTOTICKET_CDP_PORT = "9333"
python autoticket_playwright.py
```

## Notes

- Keep `QTWEBENGINE_REMOTE_DEBUGGING` local-only where possible; a CDP port can control the embedded browser session.
- The variant reuses `servicenow_config.json`, including `ready_dom_selector`, `field_bindings`, and `outlook.inbox_subfolder`.
- Outlook scanning still uses local Windows COM through the running desktop Outlook instance; Playwright only changes the embedded browser fill transport.
- Fill behavior still uses the same ServiceNow JavaScript payload, so this is intended as a transport swap before we make deeper Playwright-native actions like `locator.fill()`.
- Some QtWebEngine builds reject Playwright's browser-context setup with `Browser.setDownloadBehavior`. When that happens, AutoTicket falls back to direct page-level CDP `Runtime.evaluate` and logs the operation as `via raw-cdp`.

## Troubleshooting

If the log shows this Playwright connection error:

```text
BrowserType.connect_over_cdp: Protocol error (Browser.setDownloadBehavior): Browser context management is not supported.
```

QtWebEngine's CDP endpoint is reachable, but it does not support the browser-level command Playwright sends while attaching. This is expected on some QtWebEngine builds. The app should automatically retry through raw page-level CDP; a successful retry appears as:

```text
[playwright] fill completed via raw-cdp
```
