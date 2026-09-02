from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QLocale


_catalog: dict[str, str] = {}
_language = "en"


def set_language(preference: str) -> str:
    global _catalog, _language
    if preference == "system":
        system = QLocale.system().name().split("_", 1)[0].casefold()
        language = "es" if system == "es" else "en"
    else:
        language = preference if preference in {"es", "en"} else "en"
    path = Path(__file__).resolve().parent.parent / "assets" / "i18n" / f"{language}.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        _catalog = loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError, TypeError):
        _catalog = {}
    _language = language
    return language


def language_code() -> str:
    return _language


def tr(source: str, **values: object) -> str:
    translated = _catalog.get(source, source)
    return translated.format(**values) if values else translated
