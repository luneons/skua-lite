"""Protocol and authorization coverage for the opt-in MCP transport."""
from __future__ import annotations

import json
import socket
import struct
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin

import pytest

from skua_lite import __version__
from skua_lite.mcp_server import MCPService, create_server


def _request(url: str, token: str | None, payload: dict | None = None, scheme: str = "Bearer"):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if token is not None:
        request.add_header("Authorization", f"{scheme} {token}")
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, dict(response.headers), json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), json.loads(error.read() or b"{}")


def _running_server(**kwargs):
    server = create_server("127.0.0.1", 0, "secret", **kwargs)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_mcp_requires_bearer_token_and_does_not_echo_it():
    server = _running_server()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/sse")
        try:
            urllib.request.urlopen(request, timeout=2)
        except urllib.error.HTTPError as error:
            assert error.code == 401
            assert error.headers["WWW-Authenticate"] == "Bearer"
        else:
            raise AssertionError("unauthorized request unexpectedly succeeded")
        status, _, body = _request(f"http://127.0.0.1:{server.server_port}/messages", "wrong-secret", {
            "jsonrpc": "2.0", "id": 1, "method": "initialize"
        })
        assert status == 401
        assert "wrong-secret" not in json.dumps(body)
    finally:
        server.shutdown()
        server.server_close()


def test_mcp_sse_messages_end_to_end_and_lowercase_bearer():
    server = _running_server()
    stream = None
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/sse")
        request.add_header("Authorization", "bearer secret")
        stream = urllib.request.urlopen(request, timeout=2)
        assert stream.readline() == b"event: endpoint\n"
        endpoint = stream.readline().decode().strip()[len("data: "):]
        assert endpoint.startswith("/messages?session_id=")
        assert stream.readline() == b"\n"
        status, _, _ = _request(urljoin(f"http://127.0.0.1:{server.server_port}", endpoint), "secret", {
            "jsonrpc": "2.0", "id": 42, "method": "initialize"
        })
        assert status == 202
        assert stream.readline() == b"event: message\n"
        assert json.loads(stream.readline().decode()[len("data: "):])["id"] == 42
        assert stream.readline() == b"\n"
    finally:
        if stream is not None:
            stream.close()
        server.shutdown()
        server.server_close()


