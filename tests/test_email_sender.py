"""Tests for services.email_sender: attachments, MIME building, retries."""

import os
import smtplib
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import email_sender


class AttachmentsTest(unittest.TestCase):
    def test_lists_regular_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "a.pdf")
            with open(p, "wb") as fh:
                fh.write(b"pdf")
            atts = email_sender.get_attachments(tmp)
            self.assertEqual(atts, [p])

    def test_zip_is_extracted_and_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "bundle.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("inside.txt", "hello")

            atts = email_sender.get_attachments(tmp)
            self.assertEqual(len(atts), 1)
            self.assertTrue(atts[0].endswith("inside.txt"))
            self.assertIn("_extracted", atts[0])
            self.assertFalse(os.path.exists(zip_path))

    def test_keep_zip_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "bundle.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("inside.txt", "hello")

            atts = email_sender.get_attachments(tmp, remove_zip_after_extract=False)
            self.assertEqual(len(atts), 1)
            self.assertTrue(os.path.exists(zip_path))

    def test_missing_dir_returns_empty(self):
        self.assertEqual(email_sender.get_attachments("/no/such/dir"), [])

    def test_zip_slip_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "evil.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("../escape.txt", "owned")

            with self.assertRaises(ValueError):
                email_sender.get_attachments(tmp)
            # Nothing may have escaped the temp dir.
            escaped = os.path.join(os.path.dirname(tmp), "escape.txt")
            self.assertFalse(os.path.exists(escaped))


class CleanupTest(unittest.TestCase):
    def test_cleanup_clears_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "sub")
            os.makedirs(sub)
            with open(os.path.join(sub, "f.txt"), "w") as fh:
                fh.write("x")
            email_sender.cleanup(tmp)
            self.assertEqual(os.listdir(tmp), [])


class FakeSMTP:
    """Stand-in for smtplib.SMTP / SMTP_SSL."""

    sent_messages = []
    auth_errors = 0

    def __init__(self, host, port, timeout=30):
        self.host = host
        self.port = port

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        FakeSMTP.sent_messages.append(msg)

    def quit(self):
        pass


class FlakySMTP(FakeSMTP):
    """Fails send_message N times before succeeding."""

    fail_times = 0

    def send_message(self, msg):
        if FlakySMTP.fail_times > 0:
            FlakySMTP.fail_times -= 1
            raise smtplib.SMTPException("temporary failure")
        super().send_message(msg)


class AuthFailSMTP(FakeSMTP):
    def login(self, user, password):
        raise smtplib.SMTPAuthenticationError(535, b"auth failed")


def _cfg():
    return {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "u@example.com",
        "smtp_pass": "secret",
    }


class SendEmailTest(unittest.TestCase):
    def setUp(self):
        FakeSMTP.sent_messages = []
        FlakySMTP.fail_times = 0

    def _attach(self, tmp):
        p = os.path.join(tmp, "doc.txt")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("content")
        return p

    def test_send_success(self):
        old_smtp, old_ssl = smtplib.SMTP, smtplib.SMTP_SSL
        smtplib.SMTP = smtplib.SMTP_SSL = FakeSMTP
        try:
            with tempfile.TemporaryDirectory() as tmp:
                att = self._attach(tmp)
                names = email_sender.send_email(
                    "a@b.com, c@d.com", "Subject", "Body", [att], _cfg()
                )
            self.assertEqual(names, ["doc.txt"])
            self.assertEqual(len(FakeSMTP.sent_messages), 1)
            msg = FakeSMTP.sent_messages[0]
            self.assertEqual(msg["To"], "a@b.com, c@d.com")
        finally:
            smtplib.SMTP, smtplib.SMTP_SSL = old_smtp, old_ssl

    def test_retry_then_succeed(self):
        FlakySMTP.fail_times = 2
        old_smtp, old_ssl = smtplib.SMTP, smtplib.SMTP_SSL
        smtplib.SMTP = smtplib.SMTP_SSL = FlakySMTP
        try:
            with tempfile.TemporaryDirectory() as tmp:
                att = self._attach(tmp)
                names = email_sender.send_email(
                    "a@b.com", "s", "b", [att], _cfg(), sleep_func=lambda s: None
                )
            self.assertEqual(names, ["doc.txt"])
        finally:
            smtplib.SMTP, smtplib.SMTP_SSL = old_smtp, old_ssl

    def test_exhausted_retries_raise(self):
        FlakySMTP.fail_times = 10
        old_smtp, old_ssl = smtplib.SMTP, smtplib.SMTP_SSL
        smtplib.SMTP = smtplib.SMTP_SSL = FlakySMTP
        try:
            with tempfile.TemporaryDirectory() as tmp:
                att = self._attach(tmp)
                with self.assertRaises(smtplib.SMTPException):
                    email_sender.send_email(
                        "a@b.com",
                        "s",
                        "b",
                        [att],
                        _cfg(),
                        max_retries=2,
                        sleep_func=lambda s: None,
                    )
        finally:
            smtplib.SMTP, smtplib.SMTP_SSL = old_smtp, old_ssl

    def test_auth_error_not_retried(self):
        old_smtp, old_ssl = smtplib.SMTP, smtplib.SMTP_SSL
        smtplib.SMTP = smtplib.SMTP_SSL = AuthFailSMTP
        try:
            with tempfile.TemporaryDirectory() as tmp:
                att = self._attach(tmp)
                with self.assertRaises(smtplib.SMTPAuthenticationError):
                    email_sender.send_email(
                        "a@b.com",
                        "s",
                        "b",
                        [att],
                        _cfg(),
                        max_retries=3,
                        sleep_func=lambda s: None,
                    )
        finally:
            smtplib.SMTP, smtplib.SMTP_SSL = old_smtp, old_ssl

    def test_empty_recipients_raises(self):
        with self.assertRaises(ValueError):
            email_sender.send_email(" , ,", "s", "b", [], _cfg())

    def test_ssl_flag_uses_smtp_ssl(self):
        used = []

        class SSLTracker(FakeSMTP):
            def __init__(self, host, port, timeout=30):
                used.append(("ssl", host, port))
                super().__init__(host, port, timeout=timeout)

        class PlainTracker(FakeSMTP):
            def __init__(self, host, port, timeout=30):
                used.append(("plain", host, port))
                super().__init__(host, port, timeout=timeout)

        old_smtp, old_ssl = smtplib.SMTP, smtplib.SMTP_SSL
        smtplib.SMTP = PlainTracker
        smtplib.SMTP_SSL = SSLTracker
        try:
            cfg = _cfg()
            cfg["smtp_port"] = 465
            cfg["smtp_use_ssl"] = True
            email_sender.send_email("a@b.com", "s", "b", [], cfg)
            self.assertEqual(used[0][0], "ssl")

            used.clear()
            cfg = _cfg()
            cfg["smtp_port"] = 587
            cfg["smtp_use_ssl"] = False
            email_sender.send_email("a@b.com", "s", "b", [], cfg)
            self.assertEqual(used[0][0], "plain")
        finally:
            smtplib.SMTP, smtplib.SMTP_SSL = old_smtp, old_ssl


if __name__ == "__main__":
    unittest.main()
