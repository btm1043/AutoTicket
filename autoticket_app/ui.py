import json
import threading
from pathlib import Path

from PyQt5.QtCore import QObject, QSettings, QTimer, Qt, QUrl, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QCheckBox,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtWebEngineWidgets import QWebEngineView

from autoticket_app.browser import BrowserPage, build_profile, get_local_app_data_dir
from autoticket_app.config import (
    ALLOW_INSECURE_TLS_FOR_HOSTS,
    APP_NAME,
    PROFILE_NAME,
    load_servicenow_settings,
)
from autoticket_app.features import build_example_ticket, build_ticket_from_email
from autoticket_app.category_rules import load_category_rules
from autoticket_app.rules_store import load_rules_snapshot, save_rules_snapshot
from autoticket_app.settings_dialog import ServiceNowSettingsDialog
from autoticket_app.ticket_editor import TicketEditor, QUICK_TICKETS, build_quick_ticket
from autoticket_app.models import Ticket
from autoticket_app.msg_parser import parse_msg
from autoticket_app.outlook import (
    OutlookActedStore,
    OutlookError,
    OutlookQueueItem,
    OutlookScanner,
)
from autoticket_app.servicenow import (
    build_ready_check_js,
    build_servicenow_fill_js,
    is_servicenow_url,
)


class DropLabel(QLabel):
    def __init__(self, main_window):
        super().__init__("Navigate to ServiceNow form, then drop a .msg file here")
        self.main_window = main_window
        self.setAcceptDrops(True)
        self.armed = False
        self.update_style()

    def set_armed(self, armed: bool):
        self.armed = armed
        self.setText(
            "Ready: drop a .msg file here"
            if armed
            else "Navigate to ServiceNow form, then drop a .msg file here"
        )
        self.update_style()

    def update_style(self):
        bg = "rgba(0,120,0,0.55)" if self.armed else "rgba(0,0,0,0.55)"
        self.setStyleSheet(
            f"""
            QLabel {{
                background: {bg};
                color: white;
                padding: 10px;
                font-size: 14px;
            }}
        """
        )

    def dragEnterEvent(self, event):
        if not self.armed:
            event.ignore()
            return
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() == ".msg":
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        if not self.armed:
            return
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() == ".msg":
                self.main_window.load_msg_file(path)
                event.acceptProposedAction()
                return


