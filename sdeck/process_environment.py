from __future__ import annotations

import os
import sys
from collections.abc import Mapping

from PySide6.QtCore import QProcessEnvironment


def external_process_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Remove bundled runtime settings before launching a system program."""
    environment = dict(os.environ if source is None else source)
    # Activation identifiers belong to the interaction that launched YASDEC.
    # They are single-use and must not leak into unrelated applications started
    # later from a Stream Deck key.
    environment.pop("XDG_ACTIVATION_TOKEN", None)
    environment.pop("DESKTOP_STARTUP_ID", None)
    original_library_path = environment.pop("LD_LIBRARY_PATH_ORIG", None)
    if original_library_path is None:
        environment.pop("LD_LIBRARY_PATH", None)
    else:
        environment["LD_LIBRARY_PATH"] = original_library_path
    # PyInstaller's Qt hook points these at the bundled PySide6 plugins.
    # Host Qt programs such as kstart must discover their own plugins: mixing
    # host Qt libraries with bundled plugins can abort before main runs.
    if getattr(sys, "frozen", False) or environment.get("APPDIR"):
        environment.pop("QT_PLUGIN_PATH", None)
        environment.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)
    return environment


def external_qprocess_environment() -> QProcessEnvironment:
    environment = QProcessEnvironment()
    for name, value in external_process_environment().items():
        environment.insert(name, value)
    return environment
