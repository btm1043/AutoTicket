import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt5.QtCore import QSettings, QUrl
from types import SimpleNamespace
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QMessageBox
from autoticket_app.ui import MainWindow, DropLabel
from autoticket_app.config import OutlookSettings
from autoticket_app.models import Ticket, ParsedEmail
from autoticket_app.category_rules import CategoryRule
from autoticket_app.theme import LIGHT_THEME


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.window = MainWindow.__new__(MainWindow)
        QMainWindow.__init__(self.window)
        self.window.rules_settings = QSettings(str(Path(self.temp.name) / "settings.ini"), QSettings.IniFormat)
        self.window.outlook_settings = OutlookSettings()
        self.window.outlook_queue = []
        self.window.current_outlook_item = None
        self.window.category_rules = ()
        self.window.servicenow_settings = SimpleNamespace(start_url="https://test.example", host_regex="test.example", ready_dom_selector="#form", field_bindings=())
        self.window.view = QLabel("ServiceNow workspace")
        self.window.view.url = lambda: QUrl("https://test.example/form")
        self.window.drop_label = DropLabel(self.window)
        self.window._build_controls()
        self.window._build_layout()
        self.window.setStyleSheet(LIGHT_THEME)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.window.close)

    def test_debug_edits_do_not_change_source_preview(self):
        self.window.set_ticket(Ticket(short_description="Before", extra_fields={"priority": "2"}))
        self.window.debug_toggle.setChecked(True)
        self.assertEqual(self.window.panel_stack.currentIndex(), 2)
        self.window.set_json({"short_description": "After", "priority": "1"})
        self.window.panel_stack.setCurrentIndex(0)
        self.assertEqual(self.window.preview_ticket.short_description, "Before")
        self.assertTrue(self.window.email_preview.isReadOnly())
        self.window.panel_stack.setCurrentIndex(2)
        self.window.json_input.setPlainText("{")
        with patch.object(QMessageBox, "warning"):
            self.window.debug_toggle.setChecked(False)
        self.assertEqual(self.window.panel_stack.currentIndex(), 0)
        self.assertFalse(self.window.debug_toggle.isChecked())
        self.assertEqual(self.window.json_input.toPlainText(), "{")

    def test_category_choices_and_manual_values(self):
        from autoticket_app.ticket_editor import TicketEditor
        editor = TicketEditor()
        editor.set_rules((CategoryRule("Network", "VPN", ("vpn",)), CategoryRule("Hardware", "Printer", ("printer",))))
        editor.set_ticket(Ticket(category="Network", subcategory="VPN"))
        self.assertEqual(editor.ticket().subcategory, "VPN")
        editor.fields["category"].setCurrentText("Hardware")
        self.assertEqual(editor.ticket().subcategory, "")
        self.assertEqual(editor.fields["subcategory"].itemText(1), "Printer")
        editor.fields["subcategory"].setCurrentText("Custom")
        self.assertEqual(editor.ticket().subcategory, "Custom")

    def test_load_email_returns_to_preview_and_fills(self):
        item = SimpleNamespace(subject="VPN issue", to_email=lambda: ParsedEmail(subject="VPN issue", body="Details"))
        self.window.outlook_queue = [item]
        self.window.panel_stack.setCurrentIndex(1)
        operations = []
        def run(js, callback, operation):
            operations.append(operation)
            callback({"ready": True} if operation == "ready" else {"short_description": True})
        self.window.run_browser_js = run
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.window.load_next_outlook_email()
        self.assertEqual(self.window.panel_stack.currentIndex(), 0)
        self.assertEqual(self.window.preview_ticket.short_description, "VPN issue")
        self.assertEqual(operations, ["ready", "fill"])
        self.assertFalse(self.window.fill_pending)

    def test_not_ready_or_declined_never_fills(self):
        for ready in (False, True):
            operations = []
            def run(js, callback, operation):
                operations.append(operation)
                callback({"ready": ready})
            self.window.run_browser_js = run
            with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
                self.window.fill_from_preview()
            self.assertEqual(operations, ["ready"])
            self.assertFalse(self.window.fill_pending)

    def test_pending_fill_prevents_overlapping_load(self):
        self.window.fill_pending = True
        with patch.object(self.window, "scan_outlook") as scan:
            self.window.load_next_outlook_email()
            scan.assert_not_called()

    def test_sidebar_and_render(self):
        self.window.resize(1500, 900)
        self.window.show()
        self.app.processEvents()
        self.window.sidebar_button.setChecked(True)
        self.assertTrue(self.window.right_panel.isHidden())
        self.window.sidebar_button.setChecked(False)
        self.assertFalse(self.window.right_panel.isHidden())
        if os.environ.get("AUTOTICKET_UI_PREVIEW"):
            self.window.grab().save(os.environ["AUTOTICKET_UI_PREVIEW"])
