"""Tests for models.pop3_client: parsing and fake-mailbox fetching."""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import pop3_client


def _make_raw(sender, subject, body, date=None):
    """Build a minimal non-multipart RFC822 message."""
    headers = [
        f"From: {sender}",
        f"Subject: {subject}",
    ]
    if date is not None:
        if isinstance(date, datetime):
            headers.append(f"Date: {format_datetime(date)}")
        else:
            headers.append(f"Date: {date}")
    return ("\r\n".join(headers) + "\r\n\r\n" + body).encode("utf-8")


MS_SENDER = "Microsoft account team <account-security-noreply@accountprotection.microsoft.com>"


class ParseTest(unittest.TestCase):
    def test_parse_sender_subject_and_code(self):
        raw = _make_raw(
            MS_SENDER,
            "Your account verification code",
            "Hello, your Account verification code: 123456. It expires soon.",
        )
        sender, subject, code = pop3_client.parse_verification_message(raw)
        self.assertIn("accountprotection.microsoft.com", sender)
        self.assertIn("verification code", subject.lower())
        self.assertEqual(code, "123456")

    def test_fallback_generic_code(self):
        raw = _make_raw(MS_SENDER, "Verify", "Use code 98765432 to continue.")
        _, _, code = pop3_client.parse_verification_message(raw)
        self.assertEqual(code, "98765432")

    def test_no_code_returns_none(self):
        raw = _make_raw(MS_SENDER, "Hello", "No digits here.")
        _, _, code = pop3_client.parse_verification_message(raw)
        self.assertIsNone(code)

    def test_encoded_subject(self):
        raw = (
            f"From: {MS_SENDER}\r\n"
            "Subject: =?utf-8?b?QWNjb3VudCB2ZXJpZmljYXRpb24gY29kZQ==?=\r\n"
            "\r\n"
            "Account verification code: 445566"
        ).encode("utf-8")
        _, subject, code = pop3_client.parse_verification_message(raw)
        self.assertEqual(subject, "Account verification code")
        self.assertEqual(code, "445566")


class FakePOP3:
    """In-memory POP3 server used to test fetch_verification_code."""

    instances = []

    def __init__(self, host, port, timeout=30):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.deleted = []
        self.quit_called = False
        self.messages = []
        FakePOP3.instances.append(self)

    def user(self, u):
        self.username = u

    def pass_(self, p):
        self.password = p

    def stat(self):
        return len(self.messages), 0

    def retr(self, i):
        lines = self.messages[i - 1].split(b"\r\n")
        return b"+OK", lines, 0

    def dele(self, i):
        self.deleted.append(i)

    def quit(self):
        self.quit_called = True


class FetchTest(unittest.TestCase):
    def setUp(self):
        FakePOP3.instances = []
        FakePOP3.prototype_messages = []

    def _make_factory(self, messages):
        def factory(host, port, timeout=30):
            inst = FakePOP3(host, port, timeout=timeout)
            inst.messages = list(messages)
            return inst

        return factory

    def test_fetches_and_deletes_newest_code(self):
        good = _make_raw(
            MS_SENDER,
            "Your account verification code",
            "Account verification code: 555777",
        )
        noise = _make_raw("someone@example.com", "Lunch?", "See you at noon")
        factory = self._make_factory([good, noise])

        code = pop3_client.fetch_verification_code(
            "pop.example.com", 995, "u", "p", pop3_cls=factory
        )
        self.assertEqual(code, "555777")
        inst = FakePOP3.instances[0]
        self.assertEqual(inst.deleted, [1])
        self.assertTrue(inst.quit_called)

    def test_no_code_returns_none(self):
        noise = _make_raw("someone@example.com", "Lunch?", "See you at noon")
        factory = self._make_factory([noise])
        code = pop3_client.fetch_verification_code(
            "pop.example.com", 995, "u", "p", pop3_cls=factory
        )
        self.assertIsNone(code)

    def test_missing_config_returns_none(self):
        code = pop3_client.fetch_verification_code("", 995, "", "", pop3_cls=FakePOP3)
        self.assertIsNone(code)

    def test_exception_returns_none_and_quits(self):
        class BoomPOP3(FakePOP3):
            def stat(self):
                raise OSError("network down")

        msg = _make_raw(MS_SENDER, "code", "Account verification code: 111222")

        def boom_factory(host, port, timeout=30):
            inst = BoomPOP3(host, port, timeout=timeout)
            inst.messages = [msg]
            return inst

        code = pop3_client.fetch_verification_code(
            "pop.example.com", 995, "u", "p", pop3_cls=boom_factory
        )
        self.assertIsNone(code)
        self.assertTrue(FakePOP3.instances[0].quit_called)

    def test_skips_old_code_when_not_before_set(self):
        now = datetime.now(timezone.utc)
        old = _make_raw(
            MS_SENDER,
            "Your account verification code",
            "Account verification code: 111111",
            date=now - timedelta(minutes=10),
        )
        factory = self._make_factory([old])
        code = pop3_client.fetch_verification_code(
            "pop.example.com",
            995,
            "u",
            "p",
            pop3_cls=factory,
            not_before=now,
        )
        self.assertIsNone(code)
        self.assertEqual(FakePOP3.instances[0].deleted, [])

    def test_accepts_recent_code_within_grace(self):
        now = datetime.now(timezone.utc)
        recent = _make_raw(
            MS_SENDER,
            "Your account verification code",
            "Account verification code: 222333",
            date=now - timedelta(seconds=30),
        )
        factory = self._make_factory([recent])
        code = pop3_client.fetch_verification_code(
            "pop.example.com",
            995,
            "u",
            "p",
            pop3_cls=factory,
            not_before=now,
        )
        self.assertEqual(code, "222333")
        self.assertEqual(FakePOP3.instances[0].deleted, [1])

    def test_skips_missing_date_when_not_before_set(self):
        now = datetime.now(timezone.utc)
        missing_date = _make_raw(
            MS_SENDER,
            "Your account verification code",
            "Account verification code: 444555",
        )
        factory = self._make_factory([missing_date])
        code = pop3_client.fetch_verification_code(
            "pop.example.com",
            995,
            "u",
            "p",
            pop3_cls=factory,
            not_before=now,
        )
        self.assertIsNone(code)
        self.assertEqual(FakePOP3.instances[0].deleted, [])

    def test_prefers_fresh_over_stale_when_not_before_set(self):
        now = datetime.now(timezone.utc)
        stale = _make_raw(
            MS_SENDER,
            "Your account verification code",
            "Account verification code: 666777",
            date=now - timedelta(minutes=15),
        )
        fresh = _make_raw(
            MS_SENDER,
            "Your account verification code",
            "Account verification code: 888999",
            date=now + timedelta(seconds=5),
        )
        # mailbox order: older first, newer last (POP3 newest = highest index)
        factory = self._make_factory([stale, fresh])
        code = pop3_client.fetch_verification_code(
            "pop.example.com",
            995,
            "u",
            "p",
            pop3_cls=factory,
            not_before=now,
        )
        self.assertEqual(code, "888999")
        self.assertEqual(FakePOP3.instances[0].deleted, [2])


if __name__ == "__main__":
    unittest.main()
