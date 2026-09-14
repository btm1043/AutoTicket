import json
import re
from urllib.parse import urlsplit
from collections.abc import Iterable

from autoticket_app.models import FieldBinding, Ticket


def is_local_form_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return parsed.scheme in ("http", "https") and parsed.hostname in ("localhost", "127.0.0.1")
    except ValueError:
        return False


def is_servicenow_url(url: str, host_regex: str, start_url: str = "") -> bool:
    def origin(value):
        parsed = urlsplit(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        return parsed.scheme, parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        current = origin(url)
        if current is None:
            return False
        if start_url and current == origin(start_url):
            return True
        return bool(re.search(host_regex, url, re.IGNORECASE))
    except (ValueError, re.error):
        return False


FRAME_WINDOWS_JS = """
  const windows = [];
  function visit(w) {
    try {
      void w.document;
      windows.push(w);
      for (let i = 0; i < w.frames.length; i++) visit(w.frames[i]);
    } catch (e) { /* Cross-origin frames cannot be accessed by this transport. */ }
  }
  visit(window);
"""


def build_form_values(ticket: Ticket) -> dict[str, str]:
    values = {}
    for key, value in ticket.to_dict().items():
        if value is None:
            values[key] = ""
        elif isinstance(value, str):
            values[key] = value
        else:
            values[key] = str(value)

    values["caller_id"] = ticket.caller_name or ticket.caller_email
    return values


def _build_binding_payload(field_bindings: Iterable[FieldBinding]) -> list[dict[str, object]]:
    payload = []
    for binding in field_bindings:
        payload.append(
            {
                "value_key": binding.value_key,
                "form_field": binding.form_field,
                "selectors": list(binding.selectors),
            }
        )
    return payload


def build_servicenow_fill_js(
    ticket: Ticket,
    field_bindings: Iterable[FieldBinding],
    required_dom_selector: str = "",
    local_fields_only: bool = False,
) -> str:
    payload = {
        "bindings": _build_binding_payload(field_bindings),
        "values": build_form_values(ticket),
        "readySelector": required_dom_selector,
        "localFieldsOnly": local_fields_only,
    }
    payload_json = json.dumps(payload)

    return f"""
(() => {{
  const payload = {payload_json};
  const out = {{}};
  {FRAME_WINDOWS_JS}
  let target = null;
  try {{
    target = payload.localFieldsOnly ? window : windows.find(w => payload.readySelector && w.document.querySelector(payload.readySelector));
    if (!target && !payload.readySelector) target = windows.find(w => w.g_form) || window;
  }} catch (e) {{ return {{error: "Invalid form selector: " + String(e)}}; }}
  if (!target) return {{error: "Ticket form was not found. It may have navigated or be in an inaccessible frame."}};

  function setBySelector(sel, value) {{
    let el;
    try {{ el = target.document.querySelector(sel); }} catch (e) {{ return false; }}
    if (!el) return false;
    el.focus();
    if (el.tagName === "SELECT") {{
      const option = Array.from(el.options).find(o => o.value === value) ||
        Array.from(el.options).find(o => o.text.trim().toLowerCase() === value.trim().toLowerCase());
      if (!option && value) return false;
      el.value = option ? option.value : "";
    }} else {{ el.value = value; }}
    el.dispatchEvent(new target.Event("input", {{ bubbles: true }}));
    el.dispatchEvent(new target.Event("change", {{ bubbles: true }}));
    return el.tagName === "SELECT" ? (!value || el.selectedIndex >= 0) : el.value === value;
  }}

  function setField(binding) {{
    const value = Object.prototype.hasOwnProperty.call(payload.values, binding.value_key)
      ? String(payload.values[binding.value_key] == null ? "" : payload.values[binding.value_key])
      : "";
    let ok = false;
    if (payload.localFieldsOnly) {{
      target = windows.find(w => binding.selectors.some(sel => {{
        try {{ return Boolean(w.document.querySelector(sel)); }} catch(e) {{ return false; }}
      }}));
      if (!target) {{ out[binding.form_field] = false; return; }}
    }}

    if (target.g_form && typeof target.g_form.setValue === "function") {{
      try {{
        target.g_form.setValue(binding.form_field, value);
        ok = true;
      }} catch (e) {{
        out[binding.form_field + "_g_form_error"] = String(e);
      }}
    }}

    if (!ok && binding.selectors && binding.selectors.length) {{
      for (const sel of binding.selectors) {{
        if (setBySelector(sel, value)) {{
          ok = true;
          break;
        }}
      }}
    }}

    out[binding.form_field] = ok;
  }}

  for (const binding of payload.bindings) {{
    setField(binding);
  }}

  out.url = window.location.href;
  out.title = document.title;
  return out;
}})();
"""


def build_ready_check_js(required_dom_selector: str, field_bindings: Iterable[FieldBinding] = (),
                         local_fields_only: bool = False) -> str:
    selector_json = json.dumps(required_dom_selector)
    if local_fields_only:
        selectors = json.dumps([selector for binding in field_bindings for selector in binding.selectors])
        return f"""
(() => {{
  {FRAME_WINDOWS_JS}
  const selectors = {selectors};
  return {{ready: windows.some(w => selectors.some(sel => {{
    try {{ return Boolean(w.document.querySelector(sel)); }} catch(e) {{ return false; }}
  }})), url: window.location.href, title: document.title}};
}})();
"""
    return f"""
(() => {{
  {FRAME_WINDOWS_JS}
  try {{ return {{
    ready: windows.some(w => Boolean(w.document.querySelector({selector_json}))),
    url: window.location.href,
    title: document.title
  }}; }} catch (e) {{ return {{ready: false, error: "Invalid form selector: " + String(e)}}; }}
}})();
"""
