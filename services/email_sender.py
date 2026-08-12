"""Pure email-sending helpers.

No Qt imports live here so the module can be unit-tested without a running
QApplication. The QThread wrapper is in :mod:`services.email_worker`.
"""

import logging
import os
import shutil
import smtplib
import time
import zipfile
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def get_attachments(
    downloads_dir: str, remove_zip_after_extract: bool = True
) -> List[str]:
    """Return attachment paths from *downloads_dir*.

    Zip files are extracted into ``<downloads_dir>/_extracted`` and (by
    default) the original zip is removed so it is not sent twice.
    """
    if not os.path.isdir(downloads_dir):
        return []

    attachments: List[str] = []
    for name in os.listdir(downloads_dir):
        full = os.path.join(downloads_dir, name)
        if not os.path.isfile(full):
            continue
        if zipfile.is_zipfile(full):
            extract_dir = os.path.join(downloads_dir, "_extracted")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(full, "r") as zf:
                # Zip-slip guard: refuse entries that would escape extract_dir.
                dest_root = os.path.abspath(extract_dir)
                for member in zf.namelist():
                    target = os.path.abspath(os.path.join(extract_dir, member))
                    if os.path.commonpath([dest_root, target]) != dest_root:
                        raise ValueError(
                            f"Unsafe zip entry {member!r} in {full!r}: "
                            "path traversal outside of extraction directory"
                        )
                zf.extractall(extract_dir)
            for root, _, files in os.walk(extract_dir):
                for fname in files:
                    attachments.append(os.path.join(root, fname))
            if remove_zip_after_extract:
                os.remove(full)
        else:
            attachments.append(full)
    return attachments


def cleanup(downloads_dir: str) -> None:
    """Remove every file and sub-directory inside *downloads_dir*."""
    if not os.path.isdir(downloads_dir):
        return
    for root, dirs, files in os.walk(downloads_dir, topdown=False):
        for fname in files:
            os.remove(os.path.join(root, fname))
        for dname in dirs:
            os.rmdir(os.path.join(root, dname))


def _build_message(
    cfg: Dict,
    recipients: List[str],
    subject: str,
    body: str,
    attachment_paths: List[str],
) -> "tuple[MIMEMultipart, List[str]]":
    msg = MIMEMultipart()
    msg["From"] = cfg["smtp_user"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(body, "plain", "utf-8"))

    filenames: List[str] = []
    for path in attachment_paths:
        with open(path, "rb") as fh:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(fh.read())
        encoders.encode_base64(part)
        filename = os.path.basename(path)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)
        filenames.append(filename)
    return msg, filenames


def _connect(cfg: Dict) -> smtplib.SMTP:
    """Create and authenticate an SMTP connection based on config values."""
    host = cfg["smtp_host"]
    port = int(cfg["smtp_port"])
    use_ssl = cfg.get("smtp_use_ssl", port == 465)

    if use_ssl:
        server: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.starttls()

    server.login(cfg["smtp_user"], cfg["smtp_pass"])
    return server


def send_email(
    to: str,
    subject: str,
    body: str,
    attachment_paths: List[str],
    config: Dict,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    sleep_func: Callable[[float], None] = time.sleep,
) -> List[str]:
    """Build the MIME message and send it, retrying transient SMTP errors.

    Authentication errors are raised immediately (no retry). Any remaining
    failure after *max_retries* attempts is raised.

    Returns the list of attached filenames actually sent.
    """
    recipients = [addr.strip() for addr in to.split(",") if addr.strip()]
    if not recipients:
        raise ValueError("No recipient email addresses provided")

    msg, filenames = _build_message(config, recipients, subject, body, attachment_paths)

    last_exc: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        server: Optional[smtplib.SMTP] = None
        try:
            server = _connect(config)
            server.send_message(msg)
            logger.info("Email sent to %s (%d attachment(s))", to, len(filenames))
            return filenames
        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed for user %s", config["smtp_user"])
            raise
        except Exception as exc:
            last_exc = exc
            logger.warning("SMTP attempt %d/%d failed: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                sleep_func(retry_delay * attempt)  # simple linear backoff
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass

    assert last_exc is not None
    raise last_exc
