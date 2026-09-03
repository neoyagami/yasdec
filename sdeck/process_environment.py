from __future__ import annotations

import os
from collections.abc import Mapping

from PySide6.QtCore import QProcessEnvironment


def external_process_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Restore the host library path before launching a system program."""
    environment = dict(os.environ if source is None else source)
    original_library_path = environment.pop("LD_LIBRARY_PATH_ORIG", None)
    if original_library_path is None:
        environment.pop("LD_LIBRARY_PATH", None)
    else:
        environment["LD_LIBRARY_PATH"] = original_library_path
    return environment


def external_qprocess_environment() -> QProcessEnvironment:
    environment = QProcessEnvironment()
    for name, value in external_process_environment().items():
        environment.insert(name, value)
    return environment
