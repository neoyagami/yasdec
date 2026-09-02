from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .actions import elapsed_text
from .applications import cache_application_icon, read_desktop_application
from .icon_library import ApplicationChoiceDialog, IconChoiceDialog, lucide_dir
from .i18n import tr
from .keyboard import MODIFIER_KEYS, shortcut_from_qt
from .model import ACTION_APPLICATION, ACTION_AUDIO, ACTION_KEYBOARD, ACTION_MEDIA, ACTION_MULTI, ACTION_NONE, ACTION_OBS, ACTION_SHELL, ACTION_SPACE, ACTION_SPECTRUM, ACTION_VU, ACTION_WEBSOCKET, KeyConfig, MultiActionStep, Space, default_action_icon


class ShortcutCaptureDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.shortcut = ""
        self.setWindowTitle(tr("Record keyboard shortcut"))
        self.setModal(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        self.prompt = QLabel(tr("Press the complete key combination now…"))
        self.prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prompt.setMinimumSize(360, 70)
        self.prompt.setWordWrap(True)
        layout.addWidget(self.prompt)
        hint = QLabel(tr("Modifiers such as Ctrl, Alt, Shift, and Super are detected. F1–F24 can also be entered manually."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        cancel = QPushButton(tr("Cancel"))
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel, 0, Qt.AlignmentFlag.AlignRight)

    def showEvent(self, event: object) -> None:
        super().showEvent(event)
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            return
        if event.key() in MODIFIER_KEYS:
            names: list[str] = []
            modifiers = event.modifiers()
            for flag, name in (
                (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
                (Qt.KeyboardModifier.AltModifier, "Alt"),
                (Qt.KeyboardModifier.ShiftModifier, "Shift"),
                (Qt.KeyboardModifier.MetaModifier, "Super"),
            ):
                if modifiers & flag:
                    names.append(name)
            self.prompt.setText("+".join(names) + ("+…" if names else tr("Press another key…")))
            event.accept()
            return
        shortcut = shortcut_from_qt(event.key(), event.modifiers())
        if shortcut:
            self.shortcut = shortcut
            event.accept()
            self.accept()
            return
        super().keyPressEvent(event)


class KeyButton(QAbstractButton):
    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self.key = KeyConfig()
        self.spectrum_level: float | None = None
        self.spectrum_cells: list[float] | None = None
        self.spectrum_cell_colors: list[QColor] = []
        self.spectrum_grid_size = 1
        self.mini_spectrum: list[float] | None = None
        self.vu_cells: list[float] | None = None
        self.vu_cell_colors: list[QColor] = []
        self.mini_vu: tuple[float, float] | None = None
        self.spectrum_color = QColor("#42d3b3")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(112, 112)
        self.setAccessibleName(tr("Key {number}", number=index + 1))

    def set_key(self, key: KeyConfig) -> None:
        self.key = key
        self.setToolTip(key.label or tr("Key {number}", number=self.index + 1))
        self.update()

    def set_spectrum_level(self, level: float | None, color: str = "#42d3b3") -> None:
        self.spectrum_level = level
        self.spectrum_color = QColor(color)
        self.spectrum_cells = None if level is None else [level]
        self.spectrum_cell_colors = [QColor(color)] if level is not None else []
        self.spectrum_grid_size = 1
        self.update()

    def set_spectrum_cells(self, levels: list[float] | None, colors: list[str] | None = None, grid_size: int = 1) -> None:
        self.spectrum_level = None
        self.spectrum_cells = list(levels) if levels is not None else None
        self.spectrum_cell_colors = [QColor(color) for color in (colors or [])]
        self.spectrum_grid_size = max(1, min(3, grid_size))
        self.update()

    def set_mini_spectrum(self, levels: list[float] | None) -> None:
        self.mini_spectrum = list(levels) if levels is not None else None
        self.update()

    def set_vu_cells(self, levels: list[float] | None, colors: list[str] | None = None) -> None:
        self.vu_cells = list(levels) if levels is not None else None
        self.vu_cell_colors = [QColor(color) for color in (colors or [])]
        self.update()

    def set_mini_vu(self, levels: tuple[float, float] | None) -> None:
        self.mini_vu = tuple(levels) if levels is not None else None
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        fill = valid_color(self.key.active_background_color if self.key.active else self.key.background_color, "#171b20")
        if self.isChecked():
            painter.setPen(QColor("#42d3b3"))
        else:
            painter.setPen(QColor("#39424c"))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 7, 7)

        if self.vu_cells is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#030606"))
            painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 5, 5)
            count = max(1, len(self.vu_cells))
            margin, gap = 8, 4
            width = (self.width() - margin * 2 - gap * (count - 1)) / count
            for index in range(count):
                x = round(margin + index * (width + gap))
                active = self.vu_cells[index] >= 0.5
                color = self.vu_cell_colors[index] if index < len(self.vu_cell_colors) else QColor("#18f2a4")
                painter.setBrush(color if active else QColor("#101716"))
                painter.drawRoundedRect(x, margin, max(2, round(width)), self.height() - margin * 2, 3, 3)
            return

        if self.spectrum_cells is not None:
            painter.setPen(Qt.PenStyle.NoPen)
            if self.spectrum_grid_size == 1:
                level = max(0.0, min(1.0, self.spectrum_cells[0] if self.spectrum_cells else 0.0))
                bar_height = int((self.height() - 14) * level)
                painter.setBrush(self.spectrum_cell_colors[0] if self.spectrum_cell_colors else self.spectrum_color)
                painter.drawRoundedRect(10, self.height() - 8 - bar_height, self.width() - 20, bar_height, 4, 4)
                return
            grid = self.spectrum_grid_size
            margin, gap = 9, 4
            cell_width = (self.width() - margin * 2 - gap * (grid - 1)) / grid
            cell_height = (self.height() - margin * 2 - gap * (grid - 1)) / grid
            for cell in range(grid * grid):
                row, column = divmod(cell, grid)
                level = self.spectrum_cells[cell] if cell < len(self.spectrum_cells) else 0.0
                color = self.spectrum_cell_colors[cell] if cell < len(self.spectrum_cell_colors) else self.spectrum_color
                painter.setBrush(color if level >= 0.5 else QColor("#18211f"))
                painter.drawRoundedRect(
                    round(margin + column * (cell_width + gap)),
                    round(margin + row * (cell_height + gap)),
                    max(2, round(cell_width)),
                    max(2, round(cell_height)),
                    3,
                    3,
                )
            return

        icon_path = self.key.active_icon if self.key.active and self.key.active_icon else self.key.icon
        glyph = self.key.active_glyph if self.key.active and self.key.active_glyph else self.key.glyph
        if not icon_path and not glyph:
            icon_path = default_action_icon(self.key)
        compact = self.width() < 90
        icon_side = int(min(self.width(), self.height()) * (0.48 if compact else 0.53))
        if self.mini_vu is not None:
            count = 8
            left, right = 8, self.width() - 8
            top = 9
            bottom = self.height() - (31 if self.key.label else 9)
            lane_gap = 5
            lane_height = max(3, (bottom - top - lane_gap) // 2)
            gap = 2
            width = max(2, (right - left - gap * (count - 1)) // count)
            start = valid_color(self.key.vu_color_start, "#18f2a4")
            end = valid_color(self.key.vu_color_end, "#ff3b81")
            painter.setPen(Qt.PenStyle.NoPen)
            for channel, level in enumerate(self.mini_vu):
                active = round(max(0.0, min(1.0, level)) * count)
                y = top + channel * (lane_height + lane_gap)
                for index in range(count):
                    ratio = index / max(1, count - 1)
                    color = QColor(
                        round(start.red() + (end.red() - start.red()) * ratio),
                        round(start.green() + (end.green() - start.green()) * ratio),
                        round(start.blue() + (end.blue() - start.blue()) * ratio),
                    )
                    painter.setBrush(color if index < active else QColor("#101716"))
                    x = left + index * (width + gap)
                    painter.drawRoundedRect(x, y, width, lane_height, 2, 2)
        elif self.mini_spectrum is not None:
            levels = self.mini_spectrum
            count = max(1, len(levels))
            left, right = 9, self.width() - 9
            bottom = self.height() - (31 if self.key.label else 10)
            top = 10
            gap = 2
            width = max(2, (right - left - gap * (count - 1)) // count)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(valid_color(self.key.icon_color, "#42d3b3"))
            for index, level in enumerate(levels):
                height = max(2, round((bottom - top) * max(0.0, min(1.0, level))))
                x = left + index * (width + gap)
                painter.drawRoundedRect(x, bottom - height, width, height, 2, 2)
        elif icon_path and Path(icon_path).is_file():
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(icon_side, icon_side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                if Path(icon_path).suffix.casefold() == ".svg":
                    pixmap = tint_pixmap(pixmap, valid_color(self.key.icon_color, "#ffffff"))
                painter.drawPixmap((self.width() - pixmap.width()) // 2, 9, pixmap)
        elif glyph:
            painter.setPen(valid_color(self.key.icon_color, "#ffffff"))
            font = painter.font()
            font.setFamilies(["Noto Sans Symbols 2", "Noto Sans Symbols", "Noto Color Emoji", "sans-serif"])
            font.setPointSize(23 if compact else 31)
            font.setBold(False)
            painter.setFont(font)
            reserve = 18 if self.key.label else 0
            painter.drawText(rect.adjusted(5, 3, -5, -reserve), Qt.AlignmentFlag.AlignCenter, glyph)
        else:
            painter.setPen(valid_color(self.key.icon_color, "#647180"))
            font = painter.font()
            font.setPointSize(15 if compact else 18)
            font.setBold(True)
            painter.setFont(font)
            reserve = 18 if self.key.label else 0
            painter.drawText(rect.adjusted(0, 2, 0, -reserve), Qt.AlignmentFlag.AlignCenter, str(self.index + 1))

        timer = elapsed_text(self.key) if self.key.show_timer else ""
        label = self.key.label or ("" if compact else tr("Unassigned"))
        if label:
            painter.setPen(valid_color(self.key.text_color, "#ffffff"))
            font = painter.font()
            font.setPointSize(7 if compact else 9)
            font.setBold(True)
            painter.setFont(font)
            text = painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, self.width() - 14)
            bottom = 15 if timer else 4
            painter.drawText(7, self.height() - bottom - 15, self.width() - 14, 15, Qt.AlignmentFlag.AlignCenter, text)
        if timer:
            painter.setPen(valid_color(self.key.text_color, "#ffffff"))
            font = painter.font()
            font.setPointSize(8)
            font.setBold(False)
            painter.setFont(font)
            painter.drawText(rect.adjusted(0, 0, 0, -5), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, timer)


def valid_color(value: str, fallback: str) -> QColor:
    color = QColor(value)
    return color if color.isValid() else QColor(fallback)


def tint_pixmap(source: QPixmap, color: QColor) -> QPixmap:
    result = QPixmap(source.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), color)
    painter.end()
    return result


class ColorPicker(QToolButton):
    changed = Signal(str)

    def __init__(self, label: str, default: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = label
        self.default = default
        self.color = default
        self.setToolTip(tr("Choose {label} color", label=tr(label).casefold()))
        self.setFixedSize(32, 32)
        self.clicked.connect(self.choose)
        self.set_color(default)

    def choose(self) -> None:
        selected = QColorDialog.getColor(valid_color(self.color, self.default), self, tr("{label} color", label=tr(self.label).casefold()))
        if selected.isValid():
            self.set_color(selected.name(), emit=True)

    def set_color(self, color: str, emit: bool = False) -> None:
        self.color = valid_color(color, self.default).name()
        self.setStyleSheet(
            "QToolButton {"
            f"background: {self.color}; border: 2px solid #65727d; border-radius: 4px;"
            "min-width: 28px; min-height: 28px; padding: 0;"
            "} QToolButton:hover { border-color: #ffffff; }"
        )
        self.setAccessibleName(f"{tr(self.label)}: {self.color}")
        if emit:
            self.changed.emit(self.color)


class IconPicker(QWidget):
    changed = Signal(str, str)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = ""
        self.glyph = ""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.preview = QLabel()
        self.preview.setFixedSize(40, 40)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setObjectName("iconPreview")
        self.button = QPushButton(title)
        self.button.clicked.connect(self.choose)
        self.clear_button = QToolButton()
        self.clear_button.setText("×")
        self.clear_button.setToolTip(tr("Remove icon"))
        self.clear_button.clicked.connect(lambda: self.set_value("", "", emit=True))
        layout.addWidget(self.preview)
        layout.addWidget(self.button, 1)
        layout.addWidget(self.clear_button)

    def choose(self) -> None:
        dialog = IconChoiceDialog(self.path, self.glyph, self)
        if dialog.exec():
            self.set_value(dialog.choice_path, dialog.choice_glyph, emit=True)

    def set_path(self, path: str, emit: bool = False) -> None:
        self.set_value(path, "", emit)

    def set_value(self, path: str, glyph: str, emit: bool = False) -> None:
        self.path = path
        self.glyph = glyph
        pixmap = QPixmap(path) if path else QPixmap()
        self.preview.setPixmap(pixmap.scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.preview.setText(glyph or ("+" if pixmap.isNull() else ""))
        if emit:
            self.changed.emit(path, glyph)


class KeyInspector(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None = None, action_only: bool = False) -> None:
        super().__init__(parent)
        self.action_only = action_only
        self.key: KeyConfig | None = None
        self.spaces: list[Space] = []
        self.obs_catalog: dict = {"scenes": [], "sources": {}, "groups": {}, "inputs": []}
        self.spectrum_default_fps = 8
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        title = QLabel(tr("Configure action") if action_only else tr("Configure key"))
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setVerticalSpacing(14)
        self.label = QLineEdit(self)
        self.label.setPlaceholderText(tr("E.g. Start stream"))
        self.icon = IconPicker(tr("Choose icon"), self)
        self.active_icon = IconPicker(tr("Active icon"), self)
        self.background_color = ColorPicker("background", "#171b20", self)
        self.active_background_color = ColorPicker("toggle theme", "#167d67", self)
        self.text_color = ColorPicker("Text", "#ffffff", self)
        self.icon_color = ColorPicker("Icon", "#ffffff", self)
        color_panel = QWidget()
        color_layout = QHBoxLayout(color_panel)
        color_layout.setContentsMargins(0, 0, 0, 0)
        color_layout.setSpacing(8)
        if not action_only:
            color_layout.addWidget(self.background_color)
            color_layout.addWidget(self.active_background_color)
            color_layout.addWidget(self.text_color)
            color_layout.addWidget(self.icon_color)
            color_layout.addStretch()
        self.action = QComboBox()
        self.action.addItem(tr("No action"), ACTION_NONE)
        self.action.addItem(tr("Shell command"), ACTION_SHELL)
        self.action.addItem(tr("WebSocket message"), ACTION_WEBSOCKET)
        self.action.addItem(tr("PipeWire / PulseAudio audio"), ACTION_AUDIO)
        self.action.addItem("OBS WebSocket", ACTION_OBS)
        self.action.addItem(tr("Spectrum analyzer"), ACTION_SPECTRUM)
        self.action.addItem(tr("Stereo VU meter"), ACTION_VU)
        self.action.addItem(tr("Switch space"), ACTION_SPACE)
        self.action.addItem(tr("Open application"), ACTION_APPLICATION)
        self.action.addItem(tr("Keyboard shortcut"), ACTION_KEYBOARD)
        self.action.addItem(tr("Media control"), ACTION_MEDIA)
        if not action_only:
            self.action.addItem(tr("Multi action"), ACTION_MULTI)
            form.addRow(tr("Name"), self.label)
            form.addRow(tr("Icon"), self.icon)
            form.addRow(tr("Colors"), color_panel)
        form.addRow(tr("Action"), self.action)
        layout.addLayout(form)

        self.action_stack = QStackedWidget()
        self.action_stack.addWidget(QWidget())
        self.action_stack.addWidget(self._shell_page())
        self.action_stack.addWidget(self._websocket_page())
        self.action_stack.addWidget(self._audio_page())
        self.action_stack.addWidget(self._obs_page())
        self.action_stack.addWidget(self._spectrum_page())
        self.action_stack.addWidget(self._vu_page())
        self.action_stack.addWidget(self._space_page())
        self.action_stack.addWidget(self._application_page())
        self.action_stack.addWidget(self._keyboard_page())
        self.action_stack.addWidget(self._media_page())
        self.action_stack.addWidget(self._multi_page() if not action_only else QWidget())
        layout.addWidget(self.action_stack)

        self.toggle_box = QWidget()
        toggle_layout = QVBoxLayout(self.toggle_box)
        toggle_layout.setContentsMargins(0, 12, 0, 0)
        self.toggle = QCheckBox(tr("Keep active state"))
        self.timer = QCheckBox(tr("Show elapsed time"))
        toggle_layout.addWidget(self.toggle)
        toggle_layout.addWidget(self.timer)
        toggle_layout.addWidget(self.active_icon)
        layout.addWidget(self.toggle_box)
        layout.addStretch()

        self.label.textEdited.connect(self._store)
        self.icon.changed.connect(self._store)
        self.active_icon.changed.connect(self._store)
        self.background_color.changed.connect(self._store)
        self.active_background_color.changed.connect(self._store)
        self.text_color.changed.connect(self._store)
        self.icon_color.changed.connect(self._store)
        self.action.currentIndexChanged.connect(self._action_changed)
        self.command.textChanged.connect(self._store)
        self.command_off.textChanged.connect(self._store)
        self.ws_url.textEdited.connect(self._store)
        self.payload_on.textChanged.connect(self._store)
        self.payload_off.textChanged.connect(self._store)
        self.audio_kind.currentIndexChanged.connect(self._audio_kind_changed)
        self.audio_target.currentIndexChanged.connect(self._store)
        self.obs_operation.currentIndexChanged.connect(self._obs_operation_changed)
        self.obs_scene.currentTextChanged.connect(self._obs_scene_changed)
        self.obs_group.currentTextChanged.connect(self._obs_group_changed)
        self.obs_target.currentTextChanged.connect(self._store)
        self.spectrum_operation.currentIndexChanged.connect(self._spectrum_operation_changed)
        self.spectrum_kind.currentIndexChanged.connect(self._spectrum_kind_changed)
        self.spectrum_target.currentIndexChanged.connect(self._store)
        self.spectrum_fps.valueChanged.connect(self._store)
        self.spectrum_grid.currentIndexChanged.connect(self._store)
        self.spectrum_preview.toggled.connect(self._store)
        self.vu_operation.currentIndexChanged.connect(self._vu_operation_changed)
        self.vu_kind.currentIndexChanged.connect(self._vu_kind_changed)
        self.vu_target.currentIndexChanged.connect(self._store)
        self.vu_fps.valueChanged.connect(self._store)
        self.vu_preview.toggled.connect(self._store)
        self.vu_color_start.changed.connect(self._store)
        self.vu_color_end.changed.connect(self._store)
        self.target.currentIndexChanged.connect(self._store)
        self.keyboard_shortcut.textEdited.connect(self._store)
        self.media_control.currentIndexChanged.connect(self._store)
        self.toggle.toggled.connect(self._toggle_changed)
        self.timer.toggled.connect(self._store)
        self.setEnabled(False)

    def _shell_page(self) -> QWidget:
        page = QWidget()
        self.shell_form = QFormLayout(page)
        self.shell_form.setContentsMargins(0, 12, 0, 0)
        self.command = QLineEdit()
        self.command.setPlaceholderText("systemctl --user start ...")
        self.command_off = QLineEdit()
        self.command_off.setPlaceholderText("systemctl --user stop ...")
        self.shell_form.addRow(tr("When enabled"), self.command)
        self.shell_form.addRow(tr("When disabled"), self.command_off)
        return page

    def _websocket_page(self) -> QWidget:
        page = QWidget()
        self.websocket_form = QFormLayout(page)
        self.websocket_form.setContentsMargins(0, 12, 0, 0)
        self.ws_url = QLineEdit()
        self.ws_url.setPlaceholderText("ws://127.0.0.1:4455")
        self.payload_on = QPlainTextEdit()
        self.payload_on.setPlaceholderText('{"action": "start"}')
        self.payload_on.setFixedHeight(78)
        self.payload_off = QPlainTextEdit()
        self.payload_off.setPlaceholderText('{"action": "stop"}')
        self.payload_off.setFixedHeight(78)
        self.websocket_form.addRow("URL", self.ws_url)
        self.websocket_form.addRow(tr("When pressed"), self.payload_on)
        self.websocket_form.addRow(tr("When disabled"), self.payload_off)
        return page

    def _audio_page(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        self.audio_kind = QComboBox()
        self.audio_kind.addItem(tr("Applications · playback"), "sink-input")
        self.audio_kind.addItem(tr("Applications · recording"), "source-output")
        self.audio_kind.addItem(tr("Outputs"), "sink")
        self.audio_kind.addItem(tr("Inputs"), "source")
        self.audio_target = QComboBox()
        self.audio_target.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        layout.addRow(tr("Type"), self.audio_kind)
        layout.addRow(tr("Channel"), self.audio_target)
        return page

    def _obs_page(self) -> QWidget:
        page = QWidget()
        self.obs_form = QFormLayout(page)
        self.obs_form.setContentsMargins(0, 12, 0, 0)
        self.obs_operation = QComboBox()
        self.obs_operation.addItem(tr("Switch scene"), "scene")
        self.obs_operation.addItem(tr("Show / hide source"), "source")
        self.obs_operation.addItem(tr("Mute / unmute input"), "input_mute")
        self.obs_operation.addItem(tr("Start stream"), "stream_start")
        self.obs_operation.addItem(tr("Stop stream"), "stream_stop")
        self.obs_scene = QComboBox()
        self.obs_scene.setEditable(True)
        self.obs_scene.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.obs_group = QComboBox()
        self.obs_group.setEditable(True)
        self.obs_group.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.obs_target = QComboBox()
        self.obs_target.setEditable(True)
        self.obs_target.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.obs_form.addRow(tr("Operation"), self.obs_operation)
        self.obs_form.addRow(tr("Scene"), self.obs_scene)
        self.obs_form.addRow(tr("Group (optional)"), self.obs_group)
        self.obs_form.addRow(tr("Target"), self.obs_target)
        return page

    def _spectrum_page(self) -> QWidget:
        page = QWidget()
        self.spectrum_form = QFormLayout(page)
        self.spectrum_form.setContentsMargins(0, 12, 0, 0)
        self.spectrum_operation = QComboBox()
        self.spectrum_operation.addItem(tr("Full-screen toggle (on / off)"), "start")
        self.spectrum_operation.addItem(tr("Stop only"), "stop")
        self.spectrum_mode_hint = QLabel()
        self.spectrum_mode_hint.setWordWrap(True)
        self.spectrum_kind = QComboBox()
        self.spectrum_kind.addItem(tr("Output (monitor)"), "sink")
        self.spectrum_kind.addItem(tr("Input"), "source")
        self.spectrum_target = QComboBox()
        self.spectrum_fps = QSpinBox()
        self.spectrum_fps.setRange(1, 20)
        self.spectrum_fps.setSuffix(" FPS")
        self.spectrum_grid = QComboBox()
        self.spectrum_grid.addItem(tr("Solid block"), 1)
        self.spectrum_grid.addItem(tr("LCD cells · 2 × 2"), 2)
        self.spectrum_grid.addItem(tr("LCD cells · 3 × 3"), 3)
        self.spectrum_preview = QCheckBox(tr("Preview on this key"))
        self.spectrum_preview.setToolTip(tr("Keeps capture active and displays a mini spectrum while full screen is off"))
        self.spectrum_form.addRow(tr("Operation"), self.spectrum_operation)
        self.spectrum_form.addRow(self.spectrum_mode_hint)
        self.spectrum_form.addRow(tr("Type"), self.spectrum_kind)
        self.spectrum_form.addRow(tr("Channel"), self.spectrum_target)
        self.spectrum_form.addRow(tr("Speed"), self.spectrum_fps)
        self.spectrum_form.addRow(tr("Block style"), self.spectrum_grid)
        self.spectrum_form.addRow(tr("Inactive view"), self.spectrum_preview)
        return page

    def _vu_page(self) -> QWidget:
        page = QWidget()
        self.vu_form = QFormLayout(page)
        self.vu_form.setContentsMargins(0, 12, 0, 0)
        self.vu_operation = QComboBox()
        self.vu_operation.addItem(tr("Full-screen toggle (on / off)"), "start")
        self.vu_operation.addItem(tr("Stop only"), "stop")
        self.vu_mode_hint = QLabel()
        self.vu_mode_hint.setWordWrap(True)
        self.vu_kind = QComboBox()
        self.vu_kind.addItem(tr("Output (monitor)"), "sink")
        self.vu_kind.addItem(tr("Input"), "source")
        self.vu_target = QComboBox()
        self.vu_fps = QSpinBox()
        self.vu_fps.setRange(1, 20)
        self.vu_fps.setValue(12)
        self.vu_fps.setSuffix(" FPS")
        self.vu_preview = QCheckBox(tr("Preview on this key"))
        self.vu_preview.setToolTip(tr("Keeps stereo capture active and displays a mini VU meter while full screen is off"))
        colors = QWidget()
        color_layout = QHBoxLayout(colors)
        color_layout.setContentsMargins(0, 0, 0, 0)
        self.vu_color_start = ColorPicker("Start", "#18f2a4")
        self.vu_color_end = ColorPicker("Finish", "#ff3b81")
        color_layout.addWidget(self.vu_color_start)
        color_layout.addWidget(QLabel("→"))
        color_layout.addWidget(self.vu_color_end)
        color_layout.addStretch()
        self.vu_form.addRow(tr("Operation"), self.vu_operation)
        self.vu_form.addRow(self.vu_mode_hint)
        self.vu_form.addRow(tr("Type"), self.vu_kind)
        self.vu_form.addRow(tr("Channel"), self.vu_target)
        self.vu_form.addRow(tr("Speed"), self.vu_fps)
        self.vu_form.addRow(tr("Neon gradient"), colors)
        self.vu_form.addRow(tr("Inactive view"), self.vu_preview)
        return page

    def _space_page(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        self.target = QComboBox()
        layout.addRow(tr("Go to"), self.target)
        return page

    def _application_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        self.application_name = QLabel(tr("No application selected"))
        self.application_name.setWordWrap(True)
        choose = QPushButton(tr("Choose application…"))
        choose.clicked.connect(self._choose_application)
        layout.addWidget(self.application_name)
        layout.addWidget(choose)
        return page

    def _keyboard_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 12, 0, 0)
        self.keyboard_shortcut = QLineEdit()
        self.keyboard_shortcut.setPlaceholderText("CTRL+SHIFT+F22")
        self.keyboard_shortcut.setToolTip(tr("Type manually or record a shortcut. Use + between key names; F1–F24 are supported."))
        shortcut_row = QWidget()
        shortcut_layout = QHBoxLayout(shortcut_row)
        shortcut_layout.setContentsMargins(0, 0, 0, 0)
        shortcut_layout.addWidget(self.keyboard_shortcut, 1)
        record = QPushButton(tr("Record…"))
        record.setToolTip(tr("Listen for the next complete key combination"))
        record.clicked.connect(self._capture_keyboard_shortcut)
        shortcut_layout.addWidget(record)
        form.addRow(tr("Shortcut"), shortcut_row)
        manual_hint = QLabel(tr("You can also type combinations such as CTRL+ALT+F22 manually."))
        manual_hint.setWordWrap(True)
        form.addRow("", manual_hint)
        return page

    def _capture_keyboard_shortcut(self) -> None:
        dialog = ShortcutCaptureDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.shortcut:
            self.keyboard_shortcut.setText(dialog.shortcut)
            self._store()

    def _media_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 12, 0, 0)
        self.media_control = QComboBox()
        choices = (
            ("circle-play.svg", tr("Play / pause"), "PLAYPAUSE"),
            ("arrow-left.svg", tr("Previous track"), "PREVIOUS"),
            ("arrow-right.svg", tr("Next track"), "NEXT"),
            ("square.svg", tr("Stop playback"), "STOP"),
            ("volume-x.svg", tr("Mute / unmute"), "MUTE"),
            ("volume-1.svg", tr("Volume down"), "VOLUMEDOWN"),
            ("volume-2.svg", tr("Volume up"), "VOLUMEUP"),
        )
        for icon_name, label, key_name in choices:
            self.media_control.addItem(QIcon(str(lucide_dir() / icon_name)), label, key_name)
        self.media_control.setIconSize(QSize(24, 24))
        form.addRow(tr("Control"), self.media_control)
        hint = QLabel(tr("Sends a global Linux media key through uinput."))
        hint.setWordWrap(True)
        form.addRow("", hint)
        return page

    def _multi_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        hint = QLabel(tr("In runs when enabling; Out runs when disabling. Steps execute from top to bottom."))
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        layout.addWidget(hint)
        tabs = QTabWidget()
        self.multi_lists: dict[str, QListWidget] = {}
        for direction, title in (("in", tr("In · enable")), ("out", tr("Out · disable"))):
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            sequence = QListWidget()
            sequence.itemDoubleClicked.connect(lambda _item, d=direction: self._multi_edit(d))
            self.multi_lists[direction] = sequence
            tab_layout.addWidget(sequence)
            add_row = QHBoxLayout()
            edit_row = QHBoxLayout()
            for text, callback, row in (
                (tr("+ Action"), lambda _checked=False, d=direction: self._multi_add_action(d), add_row),
                (tr("+ Pause"), lambda _checked=False, d=direction: self._multi_add_pause(d), add_row),
                (tr("Edit"), lambda _checked=False, d=direction: self._multi_edit(d), edit_row),
                ("↑", lambda _checked=False, d=direction: self._multi_move(d, -1), edit_row),
                ("↓", lambda _checked=False, d=direction: self._multi_move(d, 1), edit_row),
                (tr("Delete"), lambda _checked=False, d=direction: self._multi_remove(d), edit_row),
            ):
                button = QPushButton(text)
                button.clicked.connect(callback)
                row.addWidget(button)
            tab_layout.addLayout(add_row)
            tab_layout.addLayout(edit_row)
            tabs.addTab(tab, title)
        layout.addWidget(tabs)
        return page

    def _multi_steps(self, direction: str) -> list[MultiActionStep]:
        return self.multi_action_in if direction == "in" else self.multi_action_out

    def _refresh_multi_lists(self) -> None:
        if not hasattr(self, "multi_lists"):
            return
        for direction, sequence in self.multi_lists.items():
            selected = sequence.currentRow()
            sequence.clear()
            for step in self._multi_steps(direction):
                sequence.addItem(QListWidgetItem(describe_multi_step(step)))
            if sequence.count():
                sequence.setCurrentRow(min(max(0, selected), sequence.count() - 1))

    def _multi_add_action(self, direction: str) -> None:
        dialog = MultiActionStepDialog(None, direction == "in", self, self)
        if dialog.exec():
            self._multi_steps(direction).append(dialog.step())
            self._refresh_multi_lists()
            self._store()

    def _multi_add_pause(self, direction: str) -> None:
        seconds, ok = QInputDialog.getDouble(self, tr("Add pause"), tr("Seconds"), 1.0, 0.0, 3600.0, 2)
        if ok:
            self._multi_steps(direction).append(MultiActionStep("pause", round(seconds * 1000)))
            self._refresh_multi_lists()
            self._store()

    def _multi_edit(self, direction: str) -> None:
        sequence = self.multi_lists[direction]
        row = sequence.currentRow()
        steps = self._multi_steps(direction)
        if not (0 <= row < len(steps)):
            return
        current = steps[row]
        if current.kind == "pause":
            seconds, ok = QInputDialog.getDouble(self, tr("Edit pause"), tr("Seconds"), current.delay_ms / 1000, 0.0, 3600.0, 2)
            if ok:
                current.delay_ms = round(seconds * 1000)
        else:
            dialog = MultiActionStepDialog(current, direction == "in", self, self)
            if dialog.exec():
                steps[row] = dialog.step()
        self._refresh_multi_lists()
        self._store()

    def _multi_move(self, direction: str, offset: int) -> None:
        sequence = self.multi_lists[direction]
        row = sequence.currentRow()
        target = row + offset
        steps = self._multi_steps(direction)
        if not (0 <= row < len(steps) and 0 <= target < len(steps)):
            return
        steps[row], steps[target] = steps[target], steps[row]
        self._refresh_multi_lists()
        sequence.setCurrentRow(target)
        self._store()

    def _multi_remove(self, direction: str) -> None:
        row = self.multi_lists[direction].currentRow()
        steps = self._multi_steps(direction)
        if 0 <= row < len(steps):
            del steps[row]
            self._refresh_multi_lists()
            self._store()

    def _choose_application(self) -> None:
        dialog = ApplicationChoiceDialog(self)
        if not dialog.exec() or dialog.application is None:
            return
        application = dialog.application
        self.application_desktop_file = application.desktop_file
        self.application_name.setText(application.name)
        self.label.setText(application.name)
        icon_path = cache_application_icon(application)
        if icon_path:
            self.icon.set_path(icon_path)
        self._store()

    def set_spaces(self, spaces: list[Space]) -> None:
        self.spaces = spaces
        selected = self.key.target_space if self.key else ""
        self.target.blockSignals(True)
        self.target.clear()
        for space in spaces:
            self.target.addItem(space.name, space.id)
        index = self.target.findData(selected)
        self.target.setCurrentIndex(max(0, index))
        self.target.blockSignals(False)

    def set_spectrum_default_fps(self, fps: int) -> None:
        self.spectrum_default_fps = fps

    def commit(self) -> None:
        """Store every visible editor value before an explicit device sync."""
        self._store()

    def set_audio_targets(self, targets: list[object]) -> None:
        self._audio_targets = targets
        self._reload_audio_targets(self.key.audio_target if self.key else "")
        self._reload_spectrum_targets(self.key.spectrum_target if self.key else "")
        self._reload_vu_targets(self.key.vu_target if self.key else "")

    def set_obs_catalog(self, catalog: dict) -> None:
        self.obs_catalog = catalog
        scene = self.key.obs_scene if self.key else self.obs_scene.currentText()
        group = self.key.obs_group if self.key else self.obs_group.currentText()
        target = self.key.obs_target if self.key else self.obs_target.currentText()
        self._reload_obs_choices(scene, target, group)

    @staticmethod
    def _set_editable_combo(combo: QComboBox, values: list[str], selected: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(values)
        index = combo.findText(selected)
        if index >= 0:
            combo.setCurrentIndex(index)
        else:
            combo.setEditText(selected)
        combo.blockSignals(False)

    def _reload_obs_choices(self, selected_scene: str = "", selected_target: str = "", selected_group: str = "") -> None:
        scenes = [str(value) for value in self.obs_catalog.get("scenes", [])]
        self._set_editable_combo(self.obs_scene, scenes, selected_scene)
        operation = str(self.obs_operation.currentData())
        groups = self.obs_catalog.get("groups", {}).get(selected_scene, {})
        self._set_editable_combo(self.obs_group, [""] + [str(value) for value in groups], selected_group)
        if operation == "scene":
            choices = scenes
        elif operation == "source":
            collection = groups.get(selected_group, []) if selected_group else self.obs_catalog.get("sources", {}).get(selected_scene, [])
            choices = [str(value) for value in collection]
        elif operation == "input_mute":
            choices = [str(value) for value in self.obs_catalog.get("inputs", [])]
        else:
            choices = []
        self._set_editable_combo(self.obs_target, choices, selected_target)

    def _reload_audio_targets(self, selected: str = "") -> None:
        if not hasattr(self, "_audio_targets"):
            self._audio_targets = []
        kind = str(self.audio_kind.currentData())
        self.audio_target.blockSignals(True)
        self.audio_target.clear()
        self.audio_target.addItem(tr("Select…"), "")
        for target in self._audio_targets:
            if target.kind == kind:
                self.audio_target.addItem(target.label, target.target)
        index = self.audio_target.findData(selected)
        self.audio_target.setCurrentIndex(max(0, index))
        self.audio_target.blockSignals(False)

    def _reload_spectrum_targets(self, selected: str = "") -> None:
        if not hasattr(self, "_audio_targets"):
            self._audio_targets = []
        kind = str(self.spectrum_kind.currentData())
        self.spectrum_target.blockSignals(True)
        self.spectrum_target.clear()
        self.spectrum_target.addItem(tr("Select…"), "")
        for target in self._audio_targets:
            if target.kind == kind and target.capture_device:
                self.spectrum_target.addItem(target.label, target.target)
        index = self.spectrum_target.findData(selected)
        self.spectrum_target.setCurrentIndex(max(0, index))
        self.spectrum_target.blockSignals(False)

    def _reload_vu_targets(self, selected: str = "") -> None:
        if not hasattr(self, "_audio_targets"):
            self._audio_targets = []
        kind = str(self.vu_kind.currentData())
        self.vu_target.blockSignals(True)
        self.vu_target.clear()
        self.vu_target.addItem(tr("Select…"), "")
        for target in self._audio_targets:
            if target.kind == kind and target.capture_device:
                self.vu_target.addItem(target.label, target.target)
        index = self.vu_target.findData(selected)
        self.vu_target.setCurrentIndex(max(0, index))
        self.vu_target.blockSignals(False)

    def edit_key(self, key: KeyConfig) -> None:
        self.key = key
        self.setEnabled(True)
        widgets = [self.label, self.background_color, self.active_background_color, self.text_color, self.icon_color, self.action, self.command, self.command_off, self.ws_url, self.payload_on, self.payload_off, self.audio_kind, self.audio_target, self.obs_operation, self.obs_scene, self.obs_group, self.obs_target, self.spectrum_operation, self.spectrum_kind, self.spectrum_target, self.spectrum_fps, self.spectrum_grid, self.spectrum_preview, self.vu_operation, self.vu_kind, self.vu_target, self.vu_fps, self.vu_preview, self.vu_color_start, self.vu_color_end, self.target, self.keyboard_shortcut, self.media_control, self.toggle, self.timer]
        for widget in widgets:
            widget.blockSignals(True)
        self.label.setText(key.label)
        self.icon.set_value(key.icon, key.glyph)
        self.active_icon.set_value(key.active_icon, key.active_glyph)
        self.background_color.set_color(key.background_color)
        self.active_background_color.set_color(key.active_background_color)
        self.text_color.set_color(key.text_color)
        self.icon_color.set_color(key.icon_color)
        self.action.setCurrentIndex(max(0, self.action.findData(key.action)))
        self.command.setText(key.command)
        self.command_off.setText(key.command_off)
        self.application_desktop_file = key.application_desktop_file
        application = read_desktop_application(Path(key.application_desktop_file)) if key.application_desktop_file else None
        self.application_name.setText(application.name if application else tr("No application selected"))
        self.ws_url.setText(key.websocket_url)
        self.payload_on.setPlainText(key.payload_on)
        self.payload_off.setPlainText(key.payload_off)
        self.audio_kind.setCurrentIndex(max(0, self.audio_kind.findData(key.audio_kind)))
        self._reload_audio_targets(key.audio_target)
        self.obs_operation.setCurrentIndex(max(0, self.obs_operation.findData(key.obs_operation)))
        self._reload_obs_choices(key.obs_scene, key.obs_target, key.obs_group)
        self.spectrum_operation.setCurrentIndex(max(0, self.spectrum_operation.findData(key.spectrum_operation)))
        self.spectrum_kind.setCurrentIndex(max(0, self.spectrum_kind.findData(key.spectrum_kind)))
        self._reload_spectrum_targets(key.spectrum_target)
        self.spectrum_fps.setValue(key.spectrum_fps)
        self.spectrum_grid.setCurrentIndex(max(0, self.spectrum_grid.findData(max(1, min(3, key.spectrum_grid_size)))))
        self.spectrum_preview.setChecked(key.spectrum_preview)
        self.vu_operation.setCurrentIndex(max(0, self.vu_operation.findData(key.vu_operation)))
        self.vu_kind.setCurrentIndex(max(0, self.vu_kind.findData(key.vu_kind)))
        self._reload_vu_targets(key.vu_target)
        self.vu_fps.setValue(key.vu_fps)
        self.vu_preview.setChecked(key.vu_preview)
        self.vu_color_start.set_color(key.vu_color_start)
        self.vu_color_end.set_color(key.vu_color_end)
        self.keyboard_shortcut.setText(key.keyboard_shortcut)
        self.media_control.setCurrentIndex(max(0, self.media_control.findData(key.media_control)))
        self.multi_action_in = deepcopy(key.multi_action_in)
        self.multi_action_out = deepcopy(key.multi_action_out)
        self._refresh_multi_lists()
        self.toggle.setChecked(key.toggle)
        self.timer.setChecked(key.show_timer)
        self.set_spaces(self.spaces)
        for widget in widgets:
            widget.blockSignals(False)
        self._update_visibility()

    def _action_changed(self) -> None:
        if self.action.currentData() in (ACTION_SPECTRUM, ACTION_VU) and self.key and self.key.action != self.action.currentData():
            fps = self.spectrum_fps if self.action.currentData() == ACTION_SPECTRUM else self.vu_fps
            fps.blockSignals(True)
            fps.setValue(self.spectrum_default_fps)
            fps.blockSignals(False)
        self._update_visibility()
        self._store()

    def _toggle_changed(self) -> None:
        self._update_visibility()
        self._store()

    def _audio_kind_changed(self) -> None:
        self._reload_audio_targets()
        self._store()

    def _obs_operation_changed(self) -> None:
        operation = self.obs_operation.currentData()
        if operation in ("scene", "stream_start", "stream_stop"):
            self.toggle.setChecked(False)
        else:
            self.toggle.setChecked(True)
        self._reload_obs_choices(self.obs_scene.currentText(), "")
        self._update_visibility()
        self._store()

    def _obs_scene_changed(self) -> None:
        if self.obs_operation.currentData() == "source":
            self._reload_obs_choices(self.obs_scene.currentText(), "")
        self._store()

    def _obs_group_changed(self) -> None:
        if self.obs_operation.currentData() == "source":
            self._reload_obs_choices(self.obs_scene.currentText(), "", self.obs_group.currentText())
        self._store()

    def _spectrum_operation_changed(self) -> None:
        self._update_visibility()
        self._store()

    def _spectrum_kind_changed(self) -> None:
        self._reload_spectrum_targets()
        self._store()

    def _vu_operation_changed(self) -> None:
        self._update_visibility()
        self._store()

    def _vu_kind_changed(self) -> None:
        self._reload_vu_targets()
        self._store()

    def _update_visibility(self) -> None:
        action = self.action.currentData()
        pages = {ACTION_NONE: 0, ACTION_SHELL: 1, ACTION_WEBSOCKET: 2, ACTION_AUDIO: 3, ACTION_OBS: 4, ACTION_SPECTRUM: 5, ACTION_VU: 6, ACTION_SPACE: 7, ACTION_APPLICATION: 8, ACTION_KEYBOARD: 9, ACTION_MEDIA: 10, ACTION_MULTI: 11}
        self.action_stack.setCurrentIndex(pages.get(action, 0))
        obs_operation = self.obs_operation.currentData()
        obs_toggle = action == ACTION_OBS and obs_operation in ("source", "input_mute")
        spectrum_start = action == ACTION_SPECTRUM and self.spectrum_operation.currentData() == "start"
        vu_start = action == ACTION_VU and self.vu_operation.currentData() == "start"
        self.spectrum_mode_hint.setText(
            tr("First press opens the analyzer full screen; second press returns to the optional key preview.")
            if spectrum_start else tr("This key only stops the analyzer; it never starts it.")
        )
        self.vu_mode_hint.setText(
            tr("First press opens the VU meter full screen; second press returns to the optional key preview.")
            if vu_start else tr("This key only stops the VU meter; it never starts it.")
        )
        supports_toggle = action in (ACTION_SHELL, ACTION_WEBSOCKET, ACTION_AUDIO, ACTION_MULTI) or obs_toggle or spectrum_start or vu_start
        forced_toggle = action in (ACTION_AUDIO, ACTION_MULTI) or obs_toggle or spectrum_start or vu_start
        if forced_toggle and not self.toggle.isChecked():
            self.toggle.blockSignals(True)
            self.toggle.setChecked(True)
            self.toggle.blockSignals(False)
            if self.key:
                self.key.toggle = True
        elif action == ACTION_OBS and obs_operation in ("scene", "stream_start", "stream_stop") and self.toggle.isChecked():
            self.toggle.blockSignals(True)
            self.toggle.setChecked(False)
            self.toggle.blockSignals(False)
            if self.key:
                self.key.toggle = False
        self.toggle.setEnabled(not forced_toggle)
        self.toggle.setVisible(supports_toggle and not spectrum_start and not vu_start)
        self.toggle_box.setVisible(supports_toggle or spectrum_start or vu_start)
        self.timer.setVisible(not self.action_only and supports_toggle and self.toggle.isChecked())
        self.active_icon.setVisible(not self.action_only and ((supports_toggle and self.toggle.isChecked()) or spectrum_start or vu_start))
        self.shell_form.setRowVisible(self.command_off, self.toggle.isChecked())
        self.websocket_form.setRowVisible(self.payload_off, self.toggle.isChecked())
        stream_operation = obs_operation in ("stream_start", "stream_stop")
        self.obs_form.setRowVisible(self.obs_scene, obs_operation == "source")
        self.obs_form.setRowVisible(self.obs_group, obs_operation == "source")
        self.obs_form.setRowVisible(self.obs_target, not stream_operation)
        target_label = self.obs_form.labelForField(self.obs_target)
        if target_label:
            target_label.setText(tr("Scene") if obs_operation == "scene" else tr("Audio input") if obs_operation == "input_mute" else tr("Source"))
        self.spectrum_form.setRowVisible(self.spectrum_kind, spectrum_start)
        self.spectrum_form.setRowVisible(self.spectrum_target, spectrum_start)
        self.spectrum_form.setRowVisible(self.spectrum_fps, spectrum_start)
        self.spectrum_form.setRowVisible(self.spectrum_grid, spectrum_start)
        self.spectrum_form.setRowVisible(self.spectrum_preview, spectrum_start)
        self.vu_form.setRowVisible(self.vu_kind, vu_start)
        self.vu_form.setRowVisible(self.vu_target, vu_start)
        self.vu_form.setRowVisible(self.vu_fps, vu_start)
        self.vu_form.setRowVisible(self.vu_preview, vu_start)
        self.vu_form.setRowVisible(self.vu_color_start.parentWidget(), vu_start)

    def _store(self, *_args: object) -> None:
        if not self.key:
            return
        self.key.label = self.label.text().strip()
        self.key.icon = self.icon.path
        self.key.active_icon = self.active_icon.path
        self.key.glyph = self.icon.glyph
        self.key.active_glyph = self.active_icon.glyph
        self.key.background_color = self.background_color.color
        self.key.active_background_color = self.active_background_color.color
        self.key.text_color = self.text_color.color
        self.key.icon_color = self.icon_color.color
        self.key.action = str(self.action.currentData())
        self.key.command = self.command.text()
        self.key.command_off = self.command_off.text()
        self.key.application_desktop_file = getattr(self, "application_desktop_file", "")
        self.key.keyboard_shortcut = self.keyboard_shortcut.text().strip()
        self.key.media_control = str(self.media_control.currentData() or "PLAYPAUSE")
        self.key.websocket_url = self.ws_url.text().strip()
        self.key.payload_on = self.payload_on.toPlainText()
        self.key.payload_off = self.payload_off.toPlainText()
        self.key.audio_kind = str(self.audio_kind.currentData())
        self.key.audio_target = str(self.audio_target.currentData() or "")
        self.key.obs_operation = str(self.obs_operation.currentData())
        self.key.obs_scene = self.obs_scene.currentText().strip()
        self.key.obs_group = self.obs_group.currentText().strip()
        self.key.obs_target = self.obs_target.currentText().strip()
        self.key.spectrum_operation = str(self.spectrum_operation.currentData())
        self.key.spectrum_kind = str(self.spectrum_kind.currentData())
        self.key.spectrum_target = str(self.spectrum_target.currentData() or "")
        self.key.spectrum_fps = self.spectrum_fps.value()
        self.key.spectrum_grid_size = int(self.spectrum_grid.currentData() or 1)
        self.key.spectrum_preview = self.spectrum_preview.isChecked()
        self.key.vu_operation = str(self.vu_operation.currentData())
        self.key.vu_kind = str(self.vu_kind.currentData())
        self.key.vu_target = str(self.vu_target.currentData() or "")
        self.key.vu_fps = self.vu_fps.value()
        self.key.vu_preview = self.vu_preview.isChecked()
        self.key.vu_color_start = self.vu_color_start.color
        self.key.vu_color_end = self.vu_color_end.color
        self.key.multi_action_in = deepcopy(getattr(self, "multi_action_in", []))
        self.key.multi_action_out = deepcopy(getattr(self, "multi_action_out", []))
        self.key.target_space = str(self.target.currentData() or "")
        self.key.toggle = self.toggle.isChecked()
        self.key.show_timer = self.timer.isChecked() and self.key.toggle
        if not self.key.toggle:
            self.key.active = False
            self.key.started_at = None
        self.changed.emit()


class MultiActionStepDialog(QDialog):
    def __init__(self, step: MultiActionStep | None, default_state: bool, source: KeyInspector, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Configure sequence action"))
        self.resize(560, 680)
        layout = QVBoxLayout(self)
        state_form = QFormLayout()
        self.state = QComboBox()
        self.state.addItem(tr("Enable / on"), True)
        self.state.addItem(tr("Disable / off"), False)
        selected_state = step.desired_state if step else default_state
        self.state.setCurrentIndex(0 if selected_state else 1)
        state_form.addRow(tr("Requested state"), self.state)
        layout.addLayout(state_form)
        state_hint = QLabel(tr("The requested state applies to toggle actions; one-shot actions simply run."))
        state_hint.setWordWrap(True)
        state_hint.setObjectName("hint")
        layout.addWidget(state_hint)
        self.editor = KeyInspector(self, action_only=True)
        self.editor.set_spaces(source.spaces)
        self.editor.set_audio_targets(getattr(source, "_audio_targets", []))
        self.editor.set_obs_catalog(source.obs_catalog)
        action = KeyConfig.from_dict(step.action) if step else KeyConfig()
        if action.action == ACTION_MULTI:
            action.action = ACTION_NONE
        if action.action in (ACTION_SHELL, ACTION_WEBSOCKET):
            action.toggle = True
        self.editor.edit_key(action)
        layout.addWidget(self.editor, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancel"))
        buttons.button(QDialogButtonBox.StandardButton.Save).setText(tr("Save"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def step(self) -> MultiActionStep:
        self.editor.commit()
        assert self.editor.key is not None
        action = self.editor.key.to_dict()
        action["active"] = False
        action["started_at"] = None
        action["multi_action_in"] = []
        action["multi_action_out"] = []
        return MultiActionStep("action", 0, bool(self.state.currentData()), action)


def describe_multi_step(step: MultiActionStep) -> str:
    if step.kind == "pause":
        return tr("Pause · {seconds:.2f} s", seconds=step.delay_ms / 1000)
    key = KeyConfig.from_dict(step.action)
    state = tr("on") if step.desired_state else tr("off")
    details = {
        ACTION_SHELL: key.command if step.desired_state or not key.command_off else key.command_off,
        ACTION_WEBSOCKET: key.websocket_url,
        ACTION_AUDIO: key.audio_target,
        ACTION_OBS: key.obs_target or key.obs_operation,
        ACTION_SPECTRUM: key.spectrum_operation,
        ACTION_VU: key.vu_operation,
        ACTION_SPACE: key.target_space,
        ACTION_APPLICATION: Path(key.application_desktop_file).stem,
        ACTION_KEYBOARD: key.keyboard_shortcut,
        ACTION_MEDIA: key.media_control,
    }.get(key.action, "")
    label = {
        ACTION_SHELL: tr("Shell command"),
        ACTION_WEBSOCKET: tr("WebSocket message"),
        ACTION_AUDIO: tr("Audio"),
        ACTION_OBS: "OBS",
        ACTION_SPECTRUM: tr("Spectrum analyzer"),
        ACTION_VU: tr("Stereo VU meter"),
        ACTION_SPACE: tr("Switch space"),
        ACTION_APPLICATION: tr("Open application"),
        ACTION_KEYBOARD: tr("Keyboard shortcut"),
        ACTION_MEDIA: tr("Media control"),
    }.get(key.action, tr("No action"))
    suffix = f" · {details}" if details else ""
    return f"{label}{suffix} · {state}"