def test_mcp_basic_json_rpc_and_read_only_health_tool():
    server = _running_server(status_provider=lambda: {"status": "ok", "read_only": True})
    url = f"http://127.0.0.1:{server.server_port}/messages"
    try:
        status, _, _ = _request(url, "secret", {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert status == 400
        status, _, _ = _request(url + "?session_id=a&session_id=b", "secret", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert status == 400
        status, _, _ = _request(url + "?session_id=bad%20id", "secret", {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert status == 400
        status, _, _ = _request(url + "?session_id=abcdefgh", "secret", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert status == 404
        status, _, _ = _request(url + "?session_id=abcdefgh", "secret", {"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert status == 404
        body = server.mcp_service.request({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "health"}})
        assert json.loads(body["result"]["content"][0]["text"])["read_only"] is True
        body = server.mcp_service.request({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "exec"}})
        assert body["error"]["code"] == -32602
        init = server.mcp_service.request({"jsonrpc": "2.0", "id": 5, "method": "initialize"})
        assert init["result"]["serverInfo"]["version"] == __version__
    finally:
        server.shutdown()
        server.server_close()


def test_service_publish_statuses():
    service = MCPService(queue_size=1)
    session_id, _ = service.new_session()
    assert service.publish(session_id, b"one") == "ok"
    assert service.publish(session_id, b"two") == "queue_full"
    assert service.publish("abcdefgh", b"x") == "not_found"


def test_http_queue_full_mapping():
    server = _running_server()
    stream = None
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/sse", headers={"Authorization": "Bearer secret"})
        stream = urllib.request.urlopen(request, timeout=2)
        stream.readline(); endpoint = stream.readline().decode().strip()[len("data: "):]; stream.readline()
        server.mcp_service.publish = lambda *_args: "queue_full"
        status, headers, body = _request(urljoin(f"http://127.0.0.1:{server.server_port}", endpoint), "secret", {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert status == 503 and headers["Retry-After"] == "1" and body["error"] == "session queue full"
    finally:
        if stream: stream.close()
        server.shutdown(); server.server_close()


@pytest.mark.parametrize("kwargs", [{"max_sessions": 0}, {"queue_size": 0}, {"session_idle_timeout": 0}, {"session_idle_timeout": float("nan")}])
def test_invalid_service_config(kwargs):
    with pytest.raises(ValueError):
        MCPService(**kwargs)


@pytest.mark.parametrize("kwargs", [{"max_connections": 0}, {"keepalive_interval": 0}, {"keepalive_interval": float("inf")}])
def test_invalid_server_config(kwargs):
    with pytest.raises(ValueError):
        create_server("127.0.0.1", 0, "secret", **kwargs)


def test_max_sessions_and_connection_timeout():
    server = _running_server(max_sessions=1, request_timeout=0.2)
    stream = None; raw = None
    try:
        stream = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{server.server_port}/sse", headers={"Authorization": "Bearer secret"}), timeout=2)
        raw = socket.create_connection(("127.0.0.1", server.server_port), timeout=2)
        raw.settimeout(1)
        raw.sendall(b"GET /sse HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer secret\r\n\r\n")
        response = raw.recv(256)
        assert response.startswith(b"HTTP/1.0 503")
        assert b"Retry-After: 1" in response
        slow = socket.create_connection(("127.0.0.1", server.server_port), timeout=2); slow.settimeout(2)
        started = time.monotonic()
        while True:
            try:
                if not slow.recv(1): break
            except (socket.timeout, ConnectionResetError): break
        assert time.monotonic() - started < 2
        slow.close()
    finally:
        if stream: stream.close()
        if raw: raw.close()
        server.shutdown(); server.server_close()


def test_sse_rst_closes_session_and_releases_slot():
    server = _running_server(max_sessions=1, keepalive_interval=0.2)
    raw = socket.create_connection(("127.0.0.1", server.server_port), timeout=2)
    try:
        raw.sendall(b"GET /sse HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer secret\r\n\r\n")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and server.mcp_service.session_count() != 1:
            time.sleep(0.01)
        assert server.mcp_service.session_count() == 1
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    finally:
        raw.close()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and server.mcp_service.session_count() != 0:
        time.sleep(0.01)
    try:
        assert server.mcp_service.session_count() == 0
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/sse",
            headers={"Authorization": "Bearer secret"},
        )
        stream = urllib.request.urlopen(request, timeout=2)
        try:
            assert stream.status == 200
            assert stream.readline() == b"event: endpoint\n"
        finally:
            stream.close()
    finally:
        server.shutdown(); server.server_close()


def test_sse_early_write_failure_closes_session(monkeypatch):
    server = _running_server(max_sessions=1, keepalive_interval=0.2)
    created_sessions = []
    original_new_session = MCPService.new_session

    def record_new_session(service):
        result = original_new_session(service)
        if result is not None:
            created_sessions.append(result[0])
        return result

    monkeypatch.setattr(MCPService, "new_session", record_new_session)
    original_flush_headers = __import__("skua_lite.mcp_server", fromlist=["_MCPHandler"])._MCPHandler.flush_headers

    def fail_sse_headers(handler):
        original_flush_headers(handler)
        if handler.path.startswith("/sse"):
            raise BrokenPipeError

    monkeypatch.setattr(
        "skua_lite.mcp_server._MCPHandler.flush_headers", fail_sse_headers
    )
    raw = socket.create_connection(("127.0.0.1", server.server_port), timeout=2)
    try:
        raw.sendall(b"GET /sse HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer secret\r\n\r\n")
        raw.settimeout(2)
        while raw.recv(1024):
            pass
    except (ConnectionResetError, socket.timeout):
        pass
    finally:
        raw.close()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and server.mcp_service.session_count() != 0:
        time.sleep(0.01)
    try:
        assert len(created_sessions) == 1
        assert server.mcp_service.session_count() == 0
        assert server.mcp_service.has_session(created_sessions[0]) is False
    finally:
        server.shutdown(); server.server_close()


def test_connection_cap():
    server = _running_server(max_connections=1, request_timeout=5)
    a = socket.create_connection(("127.0.0.1", server.server_port), timeout=2)
    b = None
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and server.active_connections != 1:
            time.sleep(0.01)
        assert server.active_connections == 1
        b = socket.create_connection(("127.0.0.1", server.server_port), timeout=2)
        b.settimeout(2)
        b.sendall(b"GET /sse HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer secret\r\n\r\n")
        try:
            assert b.recv(1) == b""
        except ConnectionResetError:
            pass
        a.close()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and server.active_connections != 0:
            time.sleep(0.01)
        assert server.active_connections == 0
        status, _, _ = _request(f"http://127.0.0.1:{server.server_port}/sse", None)
        assert status == 401
    finally:
        a.close()
        if b: b.close()
        server.shutdown(); server.server_close()
