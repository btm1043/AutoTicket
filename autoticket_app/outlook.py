from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autoticket_app.models import ParsedEmail


INBOX_FOLDER_ID = 6
INTERNET_MESSAGE_ID_SCHEMA = "http://schemas.microsoft.com/mapi/proptag/0x1035001E"


class OutlookError(RuntimeError):
    pass


@dataclass(frozen=True)
class OutlookQueueItem:
    key: str
    entry_id: str
    subject: str
    sender_name: str
    sender_email: str
    received_at: str
    body: str

    def to_email(self) -> ParsedEmail:
        return ParsedEmail(
            subject=self.subject,
            body=self.body,
            sender_name=self.sender_name,
            sender_email=self.sender_email,
            message_id=self.key,
            received_at=self.received_at,
        )


class OutlookActedStore:
    def __init__(self, path: Path):
        self.path = path
        self._acted = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}

        if not isinstance(data, dict):
            return {}

        acted = data.get("acted")
        return acted if isinstance(acted, dict) else {}

    def acted_keys(self) -> set[str]:
        return set(self._acted)

    def has_acted(self, key: str) -> bool:
        return key in self._acted

    def mark_acted(self, item: OutlookQueueItem):
        self._acted[item.key] = {
            "entry_id": item.entry_id,
            "subject": item.subject,
            "sender_email": item.sender_email,
            "received_at": item.received_at,
            "acted_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"acted": self._acted}
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        tmp_path.replace(self.path)


class OutlookScanner:
    def __init__(self, inbox_subfolder: str):
        self.inbox_subfolder = inbox_subfolder.strip()

    def scan(self, acted_keys: set[str] | None = None, limit: int = 50) -> list[OutlookQueueItem]:
        acted_keys = acted_keys or set()
        folder = self._get_folder()
        items = folder.Items
        try:
            items.Sort("[ReceivedTime]", True)
        except Exception:
            pass

        queue_items: list[OutlookQueueItem] = []
        for item in items:
            if len(queue_items) >= limit:
                break
            if not self._is_mail_item(item):
                continue

            queue_item = self._to_queue_item(item)
            if not queue_item.key or queue_item.key in acted_keys:
                continue
            queue_items.append(queue_item)

        return queue_items

    def _get_folder(self):
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise OutlookError("pywin32 is required for local Outlook integration") from exc

        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

        try:
            outlook = self._get_outlook_application(win32com.client)
            namespace = outlook.GetNamespace("MAPI")
            folder = namespace.GetDefaultFolder(INBOX_FOLDER_ID)
        except Exception as exc:
            raise OutlookError(
                "could not attach to the running Outlook instance. "
                "Make sure Outlook and AutoTicket are running at the same privilege level "
                "and that desktop Outlook is fully started."
            ) from exc

        if not self.inbox_subfolder:
            return folder

        for part in self._folder_parts(self.inbox_subfolder):
            folder = self._child_folder(folder, part)
        return folder

    @staticmethod
    def _get_outlook_application(win32_client):
        try:
            return win32_client.GetActiveObject("Outlook.Application")
        except Exception:
            return win32_client.Dispatch("Outlook.Application")

    @staticmethod
    def _folder_parts(path: str) -> list[str]:
        normalized = path.replace("\\", "/")
        return [part.strip() for part in normalized.split("/") if part.strip()]

    @staticmethod
    def _child_folder(parent, name: str):
        for folder in parent.Folders:
            try:
                if str(folder.Name).strip().lower() == name.lower():
                    return folder
            except Exception:
                continue
        raise OutlookError(f"Outlook Inbox subfolder was not found: {name}")

    @staticmethod
    def _is_mail_item(item) -> bool:
        try:
            return str(item.MessageClass).startswith("IPM.Note")
        except Exception:
            return False

    def _to_queue_item(self, item) -> OutlookQueueItem:
        entry_id = self._safe_str(item, "EntryID")
        message_id = self._internet_message_id(item)
        key = message_id or entry_id
        sender_name = self._safe_str(item, "SenderName")
        sender_email = self._sender_email(item)

        return OutlookQueueItem(
            key=key,
            entry_id=entry_id,
            subject=self._safe_str(item, "Subject"),
            sender_name=sender_name,
            sender_email=sender_email,
            received_at=self._received_at(item),
            body=self._safe_str(item, "Body").strip(),
        )

    @staticmethod
    def _safe_str(item, attr: str) -> str:
        try:
            value = getattr(item, attr)
        except Exception:
            return ""
        return "" if value is None else str(value)

    @staticmethod
    def _internet_message_id(item) -> str:
        try:
            value = item.PropertyAccessor.GetProperty(INTERNET_MESSAGE_ID_SCHEMA)
        except Exception:
            return ""
        return "" if value is None else str(value).strip()

    def _sender_email(self, item) -> str:
        email = self._safe_str(item, "SenderEmailAddress")
        if email and not email.startswith("/"):
            return email

        try:
            exchange_user = item.Sender.GetExchangeUser()
            primary = exchange_user.PrimarySmtpAddress
        except Exception:
            return email
        return "" if primary is None else str(primary)

    @staticmethod
    def _received_at(item) -> str:
        try:
            value = item.ReceivedTime
        except Exception:
            return ""
        try:
            return value.isoformat()
        except Exception:
            return "" if value is None else str(value)
