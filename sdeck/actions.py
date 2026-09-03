from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QStandardPaths, QTimer, QUrl, Signal
from PySide6.QtWebSockets import QWebSocket

from .audio import AudioController
from .applications import desktop_activation_uri, desktop_exec
from .i18n import tr
from .keyboard import ShortcutError, VirtualKeyboard
from .model import ACTION_APPLICATION, ACTION_AUDIO, ACTION_KEYBOARD, ACTION_MEDIA, ACTION_MULTI, ACTION_NONE, ACTION_OBS, ACTION_SHELL, ACTION_SPACE, ACTION_SPECTRUM, ACTION_VU, ACTION_WEBSOCKET, KeyConfig, MultiActionStep
from .obs import ObsManager
from .process_environment import external_qprocess_environment
from .spectrum import SpectrumController, StereoVuController


class ActionRunner(QObject):
    key_changed = Signal(int)
    space_requested = Signal(str)
    status = Signal(str, bool)
    spectrum_levels = Signal(object)
    spectrum_mode_changed = Signal(bool, int)
    vu_levels = Signal(object)
    vu_mode_changed = Signal(bool, int)
    obs_connection_changed = Signal(bool, str)
    obs_catalog_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sockets: set[QWebSocket] = set()
        self._processes: set[QProcess] = set()
        self._multi_running: set[int] = set()
        self._multi_timers: set[QTimer] = set()
        self.keyboard = VirtualKeyboard()
        self.audio = AudioController(self)
        self.obs = ObsManager(self)
        self.spectrum = SpectrumController(self)
        self.spectrum_active = False
        self.spectrum_fullscreen = False
        self.spectrum_key: KeyConfig | None = None
        self._spectrum_device = ""
        self._spectrum_band_count = 0
        self.vu = StereoVuController(self)
        self.vu_active = False
        self.vu_fullscreen = False
        self.vu_key: KeyConfig | None = None
        self._vu_device = ""
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._emit_timer_updates)
        self._timer.start()
        self._visible_keys: list[KeyConfig] = []
        self._spectrum_columns = 1
        self._obs_url = "ws://127.0.0.1:4455"
        self._obs_password = ""
        self.audio.state_changed.connect(self._audio_state_changed)
        self.audio.targets_changed.connect(lambda _targets: self._sync_visual_previews())
        self.audio.status.connect(self.status)
        self.obs.state_changed.connect(self._obs_state_changed)
        self.obs.status.connect(self.status)
        self.obs.connection_changed.connect(self.obs_connection_changed)
        self.obs.catalog_changed.connect(self.obs_catalog_changed)
        self.spectrum.levels_changed.connect(self.spectrum_levels)
        self.spectrum.status.connect(self.status)
        self.spectrum.ended.connect(self._spectrum_ended)
        self.vu.levels_changed.connect(self.vu_levels)
        self.vu.status.connect(self.status)
        self.vu.ended.connect(self._vu_ended)

    def set_visible_keys(self, keys: list[KeyConfig], columns: int = 1) -> None:
        self._visible_keys = keys
        self._spectrum_columns = max(1, columns)
        for target in self.audio.targets:
            self._audio_state_changed(target.kind, target.target, target.muted)
        self.obs.watch(keys)
        self._sync_visual_previews()

    def configure_obs(self, url: str, password: str) -> None:
        self._obs_url = url
        self._obs_password = password
        self.obs.configure(url, password)
        self.obs.watch(self._visible_keys)

    def connect_obs(self) -> None:
        self.obs.connect_now()

    def trigger(self, index: int, key: KeyConfig, space_id: str = "") -> None:
        if key.action == ACTION_MULTI:
            self._run_multi_action(index, key, space_id)
            return
        if key.action == ACTION_SPACE:
            if key.target_space:
                self.space_requested.emit(key.target_space)
            return

        desired_state = not key.active if key.toggle else True
        executed = True
        if key.action == ACTION_SHELL:
            command = key.command if desired_state or not key.command_off.strip() else key.command_off
            executed = self._run_shell(command, index, key, space_id, desired_state)
        elif key.action == ACTION_APPLICATION:
            executed = self._run_application(key.application_desktop_file)
        elif key.action == ACTION_KEYBOARD:
            executed = self._send_keyboard(key.keyboard_shortcut)
        elif key.action == ACTION_MEDIA:
            executed = self._send_keyboard(key.media_control, media=True)
        elif key.action == ACTION_WEBSOCKET:
            payload = key.payload_on if desired_state else key.payload_off
            self._send_websocket(key.websocket_url, payload)
        elif key.action == ACTION_AUDIO:
            executed = self.audio.toggle(key.audio_kind, key.audio_target, desired_state)
        elif key.action == ACTION_OBS:
            self.obs.trigger(key.obs_operation, key.obs_scene, key.obs_target, desired_state, key.obs_group)
            executed = False
        elif key.action == ACTION_SPECTRUM:
            if key.spectrum_operation == "start":
                if self.spectrum_fullscreen and self.spectrum_key is key:
                    self.spectrum_fullscreen = False
                    self._set_state(key, False)
                    self.key_changed.emit(index)
                    if key.spectrum_preview:
                        self.spectrum_mode_changed.emit(True, max(1, min(20, key.spectrum_fps)))
                        self.status.emit(tr("Analyzer preview active"), True)
                    else:
                        self._stop_spectrum()
                    self._sync_visual_previews()
                    return
                if self.vu_active:
                    self._stop_vu()
                device = self.audio.capture_device(key.spectrum_kind, key.spectrum_target)
                band_count = self._spectrum_columns * max(1, min(3, key.spectrum_grid_size))
                if self.spectrum_active and self.spectrum_key is key and device == self._spectrum_device and band_count == self._spectrum_band_count:
                    executed = True
                else:
                    executed = self.spectrum.start(device, band_count)
                if executed:
                    self.spectrum_active = True
                    self.spectrum_fullscreen = True
                    self.spectrum_key = key
                    self._spectrum_device = device
                    self._spectrum_band_count = band_count
                    self._set_state(key, True)
                    self.spectrum_mode_changed.emit(True, max(1, min(20, key.spectrum_fps)))
                    self._set_spectrum_key_states(index)
            else:
                self._stop_spectrum()
                self.status.emit(tr("Analyzer stopped"), True)
            return
        elif key.action == ACTION_VU:
            if key.vu_operation == "start":
                if self.vu_fullscreen and self.vu_key is key:
                    self.vu_fullscreen = False
                    self._set_state(key, False)
                    self.key_changed.emit(index)
                    if key.vu_preview:
                        self.vu_mode_changed.emit(True, max(1, min(20, key.vu_fps)))
                        self.status.emit(tr("VU meter preview active"), True)
                    else:
                        self._stop_vu()
                    self._sync_visual_previews()
                    return
                if self.spectrum_active:
                    self._stop_spectrum()
                device = self.audio.capture_device(key.vu_kind, key.vu_target)
                if self.vu_active and self.vu_key is key and device == self._vu_device:
                    executed = True
                else:
                    executed = self.vu.start(device)
                if executed:
                    self.vu_active = True
                    self.vu_fullscreen = True
                    self.vu_key = key
                    self._vu_device = device
                    self._set_state(key, True)
                    self.vu_mode_changed.emit(True, max(1, min(20, key.vu_fps)))
                    self._set_vu_key_states(index)
            else:
                self._stop_vu()
                self.status.emit(tr("VU meter stopped"), True)
            return
        else:
            self.status.emit(tr("The key has no assigned action"), False)
            return

        if key.toggle and executed:
            self._set_state(key, desired_state)
        self.key_changed.emit(index)

    def _send_keyboard(self, shortcut: str, media: bool = False) -> bool:
        try:
            self.keyboard.send(shortcut)
        except ShortcutError as exc:
            self.status.emit(tr("Could not send keyboard shortcut: {error}", error=exc), False)
            return False
        except ImportError:
            self.status.emit(tr("Virtual keyboard support is not installed"), False)
            return False
        except OSError:
            self.status.emit(tr("Virtual keyboard is not configured. Install uinput permissions and sign in again."), False)
            return False
        self.status.emit(tr("Media control sent") if media else tr("Keyboard shortcut sent"), True)
        return True

    def _run_multi_action(self, index: int, key: KeyConfig, space_id: str) -> None:
        identity = id(key)
        if identity in self._multi_running:
            self.status.emit(tr("This multi action is still running"), False)
            return
        desired_state = not key.active
        steps = list(key.multi_action_in if desired_state else key.multi_action_out)
        if not steps:
            self.status.emit(tr("The selected multi action list is empty"), False)
            return
        self._multi_running.add(identity)
        self.status.emit(tr("Multi action started"), True)

        def finish() -> None:
            self._multi_running.discard(identity)
            self._set_state(key, desired_state)
            self.key_changed.emit(index)
            self.status.emit(tr("Multi action completed"), True)

        def advance(position: int) -> None:
            while position < len(steps):
                step = steps[position]
                position += 1
                if step.kind == "pause":
                    timer = QTimer(self)
                    timer.setSingleShot(True)
                    self._multi_timers.add(timer)

                    def resume(t: QTimer = timer, next_position: int = position) -> None:
                        self._multi_timers.discard(t)
                        t.deleteLater()
                        advance(next_position)

                    timer.timeout.connect(resume)
                    timer.start(max(0, step.delay_ms))
                    return
                self._run_multi_step(index, space_id, step)
            finish()

        advance(0)

    def _run_multi_step(self, index: int, space_id: str, step: MultiActionStep) -> None:
        action = KeyConfig.from_dict(step.action)
        if action.action in (ACTION_NONE, ACTION_MULTI):
            self.status.emit(tr("Skipped an invalid multi action step"), False)
            return
        if action.action == ACTION_OBS:
            self.obs.trigger(
                action.obs_operation,
                action.obs_scene,
                action.obs_target,
                step.desired_state,
                action.obs_group,
                exact=True,
            )
            return
        action.toggle = True
        action.active = not step.desired_state
        if action.action == ACTION_SPECTRUM and not step.desired_state:
            action.spectrum_operation = "stop"
        if action.action == ACTION_VU and not step.desired_state:
            action.vu_operation = "stop"
        # Reusing the normal dispatcher keeps every action type consistent.
        # The temporary state belongs to the sequence step, while the visible
        # parent key changes state only after the complete sequence finishes.
        self.trigger(index, action, space_id)

    def _run_shell(self, command: str, index: int, key: KeyConfig, space_id: str, desired_state: bool) -> bool:
        if not command.strip():
            self.status.emit(tr("The command is empty"), False)
            return False
        process = QProcess(self)
        environment = external_qprocess_environment()
        environment.insert("SDECK_TOGGLE_STATE", "on" if desired_state else "off")
        environment.insert("SDECK_TOGGLE_ACTIVE", "1" if desired_state else "0")
        environment.insert("SDECK_KEY_INDEX", str(index))
        environment.insert("SDECK_KEY_LABEL", key.label)
        environment.insert("SDECK_SPACE_ID", space_id)
        process.setProcessEnvironment(environment)
        self._processes.add(process)
        process.finished.connect(lambda *_args, p=process: self._processes.discard(p))
        process.errorOccurred.connect(lambda error: self.status.emit(tr("Shell error ({error})", error=error), False))
        process.start("/bin/sh", ["-lc", command])
        self.status.emit(tr("Command started"), True)
        return True

    def _run_application(self, desktop_file: str) -> bool:
        path = Path(desktop_file)
        if not path.is_file():
            self.status.emit(tr("The application shortcut no longer exists"), False)
            return False
        gio = QStandardPaths.findExecutable("gio")
        if gio:
            activation_uri = desktop_activation_uri(path)
            if activation_uri:
                program, arguments = gio, ["open", activation_uri]
            else:
                program, arguments = gio, ["launch", str(path)]
        else:
            launch = desktop_exec(path)
            if launch is None:
                self.status.emit(tr("The application shortcut does not contain a valid command"), False)
                return False
            program, arguments = launch
        process = QProcess(self)
        process.setProcessEnvironment(external_qprocess_environment())
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._processes.add(process)
        def finished(exit_code: int, _exit_status: QProcess.ExitStatus) -> None:
            self._processes.discard(process)
            if exit_code != 0:
                detail = bytes(process.readAllStandardOutput()).decode(errors="replace").strip()
                message = tr("Could not open the application")
                self.status.emit(f"{message}: {detail}" if detail else message, False)
            process.deleteLater()

        process.finished.connect(finished)
        process.errorOccurred.connect(lambda error: self.status.emit(tr("Could not open the application ({error})", error=error), False))
        process.start(program, arguments)
        self.status.emit(tr("Opening {name}", name=path.stem), True)
        return True

    def _send_websocket(self, url: str, payload: str) -> None:
        socket = QWebSocket()
        self._sockets.add(socket)

        def connected() -> None:
            normalized = payload.strip()
            if normalized:
                try:
                    normalized = json.dumps(json.loads(normalized), ensure_ascii=False)
                except json.JSONDecodeError:
                    pass
                socket.sendTextMessage(normalized)
            self.status.emit(tr("WebSocket message sent"), True)
            socket.close()

        def failed(_error: object) -> None:
            self.status.emit(tr("WebSocket error: {error}", error=socket.errorString()), False)
            self._sockets.discard(socket)

        socket.connected.connect(connected)
        socket.disconnected.connect(lambda: self._sockets.discard(socket))
        socket.errorOccurred.connect(failed)
        socket.open(QUrl(url))

    def _emit_timer_updates(self) -> None:
        for index, key in enumerate(self._visible_keys):
            if key.active and key.show_timer:
                self.key_changed.emit(index)

    def _audio_state_changed(self, kind: str, target: str, muted: bool) -> None:
        for index, key in enumerate(self._visible_keys):
            if key.action == ACTION_AUDIO and key.audio_kind == kind and key.audio_target == target:
                self._set_state(key, muted)
                self.key_changed.emit(index)

    def _obs_state_changed(self, operation: str, scene: str, target: str, active: bool) -> None:
        for index, key in enumerate(self._visible_keys):
            if key.action != ACTION_OBS:
                continue
            if operation == "stream":
                if key.obs_operation == "stream_start":
                    self._set_state(key, active)
                    self.key_changed.emit(index)
                elif key.obs_operation == "stream_stop" and key.active:
                    self._set_state(key, False)
                    self.key_changed.emit(index)
                continue
            if key.obs_operation != operation:
                continue
            if operation == "scene":
                desired = key.obs_target == target
                self._set_state(key, desired)
                self.key_changed.emit(index)
            elif key.obs_target == target and (not scene or key.obs_scene == scene):
                self._set_state(key, active)
                self.key_changed.emit(index)

    def _set_spectrum_key_states(self, active_index: int = -1) -> None:
        for index, item in enumerate(self._visible_keys):
            if item.action == ACTION_SPECTRUM:
                self._set_state(item, index == active_index and item.spectrum_operation == "start")
                self.key_changed.emit(index)

    def _set_vu_key_states(self, active_index: int = -1) -> None:
        for index, item in enumerate(self._visible_keys):
            if item.action == ACTION_VU:
                self._set_state(item, index == active_index and item.vu_operation == "start")
                self.key_changed.emit(index)

    def _sync_visual_previews(self) -> None:
        self.sync_spectrum_preview()
        self.sync_vu_preview()

    def sync_spectrum_preview(self) -> None:
        """Keep capture resolution and inactive preview in sync with the editor."""
        if self.vu_fullscreen:
            if self.spectrum_active:
                self._stop_spectrum()
            return
        if self.spectrum_fullscreen:
            candidate = self.spectrum_key
            if candidate is None:
                return
            device = self.audio.capture_device(candidate.spectrum_kind, candidate.spectrum_target)
            band_count = self._spectrum_columns * max(1, min(3, candidate.spectrum_grid_size))
            if not device:
                return
            if device == self._spectrum_device and band_count == self._spectrum_band_count:
                self.spectrum_mode_changed.emit(True, max(1, min(20, candidate.spectrum_fps)))
                return
            if self.spectrum.start(device, band_count):
                self.spectrum_active = True
                self._spectrum_device = device
                self._spectrum_band_count = band_count
                self.spectrum_mode_changed.emit(True, max(1, min(20, candidate.spectrum_fps)))
            return
        candidate = next((
            key for key in self._visible_keys
            if key.action == ACTION_SPECTRUM and key.spectrum_operation == "start" and key.spectrum_preview
        ), None)
        if candidate is None:
            if self.spectrum_active:
                self._stop_spectrum()
            return
        device = self.audio.capture_device(candidate.spectrum_kind, candidate.spectrum_target)
        band_count = self._spectrum_columns * max(1, min(3, candidate.spectrum_grid_size))
        if not device:
            return
        if self.spectrum_active and self.spectrum_key is candidate and device == self._spectrum_device and band_count == self._spectrum_band_count:
            return
        if self.spectrum.start(device, band_count):
            self.spectrum_active = True
            self.spectrum_fullscreen = False
            self.spectrum_key = candidate
            self._spectrum_device = device
            self._spectrum_band_count = band_count
            self._set_spectrum_key_states()
            self.spectrum_mode_changed.emit(True, max(1, min(20, candidate.spectrum_fps)))

    def sync_vu_preview(self) -> None:
        """Keep stereo capture and its inactive per-key preview synchronized."""
        if self.spectrum_fullscreen:
            if self.vu_active:
                self._stop_vu()
            return
        if self.vu_fullscreen:
            candidate = self.vu_key
            if candidate is None:
                return
            device = self.audio.capture_device(candidate.vu_kind, candidate.vu_target)
            if not device:
                return
            if device == self._vu_device:
                self.vu_mode_changed.emit(True, max(1, min(20, candidate.vu_fps)))
                return
            if self.vu.start(device):
                self.vu_active = True
                self._vu_device = device
                self.vu_mode_changed.emit(True, max(1, min(20, candidate.vu_fps)))
            return
        candidate = next((
            key for key in self._visible_keys
            if key.action == ACTION_VU and key.vu_operation == "start" and key.vu_preview
        ), None)
        if candidate is None:
            if self.vu_active:
                self._stop_vu()
            return
        device = self.audio.capture_device(candidate.vu_kind, candidate.vu_target)
        if not device:
            return
        if self.vu_active and self.vu_key is candidate and device == self._vu_device:
            return
        if self.vu.start(device):
            self.vu_active = True
            self.vu_fullscreen = False
            self.vu_key = candidate
            self._vu_device = device
            self._set_vu_key_states()
            self.vu_mode_changed.emit(True, max(1, min(20, candidate.vu_fps)))

    def _stop_spectrum(self) -> None:
        active_key = self.spectrum_key
        self.spectrum.stop()
        self.spectrum_active = False
        self.spectrum_fullscreen = False
        self.spectrum_key = None
        self._spectrum_device = ""
        self._spectrum_band_count = 0
        if active_key is not None:
            self._set_state(active_key, False)
        self._set_spectrum_key_states()
        self.spectrum_mode_changed.emit(False, 0)

    def _spectrum_ended(self) -> None:
        active_key = self.spectrum_key
        self.spectrum_active = False
        self.spectrum_fullscreen = False
        self.spectrum_key = None
        self._spectrum_device = ""
        self._spectrum_band_count = 0
        if active_key is not None:
            self._set_state(active_key, False)
        self._set_spectrum_key_states()
        self.spectrum_mode_changed.emit(False, 0)

    def _stop_vu(self) -> None:
        active_key = self.vu_key
        self.vu.stop()
        self.vu_active = False
        self.vu_fullscreen = False
        self.vu_key = None
        self._vu_device = ""
        if active_key is not None:
            self._set_state(active_key, False)
        self._set_vu_key_states()
        self.vu_mode_changed.emit(False, 0)

    def _vu_ended(self) -> None:
        active_key = self.vu_key
        self.vu_active = False
        self.vu_fullscreen = False
        self.vu_key = None
        self._vu_device = ""
        if active_key is not None:
            self._set_state(active_key, False)
        self._set_vu_key_states()
        self.vu_mode_changed.emit(False, 0)

    @staticmethod
    def _set_state(key: KeyConfig, active: bool) -> None:
        if key.active == active:
            return
        key.active = active
        key.started_at = datetime.now(timezone.utc).isoformat() if active else None

    def close(self) -> None:
        for timer in tuple(self._multi_timers):
            timer.stop()
        self._multi_timers.clear()
        self._multi_running.clear()
        self.keyboard.close()
        self.spectrum.close()
        self.vu.close()
        self.obs.close()
        for socket in tuple(self._sockets):
            socket.close()
        for process in tuple(self._processes):
            process.blockSignals(True)
        self._processes.clear()


def elapsed_text(key: KeyConfig) -> str:
    if not key.active or not key.started_at:
        return ""
    try:
        started = datetime.fromisoformat(key.started_at)
        seconds = max(0, int((datetime.now(timezone.utc) - started).total_seconds()))
    except (ValueError, TypeError):
        return ""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
