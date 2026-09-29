"""Owner follow mode driven by the chat command ``Ikuti aku``.

The owner asks once and the bot mirrors their movement: cell/pad changes
become ``moveToCell``, position updates become ``mv``. When the owner leaves
the area (``exitArea`` / ``userGone``) the follower stops mirroring and issues
a single ``/goto <owner>`` so it can catch up; mirroring resumes by itself as
soon as the owner's ``uotls`` updates arrive again.

Packet shapes are grounded in the AQW client: inbound ``uotls`` field map is
built in ``Game.as:1411-1420`` and applied by ``userTreeWrite`` (5377+), while
outbound mirrors come from ``World.as:3491`` (``mv``) and ``World.as:2884``
(``moveToCell``). This module only builds packets; the bot owns the socket.
"""
from __future__ import annotations

import threading
from typing import Iterable

from . import sfs

_START_COMMANDS = frozenset({"ikuti aku"})
# `Berhenti` is the only word the owner asked for; the older verbose phrases
# are deliberately NOT commands any more so they fall through as normal chat.
_STOP_COMMANDS = frozenset({"berhenti"})

# Movement fields that belong to a cell change vs. a position update.
_CELL_FIELDS = ("strFrame", "strPad")
_POSITION_FIELDS = ("tx", "ty")


def normalize_command(text: str) -> str:
    """Collapse whitespace and case the way the command table expects."""
    return " ".join((text or "").split()).casefold()


def parse_follow_command(text: str) -> str | tuple[str] | None:
    """Return start/stop for the owner phrases, else None.

    ``"start"`` = follow the speaker (``Ikuti aku``). A start with an explicit
    target (``Ikuti alice``) returns ``(target,)``; the bot then binds any UID
    to that display name when its ``uotls`` updates arrive. ``"stop"`` keeps
    accepting the old longer phrases so prior muscle memory still works.
    """
    clean = " ".join((text or "").split())
    normalized = clean.casefold()
    if normalized in _START_COMMANDS:
        return "start"
    if normalized in _STOP_COMMANDS:
        return "stop"
    if normalized.startswith("ikuti "):
        target = clean[len("ikuti "):].strip()
        # `Ikuti aku ...` is a malformed self-follow command, not a player
        # named "aku ...".
        if target and not target.casefold().startswith("aku "):
            return (target,)
    return None


class OwnerFollower:
    """Track one owner and turn their updates into mirror packets."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._following = False
        self._owner_name = ""
        self._owner_id: int | None = None
        self._cell: str | None = None
        self._pad: str | None = None
        self._position: tuple[int, int, int] | None = None
        # A departure may arrive as both `exitArea` and `userGone`; send one
        # goto per absence so the catching-up request is not doubled.
        self._departed: bool = False

    @property
    def is_following(self) -> bool:
        with self._lock:
            return self._following

    @property
    def owner_name(self) -> str:
        with self._lock:
            return self._owner_name

    def start(self, owner_name: str, owner_id: int | None = None) -> None:
        """Begin following one player; resets the last-known snapshot."""
        clean = " ".join((owner_name or "").split())
        with self._lock:
            self._following = True
            self._owner_name = clean
            self._owner_id = int(owner_id) if owner_id is not None else None
            self._cell = None
            self._pad = None
            self._position = None
            self._departed = False

    def stop(self) -> None:
        """Stop mirroring; the tracked owner is forgotten."""
        with self._lock:
            self._following = False
            self._owner_name = ""
            self._owner_id = None
            self._cell = None
            self._pad = None
            self._position = None
            self._departed = False

    def matches(self, username: str = "", user_id: int | None = None) -> bool:
        """True when this identity is the owner currently being followed."""
        with self._lock:
            if not self._following:
                return False
            if self._owner_id is not None and user_id is not None:
                return int(user_id) == self._owner_id
            if not username:
                return False
            return " ".join(username.split()).casefold() == self._owner_name.casefold()

    def packets_for_update(
        self, room: int, username: str, fields: dict
    ) -> list[bytes]:
        """Mirror one ``uotls`` update; empty when nothing relevant changed."""
        if not self.matches(username):
            return []
        packets: list[bytes] = []
        with self._lock:
            cell = fields.get("strFrame")
            pad = fields.get("strPad")
            if isinstance(cell, str) and cell:
                target_pad = pad if isinstance(pad, str) and pad else (self._pad or "Spawn")
                if cell != self._cell or target_pad != self._pad:
                    self._cell = cell
                    self._pad = target_pad
                    packets.append(sfs.move_to_cell_packet(int(room), cell, target_pad))
            x = fields.get("tx")
            y = fields.get("ty")
            if isinstance(x, int) and isinstance(y, int):
                speed = fields.get("sp")
                if not isinstance(speed, int) or speed <= 0:
                    speed = 10
                if (x, y, speed) != self._position:
                    self._position = (x, y, speed)
                    packets.append(sfs.move_packet(int(room), x, y, speed))
            if packets:
                # The owner is visible again; the next departure deserves its
                # own goto request.
                self._departed = False
        return packets

    def packets_for_departure(self) -> list[bytes]:
        """``/goto <owner>`` once, so the bot can follow into the next map."""
        with self._lock:
            if not self._following or not self._owner_name:
                return []
            if self._departed:
                return []
            self._departed = True
            return [sfs.goto_player_packet(self._owner_name)]


def iter_packets(packets: Iterable[bytes]) -> list[bytes]:
    """Materialize packets so callers can log or assert on them."""
    return list(packets)
