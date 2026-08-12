"""Path helpers for Auto Mail Sender.

All directory resolution is pure: no module-level side effects, so importing
this module never creates directories or reads files.
"""

import os
import sys


def get_base_path() -> str:
    """Return the application base directory.

    In a PyInstaller frozen build this is the folder containing the exe;
    in development it is the folder containing this file.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_config_path() -> str:
    return os.path.join(get_base_path(), "config.json")


def get_downloads_dir() -> str:
    return os.path.join(get_base_path(), "downloads")


def get_user_data_dir() -> str:
    return os.path.join(get_base_path(), "browser_data")


def get_sent_log_path() -> str:
    return os.path.join(get_base_path(), "sent_log.json")
