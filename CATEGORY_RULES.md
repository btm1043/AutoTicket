# Email category rules

Open **Settings > Category Rules**, then use **Browse Rules** to select a UTF-8
JSON or XML file. The main window shows a compact summary of the active rules.
Examples are in `examples/category_rules.json` and `examples/category_rules.xml`;
both describe the same rules. Edit their category/subcategory names to match the
values expected by your ServiceNow form.

After the status says rules are loaded, drop a `.msg` file or load an Outlook
queue email. Its category and subcategory appear in the editable ticket JSON.
Review the result before using **Fill From JSON**. Both application variants
support these controls. Pasted ticket JSON is not automatically classified.

Each category has a `name` and a non-empty `subcategories` list. Each subcategory
has a `name` and a non-empty `keywords` list. The XML equivalent uses a
`categories` root, `category` and `subcategory` elements with `name` attributes,
and one `keyword` element per keyword or phrase. Empty names/keywords are errors.

Matching checks the complete email subject and body, ignoring case and repeated
whitespace. Keywords are literal words or phrases, not regular expressions.
Word boundaries prevent `vpn` from matching `myvpnclient`. Add spelling variants
or plurals explicitly. Each distinct keyword contributes one point, regardless
of how often it appears. The subcategory with the most matching keywords wins;
ties use the first subcategory in file order. At least one keyword must match.
No match leaves category and subcategory blank. Quoted email history is included
when it is part of the parsed body; negation is not interpreted.

## Web hosting

When a server is available, host the same JSON/XML file and enter its HTTP(S) URL
in the rules source field, then click **Load / Reload Rules**. The URL need not
end in `.json` or `.xml`; content determines the format. Only the rules are
downloaded; email contents are not sent to the rules server.

The last successfully loaded rules are saved per Windows user and restored
from local storage on startup, even if the original file or server is unavailable.
No rules server connection is required unless you click **Load / Reload Rules**
or enable **Refresh from source when the app starts** in Settings (off by default).
Relative file paths are relative to the process working
directory; the file picker supplies an absolute path. Reload after changing a
file or its hosted contents. New rules apply to subsequently loaded emails;
reload an email to classify it again. While loading, emails use the current
rules. Downloads run in a background thread, use a 10-second socket timeout,
and accept at most 2 MB. HTTPS uses normal certificate validation.

Preferences are stored in `settings.ini` and the last valid rules and their source
in `category_rules_cache.json` in the application's local data directory (normally
`%LOCALAPPDATA%/AutoTicket`). The Settings dialog displays the exact directory.
The previous registry-based source preference is migrated automatically.
Snapshots are validated and replaced atomically. On a failed reload or save,
the previous rules remain active and the previous snapshot is retained. If the
snapshot is missing or corrupt, load the source again through Settings.
Changes apply to the next email loaded. Closing Settings does not load an edited
source: use **Load / Reload Rules** to validate and save it. The refresh checkbox
is saved immediately.

Local rule matching works offline; accessing ServiceNow still requires its normal
connection. Authenticated rules hosting is not configured yet.
XML DTDs and entity declarations are rejected.
