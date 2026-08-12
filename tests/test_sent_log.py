"""Tests for models.sent_log: thread-safety and unique keys."""

import json
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models.sent_log as sent_log


class _TempLog:
    """Redirect the module's log file into a temporary directory."""

    def __init__(self):
        self._old_path = None
        self._tmpdir = None

    def __enter__(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old_path = sent_log.SENT_LOG_PATH
        sent_log.SENT_LOG_PATH = os.path.join(self._tmpdir.name, "sent_log.json")
        return sent_log.SENT_LOG_PATH

    def __exit__(self, *exc):
        sent_log.SENT_LOG_PATH = self._old_path
        self._tmpdir.cleanup()


class SentLogTest(unittest.TestCase):
    def test_log_and_get_sent_time(self):
        with _TempLog() as path:
            sent_log.log_sent_file("report.pdf", "a@b.com", "Hi", ["report.pdf"])
            self.assertIsNotNone(sent_log.get_sent_time("report.pdf"))
            self.assertIsNone(sent_log.get_sent_time("other.pdf"))

            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertIn("report.pdf", data)
            self.assertEqual(data["report.pdf"]["to"], "a@b.com")
            self.assertFalse(data["report.pdf"]["is_folder"])

    def test_same_name_different_folder_does_not_overwrite(self):
        with _TempLog():
            sent_log.log_sent_file(
                "data.zip", "a@b.com", "s1", ["data.zip"], full_path="Domestic/data.zip"
            )
            sent_log.log_sent_file(
                "data.zip", "a@b.com", "s2", ["data.zip"], full_path="Export/data.zip"
            )
            self.assertIsNotNone(
                sent_log.get_sent_time("data.zip", full_path="Domestic/data.zip")
            )
            self.assertIsNotNone(
                sent_log.get_sent_time("data.zip", full_path="Export/data.zip")
            )
            # The bare name key must not exist; lookup without path finds nothing.
            self.assertIsNone(sent_log.get_sent_time("data.zip"))

    def test_folder_sent_time_does_not_bubble_to_parents(self):
        with _TempLog():
            sent_log.log_sent_folder(
                "PDMM 111-2026 Done",
                "a@b.com",
                "s",
                ["a.pdf"],
                full_path="05/EXPORT/PDMM 111-2026 Done",
            )
            self.assertIsNone(sent_log.get_folder_sent_time("05"))
            self.assertIsNone(
                sent_log.get_folder_sent_time("EXPORT", full_path="05/EXPORT")
            )
            self.assertIsNotNone(
                sent_log.get_folder_sent_time(
                    "PDMM 111-2026 Done",
                    full_path="05/EXPORT/PDMM 111-2026 Done",
                )
            )

    def test_children_inherit_sent_folder_time(self):
        with _TempLog():
            sent_log.log_sent_folder(
                "PDMM 111-2026 Done",
                "a@b.com",
                "s",
                ["00531842.pdf", "notes/a.txt"],
                full_path="05/EXPORT/PDMM 111-2026 Done",
            )
            ts = sent_log.get_folder_sent_time(
                "PDMM 111-2026 Done",
                full_path="05/EXPORT/PDMM 111-2026 Done",
            )
            self.assertIsNotNone(ts)
            self.assertEqual(
                sent_log.get_sent_time(
                    "00531842.pdf",
                    full_path="05/EXPORT/PDMM 111-2026 Done/00531842.pdf",
                ),
                ts,
            )
            self.assertEqual(
                sent_log.get_folder_sent_time(
                    "notes",
                    full_path="05/EXPORT/PDMM 111-2026 Done/notes",
                ),
                ts,
            )

    def test_file_send_does_not_mark_parent_or_siblings(self):
        with _TempLog():
            sent_log.log_sent_file(
                "a.pdf",
                "a@b.com",
                "s",
                ["a.pdf"],
                full_path="Domestic/Q1/a.pdf",
            )
            self.assertIsNone(sent_log.get_folder_sent_time("Domestic"))
            self.assertIsNone(
                sent_log.get_folder_sent_time("Q1", full_path="Domestic/Q1")
            )
            self.assertIsNotNone(
                sent_log.get_sent_time("a.pdf", full_path="Domestic/Q1/a.pdf")
            )
            self.assertIsNone(
                sent_log.get_sent_time("b.pdf", full_path="Domestic/Q1/b.pdf")
            )

    def test_is_already_sent_mixed(self):
        with _TempLog():
            sent_log.log_sent_file("old.pdf", "a@b.com", "s", ["old.pdf"])
            already = sent_log.is_already_sent(["old.pdf", "new.pdf"])
            self.assertEqual(len(already), 1)
            self.assertEqual(already[0][0], "old.pdf")

    def test_is_already_sent_inherits_sent_folder(self):
        with _TempLog():
            sent_log.log_sent_folder(
                "Done",
                "a@b.com",
                "s",
                ["a.pdf"],
                full_path="05/EXPORT/Done",
            )
            already = sent_log.is_already_sent(
                ["a.pdf"],
                ["05/EXPORT/Done/a.pdf"],
            )
            self.assertEqual(len(already), 1)
            self.assertEqual(already[0][0], "a.pdf")

    def test_concurrent_writes_keep_every_key(self):
        with _TempLog() as path:

            def write(i):
                sent_log.log_sent_file(f"file_{i}.pdf", "t@t.com", "s", [f"f{i}"])

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(write, range(50)))

            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for i in range(50):
                self.assertIn(f"file_{i}.pdf", data)


if __name__ == "__main__":
    unittest.main()
