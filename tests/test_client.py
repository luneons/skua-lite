"""Test TCP client SmartFox (pakai mock server, tanpa koneksi internet)."""
import socket
import threading
import time

import pytest

from skua_lite import client, sfs


class MockSFSServer:
    """Server palsu: mengirim respons terprogram lalu merekam kiriman klien."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.host, self.port = self.sock.getsockname()
        self.received: list[str] = []
        self.scripted: list[str] = []
        # Balasan dinamis: {substring paket masuk: [paket balasan]}
        self.replies: dict[str, list[str]] = {}
        self._thread = None
        self._conn = None
        self._stop = False

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self._conn, _ = self.sock.accept()
            self._conn.settimeout(0.05)
            framer = sfs.PacketFramer()
            for msg in self.scripted:
                self._conn.sendall(sfs.build_packet(msg))
                time.sleep(0.02)
            while not self._stop:
                try:
                    data = self._conn.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                for pkt in framer.feed(data):
                    self.received.append(pkt)
                    self._maybe_reply(pkt)
        except OSError:
            pass

    def _maybe_reply(self, pkt: str) -> None:
        """Kirim balasan terdaftar bila paket masuk cocok dengan sebuah kunci."""
        for key, responses in self.replies.items():
            if key in pkt:
                for resp in responses:
                    try:
                        self._conn.sendall(sfs.build_packet(resp))
                    except OSError:
                        return
                    time.sleep(0.02)
                return

    def stop(self):
        self._stop = True
        try:
            if self._conn:
                self._conn.close()
        except OSError:
            pass
        self.sock.close()


@pytest.fixture
def mock_server():
    srv = MockSFSServer()
    srv.start()
    yield srv
    srv.stop()


def test_connect_and_receive_packet(mock_server):
    mock_server.scripted.append("<msg t='sys'><body action='verChk' r='0'>ok</body></msg>")
    c = client.SFSClient(mock_server.host, mock_server.port, timeout=3.0)
    c.connect()
    got = c.recv_packet(timeout=2.0)
    assert got is not None
    assert "verChk" in got
    c.close()


def test_send_packet_reaches_server(mock_server):
    c = client.SFSClient(mock_server.host, mock_server.port, timeout=3.0)
    c.connect()
    c.send(sfs.verchk_packet())
    time.sleep(0.3)
    assert any("verChk" in p for p in mock_server.received)
    c.close()


def test_recv_returns_none_on_timeout(mock_server):
    c = client.SFSClient(mock_server.host, mock_server.port, timeout=3.0)
    c.connect()
    assert c.recv_packet(timeout=0.3) is None
    c.close()


def test_connect_fails_on_closed_port():
    c = client.SFSClient("127.0.0.1", 1, timeout=1.0)
    with pytest.raises(client.ConnectionFailed):
        c.connect()


def test_alive_reflects_socket_state(mock_server):
    c = client.SFSClient(mock_server.host, mock_server.port, timeout=3.0)
    c.connect()
    assert c.alive is True
    c.close()
    assert c.alive is False


def test_multiple_packets_in_one_read_are_queued(mock_server):
    # server mengirim 3 paket sekaligus; client harus mengembalikan semuanya
    mock_server.scripted.extend([
        "<msg t='sys'><body action='logOK' r='0'>1</body></msg>",
        "%xt%zm%firstJoin%1%",
        "%xt%zm%cmd%1%tfer%ok%",
    ])
    c = client.SFSClient(mock_server.host, mock_server.port, timeout=3.0)
    c.connect()
    got = []
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and len(got) < 3:
        p = c.recv_packet(timeout=0.5)
        if p:
            got.append(p)
    c.close()
    assert len(got) == 3
    assert any("logOK" in g for g in got)
    assert any("firstJoin" in g for g in got)
    assert any("tfer" in g for g in got)


def test_recv_packet_survives_socket_closed_between_poll_steps():
    """Concurrent close tidak boleh membuat recv_packet dereference None."""
    c = client.SFSClient("127.0.0.1", 1)

    class ClosingSocket:
        def settimeout(self, _value):
            c._sock = None

        def recv(self, _size):
            return b""

    c._sock = ClosingSocket()
    assert c.recv_packet(timeout=0.2) is None


def test_queue_cleared_on_close(mock_server):
    mock_server.scripted.extend([
        "<msg t='sys'><body action='a' r='0'>1</body></msg>",
        "<msg t='sys'><body action='b' r='0'>2</body></msg>",
    ])
    c = client.SFSClient(mock_server.host, mock_server.port, timeout=3.0)
    c.connect()
    time.sleep(0.4)
    first = c.recv_packet(timeout=1.0)
    assert first is not None
    c.close()
    assert c.recv_packet(timeout=0.2) is None
