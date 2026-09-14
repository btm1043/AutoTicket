from __future__ import annotations

import threading

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QSpinBox

from autoticket_app.playwright_cdp import (
    PlaywrightCdpError,
    PlaywrightCdpEvaluator,
    PlaywrightCdpSettings,
)
from autoticket_app.ui import MainWindow


class ScriptResultBridge(QObject):
    succeeded = pyqtSignal(str, object, object)
    failed = pyqtSignal(str, object, str)


class PlaywrightMainWindow(MainWindow):
    def __init__(self, cdp_settings: PlaywrightCdpSettings):
        self.cdp_evaluator = PlaywrightCdpEvaluator(cdp_settings)
        self.script_result_bridge = ScriptResultBridge()
        self.script_result_bridge.succeeded.connect(self._on_script_succeeded)
        self.script_result_bridge.failed.connect(self._on_script_failed)
        super().__init__()
        self.settings_menu.addAction("Playwright Connection...", self.edit_connection_settings)

    def edit_connection_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Playwright Connection Settings")
        layout = QFormLayout(dialog)
        host = QLineEdit(self.rules_settings.value("cdp/host", "127.0.0.1", type=str))
        port = QSpinBox()
        port.setRange(1, 65535)
        port.setValue(self.rules_settings.value("cdp/port", 9222, type=int))
        timeout = QSpinBox()
        timeout.setRange(1000, 120000)
        timeout.setSuffix(" ms")
        timeout.setValue(self.rules_settings.value("cdp/timeout_ms", 15000, type=int))
        layout.addRow("Endpoint host", host)
        layout.addRow("Debugging port", port)
        layout.addRow("Operation timeout", timeout)
        note = QLabel("Changes apply after restart. AUTOTICKET_CDP_HOST/PORT and QTWEBENGINE_REMOTE_DEBUGGING environment overrides remain in effect.")
        note.setWordWrap(True)
        layout.addRow(note)
        layout.addRow(QLabel(f"Active endpoint: {self.cdp_evaluator.settings.endpoint_url}"))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        def save():
            import re
            value = host.text().strip()
            if not re.fullmatch(r"[a-zA-Z0-9.-]+", value):
                QMessageBox.warning(dialog, "Invalid Host", "Enter a hostname or IPv4 address without a URL scheme or port.")
                return
            self.rules_settings.setValue("cdp/host", value)
            self.rules_settings.setValue("cdp/port", port.value())
            self.rules_settings.setValue("cdp/timeout_ms", timeout.value())
            self.rules_settings.sync()
            if self.rules_settings.status() != self.rules_settings.NoError:
                QMessageBox.warning(dialog, "Settings Not Saved", "Could not write local settings.")
                return
            dialog.accept()
        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        dialog.exec()

    def _log_startup(self):
        super()._log_startup()
        self.log(f"[playwright] CDP endpoint: {self.cdp_evaluator.settings.endpoint_url}")

    def run_browser_js(self, js: str, callback, operation: str):
        current_url = self.view.url().toString()
        self.log(f"[playwright] running {operation} over CDP")

        worker = threading.Thread(
            target=self._evaluate_in_worker,
            args=(operation, callback, js, current_url),
            daemon=True,
        )
        worker.start()

    def _evaluate_in_worker(self, operation: str, callback, js: str, current_url: str):
        try:
            result = self.cdp_evaluator.evaluate(js, current_url=current_url)
        except PlaywrightCdpError as exc:
            self.script_result_bridge.failed.emit(operation, callback, str(exc))
        except Exception as exc:
            self.script_result_bridge.failed.emit(operation, callback, repr(exc))
        else:
            self.script_result_bridge.succeeded.emit(operation, callback, result)

    def _on_script_succeeded(self, operation: str, callback, result):
        transport = self.cdp_evaluator.last_transport
        self.log(f"[playwright] {operation} completed via {transport}")
        callback(result)

    def _on_script_failed(self, operation: str, callback, error: str):
        self.log(f"[playwright][error] {operation} failed: {error}")
        callback({"ready": False, "error": error} if operation == "ready" else {"error": error})
