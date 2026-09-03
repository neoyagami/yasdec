from __future__ import annotations

import configparser
import hashlib
import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QLocale, QStandardPaths
from PySide6.QtGui import QIcon

from .i18n import language_code


_ACTIVATION_URIS = {
    "discord": "discord://-/channels/@me",
}


@dataclass(frozen=True)
class DesktopApplication:
    desktop_id: str
    name: str
    icon_name: str
    desktop_file: str
    comment: str = ""

    def icon(self) -> QIcon:
        if self.icon_name:
            path = Path(self.icon_name)
            if path.is_absolute() and path.is_file():
                return QIcon(str(path))
            themed = QIcon.fromTheme(self.icon_name)
            if not themed.isNull():
                return themed
        return QIcon.fromTheme("application-x-executable")


def application_directories() -> list[Path]:
    paths = [Path(value) for value in QStandardPaths.standardLocations(QStandardPaths.StandardLocation.ApplicationsLocation)]
    desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    if desktop:
        paths.insert(0, Path(desktop))
    result: list[Path] = []
    for path in paths:
        if path not in result:
            result.append(path)
    return result


def discover_applications() -> list[DesktopApplication]:
    applications: dict[str, DesktopApplication] = {}
    for directory in application_directories():
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.desktop")):
            relative = path.relative_to(directory)
            desktop_id = str(relative).replace(os.sep, "-")
            if desktop_id in applications:
                continue
            application = read_desktop_application(path, desktop_id)
            if application is not None:
                applications[desktop_id] = application
    return sorted(applications.values(), key=lambda item: item.name.casefold())


def read_desktop_application(path: Path, desktop_id: str | None = None) -> DesktopApplication | None:
    parser = _read_desktop_file(path)
    if parser is None or not parser.has_section("Desktop Entry"):
        return None
    entry = parser["Desktop Entry"]
    if entry.get("Type", "Application") != "Application" or _truthy(entry.get("Hidden", "false")):
        return None
    # NoDisplay entries are implementation helpers, but shortcuts explicitly
    # placed on the user's desktop remain useful to a Stream Deck.
    if _truthy(entry.get("NoDisplay", "false")) and path.parent != Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    ):
        return None
    try_exec = entry.get("TryExec", "").strip()
    if try_exec and not _find_executable(try_exec):
        return None
    name = _localized(entry, "Name")
    if not name or not entry.get("Exec", "").strip():
        return None
    return DesktopApplication(
        desktop_id or path.name,
        name,
        entry.get("Icon", "").strip(),
        str(path),
        _localized(entry, "Comment"),
    )


def cache_application_icon(application: DesktopApplication) -> str:
    icon = application.icon()
    if icon.isNull():
        return ""
    root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation)
    directory = Path(root) / "SDeck" / "application-icons"
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return ""
    digest = hashlib.sha256(application.desktop_file.encode()).hexdigest()[:16]
    output = directory / f"{digest}.png"
    pixmap = icon.pixmap(256, 256)
    if pixmap.isNull() or not pixmap.save(str(output), "PNG"):
        return ""
    return str(output)


def desktop_exec(path: Path) -> tuple[str, list[str]] | None:
    """Return a no-document launch command from a freedesktop desktop entry."""
    parser = _read_desktop_file(path)
    if parser is None or not parser.has_section("Desktop Entry"):
        return None
    entry = parser["Desktop Entry"]
    try:
        tokens = shlex.split(entry.get("Exec", ""), posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    result: list[str] = []
    for token in tokens:
        if token == "%i":
            icon = entry.get("Icon", "").strip()
            if icon:
                result.extend(["--icon", icon])
            continue
        if token in {"%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%v", "%m"}:
            continue
        token = token.replace("%%", "\0")
        token = token.replace("%c", _localized(entry, "Name"))
        token = token.replace("%k", str(path))
        token = token.replace("\0", "%")
        result.append(token)
    return (result[0], result[1:]) if result else None


def desktop_activation_uri(path: Path) -> str:
    """Return an URI that asks a running single-instance app to show itself.

    Only schemes with a known safe landing page belong here.  An empty URI is
    not universally valid, so unknown handlers keep the standard desktop-entry
    launch path.
    """
    parser = _read_desktop_file(path)
    if parser is None or not parser.has_section("Desktop Entry"):
        return ""
    mime_types = parser["Desktop Entry"].get("MimeType", "").split(";")
    for mime_type in mime_types:
        prefix = "x-scheme-handler/"
        if mime_type.startswith(prefix):
            scheme = mime_type[len(prefix) :].strip().casefold()
            if scheme in _ACTIVATION_URIS:
                return _ACTIVATION_URIS[scheme]
    return ""


def _read_desktop_file(path: Path) -> configparser.ConfigParser | None:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read(path, encoding="utf-8")
    except (OSError, UnicodeError, configparser.Error):
        return None
    return parser


def _localized(entry: configparser.SectionProxy, key: str) -> str:
    selected = language_code()
    system_locale = QLocale.system().name()
    locale = system_locale if system_locale.split("_", 1)[0].casefold() == selected else selected
    for suffix in (locale, locale.split("_", 1)[0] if "_" in locale else "", ""):
        candidate = f"{key}[{suffix}]" if suffix else key
        value = entry.get(candidate, "").strip()
        if value:
            return value
    return ""


def _truthy(value: str) -> bool:
    return value.strip().casefold() == "true"


def _find_executable(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path) if path.is_file() and os.access(path, os.X_OK) else ""
    return QStandardPaths.findExecutable(value)
