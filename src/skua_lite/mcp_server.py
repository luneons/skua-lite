"""Minimal, read-only MCP HTTP/SSE transport using only the Python stdlib.

The server is intentionally independent from the game client: it can be run as
an explicit local status endpoint without logging in or executing commands.
"""
from __future__ import annotations

import hmac
import json
import math
import queue
import re
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from . import __version__

JSON = dict[str, Any]
PROTOCOL_VERSION = "2024-11-05"


class MCPService:
    """MCP JSON-RPC methods and the small SSE session registry."""

    def __init__(
        self,
        status_provider: Callable[[], Any] | None = None,
        max_sessions: int = 32,
        session_idle_timeout: float = 120.0,
        queue_size: int = 64,
    ):
        if not isinstance(max_sessions, int) or isinstance(max_sessions, bool) or max_sessions < 1:
            raise ValueError("max_sessions must be an integer >= 1")
        if not isinstance(queue_size, int) or isinstance(queue_size, bool) or queue_size < 1:
            raise ValueError("queue_size must be an integer >= 1")
        if not isinstance(session_idle_timeout, (int, float)) or isinstance(session_idle_timeout, bool):
            raise ValueError("session_idle_timeout must be a finite number > 0")
        if not math.isfinite(session_idle_timeout) or session_idle_timeout <= 0:
            raise ValueError("session_idle_timeout must be a finite number > 0")
        self.status_provider = status_provider or (lambda: {"status": "ok"})
        self.max_sessions = max_sessions
        self.session_idle_timeout = session_idle_timeout
        self.queue_size = queue_size
        self._sessions: dict[str, queue.Queue[bytes]] = {}
        self._last_activity: dict[str, float] = {}
        self._lock = threading.Lock()

    def _cleanup_idle_locked(self, now: float) -> None:
        for session_id, last_activity in list(self._last_activity.items()):
            if now - last_activity >= self.session_idle_timeout:
                self._sessions.pop(session_id, None)
                self._last_activity.pop(session_id, None)

    def new_session(self) -> tuple[str, queue.Queue[bytes]] | None:
        now = time.monotonic()
        with self._lock:
            self._cleanup_idle_locked(now)
            if len(self._sessions) >= self.max_sessions:
                return None
            session_id = secrets.token_urlsafe(18)
            channel: queue.Queue[bytes] = queue.Queue(maxsize=self.queue_size)
            self._sessions[session_id] = channel
            self._last_activity[session_id] = now
        return session_id, channel

    def has_session(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def touch_session(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                self._last_activity[session_id] = time.monotonic()

    def session_expired(self, session_id: str) -> bool:
        with self._lock:
            last_activity = self._last_activity.get(session_id)
            return last_activity is None or time.monotonic() - last_activity >= self.session_idle_timeout

    def close_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
            self._last_activity.pop(session_id, None)

    def publish(self, session_id: str, payload: bytes) -> str:
        with self._lock:
            channel = self._sessions.get(session_id)
            if channel is None:
                return "not_found"
            try:
                channel.put_nowait(payload)
            except queue.Full:
                return "queue_full"
            self._last_activity[session_id] = time.monotonic()
            return "ok"

    def request(self, request: JSON) -> JSON | None:
        """Handle the basic MCP methods; return None for JSON-RPC notifications."""
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return self._error(request_id, -32600, "Invalid Request")
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "skua-lite", "version": __version__},
            }
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            result = {"tools": [{
                "name": "health",
                "description": "Return a safe, read-only server status snapshot.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            }]}
        elif method == "tools/call":
            if not isinstance(params, dict) or params.get("name") != "health":
                return self._error(request_id, -32602, "Unknown tool")
            try:
                value = self.status_provider()
                json.dumps(value)  # validate provider output before embedding it
            except Exception:
                return self._error(request_id, -32603, "Status unavailable")
            result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}], "isError": False}
        else:
            return self._error(request_id, -32601, "Method not found")
        if "id" not in request:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> JSON:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class _MCPHTTPServer(ThreadingHTTPServer):
    def __init__(self, *args: Any, max_connections: int = 64, **kwargs: Any):
        self._connection_slots = threading.BoundedSemaphore(max_connections)
        self._active_connections = 0
        self._active_connections_lock = threading.Lock()
        super().__init__(*args, **kwargs)

    @property
    def active_connections(self) -> int:
        with self._active_connections_lock:
            return self._active_connections

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._connection_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        with self._active_connections_lock:
            self._active_connections += 1
        try:
            super().process_request(request, client_address)
        except BaseException:
            with self._active_connections_lock:
                self._active_connections -= 1
            self._connection_slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self._active_connections_lock:
                self._active_connections -= 1
            self._connection_slots.release()

