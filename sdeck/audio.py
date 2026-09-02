from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal

from .i18n import tr


@dataclass(frozen=True)
class AudioTarget:
    kind: str
    target: str
    label: str
    muted: bool
    capture_device: str = ""


PACTL_TYPES = {
    "sink": ("sinks", "set-sink-mute"),
    "source": ("sources", "set-source-mute"),
    "sink-input": ("sink-inputs", "set-sink-input-mute"),
    "source-output": ("source-outputs", "set-source-output-mute"),
}


class AudioController(QObject):
    targets_changed = Signal(object)
    state_changed = Signal(str, str, bool)
    status = Signal(str, bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.targets: list[AudioTarget] = []
        self.timer = QTimer(self)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        QTimer.singleShot(0, self.refresh)

    def refresh(self) -> None:
        discovered: list[AudioTarget] = []
        try:
            for kind, (plural, _command) in PACTL_TYPES.items():
                result = subprocess.run(
                    ["pactl", "-f", "json", "list", plural],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                if result.returncode != 0:
                    continue
                for item in json.loads(result.stdout or "[]"):
                    properties = item.get("properties") or {}
                    target = str(item.get("name") if kind in ("sink", "source") else item.get("index", ""))
                    label = (
                        properties.get("application.name")
                        or item.get("description")
                        or properties.get("device.description")
                        or target
                    )
                    if kind in ("sink-input", "source-output"):
                        media = properties.get("media.name")
                        label = f"{label} · {media}" if media and media != label else label
                    capture_device = ""
                    if kind == "sink":
                        capture_device = str(item.get("monitor_source_name") or f"{target}.monitor")
                    elif kind == "source":
                        capture_device = target
                    discovered.append(AudioTarget(kind, target, str(label), bool(item.get("mute", False)), capture_device))
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            self.status.emit(tr("Could not query PipeWire/PulseAudio: {error}", error=exc), False)
            return

        changed = discovered != self.targets
        self.targets = discovered
        if changed:
            self.targets_changed.emit(discovered)
        for target in discovered:
            self.state_changed.emit(target.kind, target.target, target.muted)

    def toggle(self, kind: str, target: str, desired_muted: bool) -> bool:
        if kind not in PACTL_TYPES or not target:
            self.status.emit(tr("Select a valid audio channel"), False)
            return False
        command = PACTL_TYPES[kind][1]
        try:
            result = subprocess.run(
                ["pactl", command, target, "1" if desired_muted else "0"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.status.emit(tr("Audio error: {error}", error=exc), False)
            return False
        ok = result.returncode == 0
        self.status.emit(tr("Audio channel updated") if ok else (result.stderr.strip() or tr("Could not update the channel")), ok)
        if ok:
            self.state_changed.emit(kind, target, desired_muted)
            QTimer.singleShot(200, self.refresh)
        return ok

    def capture_device(self, kind: str, target: str) -> str:
        match = next((item for item in self.targets if item.kind == kind and item.target == target), None)
        return match.capture_device if match else ""
