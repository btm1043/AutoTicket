"""Load category keywords independently of the email and browser integrations."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
import xml.etree.ElementTree as ET

from autoticket_app.models import ParsedEmail

MAX_RULE_BYTES = 2 * 1024 * 1024


class CategoryRulesError(ValueError):
    pass


@dataclass(frozen=True)
class CategoryRule:
    category: str
    subcategory: str
    keywords: tuple[str, ...]


def _name(value, location):
    if not isinstance(value, str) or not value.strip():
        raise CategoryRulesError(f"{location} must be a non-empty string")
    return value.strip()


def parse_category_rules(payload: bytes) -> tuple[CategoryRule, ...]:
    if len(payload) > MAX_RULE_BYTES:
        raise CategoryRulesError("Rules file exceeds the 2 MB limit")
    try:
        text = payload.decode("utf-8-sig")
        if text.lstrip().startswith("<"):
            if re.search(r"<!\s*(DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
                raise CategoryRulesError("XML DTDs and entities are not supported")
            root = ET.fromstring(text)
            if root.tag != "categories":
                raise CategoryRulesError("XML root must be <categories>")
            categories = []
            for category in root:
                if category.tag != "category":
                    raise CategoryRulesError("Expected <category> inside <categories>")
                subcategories = []
                for sub in category:
                    if sub.tag != "subcategory" or any(k.tag != "keyword" or len(k) for k in sub):
                        raise CategoryRulesError("Expected <subcategory> containing <keyword> elements")
                    subcategories.append({"name": sub.get("name"), "keywords": [k.text for k in sub]})
                categories.append({"name": category.get("name"), "subcategories": subcategories})
            data = {"categories": categories}
        else:
            data = json.loads(text)
    except (UnicodeError, json.JSONDecodeError, ET.ParseError) as exc:
        raise CategoryRulesError(f"Invalid UTF-8 JSON/XML rules: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("categories"), list) or not data["categories"]:
        raise CategoryRulesError("'categories' must be a non-empty array")
    rules = []
    for category in data["categories"]:
        if not isinstance(category, dict):
            raise CategoryRulesError("Each category must be an object")
        name = _name(category.get("name"), "Category name")
        subs = category.get("subcategories")
        if not isinstance(subs, list) or not subs:
            raise CategoryRulesError(f"{name}: subcategories must be a non-empty array")
        for sub in subs:
            if not isinstance(sub, dict):
                raise CategoryRulesError("Each subcategory must be an object")
            subname = _name(sub.get("name"), "Subcategory name")
            keywords = sub.get("keywords")
            if not isinstance(keywords, list) or not keywords:
                raise CategoryRulesError(f"{name}/{subname}: keywords must be a non-empty array")
            normalized = tuple(dict.fromkeys(_normalize(_name(k, "Keyword")) for k in keywords))
            rules.append(CategoryRule(name, subname, normalized))
    return tuple(rules)


def load_category_rules(source: str) -> tuple[CategoryRule, ...]:
    source = source.strip()
    if not source:
        raise CategoryRulesError("Choose a JSON/XML file or enter an HTTP(S) URL")
    try:
        if urlsplit(source).scheme.lower() in ("http", "https"):
            with urlopen(source, timeout=10) as response:
                payload = response.read(MAX_RULE_BYTES + 1)
        else:
            with Path(source).open("rb") as handle:
                payload = handle.read(MAX_RULE_BYTES + 1)
        return parse_category_rules(payload)
    except CategoryRulesError:
        raise
    except (OSError, ValueError) as exc:
        raise CategoryRulesError(f"Could not load category rules: {exc}") from exc


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def match_category(email: ParsedEmail, rules: tuple[CategoryRule, ...]) -> CategoryRule | None:
    # Keep subject/body separate so a phrase cannot accidentally span both fields.
    texts = (_normalize(email.subject), _normalize(email.body))
    best = None
    best_score = 0
    for rule in rules:
        score = sum(any(re.search(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)", text)
                        for text in texts) for keyword in rule.keywords)
        if score > best_score:
            best, best_score = rule, score
    return best
