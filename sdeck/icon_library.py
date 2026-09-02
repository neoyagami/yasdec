from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
    QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from .applications import DesktopApplication, discover_applications
from .i18n import tr


LUCIDE_LABELS = {
    "mic": "Microphone", "mic-off": "Muted microphone",
    "volume-2": "Volume", "volume-x": "Mute", "speaker": "Speaker",
    "headphones": "Headphones", "radio": "Broadcast", "antenna": "Antenna",
    "audio-waveform": "Audio waveform", "music": "Music", "video": "Video",
    "video-off": "Video off", "camera": "Camera", "eye": "Visible",
    "eye-off": "Hidden", "play": "Play", "pause": "Pause",
    "square": "Stop", "circle-play": "Start", "circle-stop": "Finish",
    "power": "Power", "terminal": "Terminal", "command": "Command",
    "shell": "Shell", "monitor": "Monitor", "layout-grid": "Grid",
    "panels-top-left": "Panels", "list-video": "Video list", "house": "Home",
    "settings": "Settings", "sliders-horizontal": "Controls",
    "arrow-left": "Left", "arrow-right": "Right",
    "arrow-up": "Up", "arrow-down": "Down",
}

UTF8_SUGGESTIONS = (
    "●", "○", "▶", "■", "⏸", "⏺", "⏹", "⏻", "⚡", "⏱", "✓", "✕",
    "★", "☆", "▲", "▼", "◀", "▶", "↩", "↪", "♫", "♪", "⌂", "∞",
)


def lucide_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "icons" / "lucide"


class ApplicationChoiceDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.application: DesktopApplication | None = None
        self.setWindowTitle(tr("Choose application"))
        self.resize(600, 560)
        layout = QVBoxLayout(self)
        search = QLineEdit()
        search.setPlaceholderText(tr("Search applications…"))
        self.list = QListWidget()
        self.list.setIconSize(QSize(40, 40))
        for application in discover_applications():
            item = QListWidgetItem(application.icon(), application.name)
            item.setToolTip(application.comment or application.desktop_file)
            item.setData(Qt.ItemDataRole.UserRole, application)
            self.list.addItem(item)
        search.textChanged.connect(self._filter)
        self.list.itemDoubleClicked.connect(lambda _item: self._accept_selected())
        layout.addWidget(search)
        layout.addWidget(self.list, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Open)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        buttons.button(QDialogButtonBox.StandardButton.Open).setText(tr("Use application"))
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _filter(self, text: str) -> None:
        query = text.casefold().strip()
        for row in range(self.list.count()):
            item = self.list.item(row)
            application = item.data(Qt.ItemDataRole.UserRole)
            terms = f"{application.name} {application.comment} {application.desktop_id}".casefold()
            item.setHidden(query not in terms)

    def _accept_selected(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self.application = item.data(Qt.ItemDataRole.UserRole)
            self.accept()


class IconChoiceDialog(QDialog):
    def __init__(self, current_path: str = "", current_glyph: str = "", parent=None) -> None:
        super().__init__(parent)
        self.choice_path = current_path
        self.choice_glyph = current_glyph
        self.setWindowTitle(tr("Choose icon"))
        self.resize(560, 470)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._library_tab(), tr("Library"))
        tabs.addTab(self._glyph_tab(current_glyph), tr("UTF-8 symbol"))
        tabs.addTab(self._file_tab(), tr("File"))
        layout.addWidget(tabs)
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(cancel)
        layout.addLayout(row)

    def _library_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        search = QLineEdit()
        search.setPlaceholderText(tr("Search icons…"))
        page_layout.addWidget(search)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content.setStyleSheet("background: #111519;")
        grid = QGridLayout(content)
        grid.setSpacing(8)
        buttons: list[tuple[QToolButton, str]] = []
        position = 0
        for name, source_label in LUCIDE_LABELS.items():
            label = tr(source_label)
            path = lucide_dir() / f"{name}.svg"
            if not path.exists():
                continue
            button = QToolButton()
            button.setIcon(QIcon(str(path)))
            button.setIconSize(QSize(32, 32))
            button.setFixedSize(52, 52)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.clicked.connect(lambda _checked=False, p=str(path): self._choose_path(p))
            grid.addWidget(button, position // 8, position % 8)
            buttons.append((button, f"{name} {label}".casefold()))
            position += 1
        grid.setRowStretch(grid.rowCount(), 1)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)

        def filter_icons(text: str) -> None:
            query = text.casefold()
            for button, terms in buttons:
                button.setVisible(query in terms)

        search.textChanged.connect(filter_icons)
        return page

    def _glyph_tab(self, current: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(tr("Type any symbol or choose one from the palette.")))
        self.glyph_input = QLineEdit(current)
        self.glyph_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont(self.glyph_input.font())
        font.setPointSize(28)
        self.glyph_input.setFont(font)
        self.glyph_input.setMaxLength(8)
        self.glyph_input.returnPressed.connect(self._choose_typed_glyph)
        layout.addWidget(self.glyph_input)
        grid = QGridLayout()
        for index, glyph in enumerate(UTF8_SUGGESTIONS):
            button = QToolButton()
            button.setText(glyph)
            button.setFixedSize(48, 48)
            button.setToolTip(tr("Use {glyph}", glyph=glyph))
            button.clicked.connect(lambda _checked=False, value=glyph: self._choose_glyph(value))
            grid.addWidget(button, index // 8, index % 8)
        layout.addLayout(grid)
        use = QPushButton(tr("Use symbol"))
        use.clicked.connect(self._choose_typed_glyph)
        layout.addWidget(use)
        layout.addStretch()
        return page

    def _file_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addStretch()
        choose = QPushButton(tr("Select PNG, JPG, WebP, or SVG…"))
        choose.clicked.connect(self._choose_file)
        layout.addWidget(choose)
        layout.addStretch()
        return page

    def _choose_path(self, path: str) -> None:
        self.choice_path, self.choice_glyph = path, ""
        self.accept()

    def _choose_glyph(self, glyph: str) -> None:
        self.choice_path, self.choice_glyph = "", glyph
        self.accept()

    def _choose_typed_glyph(self) -> None:
        glyph = self.glyph_input.text().strip()
        if glyph:
            self._choose_glyph(glyph)

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Select icon"), "", f"{tr('Images')} (*.png *.jpg *.jpeg *.webp *.svg)")
        if path:
            self._choose_path(path)
