"""Path/URL helpers and navigation for SharePoint browsing."""

import logging
import urllib.parse
from typing import List, Optional

from .selectors import BASE_ID

logger = logging.getLogger(__name__)


def _strip_path_suffix(full_path: str, path_parts: Optional[List[str]]) -> str:
    """Strip trailing UI path segments from a decoded library path."""
    root = full_path.rstrip("/")
    parts = [p for p in (path_parts or []) if p]
    if not parts:
        return root
    suffix = "/" + "/".join(parts)
    if root.endswith(suffix):
        return root[: -len(suffix)].rstrip("/")
    return root


def library_root_from_id(
    encoded_or_decoded_id: str, path_parts: Optional[List[str]] = None
) -> str:
    """Return the encoded library-root ``id`` with UI path segments stripped."""
    if not encoded_or_decoded_id:
        return BASE_ID
    decoded = urllib.parse.unquote(encoded_or_decoded_id)
    root = _strip_path_suffix(decoded, path_parts)
    return urllib.parse.quote(root, safe="")


def build_library_id(
    path_parts: Optional[List[str]] = None, base_id: str = BASE_ID
) -> str:
    """Build an encoded SharePoint ``id`` for the library root + relative path.

    ``base_id`` may be encoded or decoded; ``path_parts`` are plain folder
    names from the UI (e.g. ``["05", "EXPORT"]``).
    """
    root = urllib.parse.unquote(base_id).rstrip("/")
    parts = [p for p in (path_parts or []) if p]
    if parts:
        full = root + "/" + "/".join(parts)
    else:
        full = root
    return urllib.parse.quote(full, safe="")


def build_onedrive_url(current_url: str, path_parts: Optional[List[str]] = None) -> str:
    """Rewrite the current OneDrive URL ``id`` for ``path_parts``.

    Workflow:
    1. Decode the live ``id`` (parse_qs decodes once).
    2. Strip the UI ``path_parts`` suffix to recover the library root.
    3. Rebuild ``root + path_parts`` and encode **once** into the query.
    """
    parsed = urllib.parse.urlparse(current_url)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

    if params.get("id") and params["id"][0]:
        current_decoded = params["id"][0]
    else:
        current_decoded = urllib.parse.unquote(BASE_ID)

    root_decoded = _strip_path_suffix(current_decoded, path_parts)
    parts = [p for p in (path_parts or []) if p]
    if parts:
        full_decoded = root_decoded.rstrip("/") + "/" + "/".join(parts)
    else:
        full_decoded = root_decoded.rstrip("/")

    # Store the decoded path; urlencode(..., quote_via=quote) encodes once.
    # Using quote (not quote_plus) keeps spaces as %20 like SharePoint.
    params["id"] = [full_decoded]
    new_query = urllib.parse.urlencode(
        params, doseq=True, quote_via=urllib.parse.quote
    )
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query}"


def get_current_url(page) -> str:
    """Synchronous: just reads page.url, no await needed."""
    return page.url


async def navigate_to_path(page, path_parts: List[str]):
    """Navigate to a sub-path of the library by rewriting the ``id`` param."""
    new_url = build_onedrive_url(page.url, path_parts)
    response = await page.goto(new_url, wait_until="domcontentloaded")
    if response:
        logger.info("navigate_to_path: %s %s", response.status, response.url)


async def navigate_to_url(page, url: str):
    response = await page.goto(url, wait_until="domcontentloaded")
    if response:
        logger.info("navigate_to_url: %s %s", response.status, response.url)
