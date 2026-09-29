"""Daftar server AQW (diambil dari /api/data/servers).

Field objek server (berdasarkan Game.as & Skua.Model.Server):
  sName  - nama server (mis. "Yorumi")
  sIP    - hostname / IP tujuan SFS
  iPort  - port SFS
  iCount - jumlah pemain saat ini
  iMax   - kapasitas
  bOnline - 1 = online
  bUpg   - 1 = server member-only
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import config


@dataclass(frozen=True)
class Server:
    name: str
    ip: str
    port: int
    online: bool
    full: bool
    upgrade_only: bool


class ServerUnavailable(Exception):
    """Server offline, penuh, atau tidak ditemukan."""


def parse_server_list(payload: str) -> dict[str, Server]:
    """Parse JSON array menjadi dict {name: Server}."""
    data = json.loads(payload)
    out: dict[str, Server] = {}
    for entry in data:
        name = str(entry.get("sName", "")).strip()
        if not name:
            continue
        count = int(entry.get("iCount", 0))
        maxp = int(entry.get("iMax", 0))
        online = bool(int(entry.get("bOnline", 0)) == 1)
        full = maxp > 0 and count >= maxp
        out[name] = Server(
            name=name,
            ip=str(entry.get("sIP", "")),
            port=int(entry.get("iPort", 0)),
            online=online,
            full=full,
            upgrade_only=bool(int(entry.get("bUpg", 0)) == 1),
        )
    return out


def fetch_server_list(*, timeout: float = 20.0) -> dict[str, Server]:
    """GET /api/data/servers."""
    req = urllib.request.Request(
        config.SERVER_LIST_URL,
        headers={"User-Agent": "AQW/Skua-Lite"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        raise ServerUnavailable(f"gagal fetch server list: {e}") from e
    return parse_server_list(raw)


def pick(servers_dict: dict[str, Server], name: str) -> Server:
    """Ambil server berdasarkan nama; lempar ServerUnavailable bila tidak layak."""
    s = servers_dict.get(name)
    if s is None:
        raise ServerUnavailable(f"server '{name}' tidak ditemukan")
    if not s.online:
        raise ServerUnavailable(f"server '{name}' sedang offline")
    if s.full:
        raise ServerUnavailable(f"server '{name}' penuh")
    return s