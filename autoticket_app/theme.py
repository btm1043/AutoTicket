"""Application chrome only; the embedded ServiceNow page keeps its own styling."""

LIGHT_THEME = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #243247; }
QMainWindow, QDialog { background: #f3f5f9; }
QMenuBar, QMenu { background: white; }
QMenu::item:selected { background: #e7efff; }
QWidget#header { background: white; border-bottom: 1px solid #dce3ed; }
QWidget#ticketForm { background: white; }
QLabel#brand { font-size: 18pt; font-weight: 600; color: #18345b; }
QLabel#muted { color: #65748a; }
QLabel#badge { background: #eaf1fc; color: #345a88; border-radius: 6px; padding: 7px; }
QPushButton { background: white; border: 1px solid #ccd6e3; border-radius: 6px; padding: 8px 12px; }
QPushButton:hover { background: #edf3ff; border-color: #8caee1; }
QPushButton:pressed { background: #dce9fd; }
QPushButton:disabled { color: #99a3b2; background: #f1f3f6; }
QPushButton#primary { background: #2563b9; color: white; border: 1px solid #2563b9; font-weight: 600; }
QPushButton#primary:hover { background: #1d5098; }
QLineEdit, QTextEdit, QComboBox, QSpinBox, QListWidget {
 background: white; border: 1px solid #d3dce8; border-radius: 5px; padding: 6px; selection-background-color: #d5e5ff;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color: #4380d0; }
QComboBox { padding-right: 24px; }
QTabWidget::pane { border: 1px solid #dce3ed; background: white; border-radius: 6px; }
QTabBar::tab { background: #edf1f7; color: #627188; padding: 10px 18px; border-bottom: 3px solid transparent; }
QTabBar::tab:selected { background: white; color: #205baf; border-bottom: 3px solid #2563b9; }
QScrollArea { border: none; background: white; }
QSplitter::handle { background: #e5eaf2; width: 5px; }
QListWidget::item { padding: 10px; border-bottom: 1px solid #edf0f5; }
QListWidget::item:selected { background: #e3edfc; color: #18345b; }
"""
