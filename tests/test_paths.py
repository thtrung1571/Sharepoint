"""Tests for paths: pure functions, no side effects on import."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths


class PathsTest(unittest.TestCase):
    def test_base_path_exists(self):
        base = paths.get_base_path()
        self.assertTrue(os.path.isdir(base))

    def test_paths_are_under_base(self):
        base = paths.get_base_path()
        for p in (
            paths.get_config_path(),
            paths.get_downloads_dir(),
            paths.get_user_data_dir(),
            paths.get_sent_log_path(),
        ):
            self.assertTrue(p.startswith(base), p)

    def test_frozen_switch(self):
        old_frozen = getattr(sys, "frozen", None)
        old_exe = sys.executable
        try:
            sys.frozen = True
            sys.executable = r"C:\fake\dist\AutoMailSender.exe"
            self.assertEqual(paths.get_base_path(), r"C:\fake\dist")
        finally:
            if old_frozen is None:
                del sys.frozen
            else:
                sys.frozen = old_frozen
            sys.executable = old_exe

    def test_import_heavy_module_has_no_file_side_effects(self):
        # Re-importing paths must not create directories or touch config.json
        before = set(os.listdir(paths.get_base_path()))
        import importlib

        importlib.reload(paths)
        after = set(os.listdir(paths.get_base_path()))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
