"""Download helper for selected SharePoint items."""

import logging
import os
from typing import Optional

from .selectors import Selectors

logger = logging.getLogger(__name__)


async def download_selected(page, download_dir: Optional[str] = None) -> Optional[str]:
    if download_dir is None:
        from paths import get_downloads_dir

        download_dir = get_downloads_dir()
    os.makedirs(download_dir, exist_ok=True)

    btn = page.locator(Selectors.DOWNLOAD_BUTTON)
    if await btn.count() == 0:
        return None

    async with page.expect_download() as dl_info:
        await btn.click()

    download = await dl_info.value
    logger.debug("Download url: %s", download.url)
    logger.debug("Suggested filename: %s", download.suggested_filename)
    path = os.path.join(download_dir, download.suggested_filename)
    await download.save_as(path)
    return path
