"""Quest state reduced from authoritative AQW extension responses.

This store deliberately distinguishes `unknown` from rejected: lack of a packet
is never treated as proof that a prerequisite is complete or missing.
"""
from __future__ import annotations

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
            if _int(obj.get("bSuccess")) == 1:
                status.complete = True
                status.accepted = False
            return True
        return False


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
