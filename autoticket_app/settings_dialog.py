import json
import re
from dataclasses import asdict
from urllib.parse import urlsplit

from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from autoticket_app.config import ConfigError, save_servicenow_settings


class ServiceNowSettingsDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.result_settings = None
        self.setWindowTitle("ServiceNow and Outlook Settings")
        self.resize(700, 520)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        general = QWidget()
        form = QFormLayout(general)
        settings = window.servicenow_settings
        self.landing = QLineEdit(settings.start_url)
        self.folder = QLineEdit(window.outlook_settings.inbox_subfolder)
        form.addRow("ServiceNow landing URL", self.landing)
        form.addRow("Outlook folder under Inbox", self.folder)
        note = QLabel("Save applies settings immediately. Use Settings > Open ServiceNow Landing Page to navigate.")
        note.setWordWrap(True)
        form.addRow(note)
        tabs.addTab(general, "General")
        advanced = QWidget()
        advanced_form = QFormLayout(advanced)
        self.host = QLineEdit(settings.host_regex)
        self.ready = QLineEdit(settings.ready_dom_selector)
        self.bindings = QTextEdit()
        self.bindings.setPlainText(json.dumps([asdict(b) for b in settings.field_bindings], indent=2))
        advanced_form.addRow("Allowed URL pattern (regex)", self.host)
        derive = QPushButton("Use Landing URL Host")
        derive.clicked.connect(self.derive_host)
        advanced_form.addRow(derive)
        advanced_form.addRow("Form ready selector", self.ready)
        advanced_form.addRow("Field mappings (JSON array)", self.bindings)
        tabs.addTab(advanced, "Advanced Form Settings")
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def derive_host(self):
        try:
            url = urlsplit(self.landing.text().strip())
            if url.scheme not in ("http", "https") or not url.hostname:
                raise ValueError("Enter a valid HTTP(S) landing URL first")
            self.host.setText(r"^https?://" + re.escape(url.netloc) + r"(?:/|\?|#|$)")
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid URL", str(exc))

    def save(self):
        try:
            bindings = json.loads(self.bindings.toPlainText())
            self.result_settings = save_servicenow_settings(
                self.window.local_data_dir, self.window.servicenow_settings,
                self.landing.text(), self.host.text(), self.ready.text(), bindings, self.folder.text())
        except (ConfigError, ValueError) as exc:
            QMessageBox.warning(self, "Settings Not Saved", str(exc))
            return
        self.accept()
