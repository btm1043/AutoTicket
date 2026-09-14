import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from autoticket_app.config import (
    ConfigError, _parse_servicenow_settings, load_servicenow_settings, save_servicenow_settings,
)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.json"
        self.data = dict(start_url="https://old.example/", host_regex="old", ready_dom_selector="#form",
                         field_bindings=[dict(value_key="category", form_field="category", selectors=["#category"])],
                         outlook={"inbox_subfolder": "Old", "extra": True}, extra="preserved")
        self.source.write_text(json.dumps(self.data), encoding="utf-8")
        self.current = _parse_servicenow_settings(self.data, self.source)
        self.local = self.root / "local"

    def save(self, **changes):
        values = dict(start_url="https://new.example/incident", host_regex=r"^https://new\.example/",
                      ready_dom_selector="#new", field_bindings=self.data["field_bindings"], inbox_subfolder="Help/New")
        values.update(changes)
        return save_servicenow_settings(self.local, self.current, **values)

    def test_persistence_precedence_and_preserved_keys(self):
        result = self.save()
        loaded = load_servicenow_settings(self.local)
        self.assertEqual(result.settings, loaded.settings)
        self.assertEqual(loaded.outlook.inbox_subfolder, "Help/New")
        saved = json.loads(result.settings.source_path.read_text())
        self.assertEqual(saved["extra"], "preserved")
        self.assertTrue(saved["outlook"]["extra"])
        self.assertEqual(json.loads(self.source.read_text()), self.data)

    def test_invalid_input_does_not_replace_saved_settings(self):
        result = self.save()
        before = result.settings.source_path.read_bytes()
        for change in ({"start_url": "file:///tmp/x"}, {"host_regex": "["},
                       {"host_regex": "wrong-host"}, {"inbox_subfolder": " "},
                       {"ready_dom_selector": ""}, {"field_bindings": []}):
            with self.subTest(change=change), self.assertRaises(ConfigError):
                self.save(**change)
            self.assertEqual(result.settings.source_path.read_bytes(), before)

    def test_failed_save_preserves_previous_file(self):
        result = self.save()
        before = result.settings.source_path.read_bytes()
        with patch("autoticket_app.config.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(ConfigError):
                self.save(inbox_subfolder="Different")
        self.assertEqual(result.settings.source_path.read_bytes(), before)
