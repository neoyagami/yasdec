#!/usr/bin/env python3
"""Generate deterministic README screenshots from the real Qt interface."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from sdeck.app import STYLESHEET
from sdeck.i18n import set_language
from sdeck.model import ACTION_AUDIO, ACTION_KEYBOARD, ACTION_OBS, ACTION_SHELL, ACTION_SPECTRUM, ACTION_VU, AppConfig
from sdeck.window import MainWindow


OUTPUT_DIR = PROJECT_DIR / "docs" / "screenshots"


def icon(name: str) -> str:
    return str(PROJECT_DIR / "assets" / "icons" / "lucide" / f"{name}.svg")


def sample_config(path: Path) -> None:
    config = AppConfig.default()
    config.language = "en"
    config.api_enabled = False
    keys = config.current().keys
    samples = (
        ("Live", "radio", ACTION_OBS),
        ("Scene", "panels-top-left", ACTION_OBS),
        ("Mic", "mic", ACTION_AUDIO),
        ("Music", "music", ACTION_AUDIO),
        ("Spectrum", "audio-waveform", ACTION_SPECTRUM),
        ("Camera", "camera", ACTION_OBS),
        ("Terminal", "terminal", ACTION_SHELL),
        ("F22", "command", ACTION_KEYBOARD),
        ("Monitor", "monitor", ACTION_SHELL),
        ("Mute", "volume-x", ACTION_AUDIO),
        ("Previous", "arrow-left", ACTION_KEYBOARD),
        ("Play", "circle-play", ACTION_KEYBOARD),
        ("Pause", "pause", ACTION_KEYBOARD),
        ("Next", "arrow-right", ACTION_KEYBOARD),
        ("Stereo VU", "sliders-horizontal", ACTION_VU),
    )
    for key, (label, icon_name, action) in zip(keys, samples):
        key.label = label
        key.icon = icon(icon_name)
        key.action = action
    keys[0].obs_operation = "stream_start"
    keys[1].obs_operation = "scene"
    keys[1].obs_scene = "Program"
    keys[2].audio_kind = "source"
    keys[4].spectrum_operation = "start"
    keys[4].spectrum_grid_size = 3
    keys[4].spectrum_preview = True
    keys[7].keyboard_shortcut = "CTRL+ALT+F22"
    keys[10].keyboard_shortcut = "CTRL+LEFT"
    keys[11].keyboard_shortcut = "PLAYPAUSE"
    keys[12].keyboard_shortcut = "F13"
    keys[13].keyboard_shortcut = "CTRL+RIGHT"
    keys[14].vu_operation = "start"
    keys[14].vu_preview = True
    keys[14].vu_color_start = "#00f5b8"
    keys[14].vu_color_end = "#ff2d95"
    config.save(path)


def settle(app: QApplication, window: MainWindow) -> None:
    window.device_status.setText("●  Stream Deck MK.2")
    window.device_status.setProperty("connected", True)
    window.device_status.style().polish(window.device_status)
    window.obs_status.setText("●  OBS")
    window.obs_status.setProperty("connected", True)
    window.obs_status.style().polish(window.obs_status)
    for _ in range(4):
        app.processEvents()
    window.statusBar().showMessage("Ready")
    app.processEvents()


def save(window: MainWindow, name: str) -> None:
    destination = OUTPUT_DIR / name
    if not window.grab().save(str(destination), "PNG"):
        raise RuntimeError(f"Could not save {destination}")


@patch("sdeck.window.DeckBackend.connect_device")
@patch("sdeck.window.ActionRunner.configure_obs")
@patch("sdeck.audio.AudioController.refresh")
def main(_audio_refresh, _configure_obs, _connect_device) -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    set_language("en")
    app = QApplication([])
    app.setApplicationName("YASDEC")
    app.setApplicationDisplayName("YASDEC — Yet Another Stream Deck Controller")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    app_icon = QIcon(str(PROJECT_DIR / "assets" / "sdeck.svg"))

    with tempfile.TemporaryDirectory(prefix="yasdec-screenshots-") as directory:
        config_path = Path(directory) / "config.json"
        sample_config(config_path)
        window = MainWindow(config_path, app_icon)
        window.resize(1440, 900)
        window.show()
        settle(app, window)

        window.select_key(0)
        settle(app, window)
        save(window, "yasdec-main.png")

        window.select_key(7)
        settle(app, window)
        save(window, "yasdec-shortcut-recorder.png")

        analyzer_key = window.config.current().keys[4]
        window.select_key(4)
        window.runner.spectrum_key = analyzer_key
        window.runner.spectrum_active = True
        window.runner.spectrum_fullscreen = True
        window.spectrum_levels = [0.24, 0.38, 0.58, 0.78, 0.92, 0.72, 0.49, 0.66, 0.88, 0.63, 0.42, 0.76, 0.96, 0.68, 0.34]
        window._draw_spectrum()
        settle(app, window)
        save(window, "yasdec-spectrum-lcd.png")

        vu_key = window.config.current().keys[14]
        window.runner.spectrum_active = False
        window.runner.spectrum_fullscreen = False
        window.runner.vu_key = vu_key
        window.runner.vu_active = True
        window.runner.vu_fullscreen = True
        window.vu_levels = (0.86, 0.57)
        window.select_key(14)
        window._draw_vu()
        settle(app, window)
        save(window, "yasdec-vu-stereo.png")

        window.runner.close()
        window.deck.close()
        window.api.stop()
        window.hide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
