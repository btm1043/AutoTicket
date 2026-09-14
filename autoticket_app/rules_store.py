"""Atomic local snapshots of the last successfully loaded category rules."""

import json
import os
from pathlib import Path
import tempfile

from autoticket_app.category_rules import CategoryRulesError, parse_category_rules


def save_rules_snapshot(path: Path, source: str, rules) -> None:
    data = {"source": source, "categories": [
        {"name": rule.category, "subcategories": [
            {"name": rule.subcategory, "keywords": list(rule.keywords)}
        ]} for rule in rules
    ]}
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    # Validate before replacing the previous usable snapshot.
    parse_category_rules(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def load_rules_snapshot(path: Path):
    from autoticket_app.category_rules import MAX_RULE_BYTES

    with path.open("rb") as handle:
        payload = handle.read(MAX_RULE_BYTES + 1)
    rules = parse_category_rules(payload)
    source = json.loads(payload).get("source")
    if not isinstance(source, str) or not source.strip():
        raise CategoryRulesError("Saved rules have no source")
    return source, rules
