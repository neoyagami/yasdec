from __future__ import annotations

import base64
import hashlib
import json
import uuid

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtNetwork import QAbstractSocket

from .i18n import tr


class ObsConnection(QObject):
    status = Signal(str, bool)
    state_changed = Signal(str, str, str, bool)
    connection_changed = Signal(bool, str)
    catalog_changed = Signal(object)

    def __init__(self, url: str, password: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.url = url
        self.password = password
        self.socket = QWebSocket()
        self.identified = False
        self.queue: list[tuple[str, dict, dict]] = []
        self.pending: dict[str, dict] = {}
        self.scene_items: dict[tuple[str, int], tuple[str, str]] = {}
        self.scenes: list[str] = []
        self.sources: dict[str, list[str]] = {}
        self.groups: dict[str, dict[str, list[str]]] = {}
        self.inputs: list[str] = []
        self.socket.connected.connect(lambda: self.connection_changed.emit(False, tr("Authenticating…")))
        self.socket.disconnected.connect(self._disconnected)
        self.socket.textMessageReceived.connect(self._message)
        self.socket.errorOccurred.connect(self._socket_error)
        self.socket.open(QUrl(url))

    def _socket_error(self, _error: object) -> None:
        message = self.socket.errorString()
        self.status.emit(f"OBS: {message}", False)
        self.connection_changed.emit(False, message)

    def _disconnected(self) -> None:
        self.identified = False
        self.pending.clear()
        self.connection_changed.emit(False, tr("Disconnected"))

    def connect_now(self) -> None:
        if self.socket.state() == QAbstractSocket.SocketState.UnconnectedState:
            self.connection_changed.emit(False, tr("Connecting…"))
            self.socket.open(QUrl(self.url))

    def request(self, request_type: str, data: dict, context: dict | None = None) -> None:
        item = (request_type, data, context or {})
        if not self.identified:
            self.queue.append(item)
            if self.socket.state() == QAbstractSocket.SocketState.UnconnectedState:
                self.socket.open(QUrl(self.url))
            return
        self._send_request(*item)

    def _message(self, text: str) -> None:
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            return
        op = message.get("op")
        data = message.get("d") or {}
        if op == 0:
            # Scenes, inputs, outputs and scene items are used by assigned keys.
            identify: dict = {"rpcVersion": 1, "eventSubscriptions": (1 << 2) | (1 << 3) | (1 << 6) | (1 << 7)}
            authentication = data.get("authentication")
            if authentication:
                secret = hashlib.sha256((self.password + authentication["salt"]).encode()).digest()
                encoded = base64.b64encode(secret).decode()
                answer = hashlib.sha256((encoded + authentication["challenge"]).encode()).digest()
                identify["authentication"] = base64.b64encode(answer).decode()
            self.socket.sendTextMessage(json.dumps({"op": 1, "d": identify}))
        elif op == 2:
            self.identified = True
            self.status.emit(tr("Connected to OBS"), True)
            self.connection_changed.emit(True, tr("Connected"))
            queued, self.queue = self.queue, []
            for item in queued:
                self._send_request(*item)
            self.request("GetSceneList", {})
            self.request("GetInputList", {})
            self.request("GetStreamStatus", {}, {"operation": "stream"})
        elif op == 5:
            self._event(data.get("eventType", ""), data.get("eventData") or {})
        elif op == 7:
            self._response(data)

    def _send_request(self, request_type: str, data: dict, context: dict) -> None:
        request_id = uuid.uuid4().hex
        self.pending[request_id] = {"request_type": request_type, **context}
        payload = {"op": 6, "d": {"requestType": request_type, "requestId": request_id, "requestData": data}}
        self.socket.sendTextMessage(json.dumps(payload))

    def _response(self, data: dict) -> None:
        context = self.pending.pop(str(data.get("requestId", "")), {})
        status = data.get("requestStatus") or {}
        if not status.get("result", False):
            self.status.emit(f"OBS: {status.get('comment', tr('request rejected'))}", False)
            return
        response = data.get("responseData") or {}
        request_type = context.get("request_type")
        if request_type == "GetSceneList":
            self.scenes = [str(scene.get("sceneName", "")) for scene in response.get("scenes", []) if scene.get("sceneName")]
            self.sources = {scene: self.sources.get(scene, []) for scene in self.scenes}
            self.groups = {scene: self.groups.get(scene, {}) for scene in self.scenes}
            self._emit_catalog()
            for scene in self.scenes:
                self.request("GetSceneItemList", {"sceneName": scene}, {"scene": scene})
        elif request_type == "GetInputList":
            self.inputs = [str(item.get("inputName", "")) for item in response.get("inputs", []) if item.get("inputName")]
            self._emit_catalog()
        elif request_type == "GetSceneItemList":
            scene = str(context.get("scene", ""))
            items = response.get("sceneItems", [])
            self.sources[scene] = list(dict.fromkeys(
                str(item.get("sourceName", "")) for item in items if item.get("sourceName")
            ))
            group_names = [str(item.get("sourceName", "")) for item in items if item.get("sourceName") and item.get("isGroup")]
            self.groups[scene] = {group: self.groups.get(scene, {}).get(group, []) for group in group_names}
            for group in group_names:
                self.request("GetGroupSceneItemList", {"sceneName": group}, {"scene": scene, "group": group})
            self._emit_catalog()
        elif request_type == "GetGroupSceneItemList":
            scene = str(context.get("scene", ""))
            group = str(context.get("group", ""))
            self.groups.setdefault(scene, {})[group] = list(dict.fromkeys(
                str(item.get("sourceName", "")) for item in response.get("sceneItems", []) if item.get("sourceName")
            ))
            self._emit_catalog()
        elif request_type == "GetStreamStatus":
            self.state_changed.emit("stream", "", "", bool(response.get("outputActive")))
        elif request_type == "GetSceneItemId":
            item_id = response.get("sceneItemId")
            container = str(context.get("container") or context.get("scene", ""))
            if isinstance(item_id, int):
                self.scene_items[(container, item_id)] = (context["scene"], context["target"])
            if "desired" in context:
                self.request(
                    "SetSceneItemEnabled",
                    {"sceneName": container, "sceneItemId": item_id, "sceneItemEnabled": context["desired"]},
                    {"operation": "source", "scene": context["scene"], "target": context["target"], "desired": context["desired"]},
                )
            else:
                self.request(
                    "GetSceneItemEnabled",
                    {"sceneName": container, "sceneItemId": item_id},
                    {"operation": "source", "scene": context["scene"], "container": container, "target": context["target"], "toggle": context.get("toggle", False), "scene_item_id": item_id},
                )
        elif request_type == "GetSceneItemEnabled":
            current = bool(response.get("sceneItemEnabled"))
            if context.get("toggle"):
                desired = not current
                self.request(
                    "SetSceneItemEnabled",
                    {"sceneName": context["container"], "sceneItemId": context["scene_item_id"], "sceneItemEnabled": desired},
                    {"operation": "source", "scene": context["scene"], "target": context["target"], "desired": desired},
                )
            else:
                self.state_changed.emit("source", context["scene"], context["target"], current)
        elif request_type == "GetInputMute":
            self.state_changed.emit("input_mute", "", context["target"], bool(response.get("inputMuted")))
        elif request_type == "SetInputMute":
            self.state_changed.emit("input_mute", "", context["target"], bool(context["desired"]))
        elif request_type == "SetSceneItemEnabled":
            self.state_changed.emit("source", context["scene"], context["target"], bool(context["desired"]))
        elif request_type == "SetCurrentProgramScene":
            self.state_changed.emit("scene", "", context["target"], True)
        elif request_type in ("StartStream", "StopStream"):
            self.state_changed.emit("stream", "", "", request_type == "StartStream")
        elif context.get("request_type") == "GetCurrentProgramScene":
            self.state_changed.emit("scene", "", str(response.get("currentProgramSceneName", "")), True)
        self.status.emit(tr("OBS updated"), True)

    def _emit_catalog(self) -> None:
        self.catalog_changed.emit({"scenes": list(self.scenes), "sources": dict(self.sources), "groups": dict(self.groups), "inputs": list(self.inputs)})

    def _event(self, event_type: str, data: dict) -> None:
        if event_type == "InputMuteStateChanged":
            self.state_changed.emit("input_mute", "", str(data.get("inputName", "")), bool(data.get("inputMuted")))
        elif event_type == "SceneItemEnableStateChanged":
            scene = str(data.get("sceneName", ""))
            item_id = data.get("sceneItemId")
            mapped = self.scene_items.get((scene, item_id))
            if mapped:
                original_scene, target = mapped
                self.state_changed.emit("source", original_scene, target, bool(data.get("sceneItemEnabled")))
        elif event_type == "CurrentProgramSceneChanged":
            self.state_changed.emit("scene", "", str(data.get("sceneName", "")), True)
        elif event_type == "StreamStateChanged":
            self.state_changed.emit("stream", "", "", bool(data.get("outputActive")))

    def close(self) -> None:
        self.socket.close()


class ObsManager(QObject):
    status = Signal(str, bool)
    state_changed = Signal(str, str, str, bool)
    connection_changed = Signal(bool, str)
    catalog_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.connections: dict[tuple[str, str], ObsConnection] = {}
        self.url = "ws://127.0.0.1:4455"
        self.password = ""

    def configure(self, url: str, password: str) -> None:
        if (url, password) == (self.url, self.password):
            return
        for connection in self.connections.values():
            connection.close()
        self.connections.clear()
        self.catalog_changed.emit({"scenes": [], "sources": {}, "groups": {}, "inputs": []})
        self.url = url
        self.password = password

    def connection(self, url: str, password: str) -> ObsConnection:
        key = (url, password)
        if key not in self.connections:
            connection = ObsConnection(url, password, self)
            connection.status.connect(self.status)
            connection.state_changed.connect(self.state_changed)
            connection.connection_changed.connect(self.connection_changed)
            connection.catalog_changed.connect(self.catalog_changed)
            self.connections[key] = connection
        return self.connections[key]

    def connect_now(self) -> None:
        self.connection(self.url, self.password).connect_now()

    def trigger(self, operation: str, scene: str, target: str, desired: bool, group: str = "", exact: bool = False) -> None:
        connection = self.connection(self.url, self.password)
        if operation == "scene":
            selected = target or scene
            connection.request("SetCurrentProgramScene", {"sceneName": selected}, {"target": selected})
        elif operation == "source":
            container = group or scene
            context = {"scene": scene, "container": container, "target": target}
            if exact:
                context["desired"] = desired
            else:
                context["toggle"] = True
            connection.request(
                "GetSceneItemId",
                {"sceneName": container, "sourceName": target},
                context,
            )
        elif operation == "input_mute":
            connection.request(
                "SetInputMute",
                {"inputName": target, "inputMuted": desired},
                {"target": target, "desired": desired},
            )
        elif operation == "stream_start":
            connection.request("StartStream", {})
        elif operation == "stream_stop":
            connection.request("StopStream", {})

    def watch(self, keys: list[object]) -> None:
        stream_status_requested = False
        for key in keys:
            if getattr(key, "action", "") != "obs":
                continue
            connection = self.connection(self.url, self.password)
            if key.obs_operation == "scene":
                connection.request("GetCurrentProgramScene", {}, {"operation": "scene"})
            elif key.obs_operation == "input_mute" and key.obs_target:
                connection.request("GetInputMute", {"inputName": key.obs_target}, {"operation": "input_mute", "target": key.obs_target})
            elif key.obs_operation == "source" and key.obs_scene and key.obs_target:
                container = getattr(key, "obs_group", "") or key.obs_scene
                connection.request(
                    "GetSceneItemId",
                    {"sceneName": container, "sourceName": key.obs_target},
                    {"operation": "source", "scene": key.obs_scene, "container": container, "target": key.obs_target},
                )
            elif key.obs_operation in ("stream_start", "stream_stop") and not stream_status_requested:
                connection.request("GetStreamStatus", {}, {"operation": "stream"})
                stream_status_requested = True

    def close(self) -> None:
        for connection in self.connections.values():
            connection.close()
        self.connections.clear()