class _MCPHandler(BaseHTTPRequestHandler):
    server_version = "skua-lite-mcp/1"
    timeout = 10.0

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(self.server.request_timeout)  # type: ignore[attr-defined]

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        scheme, separator, supplied = header.partition(" ")
        if not separator or scheme.lower() != "bearer":
            supplied = ""
        expected = self.server.mcp_token  # type: ignore[attr-defined]
        # Compare even malformed/empty values; never use a normal equality check.
        return hmac.compare_digest(supplied.encode(), expected.encode()) and bool(supplied)

    def _send_json(self, payload: JSON, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _reject(self, status: int) -> None:
        # Deliberately generic: never echo Authorization or request details.
        if status == HTTPStatus.UNAUTHORIZED:
            data = json.dumps({"error": "unauthorized"}).encode("utf-8")
            self.send_response(status)
            self.send_header("WWW-Authenticate", "Bearer")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        self._send_json({"error": "not found"}, status)

    def _no_content(self, status: int = HTTPStatus.ACCEPTED) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            self._reject(HTTPStatus.UNAUTHORIZED)
            return
        if urlparse(self.path).path != "/sse":
            self._reject(HTTPStatus.NOT_FOUND)
            return
        session = self.server.mcp_service.new_session()  # type: ignore[attr-defined]
        if session is None:
            data = b'{"error": "too many sessions"}'
            self.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
            self.send_header("Retry-After", "1")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        session_id, channel = session
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            self.wfile.write(f"event: endpoint\ndata: /messages?session_id={session_id}\n\n".encode())
            self.wfile.flush()
            while True:
                try:
                    payload = channel.get(timeout=self.server.keepalive_interval)  # type: ignore[attr-defined]
                    self.server.mcp_service.touch_session(session_id)  # type: ignore[attr-defined]
                    self.wfile.write(b"event: message\ndata: " + payload + b"\n\n")
                except queue.Empty:
                    if self.server.mcp_service.session_expired(session_id):  # type: ignore[attr-defined]
                        break
                    self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.server.mcp_service.close_session(session_id)  # type: ignore[attr-defined]

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._reject(HTTPStatus.UNAUTHORIZED)
            return
        if urlparse(self.path).path != "/messages":
            self._reject(HTTPStatus.NOT_FOUND)
            return
        try:
            query = parse_qs(urlparse(self.path).query, keep_blank_values=True, strict_parsing=True)
            values = query.get("session_id", [])
            session_id = values[0] if len(values) == 1 else ""
            if len(values) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", session_id):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            self._send_json({"error": "invalid session_id"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if length < 0 or length > 1_048_576:
                raise ValueError
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict):
                raise ValueError
        except (ValueError, TypeError, json.JSONDecodeError):
            self._send_json({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, 400)
            return
        service = self.server.mcp_service  # type: ignore[attr-defined]
        if not service.has_session(session_id):
            self._send_json({"error": "session not found"}, HTTPStatus.NOT_FOUND)
            return
        response = service.request(request)
        if response is None:
            self._no_content(HTTPStatus.NO_CONTENT)
            return
        result = service.publish(session_id, json.dumps(response, ensure_ascii=False).encode("utf-8"))
        if result == "not_found":
            self._send_json({"error": "session not found"}, HTTPStatus.NOT_FOUND)
        elif result == "queue_full":
            self.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
            self.send_header("Retry-After", "1")
            self.send_header("Content-Type", "application/json")
            data = b'{"error": "session queue full"}'
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._no_content()

    def log_message(self, fmt: str, *args: Any) -> None:
        # Avoid access logs containing paths/query strings or accidental secrets.
        return


def create_server(
    host: str,
    port: int,
    token: str,
    status_provider: Callable[[], Any] | None = None,
    *,
    max_sessions: int = 32,
    session_idle_timeout: float = 120.0,
    queue_size: int = 64,
    max_connections: int = 64,
    request_timeout: float = 10.0,
    keepalive_interval: float = 15.0,
) -> ThreadingHTTPServer:
    if not token:
        raise ValueError("MCP token must not be empty")
    if not isinstance(max_connections, int) or isinstance(max_connections, bool) or max_connections < 1:
        raise ValueError("max_connections must be an integer >= 1")
    if not isinstance(request_timeout, (int, float)) or isinstance(request_timeout, bool):
        raise ValueError("request_timeout must be a finite number > 0")
    if not math.isfinite(request_timeout) or request_timeout <= 0:
        raise ValueError("request_timeout must be a finite number > 0")
    if not isinstance(keepalive_interval, (int, float)) or isinstance(keepalive_interval, bool):
        raise ValueError("keepalive_interval must be a finite number > 0")
    if not math.isfinite(keepalive_interval) or keepalive_interval <= 0:
        raise ValueError("keepalive_interval must be a finite number > 0")
    service = MCPService(
        status_provider,
        max_sessions=max_sessions,
        session_idle_timeout=session_idle_timeout,
        queue_size=queue_size,
    )
    server = _MCPHTTPServer((host, port), _MCPHandler, max_connections=max_connections)
    server.daemon_threads = True
    server.mcp_token = token  # type: ignore[attr-defined]
    server.mcp_service = service  # type: ignore[attr-defined]
    server.request_timeout = request_timeout  # type: ignore[attr-defined]
    server.keepalive_interval = keepalive_interval  # type: ignore[attr-defined]
    return server


def serve(host: str, port: int, token: str, status_provider: Callable[[], Any] | None = None) -> None:
    """Serve until interrupted. Intended for the explicit ``--mcp-only`` mode."""
    server = create_server(host, port, token, status_provider)
    try:
        server.serve_forever()
    finally:
        server.server_close()
