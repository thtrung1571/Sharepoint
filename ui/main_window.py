"""Main application window: toolbar, file tree, and thread orchestration."""

import logging

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor, QFont, QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import load_config
from models import sent_log
from services.browser_worker import BrowserThread
from services.email_worker import EmailThread
from ui.dialogs import SendMailDialog, SettingsDialog

logger = logging.getLogger(__name__)

BACK_ROW_TEXT = "\u2022\u2022\u2022  (Back)"

TREE_STYLESHEET = """
    QTreeWidget {
        border: 1px solid #ddd;
        border-radius: 6px;
        font-size: 13px;
    }
    QTreeWidget::item { padding: 6px 4px; }
    QTreeWidget::item:hover { background: #e8f0fe; }
"""

TREE_STYLESHEET_LOADING = """
    QTreeWidget {
        border: 1px solid #ddd;
        border-radius: 6px;
        font-size: 13px;
        background: #f5f5f5;
    }
    QTreeWidget::item { padding: 6px 4px; }
"""


class MainWindow(QMainWindow):
    COL_CHECK = 0
    COL_NAME = 1
    COL_MODIFIED = 2
    COL_TYPE = 3
    COL_SENT = 4

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto Mail Sender")
        self.setMinimumSize(950, 550)
        self.current_path = []
        self.checkboxes = {}
        self.items_data = []
        self.worker = None
        self._browser_started = False
        self._sending_mail = False
        self._saved_url = None
        self._pending_mail = None
        self._email_thread = None

        self.init_ui()

    # ------------------------------------------------------------------ UI

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)

        toolbar = QHBoxLayout()

        self.btn_start = QPushButton("\u25b6  Start")
        self.btn_start.setFixedWidth(100)
        self.btn_start.setStyleSheet("background:#0078d4; color:#fff; font-weight:bold;")
        self.btn_start.setToolTip("T\u1ef1 \u0111\u1ed9ng \u0111\u0103ng nh\u1eadp SharePoint")
        self.btn_start.clicked.connect(self.on_start)
        toolbar.addWidget(self.btn_start)

        self.btn_back = QPushButton("\u25c0  Back")
        self.btn_back.setFixedWidth(100)
        self.btn_back.setEnabled(False)
        self.btn_back.setToolTip("Tr\u1edf l\u1ea1i folder tr\u01b0\u1edbc")
        self.btn_back.clicked.connect(self.on_back)
        toolbar.addWidget(self.btn_back)

        self.btn_refresh = QPushButton("\u21bb  Refresh")
        self.btn_refresh.setFixedWidth(100)
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.clicked.connect(self.on_refresh)
        toolbar.addWidget(self.btn_refresh)

        self.btn_quick_select = QToolButton()
        self.btn_quick_select.setText("Quick Select \u25bc")
        self.btn_quick_select.setFixedWidth(140)
        self.btn_quick_select.setPopupMode(QToolButton.InstantPopup)
        self.btn_quick_select.setToolTip("Ch\u1ecdn nhanh")

        menu = QMenu(self.btn_quick_select)
        action_files = QAction("Ch\u1ecdn t\u1ea5t c\u1ea3 File", self)
        action_files.setToolTip("Ch\u1ec9 ch\u1ecdn file ch\u01b0a t\u1eebng g\u1eedi mail")
        action_files.triggered.connect(self._on_quick_select_files)
        action_all = QAction("Ch\u1ecdn t\u1ea5t c\u1ea3 File + Folder", self)
        action_all.setToolTip("Ch\u1ec9 ch\u1ecdn file v\u00e0 folder ch\u01b0a t\u1eebng g\u1eedi mail")
        action_all.triggered.connect(self._on_quick_select_all)
        menu.addAction(action_files)
        menu.addAction(action_all)
        self.btn_quick_select.setMenu(menu)
        toolbar.addWidget(self.btn_quick_select)

        self.btn_download = QPushButton("Download Selected")
        self.btn_download.setEnabled(False)
        self.btn_download.setToolTip(
            "T\u1ea3i file v\u1ec1 m\u00e1y (kh\u00f4ng t\u1ef1 \u0111\u1ed9ng g\u1eedi mail)"
        )
        self.btn_download.clicked.connect(self.on_download)
        toolbar.addWidget(self.btn_download)

        self.btn_send = QPushButton("Send Mail")
        self.btn_send.setEnabled(False)
        self.btn_send.setToolTip("T\u1ef1 \u0111\u1ed9ng t\u1ea3i v\u00e0 g\u1eedi email")
        self.btn_send.clicked.connect(self.on_send_mail)
        toolbar.addWidget(self.btn_send)

        self.btn_settings = QPushButton("\u2699  Settings")
        self.btn_settings.setFixedWidth(100)
        self.btn_settings.clicked.connect(self.on_settings)
        toolbar.addWidget(self.btn_settings)

        toolbar.addStretch()

        self.path_label = QLabel("Root")
        self.path_label.setStyleSheet("color:#555; font-size:13px;")
        toolbar.addWidget(self.path_label)

        layout.addLayout(toolbar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["", "Name", "Modified", "Type", "Da Gui Email"])
        self.tree.setColumnWidth(self.COL_CHECK, 40)
        self.tree.setColumnWidth(self.COL_NAME, 380)
        self.tree.setColumnWidth(self.COL_MODIFIED, 160)
        self.tree.setColumnWidth(self.COL_TYPE, 70)
        self.tree.setColumnWidth(self.COL_SENT, 160)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.NoSelection)
        self.tree.itemDoubleClicked.connect(self.on_item_double_click)
        self.tree.setStyleSheet(TREE_STYLESHEET)
        layout.addWidget(self.tree)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("B\u1ea5m Start \u0111\u1ec3 b\u1eaft \u0111\u1ea7u")

    # ------------------------------------------------------------ UI state

    def _set_loading(self, loading):
        self.btn_back.setEnabled(not loading and bool(self.current_path))
        self.btn_refresh.setEnabled(not loading)
        self.btn_quick_select.setEnabled(not loading)
        self.btn_download.setEnabled(not loading)
        self.btn_send.setEnabled(not loading)
        self.tree.setDisabled(loading)
        self.tree.setStyleSheet(TREE_STYLESHEET_LOADING if loading else TREE_STYLESHEET)

    def _current_full_path(self, name):
        return "/".join(self.current_path + [name]) if self.current_path else None

    # ------------------------------------------------------------ actions

    def on_start(self):
        self._browser_started = True
        self.btn_start.setEnabled(False)
        self.btn_start.setText("Running...")
        self.status.showMessage("Starting browser...")
        self.start_browser()

    def start_browser(self):
        self.worker = BrowserThread(load_config())
        self.worker.login_done.connect(self.on_login_done)
        self.worker.items_ready.connect(self.on_items_loaded)
        self.worker.download_done.connect(self.on_download_done)
        self.worker.url_ready.connect(self.on_url_ready)
        self.worker.error.connect(self.on_error)
        self.worker.status.connect(self.on_status)
        self.worker.start()

    def _quick_select(self, include_folders):
        selected_count = 0
        for name, (cb, item) in self.checkboxes.items():
            is_folder = item.get("is_folder")
            if is_folder and not include_folders:
                continue
            full_path = self._current_full_path(name)
            if is_folder:
                if sent_log.get_folder_sent_time(name, full_path=full_path) is not None:
                    continue
            else:
                if sent_log.get_sent_time(name, full_path=full_path) is not None:
                    continue
            new_state = not cb.isChecked()
            cb.setChecked(new_state)
            self.worker.send(
                {"action": "check", "row_id": item["row_id"], "checked": new_state}
            )
            if new_state:
                selected_count += 1
        label = "items" if include_folders else "file"
        self.status.showMessage(f"Da chon {selected_count} {label}")

    def _on_quick_select_files(self):
        self._quick_select(include_folders=False)

    def _on_quick_select_all(self):
        self._quick_select(include_folders=True)

    def on_back(self):
        if not self.current_path or not self.tree.isEnabled():
            return
        self.current_path.pop()
        self._set_loading(True)
        self.status.showMessage("Going back...")
        self.worker.send({"action": "back"})

    def on_refresh(self):
        if not self.tree.isEnabled():
            return
        self._set_loading(True)
        self.status.showMessage("Refreshing...")
        self.worker.send({"action": "navigate", "path": list(self.current_path)})

    def _selected_names(self):
        return [name for name, (cb, _item) in self.checkboxes.items() if cb.isChecked()]

    def on_download(self):
        if not self.tree.isEnabled():
            return
        selected = self._selected_names()
        if not selected:
            self.status.showMessage("No items selected")
            return
        self._set_loading(True)
        self.status.showMessage(f"Downloading {len(selected)} items...")
        self.worker.send({"action": "download"})

    def on_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.status.showMessage("Settings saved. Restart to apply browser changes.")

    def on_send_mail(self):
        selected = self._selected_names()
        if not selected:
            self.status.showMessage("No items selected for download")
            return

        full_paths = [self._current_full_path(name) for name in selected]
        already = sent_log.is_already_sent(selected, full_paths)
        if already:
            lines = "\n".join([f"- {name} (gui luc {t})" for name, t in already])
            reply = QMessageBox.question(
                self,
                "Da Gui",
                f"Cac file sau da tung duoc gui:\n{lines}\n\nBan co muon gui lai?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        dlg = SendMailDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        to, subject, body = dlg.get_data()
        if not to:
            QMessageBox.warning(self, "Error", "Recipient email is required")
            return

        self._pending_mail = (to, subject, body, selected, self.items_data)
        self._sending_mail = True
        self.worker.url_ready.connect(self._on_url_for_mail_ready)
        self.worker.send({"action": "url"})

    # -------------------------------------------------------------- slots

    @Slot(str)
    def on_url_ready(self, url):
        # Persistent connection used by the URL-refresh bookkeeping.
        self._saved_url = url

    @Slot()
    def on_login_done(self):
        self.status.showMessage("Logged in. Loading...")
        self.worker.send({"action": "load"})

    @Slot(str)
    def on_status(self, msg):
        self.status.showMessage(msg)

    @Slot(list)
    def on_items_loaded(self, items):
        self.tree.clear()
        self.checkboxes.clear()
        self.items_data = items

        if self.current_path:
            up = QTreeWidgetItem(["", BACK_ROW_TEXT, "", "Folder", ""])
            up.setFont(self.COL_NAME, QFont("Segoe UI", 11, QFont.Bold))
            up.setForeground(self.COL_NAME, QColor("#0078d4"))
            up.setToolTip(self.COL_NAME, "Tr\u1edf l\u1ea1i folder tr\u01b0\u1edbc")
            self.tree.addTopLevelItem(up)

        for item in items:
            is_folder = item["is_folder"]
            full_path = self._current_full_path(item["name"])
            if is_folder:
                sent_time = sent_log.get_folder_sent_time(
                    item["name"], full_path=full_path
                )
            else:
                sent_time = sent_log.get_sent_time(item["name"], full_path=full_path)
            sent_str = sent_time or ""
            it = QTreeWidgetItem(
                ["", item["name"], item["modified"], "Folder" if is_folder else "File", sent_str]
            )
            it.setFont(self.COL_NAME, QFont("Segoe UI", 11))
            if is_folder:
                it.setForeground(self.COL_NAME, QColor("#0078d4"))
            if sent_str:
                it.setFont(self.COL_SENT, QFont("Segoe UI", 10, QFont.Bold))
                it.setForeground(self.COL_SENT, QColor("#555555"))

            cb = QCheckBox()
            row_id = item["row_id"]
            cb.stateChanged.connect(
                lambda state, rid=row_id: self.on_checkbox_changed(rid, state)
            )
            self.tree.addTopLevelItem(it)
            self.tree.setItemWidget(it, self.COL_CHECK, cb)
            self.checkboxes[item["name"]] = (cb, item)

        self.btn_back.setEnabled(bool(self.current_path))
        self.btn_refresh.setEnabled(True)
        self.btn_download.setEnabled(True)
        self.btn_send.setEnabled(True)
        self.path_label.setText(
            " / ".join(["Root"] + self.current_path) if self.current_path else "Root"
        )
        self.status.showMessage(f"{len(items)} items ready")
        self._set_loading(False)

    @Slot(str)
    def on_error(self, err):
        self.status.showMessage(f"Error: {err}")
        self._set_loading(False)
        self.btn_refresh.setEnabled(True)

    def on_checkbox_changed(self, row_id, state):
        if not self.tree.isEnabled():
            return
        checked = state == Qt.Checked.value
        self.worker.send({"action": "check", "row_id": row_id, "checked": checked})

    def on_item_double_click(self, item, column):
        if not self.tree.isEnabled():
            return
        name = item.text(self.COL_NAME)

        if name == BACK_ROW_TEXT:
            self.on_back()
            return

        if item.text(self.COL_TYPE) != "Folder":
            return

        self.current_path.append(name)
        self._set_loading(True)
        self.status.showMessage(f"Opening {name}...")
        self.worker.send({"action": "open", "name": name})

    @Slot(str)
    def on_download_done(self, path):
        self.status.showMessage(f"Saved: {path}")
        if not self._sending_mail:
            self._set_loading(False)

    @Slot(str)
    def _on_url_for_mail_ready(self, url):
        self.worker.url_ready.disconnect(self._on_url_for_mail_ready)
        self._saved_url = url
        self.status.showMessage("Downloading...")
        self.worker.download_done.connect(self._on_mail_download_done)
        self.worker.send({"action": "download"})

    @Slot(str)
    def _on_mail_download_done(self, path):
        self.worker.download_done.disconnect(self._on_mail_download_done)
        if not self._pending_mail:
            return
        to, subject, body, selected, items_data = self._pending_mail
        self._pending_mail = None
        self.status.showMessage("Sending email...")

        self._email_thread = EmailThread(
            to,
            subject,
            body,
            selected,
            items_data,
            load_config(),
            current_path=self.current_path,
        )
        self._email_thread.finished.connect(self._on_email_sent)
        self._email_thread.error.connect(self._on_email_error)
        self._email_thread.start()

    @Slot(str, list)
    def _on_email_sent(self, msg, filenames):
        self._sending_mail = False
        self.status.showMessage(msg)
        QMessageBox.information(self, "Success", msg)
        saved = self._saved_url or ""
        self._saved_url = None
        if saved:
            self.worker.send({"action": "reload_url", "url": saved})
        else:
            self.worker.send({"action": "refresh"})

    @Slot(str)
    def _on_email_error(self, err):
        self._sending_mail = False
        self.status.showMessage(f"Email error: {err}")
        QMessageBox.critical(self, "Error", err)
        saved = self._saved_url or ""
        self._saved_url = None
        if saved:
            self.worker.send({"action": "reload_url", "url": saved})
        else:
            self._set_loading(False)

    # ------------------------------------------------------------ shutdown

    def closeEvent(self, event):
        if self._email_thread and self._email_thread.isRunning():
            self._email_thread.wait(5000)
        if self.worker is not None:
            self.status.showMessage("Closing browser...")
            self.worker.send({"action": "quit"})
            self.worker.stop()
            if not self.worker.wait(8000):
                logger.warning(
                    "Browser thread did not finish in time; terminating now"
                )
                self.worker.terminate()
                self.worker.wait(2000)
        event.accept()
