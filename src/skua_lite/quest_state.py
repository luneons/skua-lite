"""Quest state reduced from authoritative AQW extension responses.

This store deliberately distinguishes `unknown` from rejected: lack of a packet
is never treated as proof that a prerequisite is complete or missing.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from . import sfs


@dataclass(slots=True)
class QuestStatus:
    quest_id: int
    accepted: bool | None = None
    complete: bool = False
    last_message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    turn_in_pending: bool = False
    last_turn_in_success: bool | None = None
    last_turn_in_at: float = 0.0


class QuestState:
    """Thread-safe enough for single-writer packet feed + planner reads."""

    def __init__(self) -> None:
        self._quests: dict[int, QuestStatus] = {}

    def status(self, quest_id: int) -> QuestStatus:
        qid = int(quest_id)
        return self._quests.setdefault(qid, QuestStatus(qid))

    def accepted(self, quest_id: int) -> bool:
        return self.status(quest_id).accepted is True

    def known(self, quest_id: int) -> bool:
        status = self.status(quest_id)
        return status.accepted is not None or status.complete or bool(status.data)

    def completed(self, quest_id: int) -> bool:
        return self.status(quest_id).complete

    def rejected(self, quest_id: int) -> bool:
        return self.status(quest_id).accepted is False

    def reason(self, quest_id: int) -> str:
        return self.status(quest_id).last_message

    def data(self, quest_id: int) -> dict[str, Any]:
        return dict(self.status(quest_id).data)

    def note_turn_in_sent(self, quest_id: int, now: float | None = None) -> None:
        status = self.status(quest_id)
        status.turn_in_pending = True
        status.last_turn_in_at = float(now if now is not None else time.monotonic())

    def expire_pending_turn_ins(self, timeout_s: float, now: float | None = None) -> list[int]:
        """Release requests that got no ccqr (disconnect/lost packet) for retry."""
        stamp = float(now if now is not None else time.monotonic())
        expired: list[int] = []
        for qid, status in self._quests.items():
            if status.turn_in_pending and stamp - status.last_turn_in_at >= float(timeout_s):
                status.turn_in_pending = False
                status.last_turn_in_success = None
                status.last_message = "timeout menunggu respons ccqr"
                expired.append(qid)
        return expired

    def turn_in_ready(self, quest_id: int, cooldown_s: float, now: float | None = None) -> bool:
        """True bila boleh kirim turn-in: tidak menunggu respons dan cooldown lewat."""
        status = self.status(quest_id)
        if status.turn_in_pending:
            return False
        stamp = float(now if now is not None else time.monotonic())
        return (stamp - status.last_turn_in_at) >= float(cooldown_s)

    def feed(self, packet: str) -> bool:
        parsed = sfs.parse_xt_json(packet)
        if parsed is None:
            return False
        obj = parsed.get("obj") or {}
        cmd = str(parsed.get("cmd") or "")
        if cmd == "acceptQuest":
            qid = _int(obj.get("QuestID"))
            if qid <= 0:
                return False
            status = self.status(qid)
            status.accepted = _int(obj.get("bSuccess")) == 1
            status.last_message = str(obj.get("msg") or "")
            status.turn_in_pending = False
            status.last_turn_in_success = None
            return True
        if cmd == "getQuests":
            quests = obj.get("quests") or {}
            if not isinstance(quests, dict):
                return False
            changed = False
            for key, raw in quests.items():
                if not isinstance(raw, dict):
                    continue
                qid = _int(raw.get("QuestID") or key)
                if qid <= 0:
                    continue
                status = self.status(qid)
                status.accepted = True
                status.data = dict(raw)
                changed = True
            return changed
        if cmd == "ccqr":
            qid = _int(obj.get("QuestID"))
            if qid <= 0:
                return False
            status = self.status(qid)
            status.last_message = str(obj.get("msg") or "")
            status.turn_in_pending = False
            status.last_turn_in_success = _int(obj.get("bSuccess")) == 1
            if status.last_turn_in_success:
                status.complete = True
                status.accepted = False
            return True
        return False


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
