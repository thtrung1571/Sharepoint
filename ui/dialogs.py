"""Settings dialog and send-mail dialog."""

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from config import load_config, save_config


class SendMailDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Send Mail")
        self.setMinimumWidth(500)

        cfg = load_config()
        layout = QFormLayout(self)

        self.to_input = QLineEdit(cfg.get("default_to", ""))
        self.to_input.setPlaceholderText("email1@example.com, email2@example.com")

        self.subject_input = QLineEdit(cfg.get("default_subject", ""))

        self.body_input = QTextEdit()
        self.body_input.setPlainText(cfg.get("default_body", ""))
        self.body_input.setMinimumHeight(120)

        layout.addRow("To:", self.to_input)
        layout.addRow("Subject:", self.subject_input)
        layout.addRow("Body:", self.body_input)

        hint = QLabel("Separate multiple emails with commas")
        hint.setStyleSheet("color:#888; font-size:11px;")
        layout.addRow("", hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_data(self):
        return (
            self.to_input.text().strip(),
            self.subject_input.text().strip(),
            self.body_input.toPlainText().strip(),
        )


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)

        self.cfg = dict(load_config())
        layout = QVBoxLayout(self)

        sharepoint_group = QGroupBox("SharePoint")
        sharepoint_form = QFormLayout(sharepoint_group)
        self.target_url = QLineEdit(self.cfg.get("target_url", ""))
        self.target_url.setPlaceholderText("https://...sharepoint.com/... (leave empty = built-in default)")
        sharepoint_form.addRow("Target URL:", self.target_url)
        layout.addWidget(sharepoint_group)

        smtp_group = QGroupBox("SMTP")
        smtp_form = QFormLayout(smtp_group)
        self.smtp_host = QLineEdit(self.cfg.get("smtp_host", ""))
        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(int(self.cfg.get("smtp_port", 587)))
        self.smtp_ssl = QCheckBox("Use SSL directly (port 465). Off = STARTTLS (port 587)")
        self.smtp_ssl.setChecked(bool(self.cfg.get("smtp_use_ssl", False)))
        self.smtp_user = QLineEdit(self.cfg.get("smtp_user", ""))
        self.smtp_pass = QLineEdit(self.cfg.get("smtp_pass", ""))
        self.smtp_pass.setEchoMode(QLineEdit.Password)
        smtp_form.addRow("Host:", self.smtp_host)
        smtp_form.addRow("Port:", self.smtp_port)
        smtp_form.addRow("", self.smtp_ssl)
        smtp_form.addRow("User:", self.smtp_user)
        smtp_form.addRow("Password:", self.smtp_pass)
        layout.addWidget(smtp_group)

        defaults_group = QGroupBox("Defaults")
        defaults_form = QFormLayout(defaults_group)
        self.default_to = QLineEdit(self.cfg.get("default_to", ""))
        self.default_to.setPlaceholderText("email1@example.com, email2@example.com")
        self.default_subject = QLineEdit(self.cfg.get("default_subject", ""))
        self.default_body = QTextEdit()
        self.default_body.setPlainText(self.cfg.get("default_body", ""))
        self.default_body.setMinimumHeight(80)
        defaults_form.addRow("To:", self.default_to)
        defaults_form.addRow("Subject:", self.default_subject)
        defaults_form.addRow("Body:", self.default_body)
        layout.addWidget(defaults_group)

        browser_group = QGroupBox("Browser")
        browser_form = QFormLayout(browser_group)
        self.headless_cb = QCheckBox("Run headless (no browser window)")
        self.headless_cb.setChecked(bool(self.cfg.get("headless", False)))
        self.clear_browser_cb = QCheckBox("Clear browser data before each session")
        self.clear_browser_cb.setChecked(bool(self.cfg.get("clear_browser", False)))
        browser_form.addRow(self.headless_cb)
        browser_form.addRow(self.clear_browser_cb)
        layout.addWidget(browser_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save_and_close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save_and_close(self):
        target_url = self.target_url.text().strip()
        smtp_port = self.smtp_port.value()
        smtp_host = self.smtp_host.text().strip()

        if target_url and not target_url.startswith(("http://", "https://")):
            QMessageBox.warning(
                self, "Invalid URL", "Target URL must start with http:// or https://"
            )
            return
        if smtp_host and not self._validate_port_for_host(smtp_port):
            reply = QMessageBox.question(
                self,
                "Port/protocol mismatch?",
                "Port 465 is normally used with SSL and port 587/25 with STARTTLS.\n"
                "The current combination looks unusual. Save anyway?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self.cfg["target_url"] = target_url
        self.cfg["smtp_host"] = smtp_host
        self.cfg["smtp_port"] = smtp_port
        self.cfg["smtp_use_ssl"] = self.smtp_ssl.isChecked()
        self.cfg["smtp_user"] = self.smtp_user.text().strip()
        self.cfg["smtp_pass"] = self.smtp_pass.text().strip()
        self.cfg["default_to"] = self.default_to.text().strip()
        self.cfg["default_subject"] = self.default_subject.text().strip()
        self.cfg["default_body"] = self.default_body.toPlainText().strip()
        self.cfg["headless"] = self.headless_cb.isChecked()
        self.cfg["clear_browser"] = self.clear_browser_cb.isChecked()
        save_config(self.cfg)
        self.accept()

    def _validate_port_for_host(self, port: int) -> bool:
        """Return False when the port/encryption combination looks unusual."""
        use_ssl = self.smtp_ssl.isChecked()
        if port == 465 and not use_ssl:
            return False
        if port in (25, 587) and use_ssl:
            return False
        return True
