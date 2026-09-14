from __future__ import annotations

import os
import sys


DEFAULT_CDP_HOST = "127.0.0.1"
DEFAULT_CDP_PORT = "9222"


def _get_cdp_host() -> str:
    return os.environ.get("AUTOTICKET_CDP_HOST", _local_preferences().value("cdp/host", DEFAULT_CDP_HOST, type=str)).strip() or DEFAULT_CDP_HOST


def _get_cdp_port() -> str:
    return os.environ.get("AUTOTICKET_CDP_PORT", _local_preferences().value("cdp/port", DEFAULT_CDP_PORT, type=str)).strip() or DEFAULT_CDP_PORT


def _local_preferences():
    from pathlib import Path
    from PyQt5.QtCore import QCoreApplication, QSettings, QStandardPaths
    from autoticket_app.config import APP_NAME

    QCoreApplication.setApplicationName(APP_NAME)
    location = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    directory = Path(location) if location else Path.home() / "AppData" / "Local" / APP_NAME
    return QSettings(str(directory / "settings.ini"), QSettings.IniFormat)


def _configure_qtwebengine_cdp() -> str:
    host = _get_cdp_host()
    port = _get_cdp_port()
    os.environ.setdefault("QTWEBENGINE_REMOTE_DEBUGGING", port)
    return f"http://{host}:{port}"


def main():
    cdp_endpoint = _configure_qtwebengine_cdp()

    from PyQt5.QtWidgets import QApplication, QMessageBox

    from autoticket_app.config import APP_NAME, ConfigError
    from autoticket_app.playwright_cdp import PlaywrightCdpSettings
    from autoticket_app.ui_playwright import PlaywrightMainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    try:
        timeout = _local_preferences().value("cdp/timeout_ms", 15000, type=int)
        window = PlaywrightMainWindow(PlaywrightCdpSettings(endpoint_url=cdp_endpoint, operation_timeout_ms=timeout))
    except ConfigError as exc:
        QMessageBox.critical(None, "ServiceNow Config Error", str(exc))
        sys.exit(1)
    window.show()
    sys.exit(app.exec())
