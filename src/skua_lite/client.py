"""Klien TCP SmartFoxServer untuk AQW.

Socket diberi timeout receh (RECV_TIMEOUT kecil) supaya loop bisa
melakukan keep-alive & cek status tanpa memblokir selamanya.
"""
from __future__ import annotations

import socket
import time

from . import config, sfs


class ConnectionFailed(Exception):
    """Tidak bisa membuka socket TCP ke server game."""


class SFSClient:
    def __init__(self, host: str, port: int, *, timeout: float = config.CONNECT_TIMEOUT):
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._framer = sfs.PacketFramer()
        self._queue: list[str] = []

    # ------------------------------------------------------------------
    @property
    def alive(self) -> bool:
        return self._sock is not None

    def connect(self) -> None:
        try:
            sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as e:
            raise ConnectionFailed(f"gagal konek ke {self.host}:{self.port}: {e}") from e
        sock.settimeout(0.05)   # timeout receh -> poll non-blok dengan aman
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        self._sock = sock
        self._framer = sfs.PacketFramer()
        self._queue = []

    def send(self, packet: bytes) -> None:
        if self._sock is None:
            raise ConnectionFailed("socket belum terkoneksi (send)")
        try:
            self._sock.sendall(packet)
        except OSError as e:
            self.close()
            raise ConnectionFailed(f"gagal kirim paket: {e}") from e

    def recv_packet(self, timeout: float = 0.5) -> str | None:
        """Kembalikan satu paket teks, atau None bila belum ada dalam timeout."""
        if self._sock is None:
            return None
        if self._queue:
            return self._queue.pop(0)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            sock = self._sock
            if sock is None:
                return None
            try:
                sock.settimeout(min(0.1, remaining))
                data = sock.recv(4096)
            except (socket.timeout, TimeoutError):
                continue
            except OSError:
                self.close()
                return None
            if not data:
                self.close()
                return None
            packets = self._framer.feed(data)
            if packets:
                self._queue.extend(packets[1:])
                return packets[0]

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._queue = []

    def __enter__(self) -> "SFSClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
