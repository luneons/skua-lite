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
    turn_in_blocked: bool = False
    last_turn_in_success: bool | None = None
    last_turn_in_at: float = 0.0


class QuestState:
    """Thread-safe enough for single-writer packet feed + planner reads."""

    def __init__(self) -> None:
        self._quests: dict[int, QuestStatus] = {}
        self._item_qty: dict[int, int] = {}  # ItemID -> qty terakhir dari addItems/getDrop
        self._quest_slots: list[str] = []  # strQuests array dari initUserData (index -> char)

    def note_quest_slots(self, slots: list[str]) -> None:
        """Simpan strQuests array dari initUserData (index = slot)."""
        self._quest_slots = list(slots)

    def quest_slot_value(self, slot: int) -> int | None:
        """Nilai slot quest karakter (None = belum ada data server).

        AQW Flash client menyimpan nilai 0-35 per karakter slot menggunakan
        representasi base-36 (0-9, A=10, B=11, ..., Z=35).
        """
        try:
            char = str(self._quest_slots[int(slot)]).strip()
            if not char:
                return None
            return int(char, 36)
        except (IndexError, ValueError, TypeError):
            return None

    def story_requirement_met(self, slot: int, value: int) -> bool | None:
        """True jika slot karakter >= value yang disyaratkan quest.
        False jika kurang. None jika data server belum tersedia."""
        current = self.quest_slot_value(slot)
        if current is None:
            return None
        return current >= int(value)

    def quest_completed_by_slot(self, quest_id: int) -> bool | None:
        """True jika quest sudah selesai berdasarkan strQuests slot server.

        Ambil iSlot dan iValue dari data getQuests (status.data), lalu
        bandingkan dengan _quest_slots.
        - True: strQuests[slot] >= value -> quest sudah pernah diselesaikan
        - False: strQuests[slot] < value -> quest belum selesai
        - None: data belum tersedia (slot atau getQuests belum diterima)
        """
        status = self._quests.get(int(quest_id))
        if status is None or not status.data:
            return None
        slot = status.data.get("iSlot")
        value = status.data.get("iValue")
        if slot is None or value is None:
            return None
        try:
            slot = int(slot)
            value = int(value)
        except (TypeError, ValueError):
            return None
        if slot < 0:
            return None  # slot=-1 artinya quest tanpa slot requirement
        return self.story_requirement_met(slot, value)

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

    def can_turn_in(self, quest_id: int) -> bool:
        """True jika syarat quest terpenuhi dan tidak sedang diblokir.

        Bila turnin items didefinisikan dalam data getQuests, pastikan jumlahnya cukup.
        Bila diblokir oleh penolakan ccqr (Missing Quest Progress), kembalikan False
        sampai ada drop/addItems baru.
        """
        status = self.status(quest_id)
        if status.turn_in_blocked:
            return False
        data = status.data
        if not data:
            return True
        turnin = data.get("turnin") or []
        if isinstance(turnin, list) and turnin:
            for req in turnin:
                if not isinstance(req, dict):
                    continue
                item_id = _int(req.get("ItemID"))
                req_qty = _int(req.get("iQty"), default=1)
                if item_id > 0:
                    current = self._item_qty.get(item_id, 0)
                    if current < req_qty:
                        return False
        return True

    def turn_in_ready(self, quest_id: int, cooldown_s: float, now: float | None = None) -> bool:
        """True bila boleh kirim turn-in: syarat lengkap, tidak pending, dan cooldown lewat."""
        status = self.status(quest_id)
        if status.turn_in_pending or status.turn_in_blocked:
            return False
        if not self.can_turn_in(quest_id):
            return False
        stamp = float(now if now is not None else time.monotonic())
        return (stamp - status.last_turn_in_at) >= float(cooldown_s)

    def feed(self, packet: str) -> bool:
        parsed = sfs.parse_xt_json(packet)
        if parsed is None:
            return False
        obj = parsed.get("obj") or {}
        cmd = str(parsed.get("cmd") or "")
        if cmd == "initUserData":
            data = obj.get("data") or {}
            if not isinstance(data, dict):
                return False
            slots: list[str] = []
            for key in ("strQuests", "strQuests2", "strQuests3", "strQuests4",
                        "strQuests5", "strQuests6", "strQuests7"):
                chunk = str(data.get(key) or "")
                slots.extend(list(chunk))
            if not slots:
                return False
            self.note_quest_slots(slots)
            return True
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
                # Reset turn_in_blocked bila data quest baru datang
                status.turn_in_blocked = False
                changed = True
            return changed
        if cmd == "addItems":
            items = obj.get("items") or {}
            if isinstance(items, dict):
                for k, it in items.items():
                    if isinstance(it, dict):
                        iid = _int(it.get("ItemID") or k)
                        qty_now = _int(it.get("iQtyNow") or it.get("iQty"))
                        if iid > 0 and qty_now > 0:
                            self._item_qty[iid] = qty_now
                            # Progress item bertambah -> izinkan re-evaluasi turn-in
                            for st in self._quests.values():
                                st.turn_in_blocked = False
            return True
        if cmd == "getDrop":
            iid = _int(obj.get("ItemID"))
            qty = _int(obj.get("iQty"), default=1)
            if iid > 0:
                self._item_qty[iid] = self._item_qty.get(iid, 0) + qty
                for st in self._quests.values():
                    st.turn_in_blocked = False
            return True
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
                status.turn_in_blocked = False
            else:
                # Jika ditolak Missing Quest Progress / item kurang, tahan turn-in sampai item drop baru tiba
                msg_lower = status.last_message.lower()
                if "progress" in msg_lower or "item" in msg_lower or "syarat" in msg_lower:
                    status.turn_in_blocked = True
            return True
        return False


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
