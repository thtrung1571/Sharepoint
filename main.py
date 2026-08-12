"""Auto Mail Sender - application entry point.

Run with ``--check`` for a headless sanity check that imports every layer
without starting the GUI.
"""

import logging
import os
import sys

# Playwright must find the browsers folder both in dev and in frozen builds.
from paths import get_base_path

os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH", os.path.join(get_base_path(), "browsers")
)

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.main_window import MainWindow  # noqa: E402


def _run_self_check() -> int:
    """Import all layers and print path/config sanity information."""
    import config
    import paths
    from models import pop3_client, sent_log  # noqa: F401
    from services import (  # noqa: F401
        browser_worker,
        email_sender,
        email_worker,
        sharepoint,
    )
    from ui import dialogs, main_window  # noqa: F401

    cfg = config.load_config()
    logging.basicConfig(level=logging.INFO)
    print("Base path      :", paths.get_base_path())
    print("Config path    :", paths.get_config_path())
    print("Downloads dir  :", paths.get_downloads_dir())
    print("User data dir  :", paths.get_user_data_dir())
    print("Sent log path  :", paths.get_sent_log_path())
    print("SMTP host      :", cfg.get("smtp_host"))
    print("SMTP port      :", cfg.get("smtp_port"))
    print("Target URL set :", bool(cfg.get("target_url")))
    print("POP3 host set  :", bool(config.get_pop3_config().get("host")))
    print("Self-check OK.")
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if "--check" in sys.argv:
        return _run_self_check()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
