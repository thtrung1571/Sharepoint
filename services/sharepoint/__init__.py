"""SharePoint/OneDrive automation built on Playwright's async API.

Re-exports the public API so existing callers (``from services import
sharepoint`` / ``from . import sharepoint``) keep working unchanged after the
split into submodules.
"""

from .selectors import BASE_ID, TARGET_URL, Selectors
from .auth import login, validate_code, wait_for_code
from .navigation import (
    build_library_id,
    build_onedrive_url,
    get_current_url,
    library_root_from_id,
    navigate_to_path,
    navigate_to_url,
)
from .browsing import (
    click_folder,
    get_items,
    go_back,
    toggle_checkbox,
    wait_for_folder_list,
)
from .download import download_selected

__all__ = [
    "BASE_ID",
    "TARGET_URL",
    "Selectors",
    "login",
    "validate_code",
    "wait_for_code",
    "build_library_id",
    "build_onedrive_url",
    "get_current_url",
    "library_root_from_id",
    "navigate_to_path",
    "navigate_to_url",
    "click_folder",
    "get_items",
    "go_back",
    "toggle_checkbox",
    "wait_for_folder_list",
    "download_selected",
]
