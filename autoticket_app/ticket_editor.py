from PyQt5.QtWidgets import QFormLayout, QLineEdit, QTextEdit, QWidget

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
        form = QFormLayout(self)
        labels = ("Summary", "Details", "Caller name", "Caller email", "Category", "Subcategory")
        for key, label in zip(Ticket.CORE_FIELDS, labels):
            field = QTextEdit() if key == "description" else QLineEdit()
            if key == "description":
                field.setMinimumHeight(100)
            self.fields[key] = field
            form.addRow(label, field)

    def set_ticket(self, ticket):
        self.extra_fields = dict(ticket.extra_fields)
        for key, field in self.fields.items():
            if key == "description":
                field.setPlainText(getattr(ticket, key))
            else:
                field.setText(getattr(ticket, key))

    def ticket(self):
        values = {key: field.toPlainText() if key == "description" else field.text()
                  for key, field in self.fields.items()}
        return Ticket(**values, extra_fields=dict(self.extra_fields))
