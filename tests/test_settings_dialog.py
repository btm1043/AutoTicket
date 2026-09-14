import ast
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QWidget
from autoticket_app.config import _parse_servicenow_settings, OutlookSettings, load_servicenow_settings
from autoticket_app.settings_dialog import ServiceNowSettingsDialog
import json
from autoticket_app.models import Ticket
from autoticket_app.ticket_editor import TicketEditor, QUICK_TICKETS, build_quick_ticket


class SettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_save_from_dialog(self):
        with tempfile.TemporaryDirectory() as directory:
            window = QWidget()
            source = Path(directory) / "source.json"
            data = dict(start_url="https://old.example/", host_regex="old", ready_dom_selector="#form",
                        field_bindings=[dict(value_key="category", form_field="category", selectors=[])])
            source.write_text(json.dumps(data), encoding="utf-8")
            window.servicenow_settings = _parse_servicenow_settings(data, source)
            window.outlook_settings = OutlookSettings()
            window.local_data_dir = Path(directory) / "local"
            dialog = ServiceNowSettingsDialog(window)
            dialog.landing.setText("https://test.example/incident")
            dialog.derive_host()
            dialog.folder.setText("Help/New")
            dialog.save()
            self.assertEqual(dialog.result(), dialog.Accepted)
            self.assertEqual(load_servicenow_settings(window.local_data_dir).outlook.inbox_subfolder, "Help/New")
            window.close()

    def test_project_syntax(self):
        for path in (Path(__file__).resolve().parents[1] / "autoticket_app").glob("*.py"):
            with self.subTest(path=path.name):
                ast.parse(path.read_text(encoding="utf-8"))

    def test_ticket_editor_preserves_extra_fields(self):
        editor = TicketEditor()
        original = Ticket(short_description="VPN", description="First line\nSecond line",
                          caller_email="user@example.com", category="Network",
                          extra_fields={"priority": "3"})
        editor.set_ticket(original)
        self.assertEqual(editor.ticket(), original)
        editor.fields["category"].setCurrentText("Hardware")
        self.assertEqual(editor.ticket().category, "Hardware")
        self.assertEqual(editor.ticket().extra_fields, {"priority": "3"})

    def test_quick_tickets_are_independent_drafts(self):
        editor = TicketEditor()
        editor.set_ticket(Ticket(caller_name="Previous caller", extra_fields={"priority": "1"}))
        for name in QUICK_TICKETS:
            ticket = build_quick_ticket(name)
            editor.set_ticket(ticket)
            self.assertTrue(editor.ticket().short_description)
            self.assertTrue(editor.ticket().description)
            self.assertEqual(editor.ticket().caller_name, "")
            self.assertEqual(editor.ticket().category, "")
            self.assertEqual(editor.ticket().extra_fields, {})
