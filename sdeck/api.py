from __future__ import annotations

import base64
import hmac
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from PySide6.QtCore import QObject, Signal

from .i18n import tr


def token_from_headers(headers: Any) -> str:
    supplied = headers.get("X-SDeck-Token", "")
    authorization = headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        supplied = authorization[7:]
    elif authorization.startswith("Basic "):
        try:
            decoded = base64.b64decode(authorization[6:]).decode()
            username, _, password = decoded.partition(":")
            supplied = password or username
        except (ValueError, UnicodeDecodeError):
            supplied = ""
    return supplied


class ApiServer(QObject):
    trigger_requested = Signal(str, int)
    status = Signal(str, bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.token = ""
        self._snapshot: dict[str, Any] = {}
        self._lock = threading.Lock()

    def update_snapshot(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            self._snapshot = snapshot

    def start(self, host: str, port: int, token: str) -> bool:
        self.stop()
        self.token = token
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if not self._authorized():
                    return
                if self.path == "/api/v1/state":
                    with owner._lock:
                        self._json(200, owner._snapshot)
                else:
                    self._json(404, {"error": "not_found"})

            def do_POST(self) -> None:
                if not self._authorized():
                    return
                match = re.fullmatch(r"/api/v1/(?:spaces/([^/]+)/)?keys/(\d+)/press", self.path)
                if not match:
                    self._json(404, {"error": "not_found"})
                    return
                space_id = match.group(1) or ""
                index = int(match.group(2))
                with owner._lock:
                    snapshot = owner._snapshot
                    wanted = space_id or snapshot.get("current_space", "")
                    space = next((item for item in snapshot.get("spaces", []) if item.get("id") == wanted), None)
                    valid = space is not None and 0 <= index < len(space.get("keys", []))
                if not valid:
                    self._json(404, {"error": "key_not_found"})
                    return
                owner.trigger_requested.emit(space_id, index)
                self._json(202, {"accepted": True})

            def _authorized(self) -> bool:
                supplied = token_from_headers(self.headers)
                if not owner.token or not hmac.compare_digest(supplied, owner.token):
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Bearer realm="YASDEC"')
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return False
                return True

            def _json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        try:
            self.server = ThreadingHTTPServer((host, port), Handler)
        except OSError as exc:
            self.status.emit(tr("Could not start the API: {error}", error=exc), False)
            return False
        self.thread = threading.Thread(target=self.server.serve_forever, name="sdeck-api", daemon=True)
        self.thread.start()
        self.status.emit(tr("API active at http://{host}:{port}", host=host, port=port), True)
        return True

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.server = None
        self.thread = None
