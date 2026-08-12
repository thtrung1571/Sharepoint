"""Runtime configuration management.

Configuration lives in ``config.json`` next to the executable (or next to
this file in development). Every runtime value can be overridden with an
environment variable prefixed with ``AMS_`` (``AMS_SMTP_PASS=...``).
"""

import json
import logging
import os

from dotenv import load_dotenv

from paths import get_config_path

logger = logging.getLogger(__name__)

CONFIG_PATH = get_config_path()

# Mapping: config key -> (type, default, env var name)
_KEYS = {
    "smtp_host": (str, "", "AMS_SMTP_HOST"),
    "smtp_port": (int, 587, "AMS_SMTP_PORT"),
    "smtp_user": (str, "", "AMS_SMTP_USER"),
    "smtp_pass": (str, "", "AMS_SMTP_PASS"),
    "smtp_use_ssl": (bool, False, "AMS_SMTP_USE_SSL"),
    "target_url": (str, "", "AMS_TARGET_URL"),
    "default_to": (str, "", "AMS_DEFAULT_TO"),
    "default_subject": (str, "", "AMS_DEFAULT_SUBJECT"),
    "default_body": (str, "", "AMS_DEFAULT_BODY"),
    "headless": (bool, False, "AMS_HEADLESS"),
    "clear_browser": (bool, False, "AMS_CLEAR_BROWSER"),
}


def _coerce(raw, type_):
    if type_ is bool:
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    return type_(raw)


def _apply_env_overrides(cfg):
    for key, (type_, _default, env_name) in _KEYS.items():
        value = os.getenv(env_name)
        if value is not None and value != "":
            try:
                cfg[key] = _coerce(value, type_)
            except (ValueError, TypeError):
                logger.warning("Ignoring invalid env override %s=%r", env_name, value)
    return cfg


def load_config():
    """Load config.json, apply defaults and environment overrides."""
    cfg = {key: default for key, (type_, default, _env) in _KEYS.items()}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            file_cfg = json.load(fh)
        if isinstance(file_cfg, dict):
            cfg.update(file_cfg)
    except FileNotFoundError:
        logger.warning("config.json not found at %s, using defaults", CONFIG_PATH)
    except json.JSONDecodeError:
        logger.exception("config.json is invalid JSON, using defaults")
    return _apply_env_overrides(cfg)


def save_config(cfg):
    """Write the given dict to config.json (keys not in _KEYS are kept)."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=4, ensure_ascii=False)


# .env holds the POP3 credentials used for the login 2FA code; loading it
# here keeps os.getenv() consumers working regardless of import order.
load_dotenv()


def get_pop3_config():
    """POP3 settings for the 2FA mailbox, from environment / .env only."""
    return {
        "host": os.getenv("POP3_HOST", ""),
        "port": int(os.getenv("POP3_PORT", "995")),
        "user": os.getenv("POP3_USER", ""),
        "pass": os.getenv("POP3_PASS", ""),
    }
