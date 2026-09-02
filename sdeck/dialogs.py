from __future__ import annotations

import secrets

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from .model import AppConfig
from .i18n import tr


class ApiSettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("YASDEC API"))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.enabled = QCheckBox(tr("Enable HTTP API"))
        self.enabled.setChecked(config.api_enabled)
        self.host = QComboBox()
        self.host.addItem(tr("This computer only (127.0.0.1)"), "127.0.0.1")
        self.host.addItem(tr("Local network (0.0.0.0)"), "0.0.0.0")
        self.host.setCurrentIndex(max(0, self.host.findData(config.api_host)))
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(config.api_port)
        token_row = QHBoxLayout()
        self.token = QLineEdit(config.api_token)
        self.token.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        regenerate = QPushButton(tr("Regenerate"))
        regenerate.clicked.connect(lambda: self.token.setText(secrets.token_urlsafe(24)))
        token_row.addWidget(self.token, 1)
        token_row.addWidget(regenerate)
        form.addRow(tr("Status"), self.enabled)
        form.addRow(tr("Listen on"), self.host)
        form.addRow(tr("Port"), self.port)
        form.addRow(tr("Token"), token_row)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Save"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply(self, config: AppConfig) -> None:
        config.api_enabled = self.enabled.isChecked()
        config.api_host = str(self.host.currentData())
        config.api_port = self.port.value()
        config.api_token = self.token.text().strip() or secrets.token_urlsafe(24)


class ObsSettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("OBS connection"))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.url = QLineEdit(config.obs_url)
        self.url.setPlaceholderText("ws://127.0.0.1:4455")
        self.password = QLineEdit(config.obs_password)
        self.password.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        form.addRow(tr("WebSocket URL"), self.url)
        form.addRow(tr("Password"), self.password)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Save and connect"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply(self, config: AppConfig) -> None:
        config.obs_url = self.url.text().strip() or "ws://127.0.0.1:4455"
        config.obs_password = self.password.text()
