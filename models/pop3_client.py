"""Fetch Microsoft verification codes from a POP3 mailbox.

The blocking POP3 logic is isolated here so it can be unit-tested with a
fake mailbox class; the async polling helper lives in
:mod:`services.sharepoint`.
"""

import email
import email.message
import logging
import poplib
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Sender addresses that are allowed to provide verification codes.
_TRUSTED_SENDERS: Tuple[str, ...] = (
    "account-security-noreply@accountprotection.microsoft.com",
)

# Accept codes slightly older than the local not_before anchor to absorb
# mail-server / local clock skew.
_DATE_GRACE = timedelta(seconds=60)


def _decode_str(value: Optional[str]) -> str:
    """Decode a possibly encoded-word header value to a plain string."""
    if not value:
        return ""
    parts = decode_header(value)
    out: List[str] = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _extract_body(msg: email.message.Message) -> str:
    """Extract concatenated text/plain + text/html body from a message."""
    body_parts: List[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body_parts.append(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body_parts.append(payload.decode(charset, errors="replace"))
    return "".join(body_parts)


def _extract_code(body: str) -> Optional[str]:
    """Extract a numeric verification code from an email body."""
    match = re.search(
        r"Account verification code[:\s]*(\d{4,})", body, re.IGNORECASE
    )
    if not match:
        match = re.search(r"verification code[:\s]*(\d{4,})", body, re.IGNORECASE)
    if not match:
        match = re.search(r"\b(\d{6,8})\b", body)
    return match.group(1) if match else None


def _parse_message_date(msg: email.message.Message) -> Optional[datetime]:
    """Return the message ``Date`` header as timezone-aware UTC, or ``None``."""
    value = msg.get("Date")
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_not_before(not_before: datetime) -> datetime:
    """Normalize a not-before anchor to timezone-aware UTC."""
    if not_before.tzinfo is None:
        not_before = not_before.replace(tzinfo=timezone.utc)
    return not_before.astimezone(timezone.utc)


def parse_verification_message(raw_bytes: bytes) -> Tuple[str, str, Optional[str]]:
    """Parse raw message bytes into ``(sender, subject, code)``.

    ``code`` is ``None`` if no verification-code pattern is found.
    """
    msg = email.message_from_bytes(raw_bytes)
    sender = _decode_str(msg.get("From"))
    subject = _decode_str(msg.get("Subject"))
    code = _extract_code(_extract_body(msg))
    return sender, subject, code


def fetch_verification_code(
    host: str,
    port: int,
    user: str,
    password: str,
    *,
    pop3_cls=None,
    max_messages: int = 20,
    timeout: int = 30,
    not_before: Optional[datetime] = None,
) -> Optional[str]:
    """Connect to POP3 and return the newest usable verification code, or ``None``.

    Parameters
    ----------
    pop3_cls:
        Optional class/factory used instead of :class:`poplib.POP3_SSL`.
        Tests can pass a fake to avoid network access.
    max_messages:
        How many of the most recent messages to inspect.
    timeout:
        Socket timeout in seconds.
    not_before:
        When set, only accept messages whose ``Date`` is at least
        ``not_before - 60s``. Older matching codes are skipped (not deleted).
        Messages without a usable ``Date`` are also skipped when this filter
        is active. When omitted, behavior matches the previous newest-match
        selection.
    """
    if not host or not user or not password:
        logger.error("POP3 configuration is incomplete (host/user/pass)")
        return None

    threshold: Optional[datetime] = None
    if not_before is not None:
        threshold = _normalize_not_before(not_before) - _DATE_GRACE

    factory = pop3_cls or poplib.POP3_SSL
    mail = None
    try:
        mail = factory(host, port, timeout=timeout)
        mail.user(user)
        mail.pass_(password)
        count, _ = mail.stat()

        for i in range(count, max(count - max_messages, 0), -1):
            _, lines, _ = mail.retr(i)
            raw = b"\r\n".join(lines)
            msg = email.message_from_bytes(raw)
            sender = _decode_str(msg.get("From"))
            subject = _decode_str(msg.get("Subject"))
            code = _extract_code(_extract_body(msg))

            sender_ok = any(trusted in sender for trusted in _TRUSTED_SENDERS)
            subject_ok = "account verification code" in subject.lower()
            if not (sender_ok or subject_ok):
                continue
            if not code:
                continue

            if threshold is not None:
                msg_date = _parse_message_date(msg)
                if msg_date is None:
                    logger.info(
                        "Skipping verification mail without usable Date header"
                    )
                    continue
                if msg_date < threshold:
                    logger.info(
                        "Skipping stale verification code "
                        "(message Date %s before threshold %s)",
                        msg_date.isoformat(),
                        threshold.isoformat(),
                    )
                    continue

            mail.dele(i)
            logger.info("Verification code retrieved and marked for deletion")
            return code
        return None
    except Exception:
        logger.exception("Failed to fetch verification code from POP3")
        return None
    finally:
        if mail is not None:
            try:
                mail.quit()
            except Exception:
                pass
