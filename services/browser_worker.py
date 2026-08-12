"""QThread that owns the Playwright browser session.

The UI never talks to Playwright directly; it sends command dicts through
:meth:`BrowserThread.send` and receives results via Qt signals.
"""

import asyncio
import gc
import logging
import os
import random
import shutil
import subprocess
import threading
import queue

from PySide6.QtCore import QThread, Signal
from playwright.async_api import async_playwright

from paths import get_user_data_dir

from . import sharepoint

logger = logging.getLogger(__name__)

MAX_LOGIN_ATTEMPTS = 2
RETRY_WAIT_MIN_S = 15
RETRY_WAIT_MAX_S = 30


class BrowserThread(QThread):
    """Runs an asyncio loop driving a persistent Chromium context."""

    items_ready = Signal(list)
    download_done = Signal(str)
    url_ready = Signal(str)
    error = Signal(str)
    login_done = Signal()
    status = Signal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.page = None
        self.ctx = None
        self.pw = None
        self.cmd_queue = queue.Queue()
        self._running = True
        self.quit_event = threading.Event()

    # -- thread entry point -------------------------------------------------

    def run(self):
        try:
            asyncio.run(self._async_run())
        except Exception as exc:
            logger.exception("Browser thread crashed")
            self.error.emit(str(exc))

    async def _clear_browser_data(self):
        user_data_dir = get_user_data_dir()
        if not os.path.isdir(user_data_dir):
            return
        logger.info("Clearing browser data...")
        self.status.emit("Clearing browser data...")
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "chrome.exe"],
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["taskkill", "/F", "/IM", "chromium.exe"],
                capture_output=True,
                timeout=10,
            )
            await asyncio.sleep(1)
            shutil.rmtree(user_data_dir, ignore_errors=True)
        except Exception as exc:
            logger.warning("Could not fully clear browser data: %s", exc)

    async def _try_login(self, pw, target_url: str):
        """Single login attempt; returns True/None/False like sharepoint.login."""
        headless = self.config.get("headless", False)
        self.status.emit("Launching browser...")
        self.ctx = await pw.chromium.launch_persistent_context(
            get_user_data_dir(), headless=headless, accept_downloads=True
        )
        self.page = await self.ctx.new_page()
        try:
            return await sharepoint.login(
                self.page, target_url, status_cb=self.status.emit
            )
        except Exception as exc:
            logger.exception("Login attempt raised")
            self.error.emit(str(exc))
            return False

    async def _async_run(self):
        headless = self.config.get("headless", False)
        if self.config.get("clear_browser", False):
            await self._clear_browser_data()

        target_url = self.config.get("target_url") or sharepoint.TARGET_URL
        login_ok = False
        attempts = 0

        async with async_playwright() as pw:
            self.pw = pw

            while attempts < MAX_LOGIN_ATTEMPTS and not login_ok:
                if attempts > 0:
                    logger.info("Restarting browser for login attempt %d", attempts + 1)
                    await self._close_ctx()
                    gc.collect()
                    wait_time = random.randint(RETRY_WAIT_MIN_S, RETRY_WAIT_MAX_S)
                    logger.info("Waiting %ds before retry...", wait_time)
                    self.status.emit(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)

                attempts += 1
                result = await self._try_login(pw, target_url)

                if result is True:
                    login_ok = True
                    self.status.emit("Logged in")
                    self.login_done.emit()
                elif result is None:
                    logger.warning(
                        "Code invalid, attempt %d/%d", attempts, MAX_LOGIN_ATTEMPTS
                    )
                    self.status.emit("Code invalid, retrying...")
                    await self._close_ctx()
                else:
                    logger.warning(
                        "Login failed (no code), attempt %d/%d",
                        attempts,
                        MAX_LOGIN_ATTEMPTS,
                    )
                    await self._close_ctx()

            if not login_ok:
                self.error.emit(f"Login failed after {MAX_LOGIN_ATTEMPTS} attempts")
                await self._close_ctx()
                return

            # Command loop: poll the queue without blocking the event loop.
            while self._running and not self.quit_event.is_set():
                try:
                    cmd = self.cmd_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    continue

                action = cmd.get("action")
                try:
                    if action == "load":
                        self.status.emit("Fetching list items...")
                        self.items_ready.emit(await sharepoint.get_items(self.page))
                    elif action == "open":
                        self.status.emit("Opening folder...")
                        await sharepoint.click_folder(self.page, cmd["name"])
                        self.items_ready.emit(await sharepoint.get_items(self.page))
                    elif action == "check":
                        await sharepoint.toggle_checkbox(
                            self.page, cmd["row_id"], cmd["checked"]
                        )
                    elif action == "back":
                        self.status.emit("Going back...")
                        await sharepoint.go_back(self.page)
                        self.items_ready.emit(await sharepoint.get_items(self.page))
                    elif action == "download":
                        path = await sharepoint.download_selected(self.page)
                        if path:
                            self.download_done.emit(path)
                    elif action == "navigate":
                        await sharepoint.navigate_to_path(self.page, cmd["path"])
                        self.items_ready.emit(await sharepoint.get_items(self.page))
                    elif action == "url":
                        self.url_ready.emit(sharepoint.get_current_url(self.page))
                    elif action == "reload_url":
                        await sharepoint.navigate_to_url(self.page, cmd["url"])
                        self.items_ready.emit(await sharepoint.get_items(self.page))
                    elif action == "quit":
                        break
                except Exception as exc:
                    logger.exception("Command %r failed", action)
                    self.error.emit(str(exc))

            await self._close_ctx()

    async def _close_ctx(self):
        try:
            if self.ctx:
                await self.ctx.close()
        except Exception:
            pass
        self.ctx = None

    # -- API used by the UI thread ------------------------------------------

    def send(self, cmd):
        self.cmd_queue.put(cmd)

    def stop(self):
        self._running = False
        self.quit_event.set()
