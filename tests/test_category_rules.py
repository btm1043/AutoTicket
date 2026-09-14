import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest

from autoticket_app.category_rules import (
    CategoryRulesError, MAX_RULE_BYTES, load_category_rules, match_category, parse_category_rules,
)
from autoticket_app.features import build_ticket_from_email
from autoticket_app.models import ParsedEmail

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class CategoryRulesTests(unittest.TestCase):
    def setUp(self):
        self.rules = load_category_rules(str(EXAMPLES / "category_rules.json"))

    def test_formats_are_equivalent(self):
        self.assertEqual(self.rules, load_category_rules(str(EXAMPLES / "category_rules.xml")))

    def test_subject_body_scoring_and_ticket_integration(self):
        ticket = build_ticket_from_email(
            ParsedEmail(subject="VPN issue", body="Printer has a PAPER   JAM"), category_rules=self.rules)
        self.assertEqual((ticket.category, ticket.subcategory), ("Hardware", "Printer"))
        self.assertEqual(ticket.short_description, "VPN issue")

    def test_word_boundaries_no_match_and_no_rules(self):
        self.assertIsNone(match_category(ParsedEmail(body="myvpnclient"), self.rules))
        self.assertEqual(build_ticket_from_email(ParsedEmail(body="VPN")).category, "")
        self.assertEqual(build_ticket_from_email(ParsedEmail(body="hello"), category_rules=self.rules).category, "")

    def test_ties_and_repetitions(self):
        match = match_category(ParsedEmail(body="vpn printer printer printer"), self.rules)
        self.assertEqual(match.subcategory, "VPN")

    def test_phrase_does_not_span_subject_and_body(self):
        self.assertIsNone(match_category(ParsedEmail(subject="remote", body="access"), self.rules))

    def test_duplicate_keywords_count_once(self):
        rules = parse_category_rules(b'{"categories":[{"name":"A","subcategories":[{"name":"B","keywords":["VPN","vpn"]}]}]}')
        self.assertEqual(rules[0].keywords, ("vpn",))

    def test_invalid_rules(self):
        for payload in (b"{", b"[]", b'{"categories":[]}', b"<wrong/>",
                        b'<!DOCTYPE categories><categories/>', b"\xff",
                        b'{"categories":[{"name":"X","subcategories":[{"name":"Y","keywords":[""]}]}]}',
                        b"x" * (MAX_RULE_BYTES + 1)):
            with self.subTest(payload=payload[:80]), self.assertRaises(CategoryRulesError):
                parse_category_rules(payload)

    def test_missing_file(self):
        with self.assertRaises(CategoryRulesError):
            load_category_rules(str(EXAMPLES / "missing.json"))

    def test_http_source(self):
        handler = functools.partial(SimpleHTTPRequestHandler, directory=str(EXAMPLES))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            self.assertEqual(self.rules, load_category_rules(base + "/category_rules.json"))
            self.assertEqual(self.rules, load_category_rules(base + "/category_rules.xml"))
            with self.assertRaises(CategoryRulesError):
                load_category_rules(base + "/missing.json")
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
