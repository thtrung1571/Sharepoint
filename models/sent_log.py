"""Persist the history of sent files/folders.

The log is a JSON file mapping a *key* to metadata. The key is normally the
file/folder name, but callers may provide ``full_path`` (e.g.
``"Domestic/VIET AU/report.zip"``) to distinguish items that share the same
name in different folders.

All public functions are thread-safe: a single module-level lock protects
read-modify-write cycles.
"""

import datetime
import json
import os
import threading
from typing import Dict, List, Optional, Tuple

from paths import get_sent_log_path

SENT_LOG_PATH = get_sent_log_path()

_lock = threading.Lock()


def _read_log() -> Dict:
    if not os.path.exists(SENT_LOG_PATH):
        return {}
    try:
        with open(SENT_LOG_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_log(data: Dict) -> None:
    with open(SENT_LOG_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _make_key(name: str, full_path: Optional[str]) -> str:
    return full_path if full_path else name


def _ancestor_folder_sent_at(data: Dict, key: str) -> Optional[str]:
    """Return ``sent_at`` from the nearest ancestor folder entry, if any.

    Used so children of a sent folder inherit the folder's sent timestamp in
    the UI, without marking parent folders as sent.
    """
    if "/" not in key:
        return None
    parts = key.split("/")
    for i in range(len(parts) - 1, 0, -1):
        parent = "/".join(parts[:i])
        entry = data.get(parent)
        if entry and entry.get("is_folder"):
            return entry.get("sent_at")
    return None


def log_sent_file(
    filename: str,
    to: str,
    subject: str,
    files_sent: List[str],
    full_path: Optional[str] = None,
) -> None:
    key = _make_key(filename, full_path)
    entry = {
        "name": filename,
        "sent_at": _now_str(),
        "to": to,
        "subject": subject,
        "files": files_sent,
        "is_folder": False,
    }
    with _lock:
        data = _read_log()
        data[key] = entry
        _write_log(data)


def log_sent_folder(
    folder_name: str,
    to: str,
    subject: str,
    files_sent: List[str],
    full_path: Optional[str] = None,
) -> None:
    key = _make_key(folder_name, full_path)
    entry = {
        "name": folder_name,
        "sent_at": _now_str(),
        "to": to,
        "subject": subject,
        "files": files_sent,
        "is_folder": True,
    }
    with _lock:
        data = _read_log()
        data[key] = entry
        _write_log(data)


def get_sent_time(filename: str, full_path: Optional[str] = None) -> Optional[str]:
    """Return sent time for a file: exact key, else nearest sent ancestor folder."""
    key = _make_key(filename, full_path)
    with _lock:
        data = _read_log()
        entry = data.get(key)
        if entry:
            return entry["sent_at"]
        return _ancestor_folder_sent_at(data, key)


def get_folder_sent_time(
    folder_name: str, full_path: Optional[str] = None
) -> Optional[str]:
    """Return sent time for a folder.

    Uses the exact folder key, or inherits from a nearer ancestor folder that
    was itself sent. Does **not** bubble child activity up to parents.
    """
    key = _make_key(folder_name, full_path)
    with _lock:
        data = _read_log()
        entry = data.get(key)
        if entry:
            return entry["sent_at"]
        return _ancestor_folder_sent_at(data, key)


def is_already_sent(
    filenames: List[str],
    full_paths: Optional[Optional[List[Optional[str]]]] = None,
) -> List[Tuple[str, str]]:
    """Return a list of ``(display_name, sent_at)`` for items already in the log.

    Matches exact keys and also children of a previously sent folder.
    """
    with _lock:
        data = _read_log()
        already: List[Tuple[str, str]] = []
        for idx, fname in enumerate(filenames):
            key = fname
            if full_paths is not None and idx < len(full_paths) and full_paths[idx]:
                key = full_paths[idx]
            entry = data.get(key)
            if entry:
                already.append((fname, entry["sent_at"]))
                continue
            inherited = _ancestor_folder_sent_at(data, key)
            if inherited:
                already.append((fname, inherited))
        return already
