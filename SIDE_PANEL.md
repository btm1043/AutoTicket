# Ticket side panel

The default view provides editable summary, details, caller name/email, category
and subcategory fields. Uploaded `.msg` files and loaded Outlook emails populate
this editor, including category-rule matches. **Fill ServiceNow Form** copies the
draft to the browser form for review; it does not submit the ticket.

Quick-start buttons create editable drafts for **Password Reset**, **Called-in
Issue**, and **General Inquiry**. **New Blank Ticket** starts without a template.
Replacing a nonempty draft asks for confirmation. Starting any of these drafts
clears the association with the previously loaded Outlook email so it cannot be
accidentally marked acted. Categories are left blank for the operator to choose;
templates do not assume instance-specific category or contact-type values.

**Show debug views** switches to the JSON editor, parsed output, debug actions and
logs. The preference is stored locally in `settings.ini`. Switching views carries
ticket edits across and preserves extra JSON fields. Invalid JSON must be fixed
before switching back. Logs continue collecting while hidden. The Outlook queue
and a short status message remain available in either view.

Potential next additions: configurable quick-ticket templates, category dropdowns
from loaded rules, and caller lookup once a supported directory source is chosen.
