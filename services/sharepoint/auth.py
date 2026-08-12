"""Login flow and 2FA verification-code polling."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from playwright.async_api import TimeoutError as PwTimeout, Error as PwError

from config import get_pop3_config
from models.pop3_client import fetch_verification_code

from .selectors import Selectors

logger = logging.getLogger(__name__)


async def wait_for_code(
    pop3_cfg: Dict,
    timeout: int = 120,
    interval: float = 5.0,
    status_cb=None,
):
    """Poll the POP3 mailbox until a verification code arrives.

    Captures a UTC not-before anchor at the start of the wait so older 2FA
    messages already present in the mailbox are ignored.  *status_cb* is an
    optional callable invoked with a human-readable status string on each
    poll iteration so the UI can show progress (e.g. "Waiting for code... 10s").
    """
    loop = asyncio.get_event_loop()
    not_before = datetime.now(timezone.utc)
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if status_cb:
            status_cb("Waiting for code...")
        code = await loop.run_in_executor(
            None,
            lambda: fetch_verification_code(
                pop3_cfg["host"],
                pop3_cfg["port"],
                pop3_cfg["user"],
                pop3_cfg["pass"],
                not_before=not_before,
            ),
        )
        if code:
            if status_cb:
                status_cb("Got verification code")
            return code
        await asyncio.sleep(interval)
    return None


async def validate_code(page, otc_input, code: str) -> bool:
    """Submit the verification code; return True when no error is shown."""
    await otc_input.fill(code)
    await page.click(Selectors.SUBMIT_BUTTON)
    try:
        # Fast path: an explicit error element means the code was rejected.
        await page.wait_for_selector(Selectors.OTC_ERROR, timeout=5000)
        return False
    except PwTimeout:
        return True


async def _complete_otc_challenge(page, pop3_cfg: Dict, status_cb=None):
    """Wait for the OTC input, fetch the code by email and validate it.

    Returns True on success, None when the code was rejected (caller should
    restart the browser), False when no code could be fetched.
    """
    if status_cb:
        status_cb("Waiting for OTP input...")
    otc_input = await page.wait_for_selector(Selectors.OTC_INPUT, timeout=60000)
    if status_cb:
        status_cb("Fetching verification code...")
    code = await wait_for_code(pop3_cfg, timeout=120, interval=5, status_cb=status_cb)
    if not code:
        logger.error("Failed to get verification code from email")
        return False

    logger.info("Got verification code, submitting")
    if status_cb:
        status_cb(f"Entering OTP code: {code}")
    if not await validate_code(page, otc_input, code):
        logger.warning("Verification code rejected, need restart")
        if status_cb:
            status_cb("Code invalid")
        return None
    return True


async def login(page, target_url: str, pop3_cfg: Optional[Dict] = None, status_cb=None):
    """Log in to SharePoint.

    Returns True when logged in, None when the code was invalid (retry with
    a fresh browser), False when no verification code could be fetched.
    """
    if pop3_cfg is None:
        pop3_cfg = get_pop3_config()

    response = await page.goto(target_url, wait_until="load")
    if response:
        logger.info("login goto: %s %s", response.status, response.url)
    await page.wait_for_timeout(3000)

    try:
        tile = await page.query_selector(Selectors.ACCOUNT_TILE)
        if tile:
            logger.info("Returning session detected, selecting account")
            if status_cb:
                status_cb("Selecting account tile...")
            await tile.click()
            await page.wait_for_load_state("domcontentloaded")
            result = await _complete_otc_challenge(page, pop3_cfg, status_cb)
            if result is True and status_cb:
                status_cb("Login success")
            return result

        email_input = await page.wait_for_selector(
            Selectors.EMAIL_INPUT, timeout=10000
        )
        if status_cb:
            status_cb("Mail input...")
        await email_input.fill(pop3_cfg["user"])
        await page.click(Selectors.SUBMIT_BUTTON)
        result = await _complete_otc_challenge(page, pop3_cfg, status_cb)
        if result is True and status_cb:
            status_cb("Login success")
        return result

    except PwTimeout:
        logger.info("No login form detected, assuming an existing session")
    except PwError as exc:
        # A mid-flow redirect (common right after browser-data is cleared)
        # destroys the execution context.  Treat it like "no login form":
        # the session is either already valid or SharePoint sent us
        # straight to the list.
        if "Execution context was destroyed" in str(exc):
            logger.info(
                "Navigation raced with selector query, assuming existing session"
            )
        else:
            raise

    if status_cb:
        status_cb("Login success")
    return True
