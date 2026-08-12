"""Folder list browsing, selection and back-navigation helpers."""

import logging
import urllib.parse
from typing import Dict, List

from playwright.async_api import TimeoutError as PwTimeout

from .selectors import Selectors

logger = logging.getLogger(__name__)


async def wait_for_folder_list(page, timeout: int = 30000):
    await page.wait_for_selector(Selectors.LIST_CONTAINER, timeout=timeout)
    empty_placeholder = await page.query_selector(Selectors.EMPTY_PLACEHOLDER)
    if empty_placeholder:
        return
    await page.wait_for_selector(
        "//div[@data-automationid='field-LinkFilename']", timeout=timeout
    )
    # One extra beat so the hero-field spans inside each row finish
    # rendering; otherwise get_items() can read a mid-render DOM and
    # return the parent folder's rows after an open/back navigation.
    await page.wait_for_selector(
        "//div[@data-automationid='field-LinkFilename']//span",
        timeout=5000,
    )


async def get_items(page) -> List[Dict]:
    """Return the visible rows: name, modified, is_folder, row_id."""
    await wait_for_folder_list(page)

    # Single evaluate() call: all DOM traversal inside V8
    return await page.evaluate(
        """
        () => {
            const rows = document.querySelectorAll("[data-automationid^='row-']");
            const results = [];
            for (const row of rows) {
                const rowId = (row.getAttribute("data-automationid") || "").replace("row-", "");

                const nameEl = row.querySelector(
                    "[data-automationid='field-LinkFilename'] span[data-id='heroField']"
                );
                if (!nameEl) continue;
                const name = nameEl.innerText.trim();
                if (!name) continue;

                const modEl = row.querySelector("[data-automationid='field-Modified']");
                const modified = modEl ? modEl.innerText.trim() : "";

                const icon = row.querySelector("[data-automationid='field-DocIcon'] img");
                const alt = icon ? (icon.getAttribute("alt") || "") : "";
                const isFolder = !alt.startsWith(".");

                results.push({ name, modified, is_folder: isFolder, row_id: rowId });
            }
            return results;
        }
        """
    )


def _current_folder_path(url: str) -> str:
    """Decoded library path from the current OneDrive URL ``id`` param."""
    params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    current_id = params.get("id", [""])[0]
    return urllib.parse.unquote(current_id).rstrip("/")


def _current_view(url: str) -> str:
    """The ``viewid`` GUID of the current library view ("" when absent)."""
    params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return params.get("viewid", [""])[0].lower()


def _make_list_stream_matcher(expected_folder: str, expected_view: str):
    """Build a response predicate for the ``RenderListDataAsStream`` XHR.

    The response URL must carry a ``RootFolder`` whose decoded path ends
    with *expected_folder*, and - when known - the same ``View`` GUID as
    the current page.  This keeps prefetches of sibling folders from
    satisfying the wait.
    """

    def matches(resp) -> bool:
        if resp.request.method != "POST" or "RenderListDataAsStream" not in resp.url:
            return False
        params = urllib.parse.parse_qs(urllib.parse.urlparse(resp.url).query)
        root_folder = urllib.parse.unquote(params.get("RootFolder", [""])[0])
        if not root_folder.rstrip("/").endswith(expected_folder):
            return False
        if expected_view:
            view = params.get("View", [""])[0].lower()
            if view and view != expected_view:
                return False
        return True

    return matches


async def click_folder(page, folder_name: str) -> bool:
    await wait_for_folder_list(page)

    js = """
        (folderName) => {
            const rows = document.querySelectorAll("[data-automationid^='row-']");
            for (const row of rows) {
                const nameEl = row.querySelector(
                    "[data-automationid='field-LinkFilename'] span[data-id='heroField']"
                );
                if (nameEl && nameEl.innerText.trim() === folderName) {
                    nameEl.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
                    return true;
                }
            }
            return false;
        }
    """

    current_folder = _current_folder_path(page.url)
    expected_folder = (
        f"{current_folder}/{folder_name}" if current_folder else folder_name
    )
    matcher = _make_list_stream_matcher(expected_folder, _current_view(page.url))

    try:
        async with page.expect_response(matcher, timeout=15000) as info:
            found = await page.evaluate(js, folder_name)
        if found:
            response = await info.value
            logger.info("List data XHR: %s %s", response.status, response.url)
    except PwTimeout:
        # The XHR listener timed out; the dblclick already fired so do NOT
        # re-dispatch (that could trigger a second navigation).  Just wait
        # for load state and fall back to the DOM-based check below.
        logger.info(
            "No RenderListDataAsStream after dblclick; falling back to DOM wait"
        )
        await page.wait_for_load_state("domcontentloaded")

    if found:
        await wait_for_folder_list(page, timeout=15000)
    return found


async def go_back(page) -> bool:
    crumbs = page.locator(Selectors.BREADCRUMB_ITEM)
    count = await crumbs.count()
    if count < 2:
        return False

    parent = crumbs.nth(count - 2).locator(Selectors.BREADCRUMB_CRUMB)

    current_folder = _current_folder_path(page.url)
    expected_folder = (
        current_folder.rsplit("/", 1)[0] if "/" in current_folder else current_folder
    )
    matcher = _make_list_stream_matcher(expected_folder, _current_view(page.url))

    try:
        async with page.expect_response(matcher, timeout=15000) as info:
            await parent.click()
        response = await info.value
        logger.info("List data XHR: %s %s", response.status, response.url)
    except PwTimeout:
        logger.info(
            "No RenderListDataAsStream after back; falling back to DOM wait"
        )
        await page.wait_for_load_state("domcontentloaded")

    await wait_for_folder_list(page, timeout=15000)
    return True


async def toggle_checkbox(page, row_id: str, checked: bool):
    """Set the row's checkbox, only clicking when the state differs."""
    current = await page.evaluate(
        """
        (rowId) => {
            const row = document.querySelector(`[data-automationid='row-${rowId}']`);
            if (!row) return null;
            const cb = row.querySelector("input[type='checkbox']");
            return cb ? cb.checked : null;
        }
        """,
        row_id,
    )

    if current is None or current == checked:
        return

    # Real Playwright click so React's synthetic event system is triggered.
    checkbox = page.locator(
        f"[data-automationid='row-{row_id}'] input[type='checkbox']"
    )
    await checkbox.click(force=True)
