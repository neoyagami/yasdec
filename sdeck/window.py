from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .actions import ActionRunner, elapsed_text
from .api import ApiServer
from .dialogs import ApiSettingsDialog, ObsSettingsDialog
from .hardware import DeckBackend
from .i18n import tr
from .model import ACTION_NONE, ACTION_OBS, ACTION_SPECTRUM, ACTION_VU, AppConfig, KeyConfig, replicate_key_config
from .models import BUTTON_DECK_MODELS
from .widgets import KeyButton, KeyInspector


def blend_color(start: str, end: str, position: float) -> str:
    first = QColor(start) if QColor(start).isValid() else QColor("#18f2a4")
    last = QColor(end) if QColor(end).isValid() else QColor("#ff3b81")
    ratio = max(0.0, min(1.0, position))
    return QColor(
        round(first.red() + (last.red() - first.red()) * ratio),
        round(first.green() + (last.green() - first.green()) * ratio),
        round(first.blue() + (last.blue() - first.blue()) * ratio),
    ).name()


class MainWindow(QMainWindow):
    def __init__(self, config_path: Path, app_icon: QIcon) -> None:
        super().__init__()
        self.config_path = config_path
        self.config = AppConfig.load(config_path)
        self.selected_key = 0
        self._copied_key: KeyConfig | None = None
        self._allow_close = False
        self.tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self.setWindowTitle("YASDEC — Yet Another Stream Deck Controller")
        self.setWindowIcon(app_icon)
        self.resize(1320, 800)
        self.setMinimumSize(1080, 680)

        self.runner = ActionRunner(self)
        self.runner.configure_obs(self.config.obs_url, self.config.obs_password)
        self.deck = DeckBackend(self)
        self.api = ApiServer(self)
        self.spectrum_levels: list[float] = []
        self.spectrum_timer = QTimer(self)
        self.spectrum_timer.timeout.connect(self._draw_spectrum)
        self.vu_levels: tuple[float, float] = (0.0, 0.0)
        self.vu_timer = QTimer(self)
        self.vu_timer.timeout.connect(self._draw_vu)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(250)
        self.save_timer.timeout.connect(self.save)
        self.obs_watch_timer = QTimer(self)
        self.obs_watch_timer.setSingleShot(True)
        self.obs_watch_timer.setInterval(300)
        self.obs_watch_timer.timeout.connect(self._refresh_edited_obs_key)
        self._obs_watch_key = None

        self._build_ui()
        self._build_tray(app_icon)
        self._connect_signals()
        self._reload_spaces()
        self.select_space(self.config.current_space)
        self.deck.connect_device()
        self._restart_api()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(22, 12, 22, 12)
        header_layout.setSpacing(9)
        identity_row = QHBoxLayout()
        controls_row = QHBoxLayout()
        identity_row.setSpacing(10)
        controls_row.setSpacing(9)
        brand = QLabel("YASDEC")
        brand.setObjectName("brand")
        subtitle = QLabel(tr("Stream Deck controller"))
        subtitle.setObjectName("subtitle")
        identity_row.addWidget(brand)
        identity_row.addWidget(subtitle)
        identity_row.addStretch()
        self.device_status = QLabel(tr("Searching for device…"))
        self.device_status.setObjectName("deviceStatus")
        self.test_button = QPushButton(tr("Test action"))
        self.test_button.setToolTip(tr("Runs the selected key"))
        self.model_selector = QComboBox()
        self.model_selector.setToolTip(tr("Model used by the configuration view"))
        for model_id, model in BUTTON_DECK_MODELS.items():
            self.model_selector.addItem(tr(model["name"]), model_id)
        self.model_selector.setCurrentIndex(max(0, self.model_selector.findData(self.config.model_id)))
        self.language_selector = QComboBox()
        self.language_selector.addItem(tr("System language"), "system")
        self.language_selector.addItem("English", "en")
        self.language_selector.addItem("Español", "es")
        self.language_selector.setCurrentIndex(max(0, self.language_selector.findData(self.config.language)))
        self.language_selector.setToolTip(tr("Interface language"))
        self.api_button = QPushButton("API")
        self.api_button.setToolTip(tr("Configure HTTP access"))
        self.obs_button = QPushButton("OBS")
        self.obs_button.setToolTip(tr("Configure the global OBS connection"))
        self.obs_connect_button = QPushButton(tr("Connect"))
        self.obs_connect_button.setToolTip(tr("Connect or reconnect to OBS now"))
        self.obs_status = QLabel("○  OBS")
        self.obs_status.setObjectName("obsStatus")
        self.obs_status.setProperty("connected", False)
        self.obs_status.setToolTip(f"OBS: {tr('Disconnected')}")
        self.send_button = QPushButton(tr("Send now"))
        self.send_button.setIcon(QIcon(str(Path(__file__).resolve().parent.parent / "assets/icons/lucide/arrow-up.svg")))
        self.send_button.setToolTip(tr("Save and resend the entire space to the device"))
        self.send_button.setEnabled(False)
        identity_row.addWidget(self.device_status)
        identity_row.addWidget(self.obs_status)
        controls_row.addWidget(self.model_selector)
        controls_row.addWidget(self.language_selector)
        controls_row.addStretch()
        controls_row.addWidget(self.api_button)
        controls_row.addWidget(self.obs_button)
        controls_row.addWidget(self.obs_connect_button)
        controls_row.addWidget(self.send_button)
        controls_row.addWidget(self.test_button)
        header_layout.addLayout(identity_row)
        header_layout.addLayout(controls_row)
        root.addWidget(header)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._spaces_panel())
        splitter.addWidget(self._deck_panel())
        self.inspector = KeyInspector()
        self.inspector.setMinimumWidth(410)
        self.inspector.set_spectrum_default_fps(BUTTON_DECK_MODELS[self.config.model_id]["spectrum_fps"])
        self.inspector_scroll = QScrollArea()
        self.inspector_scroll.setObjectName("inspectorScroll")
        self.inspector_scroll.setWidgetResizable(True)
        self.inspector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.inspector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.inspector_scroll.setMinimumWidth(420)
        self.inspector_scroll.setWidget(self.inspector)
        splitter.addWidget(self.inspector_scroll)
        splitter.setSizes([190, 650, 440])
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)

        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.setStatusBar(status)
        shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        shortcut.activated.connect(self.save)
        quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        quit_shortcut.activated.connect(self.quit_app)

    def _spaces_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("spacesPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 20, 14, 14)
        top = QHBoxLayout()
        title = QLabel(tr("Spaces"))
        title.setObjectName("sectionTitle")
        add = QToolButton()
        add.setText("+")
        add.setToolTip(tr("Create space"))
        add.clicked.connect(self.add_space)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(add)
        layout.addLayout(top)
        self.space_list = QListWidget()
        self.space_list.setSpacing(3)
        self.space_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.space_list.customContextMenuRequested.connect(self._space_menu)
        layout.addWidget(self.space_list, 1)
        hint = QLabel(tr("Right-click to rename, duplicate, or delete"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        panel.setMinimumWidth(180)
        panel.setMaximumWidth(260)
        return panel

    def _deck_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(28, 24, 28, 24)
        heading = QHBoxLayout()
        self.space_title = QLabel(tr("Main"))
        self.space_title.setObjectName("deckTitle")
        self.space_count = QLabel()
        self.space_count.setObjectName("hint")
        heading.addWidget(self.space_title)
        heading.addStretch()
        heading.addWidget(self.space_count)
        layout.addLayout(heading)
        layout.addSpacing(18)

        deck_frame = QWidget()
        deck_frame.setObjectName("deckFrame")
        self.grid = QGridLayout(deck_frame)
        self.grid.setContentsMargins(24, 24, 24, 24)
        self.grid.setSpacing(13)
        self.key_buttons: list[KeyButton] = []
        self._rebuild_grid()
        layout.addWidget(deck_frame, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()
        return panel

    def _build_tray(self, icon: QIcon) -> None:
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("YASDEC")
        menu = QMenu()
        show_action = QAction(tr("Open YASDEC"), menu)
        show_action.triggered.connect(self.show_from_tray)
        about_action = QAction(tr("About YASDEC"), menu)
        about_action.triggered.connect(self.show_about)
        quit_action = QAction(
            QIcon(str(Path(__file__).resolve().parent.parent / "assets/icons/lucide/power.svg")),
            tr("Quit YASDEC completely"),
            menu,
        )
        quit_action.setToolTip(tr("Stop the controller and release the device"))
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(about_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _connect_signals(self) -> None:
        self.space_list.currentItemChanged.connect(self._space_selected)
        self.inspector.changed.connect(self._key_edited)
        self.test_button.clicked.connect(self.trigger_selected)
        self.api_button.clicked.connect(self.configure_api)
        self.obs_button.clicked.connect(self.configure_obs)
        self.obs_connect_button.clicked.connect(self.connect_obs)
        self.send_button.clicked.connect(self.send_now)
        self.runner.key_changed.connect(self._runtime_key_changed)
        self.runner.space_requested.connect(self.select_space)
        self.runner.status.connect(self._show_status)
        self.runner.spectrum_levels.connect(self._spectrum_levels_changed)
        self.runner.spectrum_mode_changed.connect(self._spectrum_mode_changed)
        self.runner.vu_levels.connect(self._vu_levels_changed)
        self.runner.vu_mode_changed.connect(self._vu_mode_changed)
        self.runner.obs_connection_changed.connect(self._obs_connection_changed)
        self.runner.obs_catalog_changed.connect(self.inspector.set_obs_catalog)
        self.runner.audio.targets_changed.connect(self.inspector.set_audio_targets)
        self.deck.key_pressed.connect(self.trigger_key)
        self.deck.connection_changed.connect(self._device_changed)
        self.deck.model_detected.connect(self._detected_model)
        self.model_selector.currentIndexChanged.connect(self._model_selected)
        self.language_selector.currentIndexChanged.connect(self._language_selected)
        self.api.trigger_requested.connect(self._api_trigger)
        self.api.status.connect(self._show_status)

    def _rebuild_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().setParent(None)
                item.widget().deleteLater()
        self.key_buttons = []
        compact = self.config.columns >= 8
        size = 82 if compact else 112
        for index in range(self.config.key_count):
            button = KeyButton(index)
            button.setFixedSize(size, size)
            button.clicked.connect(lambda _checked=False, i=index: self.select_key(i))
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(lambda point, i=index: self._key_menu(i, point))
            self.key_buttons.append(button)
            self.grid.addWidget(button, index // self.config.columns, index % self.config.columns)

    def _reload_spaces(self) -> None:
        self.space_list.blockSignals(True)
        self.space_list.clear()
        for space in self.config.spaces:
            item = QListWidgetItem(space.name)
            item.setData(Qt.ItemDataRole.UserRole, space.id)
            self.space_list.addItem(item)
        self.space_list.blockSignals(False)
        self.inspector.set_spaces(self.config.spaces)

    def select_space(self, space_id: str) -> None:
        space = self.config.space_by_id(space_id)
        if not space:
            return
        self.config.current_space = space.id
        self.space_title.setText(space.name)
        self.space_count.setText(f"{self.config.key_count} {tr('keys')}")
        visible_keys = space.keys[: self.config.key_count]
        self.runner.set_visible_keys(visible_keys, self.config.columns)
        for index, button in enumerate(self.key_buttons):
            button.set_key(visible_keys[index])
        for row in range(self.space_list.count()):
            item = self.space_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == space.id:
                self.space_list.setCurrentItem(item)
                break
        self.select_key(min(self.selected_key, len(space.keys) - 1))
        self.deck.render_space(visible_keys)
        self._update_api_snapshot()
        self.schedule_save()

    def select_key(self, index: int) -> None:
        self.selected_key = index
        for button in self.key_buttons:
            button.setChecked(button.index == index)
        self.inspector.edit_key(self.config.current().keys[index])

    def _key_menu(self, index: int, point: object) -> None:
        if not 0 <= index < self.config.key_count:
            return
        self.select_key(index)
        button = self.key_buttons[index]
        menu = QMenu(self)
        copy_action = menu.addAction(tr("Copy key configuration"))
        paste_action = menu.addAction(tr("Paste key configuration"))
        paste_action.setEnabled(self._copied_key is not None)
        chosen = menu.exec(button.mapToGlobal(point))
        if chosen == copy_action:
            self._copied_key = KeyConfig.from_dict(self.config.current().keys[index].to_dict())
            self.statusBar().showMessage(tr("Key configuration copied"), 2500)
            return
        if chosen != paste_action or self._copied_key is None:
            return
        destination = self.config.current().keys[index]
        configured = bool(destination.label or destination.icon or destination.glyph or destination.action != ACTION_NONE)
        if configured:
            answer = QMessageBox.question(
                self,
                tr("Replace key configuration"),
                tr("Replace the configuration of key {number}?", number=index + 1),
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        replicate_key_config(self._copied_key, destination)
        self.key_buttons[index].set_key(destination)
        self.inspector.edit_key(destination)
        self.deck.render_key(index, destination)
        self.runner._sync_visual_previews()
        self.schedule_save()
        self._update_api_snapshot()
        self.statusBar().showMessage(tr("Key configuration pasted"), 2500)

    def trigger_selected(self) -> None:
        self.trigger_key(self.selected_key)

    def send_now(self) -> None:
        self.inspector.commit()
        self.save_timer.stop()
        self.save()
        self.deck.render_space(self.config.current().keys[: self.config.key_count])
        if self.runner.spectrum_fullscreen:
            self._draw_spectrum()
        elif self.runner.vu_fullscreen:
            self._draw_vu()
        elif self.runner.spectrum_active or self.runner.vu_active:
            self._draw_audio_previews()
        self.statusBar().showMessage(tr("Space sent to device"), 2500)

    def trigger_key(self, index: int) -> None:
        keys = self.config.current().keys
        if 0 <= index < len(keys):
            self.runner.trigger(index, keys[index], self.config.current_space)
            self.schedule_save()

    def add_space(self) -> None:
        name, ok = QInputDialog.getText(self, tr("New space"), tr("Name"))
        if ok and name.strip():
            space = self.config.add_space(name.strip())
            self._reload_spaces()
            self.select_space(space.id)

    def _space_menu(self, point: object) -> None:
        item = self.space_list.itemAt(point)
        if not item:
            return
        space = self.config.space_by_id(str(item.data(Qt.ItemDataRole.UserRole)))
        if not space:
            return
        menu = QMenu(self)
        rename = menu.addAction(tr("Rename"))
        duplicate = menu.addAction(tr("Duplicate"))
        remove = menu.addAction(tr("Delete"))
        remove.setEnabled(len(self.config.spaces) > 1)
        chosen = menu.exec(self.space_list.mapToGlobal(point))
        if chosen == rename:
            name, ok = QInputDialog.getText(self, tr("Rename space"), tr("Name"), text=space.name)
            if ok and name.strip():
                space.name = name.strip()
                self._reload_spaces()
                self.select_space(space.id)
        elif chosen == duplicate:
            copy = self.config.duplicate_space(space, f"{space.name} {tr('copy')}")
            self._reload_spaces()
            self.select_space(copy.id)
        elif chosen == remove:
            answer = QMessageBox.question(self, tr("Delete space"), tr("Delete “{name}”?", name=space.name))
            if answer == QMessageBox.StandardButton.Yes:
                self.config.spaces.remove(space)
                self._reload_spaces()
                self.select_space(self.config.spaces[0].id)

    def _space_selected(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current:
            self.select_space(str(current.data(Qt.ItemDataRole.UserRole)))

    def _key_edited(self) -> None:
        key = self.config.current().keys[self.selected_key]
        self.key_buttons[self.selected_key].set_key(key)
        self.deck.render_key(self.selected_key, key)
        self.runner._sync_visual_previews()
        if key.action == ACTION_OBS:
            self._obs_watch_key = key
            self.obs_watch_timer.start()
        self.schedule_save()
        self._update_api_snapshot()

    def _refresh_edited_obs_key(self) -> None:
        if self._obs_watch_key is not None:
            self.runner.obs.watch([self._obs_watch_key])

    def _runtime_key_changed(self, index: int) -> None:
        if 0 <= index < len(self.key_buttons):
            key = self.config.current().keys[index]
            self.key_buttons[index].set_key(key)
            self.deck.render_key(index, key)
            if index == self.selected_key:
                self.inspector.edit_key(key)
        self.schedule_save()
        self._update_api_snapshot()

    def _device_changed(self, text: str, connected: bool) -> None:
        self.device_status.setText(("●  " + text) if connected else f"○  {tr('No device')}")
        self.send_button.setEnabled(connected)
        self.device_status.setToolTip(text)
        self.device_status.setProperty("connected", connected)
        self.device_status.style().unpolish(self.device_status)
        self.device_status.style().polish(self.device_status)
        if connected:
            self.deck.render_space(self.config.current().keys[: self.config.key_count])

    def _detected_model(self, model_id: str) -> None:
        index = self.model_selector.findData(model_id)
        if index >= 0:
            self.model_selector.setCurrentIndex(index)
            self.statusBar().showMessage(tr("View adjusted to detected device"), 3000)

    def _model_selected(self) -> None:
        model_id = str(self.model_selector.currentData())
        model = BUTTON_DECK_MODELS[model_id]
        if self.config.model_id == model_id and self.config.key_count == model["key_count"]:
            return
        if self.runner.spectrum_active:
            self.runner.spectrum.stop()
            self.runner.spectrum_active = False
            self._spectrum_mode_changed(False, 0)
        self.config.apply_layout(model_id, model["key_count"], model["columns"])
        self.inspector.set_spectrum_default_fps(model["spectrum_fps"])
        self.selected_key = min(self.selected_key, self.config.key_count - 1)
        self._rebuild_grid()
        self._reload_spaces()
        self.select_space(self.config.current_space)

    def _show_status(self, message: str, success: bool) -> None:
        self.statusBar().showMessage(message, 4000)
        if not success:
            self.tray.showMessage("YASDEC", message, QSystemTrayIcon.MessageIcon.Warning, 3500)

    def _obs_connection_changed(self, connected: bool, detail: str) -> None:
        pending = detail in (tr("Connecting…"), tr("Authenticating…"))
        self.obs_status.setText(("●  OBS") if connected else ("◌  OBS" if pending else "○  OBS"))
        self.obs_status.setToolTip(f"OBS: {detail}")
        self.obs_status.setProperty("connected", connected)
        self.obs_status.style().unpolish(self.obs_status)
        self.obs_status.style().polish(self.obs_status)

    def _spectrum_levels_changed(self, levels: list[float]) -> None:
        self.spectrum_levels = levels

    def _spectrum_mode_changed(self, active: bool, fps: int) -> None:
        if active:
            self.spectrum_timer.setInterval(max(50, int(1000 / max(1, fps))))
            self.spectrum_timer.start()
            if not self.runner.spectrum_fullscreen:
                self.deck.render_space(self.config.current().keys[: self.config.key_count])
            return
        self.spectrum_timer.stop()
        self.spectrum_levels = []
        for button in self.key_buttons:
            button.set_spectrum_level(None)
            button.set_mini_spectrum(None)
        self.deck.render_space(self.config.current().keys[: self.config.key_count])
        if self.runner.vu_active:
            self._draw_audio_previews()

    def _draw_spectrum(self) -> None:
        if not self.spectrum_levels:
            return
        if not self.runner.spectrum_fullscreen:
            self._draw_audio_previews()
            return
        keys = self.config.current().keys[: self.config.key_count]
        for button in self.key_buttons:
            button.set_spectrum_level(None)
            button.set_mini_spectrum(None)
            button.set_vu_cells(None)
            button.set_mini_vu(None)
        stop_indices = {index for index, key in enumerate(keys) if key.action == ACTION_SPECTRUM and key.spectrum_operation == "stop"}
        rows = (self.config.key_count + self.config.columns - 1) // self.config.columns
        spectrum_key = self.runner.spectrum_key
        grid_size = max(1, min(3, spectrum_key.spectrum_grid_size if spectrum_key else 1))
        key_levels: list = []
        key_colors: list = []
        for index, button in enumerate(self.key_buttons):
            row, column = divmod(index, self.config.columns)
            if grid_size == 1:
                band = self.spectrum_levels[column] if column < len(self.spectrum_levels) else 0.0
                level = max(0.0, min(1.0, band * rows - (rows - 1 - row)))
                vertical = 1.0 - row / max(1, rows - 1)
                color = "#ee6c4d" if vertical > 0.66 else "#e1a94c" if vertical > 0.33 else "#42d3b3"
                key_levels.append(level)
                key_colors.append(color)
                button.set_spectrum_level(None if index in stop_indices else level, color)
                continue

            total_rows = rows * grid_size
            cells: list[float] = []
            cell_colors: list[str] = []
            for inner_row in range(grid_size):
                global_row = row * grid_size + inner_row
                vertical = 1.0 - global_row / max(1, total_rows - 1)
                color = "#ee6c4d" if vertical > 0.66 else "#e1a94c" if vertical > 0.33 else "#42d3b3"
                level_from_bottom = total_rows - 1 - global_row
                for inner_column in range(grid_size):
                    band_index = column * grid_size + inner_column
                    band = self.spectrum_levels[band_index] if band_index < len(self.spectrum_levels) else 0.0
                    cells.append(1.0 if band * total_rows > level_from_bottom else 0.0)
                    cell_colors.append(color)
            key_levels.append(cells)
            key_colors.append(cell_colors)
            button.set_spectrum_cells(None if index in stop_indices else cells, cell_colors, grid_size)
        self.deck.render_spectrum(key_levels, stop_indices, key_colors, grid_size)

    def _vu_levels_changed(self, levels: tuple[float, float]) -> None:
        self.vu_levels = (float(levels[0]), float(levels[1]))

    def _vu_mode_changed(self, active: bool, fps: int) -> None:
        if active:
            self.vu_timer.setInterval(max(50, int(1000 / max(1, fps))))
            self.vu_timer.start()
            if not self.runner.vu_fullscreen:
                self.deck.render_space(self.config.current().keys[: self.config.key_count])
            return
        self.vu_timer.stop()
        self.vu_levels = (0.0, 0.0)
        for button in self.key_buttons:
            button.set_vu_cells(None)
            button.set_mini_vu(None)
        self.deck.render_space(self.config.current().keys[: self.config.key_count])
        if self.runner.spectrum_active:
            self._draw_audio_previews()

    def _draw_vu(self) -> None:
        if not self.runner.vu_fullscreen:
            self._draw_audio_previews()
            return
        keys = self.config.current().keys[: self.config.key_count]
        for button in self.key_buttons:
            button.set_spectrum_level(None)
            button.set_mini_spectrum(None)
            button.set_vu_cells(None)
            button.set_mini_vu(None)
        meter_key = self.runner.vu_key
        if meter_key is None:
            return
        rows = (self.config.key_count + self.config.columns - 1) // self.config.columns
        segment_count = self.config.columns * 3
        colors = [blend_color(meter_key.vu_color_start, meter_key.vu_color_end, index / max(1, segment_count - 1)) for index in range(segment_count)]
        key_levels: list[list[float]] = []
        key_colors: list[list[str]] = []
        for index, button in enumerate(self.key_buttons):
            row, column = divmod(index, self.config.columns)
            channel = 0 if row == 0 else 1 if row == rows - 1 else -1
            active = round(max(0.0, min(1.0, self.vu_levels[channel])) * segment_count) if channel >= 0 else 0
            levels = [1.0 if column * 3 + inner < active else 0.0 for inner in range(3)]
            cell_colors = colors[column * 3 : column * 3 + 3]
            key_levels.append(levels)
            key_colors.append(cell_colors)
            button.set_vu_cells(levels, cell_colors)
        self.deck.render_vu(key_levels, key_colors)

    def _draw_audio_previews(self) -> None:
        """Draw both inactive audio previews without either timer erasing the other."""
        if self.runner.spectrum_fullscreen or self.runner.vu_fullscreen:
            return
        keys = self.config.current().keys[: self.config.key_count]
        for button in self.key_buttons:
            button.set_spectrum_level(None)
            button.set_mini_spectrum(None)
            button.set_vu_cells(None)
            button.set_mini_vu(None)

        spectrum_preview = None
        if self.runner.spectrum_active and self.spectrum_levels:
            spectrum_index = next((
                index for index, key in enumerate(keys)
                if key is self.runner.spectrum_key and key.spectrum_preview
            ), -1)
            if spectrum_index >= 0:
                self.key_buttons[spectrum_index].set_mini_spectrum(self.spectrum_levels)
                spectrum_preview = (spectrum_index, keys[spectrum_index], self.spectrum_levels)

        vu_preview = None
        if self.runner.vu_active:
            vu_index = next((
                index for index, key in enumerate(keys)
                if key is self.runner.vu_key and key.vu_preview
            ), -1)
            if vu_index >= 0:
                self.key_buttons[vu_index].set_mini_vu(self.vu_levels)
                vu_preview = (vu_index, keys[vu_index], self.vu_levels)

        self.deck.render_audio_previews(spectrum_preview, vu_preview)

    def configure_api(self) -> None:
        dialog = ApiSettingsDialog(self.config, self)
        if dialog.exec():
            dialog.apply(self.config)
            self._restart_api()
            self.schedule_save()

    def configure_obs(self) -> None:
        dialog = ObsSettingsDialog(self.config, self)
        if dialog.exec():
            dialog.apply(self.config)
            self._obs_connection_changed(False, tr("Connecting…"))
            self.runner.configure_obs(self.config.obs_url, self.config.obs_password)
            self.runner.connect_obs()
            self.save_timer.stop()
            self.save()
            self.statusBar().showMessage(tr("Global OBS connection updated"), 3000)

    def connect_obs(self) -> None:
        self._obs_connection_changed(False, tr("Connecting…"))
        self.runner.connect_obs()

    def _language_selected(self) -> None:
        language = str(self.language_selector.currentData())
        if language == self.config.language:
            return
        self.config.language = language
        self.save_timer.stop()
        self.save()
        QMessageBox.information(
            self,
            tr("Restart required"),
            tr("Restart YASDEC to apply the new interface language."),
        )

    def _restart_api(self) -> None:
        self.api.stop()
        if self.config.api_enabled:
            self.api.start(self.config.api_host, self.config.api_port, self.config.api_token)
        self._update_api_snapshot()

    def _api_trigger(self, space_id: str, index: int) -> None:
        if space_id and self.config.space_by_id(space_id):
            self.select_space(space_id)
        self.trigger_key(index)

    def _update_api_snapshot(self) -> None:
        spaces = []
        for space in self.config.spaces:
            keys = [
                {
                    "index": index,
                    "label": key.label,
                    "action": key.action,
                    "active": key.active,
                    "elapsed": elapsed_text(key),
                }
                for index, key in enumerate(space.keys[: self.config.key_count])
            ]
            spaces.append({"id": space.id, "name": space.name, "keys": keys})
        self.api.update_snapshot({"model": self.config.model_id, "current_space": self.config.current_space, "spaces": spaces})

    def schedule_save(self) -> None:
        self.save_timer.start()

    def save(self) -> None:
        try:
            self.config.save(self.config_path)
            self.statusBar().showMessage(tr("Configuration saved"), 1500)
        except OSError as exc:
            self.statusBar().showMessage(tr("Could not save configuration: {error}", error=exc), 5000)

    def show_from_tray(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def show_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("About YASDEC"))
        dialog.setWindowIcon(self.windowIcon())
        dialog.setMinimumWidth(430)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)

        title = QLabel("YASDEC")
        title.setObjectName("brand")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        details = QLabel(
            "<div style='text-align:center'>"
            "Yet Another Stream Deck Controller<br><br>"
            f"{tr('Version {version}', version='0.1.0')} · neoyagami · 2026<br>"
            f"{tr('Built with AI tools')}<br>"
            f"{tr('Licensed under GNU GPLv3 or later')}<br><br>"
            "<a href='https://github.com/neoyagami/yasdec'>"
            f"{tr('Download and source code')}</a>"
            "</div>"
        )
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details.setOpenExternalLinks(True)
        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(details)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr("Close"))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_from_tray()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_close:
            event.accept()
            return
        if not self.tray_available:
            self._allow_close = True
            self.quit_app()
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage(tr("YASDEC is still running"), tr("Use the tray icon to open it again."), QSystemTrayIcon.MessageIcon.Information, 2500)

    def quit_app(self) -> None:
        self._allow_close = True
        self.save_timer.stop()
        self.save()
        self.api.stop()
        self.runner.close()
        self.deck.close()
        self.tray.hide()
        from PySide6.QtWidgets import QApplication

        QApplication.quit()
