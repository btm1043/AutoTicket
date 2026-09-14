# Webpage-first ticket workflow

ServiceNow is the primary ticket editor. The sidebar has a read-only Preview,
an Email Queue tab with a count, and an optional Debug tab.

Load Next Email loads the selected email (or the first if none is selected),
shows Preview, and checks the webpage form. Dropped .msg files and quick actions
also prepare a preview and attempt to fill the webpage. Category rules still
suggest values for email tickets before filling.

If the form is ready, confirmation is required before replacing mapped webpage
fields. The app cannot reliably tell whether edits made directly in ServiceNow
are saved. Declining leaves the webpage unchanged. If the form is not ready,
navigate to it and use Fill / Retry on Webpage. Retries use the same confirmation.

Edit caller details, categories and other fields directly in ServiceNow.
Submission remains manual. The preview is the imported draft, not a live mirror
of webpage edits. Mark Email Acted remains an explicit action.

Quick actions provide Password Reset, Phone Issue and General Inquiry drafts.
New Blank Ticket fills blank mapped fields only after confirmation. Starting a
quick draft clears the association with a previously loaded Outlook email.

Debug JSON is independent of the preview. Switching tabs never writes to the
webpage or discards debug edits. Fill From JSON uses the same readiness check
and overwrite confirmation. Debug visibility is remembered locally.
