"""QThread that downloads-then-emails the selected items."""

import logging

from PySide6.QtCore import QThread, Signal

from models import sent_log
from paths import get_downloads_dir

from . import email_sender

logger = logging.getLogger(__name__)


class EmailThread(QThread):
    """Collects attachments, sends the email, then logs what was sent.

    Signals
    -------
    finished(str, list)
        Emitted with a human-readable message and the list of attached
        filenames on success.
    error(str)
        Emitted with the error message on failure.
    """

    finished = Signal(str, list)
    error = Signal(str)

    def __init__(self, to, subject, body, selection, items_data, config,
                 current_path=None):
        super().__init__()
        self.to = to
        self.subject = subject
        self.body = body
        self.selection = selection          # names of checked items
        self.items_data = items_data        # items metadata from SharePoint
        self.config = config                # config dict (already loaded)
        self.current_path = list(current_path or [])

    def _full_path(self, name: str):
        return "/".join(self.current_path + [name]) if self.current_path else None

    def run(self):  # noqa: D102 - behaviour described in class docstring
        try:
            downloads_dir = get_downloads_dir()
            attachments = email_sender.get_attachments(downloads_dir)
            if not attachments:
                self.error.emit("No files in downloads folder")
                return

            filenames = email_sender.send_email(
                self.to, self.subject, self.body, attachments, self.config
            )
            email_sender.cleanup(downloads_dir)

            name_to_item = {item["name"]: item for item in self.items_data}
            for name in self.selection:
                item = name_to_item.get(name, {})
                full_path = self._full_path(name)
                if item.get("is_folder"):
                    sent_log.log_sent_folder(
                        name, self.to, self.subject, filenames, full_path=full_path
                    )
                else:
                    sent_log.log_sent_file(
                        name, self.to, self.subject, filenames, full_path=full_path
                    )

            self.finished.emit(
                f"Sent to {self.to} with {len(filenames)} file(s)", filenames
            )
        except Exception as exc:  # surfaced to the UI via the error signal
            logger.exception("Failed to send email")
            self.error.emit(str(exc))
