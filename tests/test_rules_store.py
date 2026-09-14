from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoticket_app.category_rules import CategoryRulesError, load_category_rules
from autoticket_app.rules_store import load_rules_snapshot, save_rules_snapshot


class RulesStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "settings" / "rules.json"
        self.rules = load_category_rules(str(Path(__file__).resolve().parents[1] / "examples/category_rules.xml"))

    def test_saved_rules_work_without_source(self):
        source = "https://unavailable.example/categories.xml"
        save_rules_snapshot(self.path, source, self.rules)
        self.assertEqual(load_rules_snapshot(self.path), (source, self.rules))

    def test_failed_write_preserves_previous_rules(self):
        save_rules_snapshot(self.path, "original.json", self.rules)
        with patch("autoticket_app.rules_store.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                save_rules_snapshot(self.path, "new.json", self.rules)
        self.assertEqual(load_rules_snapshot(self.path), ("original.json", self.rules))
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_invalid_rules_do_not_replace_snapshot(self):
        save_rules_snapshot(self.path, "original.json", self.rules)
        with self.assertRaises(CategoryRulesError):
            save_rules_snapshot(self.path, "new.json", ())
        self.assertEqual(load_rules_snapshot(self.path), ("original.json", self.rules))

    def test_corrupt_snapshot_is_rejected(self):
        self.path.parent.mkdir()
        self.path.write_text('{"source":"x","categories":[]}', encoding="utf-8")
        with self.assertRaises(CategoryRulesError):
            load_rules_snapshot(self.path)