class CategoryRulesBridge(QObject):
    loaded = pyqtSignal(str, object)
    failed = pyqtSignal(str)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoTicket")
        self.resize(1500, 900)

        self.local_data_dir = get_local_app_data_dir(APP_NAME)
        config_result = load_servicenow_settings(self.local_data_dir)
        self.servicenow_settings = config_result.settings
        self.outlook_settings = config_result.outlook
        self.config_warnings = config_result.warnings
        self.profile = build_profile(self, self.local_data_dir, PROFILE_NAME)
        self.outlook_store = OutlookActedStore(self.local_data_dir / "outlook_acted.json")
        self.outlook_queue: list[OutlookQueueItem] = []
        self.current_outlook_item: OutlookQueueItem | None = None
        self.category_rules = ()
        self.rules_settings = QSettings(str(self.local_data_dir / "settings.ini"), QSettings.IniFormat)
        if not self.rules_settings.contains("source"):
            previous = QSettings(APP_NAME, "CategoryRules").value("source", "", type=str)
            self.rules_settings.setValue("source", previous)
        self.rules_snapshot_path = self.local_data_dir / "category_rules_cache.json"
        self.rules_bridge = CategoryRulesBridge(self)
        self.rules_bridge.loaded.connect(self._rules_loaded)
        self.rules_bridge.failed.connect(self._rules_failed)

        self._build_browser()
        self._build_controls()
        self._build_layout()
        self._build_settings_menu()
        self._log_startup()
        self._restore_local_rules()
        if self.refresh_rules_checkbox.isChecked() and self.rules_source_input.text().strip():
            QTimer.singleShot(0, self.reload_category_rules)

        self.view.setUrl(QUrl(self.servicenow_settings.start_url))

    def _build_browser(self):
        self.view = QWebEngineView(self)
        self.page = BrowserPage(
            self.profile,
            self.view,
            log_fn=self.log,
            insecure_tls_hosts=ALLOW_INSECURE_TLS_FOR_HOSTS,
        )
        self.view.setPage(self.page)
        self.view.urlChanged.connect(self.on_url_changed)
        self.view.loadFinished.connect(self.on_load_finished)
        self.client_cert_selection_supported = hasattr(self.page, "selectClientCertificate")
        if self.client_cert_selection_supported:
            self.page.selectClientCertificate.connect(self.on_select_client_certificate)

        self.drop_label = DropLabel(self)

    def _build_controls(self):
        self.rules_source_input = QLineEdit()
        self.rules_source_input.setPlaceholderText("JSON/XML file path or https://server/categories.json")
        self.rules_source_input.setText(self.rules_settings.value("source", "", type=str))
        self.btn_browse_rules = QPushButton("Browse Rules")
        self.btn_browse_rules.clicked.connect(self.browse_category_rules)
        self.btn_reload_rules = QPushButton("Load / Reload Rules")
        self.btn_reload_rules.clicked.connect(self.reload_category_rules)
        self.rules_status = QLabel("No category rules loaded")
        self.rules_status.setWordWrap(True)
        self.refresh_rules_checkbox = QCheckBox("Refresh from source when the app starts")
        self.refresh_rules_checkbox.setChecked(self.rules_settings.value("refresh_on_startup", False, type=bool))
        self.refresh_rules_checkbox.toggled.connect(self._save_refresh_preference)

        self.json_input = QTextEdit()
        self.json_input.setPlaceholderText("Paste normalized ticket JSON here...")

        self.parsed_output = QTextEdit()
        self.parsed_output.setReadOnly(True)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)

        self.btn_check_ready = QPushButton("Check Ready")
        self.btn_check_ready.clicked.connect(self.check_dom_ready)

        self.btn_fill_json = QPushButton("Fill From JSON")
        self.btn_fill_json.clicked.connect(self.fill_from_json)

        self.btn_pretty_json = QPushButton("Pretty JSON")
        self.btn_pretty_json.clicked.connect(self.pretty_json)

        self.btn_clear_log = QPushButton("Clear Log")
        self.btn_clear_log.clicked.connect(self.log_output.clear)

        self.btn_load_example = QPushButton("Load Example JSON")
        self.btn_load_example.clicked.connect(self.load_example_json)

        self.outlook_folder_label = QLabel(f"Outlook: Inbox/{self.outlook_settings.inbox_subfolder}")
        self.outlook_folder_label.setWordWrap(True)

        self.outlook_queue_list = QListWidget()

        self.btn_scan_outlook = QPushButton("Scan Outlook")
        self.btn_scan_outlook.clicked.connect(self.scan_outlook)

        self.btn_load_next_outlook = QPushButton("Load Next Email")
        self.btn_load_next_outlook.clicked.connect(self.load_next_outlook_email)

        self.btn_mark_outlook_acted = QPushButton("Mark Email Acted")
        self.btn_mark_outlook_acted.clicked.connect(self.mark_current_outlook_acted)

    def _build_layout(self):
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.debug_toggle = QCheckBox("Show debug views")
        right_layout.addWidget(self.debug_toggle)
        self.active_rules_status = QLabel("Category rules: none loaded")
        self.active_rules_status.setWordWrap(True)
        right_layout.addWidget(self.active_rules_status)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_check_ready)
        btn_row.addWidget(self.btn_fill_json)
        btn_row.addWidget(self.btn_pretty_json)
        btn_row.addWidget(self.btn_load_example)
        btn_row.addWidget(self.btn_clear_log)

        self.panel_stack = QStackedWidget()
        normal = QWidget()
        normal_layout = QVBoxLayout(normal)
        normal_layout.addWidget(QLabel("Start a ticket"))
        quick_row = QHBoxLayout()
        for name in QUICK_TICKETS:
            button = QPushButton(name)
            button.clicked.connect(lambda checked=False, name=name: self.start_quick_ticket(name))
            quick_row.addWidget(button)
        normal_layout.addLayout(quick_row)
        self.ticket_editor = TicketEditor()
        normal_layout.addWidget(self.ticket_editor)
        actions = QHBoxLayout()
        blank = QPushButton("New Blank Ticket")
        blank.clicked.connect(lambda: self.start_quick_ticket(None))
        fill = QPushButton("Fill ServiceNow Form")
        fill.clicked.connect(self.fill_from_editor)
        actions.addWidget(blank)
        actions.addWidget(fill)
        normal_layout.addLayout(actions)
        normal_layout.addWidget(QLabel("Review the filled form in ServiceNow before submitting."))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(normal)
        self.panel_stack.addWidget(scroll)
        debug = QWidget()
        debug_layout = QVBoxLayout(debug)
        debug_layout.addWidget(QLabel("JSON Test Input"))
        debug_layout.addWidget(self.json_input, 3)
        debug_layout.addLayout(btn_row)
        debug_layout.addWidget(QLabel("Parsed / Normalized Fields"))
        debug_layout.addWidget(self.parsed_output, 2)
        debug_layout.addWidget(QLabel("Debug Log"))
        debug_layout.addWidget(self.log_output, 2)
        self.panel_stack.addWidget(debug)
        right_layout.addWidget(self.panel_stack, 4)
        right_layout.addWidget(self.outlook_folder_label)
        outlook_btn_row = QHBoxLayout()
        outlook_btn_row.addWidget(self.btn_scan_outlook)
        outlook_btn_row.addWidget(self.btn_load_next_outlook)
        outlook_btn_row.addWidget(self.btn_mark_outlook_acted)
        right_layout.addLayout(outlook_btn_row)
        right_layout.addWidget(QLabel("Outlook Queue"))
        right_layout.addWidget(self.outlook_queue_list, 2)
        self.ticket_status = QLabel("Ready to prepare a ticket")
        self.ticket_status.setWordWrap(True)
        right_layout.addWidget(self.ticket_status)
        self.debug_toggle.toggled.connect(self.toggle_debug_views)
        self.debug_toggle.setChecked(self.rules_settings.value("ui/debug_views", False, type=bool))

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.view, 1)
        left_layout.addWidget(self.drop_label, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([950, 550])

        self.setCentralWidget(splitter)

    def toggle_debug_views(self, enabled):
        try:
            if enabled:
                self.set_json(self.ticket_editor.ticket())
            else:
                self.ticket_editor.set_ticket(Ticket.from_dict(self.get_json()))
        except (ValueError, TypeError) as exc:
            self.debug_toggle.blockSignals(True)
            self.debug_toggle.setChecked(True)
            self.debug_toggle.blockSignals(False)
            QMessageBox.warning(self, "Invalid Ticket JSON", f"Fix the JSON before leaving debug view: {exc}")
            return
        self.panel_stack.setCurrentIndex(1 if enabled else 0)
        self.rules_settings.setValue("ui/debug_views", enabled)
        self.rules_settings.sync()

    def start_quick_ticket(self, name):
        current = self.ticket_editor.ticket()
        if any(str(value).strip() for value in current.to_dict().values()):
            answer = QMessageBox.question(self, "Start New Ticket", "Replace the current ticket draft?",
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        self.current_outlook_item = None
        self.set_ticket(build_quick_ticket(name) if name else Ticket())
        self.ticket_status.setText(f"{name or 'Blank ticket'} draft ready. Add caller and issue details.")

    def fill_from_editor(self):
        ticket = self.ticket_editor.ticket()
        if not ticket.short_description.strip():
            QMessageBox.warning(self, "Summary Required", "Enter a ticket summary before filling the form.")
            return
        self.set_ticket(ticket)
        self.fill_from_json()

    def _log_startup(self):
        self.log(f"[profile] local data dir: {self.local_data_dir}")
        self.log(f"[config] ServiceNow profile: {self.servicenow_settings.source_path}")
        self.log(f"[outlook] Inbox subfolder: {self.outlook_settings.inbox_subfolder}")
        self.log(f"[outlook] acted ledger: {self.outlook_store.path}")
        for warning in self.config_warnings:
            self.log(warning)
        if self.client_cert_selection_supported:
            self.log("[tls] client certificate selection is enabled")
        else:
            self.log("[tls] client certificate selection signal not available in this QtWebEngine build")

    def log(self, msg: str):
        self.log_output.append(msg)

    def closeEvent(self, event):
        self.cleanup_webengine()
        super().closeEvent(event)

    def cleanup_webengine(self):
        page = getattr(self, "page", None)
        if page is None:
            return

        try:
            self.view.setPage(None)
        except Exception:
            pass

        try:
            page.deleteLater()
        except Exception:
            pass

        self.page = None

    @staticmethod
    def _cert_value_text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value if item)
        return str(value)

    def _cert_subject(self, cert, key: str) -> str:
        try:
            return self._cert_value_text(cert.subjectInfo(key)).strip()
        except Exception:
            return ""

    def _cert_issuer(self, cert, key: str) -> str:
        try:
            return self._cert_value_text(cert.issuerInfo(key)).strip()
        except Exception:
            return ""

    def _describe_cert(self, cert, index: int) -> str:
        subject = self._cert_subject(cert, "CN") or self._cert_subject(cert, "O") or "(unknown subject)"
        issuer = self._cert_issuer(cert, "CN") or self._cert_issuer(cert, "O") or "(unknown issuer)"

        serial = ""
        try:
            serial = str(cert.serialNumber()).strip()
        except Exception:
            serial = ""

        expires = ""
        try:
            expires = cert.expiryDate().toString(Qt.ISODate)
        except Exception:
            expires = ""

        bits = [f"{index + 1}. {subject}", f"issuer={issuer}"]
        if serial:
            bits.append(f"serial={serial}")
        if expires:
            bits.append(f"expires={expires}")
        return " | ".join(bits)

    def on_select_client_certificate(self, selection):
        try:
            certs = list(selection.certificates())
        except Exception as exc:
            self.log(f"[tls][error] could not read certificates: {exc}")
            try:
                selection.selectNone()
            except Exception:
                pass
            return

        if not certs:
            self.log("[tls] server requested a client certificate but none were available")
            try:
                selection.selectNone()
            except Exception:
                pass
            return

        host = ""
        port = ""
        try:
            host = str(selection.host())
        except Exception:
            pass
        try:
            port = str(selection.port())
        except Exception:
            pass

        item_to_cert = {}
        items = []
        for index, cert in enumerate(certs):
            label = self._describe_cert(cert, index)
            while label in item_to_cert:
                label += " "
            item_to_cert[label] = cert
            items.append(label)

        prompt = "Server requested an X.509 client certificate.\nSelect which certificate to use:"
        if host or port:
            prompt += f"\n\nTarget: {host}:{port}"

        picked_label, ok = QInputDialog.getItem(
            self,
            "Select X.509 Certificate",
            prompt,
            items,
            0,
            False,
        )

        if not ok:
            self.log("[tls] certificate selection canceled; no client certificate was sent")
            try:
                selection.selectNone()
            except Exception:
                pass
            return

        cert = item_to_cert.get(picked_label)
        if cert is None:
            self.log("[tls][error] certificate selection was invalid")
            try:
                selection.selectNone()
            except Exception:
                pass
            return

        try:
            selection.select(cert)
            self.log(f"[tls] selected client certificate: {picked_label}")
        except Exception as exc:
            self.log(f"[tls][error] failed to apply certificate selection: {exc}")
            try:
                selection.selectNone()
            except Exception:
                pass

    def on_url_changed(self, url: QUrl):
        self.drop_label.set_armed(False)
        self.log(f"[nav] {url.toString()}")

    def on_load_finished(self, ok: bool):
        self.log(f"[load] ok={ok}")
        if not ok:
            self.drop_label.set_armed(False)
            return

        url = self.view.url().toString()
        if not is_servicenow_url(url, self.servicenow_settings.host_regex):
            self.log("[ready] not on ServiceNow host")
            self.drop_label.set_armed(False)
            return

        QTimer.singleShot(500, self.check_dom_ready)

    def check_dom_ready(self):
        js = build_ready_check_js(self.servicenow_settings.ready_dom_selector)
        self.run_browser_js(js, self.on_ready_checked, "ready")

    def run_browser_js(self, js: str, callback, operation: str):
        self.view.page().runJavaScript(js, callback)

    def on_ready_checked(self, result):
        ready = bool(result.get("ready")) if isinstance(result, dict) else False
        self.drop_label.set_armed(ready)
        self.log(f"[ready] {result}")
        self.ticket_status.setText("ServiceNow form ready" if ready else "Navigate to the ServiceNow ticket form to fill it")

    def _build_settings_menu(self):
        self.category_settings_dialog = QDialog(self)
        self.category_settings_dialog.setWindowTitle("Category Rule Settings")
        self.category_settings_dialog.resize(650, 260)
        layout = QVBoxLayout(self.category_settings_dialog)
        layout.addWidget(QLabel("Rules source: local JSON/XML file or HTTP(S) URL"))
        layout.addWidget(self.rules_source_input)
        row = QHBoxLayout()
        row.addWidget(self.btn_browse_rules)
        row.addWidget(self.btn_reload_rules)
        layout.addLayout(row)
        layout.addWidget(self.refresh_rules_checkbox)
        layout.addWidget(QLabel("Successfully loaded rules are saved locally and reused on startup."))
        layout.addWidget(self.rules_status)
        storage_label = QLabel(f"Local storage: {self.local_data_dir}")
        storage_label.setWordWrap(True)
        storage_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(storage_label)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.category_settings_dialog.close)
        layout.addWidget(close_button)
        menu = self.menuBar().addMenu("Settings")
        self.settings_menu = menu
        menu.addAction("ServiceNow and Outlook...", self.edit_service_settings)
        menu.addAction("Category Rules...", self.category_settings_dialog.show)
        menu.addSeparator()
        menu.addAction("Open ServiceNow Landing Page", self.open_landing_page)

    def open_landing_page(self):
        self.view.setUrl(QUrl(self.servicenow_settings.start_url))

    def edit_service_settings(self):
        dialog = ServiceNowSettingsDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        result = dialog.result_settings
        folder_changed = self.outlook_settings != result.outlook
        self.servicenow_settings = result.settings
        self.outlook_settings = result.outlook
        self.outlook_folder_label.setText(f"Outlook: Inbox/{result.outlook.inbox_subfolder}")
        if folder_changed:
            self.outlook_queue = []
            self.current_outlook_item = None
            self.refresh_outlook_queue_list()
        self.drop_label.set_armed(False)
        self.on_load_finished(True)
        self.log(f"[config] settings saved to {result.settings.source_path}")

    def _save_refresh_preference(self, enabled):
        self.rules_settings.setValue("refresh_on_startup", enabled)
        self.rules_settings.sync()

    def _restore_local_rules(self):
        if not self.rules_snapshot_path.exists():
            return
        try:
            source, rules = load_rules_snapshot(self.rules_snapshot_path)
        except (OSError, ValueError) as exc:
            self.rules_status.setText("Saved rules could not be read. Load a rules source to recover.")
            self.log(f"[categories][error] saved rules: {exc}")
            return
        self.category_rules = rules
        self.rules_source_input.setText(source)
        self.rules_status.setText(f"Using {len(rules)} saved rules. Load / Reload Rules checks the source for updates.")
        self.active_rules_status.setText(f"Category rules: {len(rules)} loaded from local storage")

    def browse_category_rules(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Category Rules", "", "Category Rules (*.json *.xml)")
        if path:
            self.rules_source_input.setText(path)
            self.reload_category_rules()

    def reload_category_rules(self):
        source = self.rules_source_input.text().strip()
        self.btn_reload_rules.setEnabled(False)
        self.btn_browse_rules.setEnabled(False)
        self.rules_source_input.setEnabled(False)
        self.rules_status.setText("Loading rules; emails use the previous rules until loading completes.")
        threading.Thread(target=self._load_rules_worker, args=(source,), daemon=True).start()

    def _load_rules_worker(self, source):
        try:
            rules = load_category_rules(source)
            save_rules_snapshot(self.rules_snapshot_path, source, rules)
        except Exception as exc:
            self.rules_bridge.failed.emit(str(exc))
        else:
            self.rules_bridge.loaded.emit(source, rules)

    def _enable_rules_controls(self):
        self.btn_reload_rules.setEnabled(True)
        self.btn_browse_rules.setEnabled(True)
        self.rules_source_input.setEnabled(True)

    def _rules_loaded(self, source, rules):
        self.category_rules = rules
        self.rules_settings.setValue("source", source)
        self.rules_settings.sync()
        self._enable_rules_controls()
        self.rules_status.setText(f"Loaded and saved {len(rules)} subcategory rules. Applies to the next email loaded.")
        self.active_rules_status.setText(f"Category rules: {len(rules)} loaded and saved locally")
        self.log(f"[categories] loaded {len(rules)} rules")

    def _rules_failed(self, error):
        self._enable_rules_controls()
        self.rules_status.setText(f"Rules load failed; {len(self.category_rules)} previous rules remain active.")
        self.log(f"[categories][error] {error}")
        QMessageBox.warning(self, "Category Rules Error", error)

    def _ticket_from_email(self, email):
        ticket = build_ticket_from_email(email, category_rules=self.category_rules)
        if ticket.category:
            self.log(f"[categories] matched {ticket.category} / {ticket.subcategory}")
        else:
            self.log("[categories] no match" if self.category_rules else "[categories] no rules loaded")
        return ticket

    def load_msg_file(self, path: str):
        self.log(f"[msg] loading {path}")
        try:
            email = parse_msg(path)
            ticket = self._ticket_from_email(email)
            self.current_outlook_item = None
            self.set_ticket(ticket)
            self.log("[msg] parsed and loaded into JSON panel")
        except Exception as exc:
            QMessageBox.critical(self, "MSG Parse Error", str(exc))
            self.log(f"[msg][error] {exc}")

    def scan_outlook(self):
        folder = self.outlook_settings.inbox_subfolder
        if not folder:
            QMessageBox.warning(self, "Outlook Folder Required", "Enter an Inbox subfolder to scan.")
            return

        self.log(f"[outlook] scanning Inbox/{folder}")
        try:
            scanner = OutlookScanner(folder)
            self.outlook_queue = scanner.scan(self.outlook_store.acted_keys())
        except OutlookError as exc:
            QMessageBox.warning(self, "Outlook Scan Error", str(exc))
            self.log(f"[outlook][error] {exc}")
            return
        except Exception as exc:
            QMessageBox.warning(self, "Outlook Scan Error", repr(exc))
            self.log(f"[outlook][error] {repr(exc)}")
            return

        self.refresh_outlook_queue_list()
        self.log(f"[outlook] queued {len(self.outlook_queue)} unacted email(s)")

    def refresh_outlook_queue_list(self):
        self.outlook_queue_list.clear()
        for item in self.outlook_queue:
            received = f"{item.received_at} | " if item.received_at else ""
            sender = item.sender_email or item.sender_name or "(unknown sender)"
            subject = item.subject or "(no subject)"
            self.outlook_queue_list.addItem(f"{received}{sender} | {subject}")

    def _selected_outlook_index(self) -> int:
        index = self.outlook_queue_list.currentRow()
        return index if 0 <= index < len(self.outlook_queue) else 0

    def load_next_outlook_email(self):
        if not self.outlook_queue:
            self.scan_outlook()
            if not self.outlook_queue:
                return

        index = self._selected_outlook_index()
        item = self.outlook_queue[index]
        self.current_outlook_item = item
        ticket = self._ticket_from_email(item.to_email())
        self.set_ticket(ticket)
        self.outlook_queue_list.setCurrentRow(index)
        self.log(f"[outlook] loaded email: {item.subject or '(no subject)'}")

    def mark_current_outlook_acted(self):
        item = self.current_outlook_item
        if item is None:
            QMessageBox.information(self, "No Outlook Email Loaded", "Load an Outlook email first.")
            return

        self.outlook_store.mark_acted(item)
        self.outlook_queue = [queued for queued in self.outlook_queue if queued.key != item.key]
        self.current_outlook_item = None
        self.refresh_outlook_queue_list()
        self.log("[outlook] marked current email as acted")

    def set_ticket(self, ticket: Ticket):
        self.ticket_editor.set_ticket(ticket)
        data = ticket.to_dict()
        self.set_json(data)
        self.parsed_output.setPlainText(json.dumps(data, indent=2))

    def set_json(self, data):
        if isinstance(data, Ticket):
            data = data.to_dict()
        self.json_input.setPlainText(json.dumps(data, indent=2))

    def get_json(self) -> dict:
        text = self.json_input.toPlainText().strip()
        if not text:
            return {}
        return json.loads(text)

    def pretty_json(self):
        try:
            data = self.get_json()
            self.set_json(data)
            self.log("[json] formatted")
        except Exception as exc:
            QMessageBox.warning(self, "Invalid JSON", str(exc))
            self.log(f"[json][error] {exc}")

    def load_example_json(self):
        self.set_ticket(build_example_ticket())
        self.log("[json] loaded example")

    def fill_from_json(self):
        try:
            ticket = Ticket.from_dict(self.get_json())
            self.parsed_output.setPlainText(json.dumps(ticket.to_dict(), indent=2))
        except Exception as exc:
            QMessageBox.warning(self, "Invalid JSON", str(exc))
            self.log(f"[fill][error] invalid json: {exc}")
            return

        js = build_servicenow_fill_js(ticket, self.servicenow_settings.field_bindings)
        self.log("[fill] running JS")
        self.run_browser_js(js, self.on_fill_result, "fill")

    def on_fill_result(self, result):
        try:
            pretty = json.dumps(result, indent=2)
        except Exception:
            pretty = str(result)
        self.log(f"[fill][result]\n{pretty}")
        if not isinstance(result, dict) or result.get("error"):
            self.ticket_status.setText("Could not confirm the form fill. Check the ServiceNow page or enable debug views for details.")
        else:
            self.ticket_status.setText("Form fill finished. Review the ServiceNow form and check any missing fields.")
