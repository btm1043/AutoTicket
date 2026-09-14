# ServiceNow Config

`AutoTicket` now loads ServiceNow form settings from `servicenow_config.json`.

## Where the app looks

The app loads the first valid file it finds in this order:

1. `%LOCALAPPDATA%\\AutoTicket\\servicenow_config.json`
2. `servicenow_config.json` next to the app
3. The bundled fallback copy shipped with the app

If a higher-priority file exists but is invalid, the app logs a warning and tries the next one.

## What you can change

- `start_url`: the page the embedded browser opens first
- `host_regex`: what URLs count as your ServiceNow host
- `ready_dom_selector`: what selector means the target form is ready
- `outlook.inbox_subfolder`: the Outlook subfolder under Inbox that supplies queued emails
- `field_bindings`: how ticket keys map to ServiceNow fields and DOM selectors

## Outlook queue

The Outlook scanner attaches to the already-running desktop Outlook instance through Windows COM.
It does not connect directly to Exchange, Microsoft Graph, or any mail server.
Outlook should already be fully open before you scan.

By default it scans:

```text
Inbox\AutoTicket
```

To use another Inbox subfolder, change the config:

```json
"outlook": {
  "inbox_subfolder": "Help Desk/New Tickets"
}
```

The app stores acted-on email message IDs in local app data at:

```text
%LOCALAPPDATA%\AutoTicket\outlook_acted.json
```

Use `Scan Outlook` to build the queue, `Load Next Email` to create ticket JSON from the selected queued email, and `Mark Email Acted` after the ticket has been handled.

Scanning is manual right now:

- `Scan Outlook` refreshes the queue from the configured Inbox subfolder
- `Load Next Email` also scans first if the queue is empty
- Emails already listed in `outlook_acted.json` are skipped on future scans
- Nothing is marked acted automatically; click `Mark Email Acted` only after the ticket has been handled

Outlook sender details flow into the ticket when available:

- email subject -> `short_description`
- email body -> `description`
- sender display name -> `caller_name`
- sender SMTP address -> `caller_email`

## Outlook troubleshooting

If scanning reports that AutoTicket could not attach to Outlook:

- Make sure desktop Outlook is open and fully started
- Run Outlook and AutoTicket at the same privilege level; avoid running one as Administrator and the other normally
- Close and reopen both apps normally if Outlook was launched elevated earlier
- Confirm `pywin32` is installed when running from Python source with `python -m pip install -r requirements-app.txt`

If scanning reports that the folder was not found, check that `outlook.inbox_subfolder` is relative to Inbox.
For nested folders, use either `/` or `\`, for example `Help Desk/New Tickets`.

## Add or update a field

Each binding looks like this:

```json
{
  "value_key": "short_description",
  "form_field": "short_description",
  "selectors": [
    "#incident\\.short_description",
    "input[name='incident.short_description']",
    "input[name='short_description']"
  ]
}
```

- `value_key` is the ticket JSON key the app reads
- `form_field` is the `g_form.setValue(...)` field name
- `selectors` are DOM fallbacks if `g_form` is unavailable

If you add a brand-new ticket field, you still need phase 3 Python work to add that field to the canonical `Ticket` model. If you are only remapping an existing field to a different ServiceNow control, JSON-only changes are enough.
