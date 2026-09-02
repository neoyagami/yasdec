from __future__ import annotations

import json
import secrets
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .i18n import tr


ACTION_NONE = "none"
ACTION_SHELL = "shell"
ACTION_WEBSOCKET = "websocket"
ACTION_SPACE = "space"
ACTION_AUDIO = "audio"
ACTION_OBS = "obs"
ACTION_SPECTRUM = "spectrum"
ACTION_VU = "vu"
ACTION_APPLICATION = "application"
ACTION_KEYBOARD = "keyboard"
ACTION_MULTI = "multi"


@dataclass
class MultiActionStep:
    kind: str = "action"
    delay_ms: int = 1000
    desired_state: bool = True
    action: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MultiActionStep":
        kind = "pause" if str(data.get("kind")) == "pause" else "action"
        try:
            delay_ms = max(0, min(3_600_000, int(data.get("delay_ms", 1000))))
        except (TypeError, ValueError):
            delay_ms = 1000
        action = data.get("action", {})
        return cls(kind, delay_ms, bool(data.get("desired_state", True)), dict(action) if isinstance(action, dict) else {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "delay_ms": self.delay_ms,
            "desired_state": self.desired_state,
            "action": dict(self.action),
        }


@dataclass
class KeyConfig:
    label: str = ""
    icon: str = ""
    active_icon: str = ""
    glyph: str = ""
    active_glyph: str = ""
    background_color: str = "#171b20"
    active_background_color: str = "#167d67"
    text_color: str = "#ffffff"
    icon_color: str = "#ffffff"
    action: str = ACTION_NONE
    command: str = ""
    command_off: str = ""
    application_desktop_file: str = ""
    keyboard_shortcut: str = "F22"
    websocket_url: str = "ws://127.0.0.1:4455"
    payload_on: str = ""
    payload_off: str = ""
    target_space: str = ""
    audio_kind: str = "sink-input"
    audio_target: str = ""
    obs_operation: str = "scene"
    obs_scene: str = ""
    obs_group: str = ""
    obs_target: str = ""
    spectrum_operation: str = "start"
    spectrum_kind: str = "sink"
    spectrum_target: str = ""
    spectrum_fps: int = 8
    spectrum_preview: bool = False
    spectrum_grid_size: int = 1
    vu_operation: str = "start"
    vu_kind: str = "sink"
    vu_target: str = ""
    vu_fps: int = 12
    vu_preview: bool = False
    vu_color_start: str = "#18f2a4"
    vu_color_end: str = "#ff3b81"
    multi_action_in: list[MultiActionStep] = field(default_factory=list)
    multi_action_out: list[MultiActionStep] = field(default_factory=list)
    toggle: bool = False
    show_timer: bool = False
    active: bool = False
    started_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KeyConfig":
        allowed = cls.__dataclass_fields__.keys()
        values = {key: value for key, value in data.items() if key in allowed}
        for name in ("multi_action_in", "multi_action_out"):
            items = values.get(name, [])
            values[name] = [MultiActionStep.from_dict(item) for item in items if isinstance(item, dict)] if isinstance(items, list) else []
        try:
            values["spectrum_grid_size"] = max(1, min(3, int(values.get("spectrum_grid_size", 1))))
        except (TypeError, ValueError):
            values["spectrum_grid_size"] = 1
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        result = {key: getattr(self, key) for key in self.__dataclass_fields__}
        result["multi_action_in"] = [step.to_dict() for step in self.multi_action_in]
        result["multi_action_out"] = [step.to_dict() for step in self.multi_action_out]
        return result


def replicate_key_config(source: KeyConfig, destination: KeyConfig) -> None:
    """Copy configured fields while keeping the destination object stable."""
    copied = KeyConfig.from_dict(source.to_dict())
    copied.active = False
    copied.started_at = None
    for field_name in KeyConfig.__dataclass_fields__:
        setattr(destination, field_name, deepcopy(getattr(copied, field_name)))


@dataclass
class Space:
    id: str
    name: str
    keys: list[KeyConfig] = field(default_factory=list)

    @classmethod
    def create(cls, name: str, key_count: int) -> "Space":
        return cls(uuid.uuid4().hex, name, [KeyConfig() for _ in range(key_count)])

    @classmethod
    def from_dict(cls, data: dict[str, Any], key_count: int) -> "Space":
        keys = [KeyConfig.from_dict(item) for item in data.get("keys", [])]
        keys += [KeyConfig() for _ in range(max(0, key_count - len(keys)))]
        return cls(str(data.get("id") or uuid.uuid4().hex), str(data.get("name") or tr("Space")), keys)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "keys": [key.to_dict() for key in self.keys]}


@dataclass
class AppConfig:
    model_id: str = "mk2"
    key_count: int = 15
    columns: int = 5
    current_space: str = ""
    spaces: list[Space] = field(default_factory=list)
    api_enabled: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = 17321
    api_token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    obs_url: str = "ws://127.0.0.1:4455"
    obs_password: str = ""
    language: str = "system"

    @classmethod
    def default(cls) -> "AppConfig":
        space = Space.create(tr("Main"), 15)
        return cls(current_space=space.id, spaces=[space])

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        if not path.exists():
            return cls.default()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            model_id = str(data.get("model_id", "mk2"))
            key_count = max(1, int(data.get("key_count", 15)))
            columns = max(1, int(data.get("columns", 5)))
            spaces = [Space.from_dict(item, key_count) for item in data.get("spaces", [])]
            if not spaces:
                return cls.default()
            current = str(data.get("current_space", ""))
            if current not in {space.id for space in spaces}:
                current = spaces[0].id
            legacy_keys = [key for space in data.get("spaces", []) for key in space.get("keys", [])]
            legacy_obs = next((key for key in legacy_keys if key.get("obs_url") or key.get("obs_password")), {})
            return cls(
                model_id, key_count, columns, current, spaces,
                bool(data.get("api_enabled", True)),
                str(data.get("api_host", "127.0.0.1")),
                int(data.get("api_port", 17321)),
                str(data.get("api_token") or secrets.token_urlsafe(24)),
                str(data.get("obs_url") or legacy_obs.get("obs_url") or "ws://127.0.0.1:4455"),
                str(data.get("obs_password") if "obs_password" in data else legacy_obs.get("obs_password", "")),
                str(data.get("language", "system")),
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return cls.default()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "model_id": self.model_id,
            "key_count": self.key_count,
            "columns": self.columns,
            "current_space": self.current_space,
            "spaces": [space.to_dict() for space in self.spaces],
            "api_enabled": self.api_enabled,
            "api_host": self.api_host,
            "api_port": self.api_port,
            "api_token": self.api_token,
            "obs_url": self.obs_url,
            "obs_password": self.obs_password,
            "language": self.language,
        }
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    def current(self) -> Space:
        return next((space for space in self.spaces if space.id == self.current_space), self.spaces[0])

    def space_by_id(self, space_id: str) -> Space | None:
        return next((space for space in self.spaces if space.id == space_id), None)

    def add_space(self, name: str) -> Space:
        space = Space.create(name, self.key_count)
        self.spaces.append(space)
        return space

    def duplicate_space(self, source: Space, name: str) -> Space:
        space = Space(uuid.uuid4().hex, name, deepcopy(source.keys))
        self.spaces.append(space)
        return space

    def apply_layout(self, model_id: str, key_count: int, columns: int) -> None:
        self.model_id = model_id
        self.key_count = key_count
        self.columns = columns
        for space in self.spaces:
            current = len(space.keys)
            if current < key_count:
                space.keys.extend(KeyConfig() for _ in range(key_count - current))
