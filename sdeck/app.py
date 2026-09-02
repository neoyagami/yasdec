from __future__ import annotations

import os
import signal
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QTimer
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .window import MainWindow
from .i18n import set_language, tr
from .model import AppConfig


STYLESHEET = """
QWidget { color: #e8edf0; font-family: Inter, "Noto Sans", sans-serif; font-size: 13px; }
QMainWindow, QSplitter, QStackedWidget { background: #111519; }
QDialog { background: #111519; }
QTabWidget::pane { background: #111519; border: 1px solid #3a454f; }
QTabBar::tab { background: #20272e; color: #aeb8c0; padding: 8px 14px; border: 1px solid #3a454f; }
QTabBar::tab:selected { background: #236d61; color: white; }
#header { background: #191f25; border-bottom: 1px solid #303943; }
#brand { font-size: 21px; font-weight: 800; color: #f5f7f8; }
#subtitle, #hint, .hint { color: #87939e; }
#deviceStatus { color: #e1a94c; padding-right: 10px; }
#deviceStatus[connected="true"] { color: #55d6b7; }
#obsStatus { color: #e1a94c; padding: 0 6px; }
#obsStatus[connected="true"] { color: #55d6b7; }
#spacesPanel { background: #151a1f; border-right: 1px solid #303943; }
#inspectorScroll, #inspectorScroll > QWidget > QWidget { background: #111519; }
#sectionTitle, #panelTitle { font-size: 16px; font-weight: 700; }
#deckTitle { font-size: 23px; font-weight: 750; }
#deckFrame { background: #242b32; border: 1px solid #3b4650; border-radius: 8px; }
#iconPreview { background: #20272e; border: 1px solid #3b4650; border-radius: 5px; color: #87939e; font-size: 20px; }
QLineEdit, QPlainTextEdit, QComboBox { background: #1b2127; border: 1px solid #3a454f; border-radius: 5px; padding: 7px 9px; selection-background-color: #147b68; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #42d3b3; }
QPushButton { background: #2a333c; border: 1px solid #43505b; border-radius: 5px; padding: 8px 13px; font-weight: 600; }
QPushButton:hover { background: #34404a; border-color: #647482; }
QPushButton:pressed { background: #147b68; }
QToolButton { background: #262e35; border: 1px solid #3d4852; border-radius: 4px; min-width: 26px; min-height: 26px; font-size: 18px; }
QToolButton:hover { background: #35414a; }
QListWidget { background: transparent; border: 0; outline: 0; }
QListWidget::item { padding: 10px 9px; border-radius: 5px; }
QListWidget::item:selected { background: #236d61; color: white; }
QListWidget::item:hover:!selected { background: #20272d; }
QCheckBox { spacing: 9px; padding: 3px 0; }
QCheckBox::indicator { width: 17px; height: 17px; }
QCheckBox::indicator:unchecked { background: #1b2127; border: 1px solid #53606b; border-radius: 3px; }
QCheckBox::indicator:checked { background: #42d3b3; border: 1px solid #42d3b3; border-radius: 3px; }
QFormLayout QLabel { color: #aeb8c0; }
QStatusBar { background: #191f25; color: #9eabb5; border-top: 1px solid #303943; }
QMenu { background: #20262c; border: 1px solid #414b54; padding: 5px; }
QMenu::item { padding: 7px 24px; border-radius: 4px; }
QMenu::item:selected { background: #236d61; }
QSplitter::handle { background: #303943; width: 1px; }
"""


def data_dir() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation)
    target = Path(root or Path.home() / ".config") / "SDeck"
    legacy = Path(root or Path.home() / ".config") / "Backloop" / "SDeck"
    if not target.exists() and legacy.is_dir():
        try:
            shutil.copytree(legacy, target)
        except OSError:
            pass
    return target


def resource_path(name: str) -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / name


def main() -> int:
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.services=false")
    app = QApplication(sys.argv)
    app.setApplicationName("YASDEC")
    app.setApplicationDisplayName("YASDEC — Yet Another Stream Deck Controller")
    app.setOrganizationName("YASDEC")
    config_path = data_dir() / "config.json"
    set_language(AppConfig.load(config_path).language)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    icon = QIcon(str(resource_path("sdeck.svg")))
    app.setWindowIcon(icon)
    window = MainWindow(config_path, icon)
    window.show()
    signal.signal(signal.SIGINT, lambda *_args: window.quit_app())
    signal_timer = QTimer()
    signal_timer.setInterval(250)
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start()
    if not QSystemTrayIcon.isSystemTrayAvailable():
        window.statusBar().showMessage(tr("The desktop does not provide a system tray; closing the window will end the visual session."))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
