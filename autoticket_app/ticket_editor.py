from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QCompleter, QFormLayout, QLineEdit, QTextEdit, QWidget

from autoticket_app.models import Ticket


QUICK_TICKETS = {
    "Password Reset": ("Password reset request", "User requests a password reset.\nAccount / system: \nDetails: "),
    "Called-in Issue": ("Issue reported by phone", "Issue reported over the phone.\nAffected service: \nIssue details: \nImpact: \nCallback number: "),
    "General Inquiry": ("General inquiry", "Inquiry details: \nRequested information: "),
}


def build_quick_ticket(name):
    subject, body = QUICK_TICKETS[name]
    return Ticket(short_description=subject, description=body)


class TicketEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.extra_fields = {}
        self.fields = {}
        self.rules = ()
        form = QFormLayout(self)
        form.setContentsMargins(0, 8, 0, 8)
        form.setVerticalSpacing(12)
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        labels = ("Summary", "Details", "Caller name", "Caller email", "Category", "Subcategory")
        for key, label in zip(Ticket.CORE_FIELDS, labels):
            field = QTextEdit() if key == "description" else QLineEdit()
            if key in ("category", "subcategory"):
                field = QComboBox()
                field.setEditable(True)
                field.setInsertPolicy(QComboBox.NoInsert)
                field.completer().setCaseSensitivity(Qt.CaseInsensitive)
                field.completer().setFilterMode(Qt.MatchContains)
                field.completer().setCompletionMode(QCompleter.PopupCompletion)
            if key == "description":
                field.setMinimumHeight(100)
            self.fields[key] = field
            form.addRow(label, field)
        self.fields["category"].currentTextChanged.connect(self._category_changed)

    def set_rules(self, rules):
        self.rules = rules
        category = self.fields["category"]
        value = category.currentText()
        category.blockSignals(True)
        category.clear()
        category.addItem("")
        category.addItems(list(dict.fromkeys(rule.category for rule in rules)))
        category.setCurrentText(value)
        category.blockSignals(False)
        self._refresh_subcategories(preserve=True)

    def _category_changed(self, value):
        self._refresh_subcategories(preserve=False)

    def _refresh_subcategories(self, preserve):
        category = self.fields["category"].currentText()
        sub = self.fields["subcategory"]
        value = sub.currentText() if preserve else ""
        sub.clear()
        sub.addItem("")
        sub.addItems(list(dict.fromkeys(rule.subcategory for rule in self.rules if rule.category == category)))
        sub.setCurrentText(value)

    def set_ticket(self, ticket):
        self.extra_fields = dict(ticket.extra_fields)
        for key, field in self.fields.items():
            if key == "description":
                field.setPlainText(getattr(ticket, key))
            elif isinstance(field, QComboBox):
                field.setCurrentText(getattr(ticket, key))
            else:
                field.setText(getattr(ticket, key))

    def ticket(self):
        values = {key: field.toPlainText() if key == "description" else
                  field.currentText() if isinstance(field, QComboBox) else field.text()
                  for key, field in self.fields.items()}
        return Ticket(**values, extra_fields=dict(self.extra_fields))
