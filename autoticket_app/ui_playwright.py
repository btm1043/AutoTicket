from __future__ import annotations

import threading

from PyQt5.QtCore import QObject, pyqtSignal

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
