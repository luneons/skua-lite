"""Failure reasoning: diagnose server rejections and plan prerequisite repair.

The server is authoritative: every acceptQuest/ccqr/join verdict carries a
``bSuccess`` flag plus a human message. This module turns that message into a
structured :class:`FailureReason`, then plans the *previous requirement* the
bot must finish first (earlier quest in the chain, missing level, missing
items) instead of retrying the same failing action blindly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any


class FailureKind(Enum):
    PREREQUISITE_QUEST = "prerequisite_quest"
    ITEMS_MISSING = "items_missing"
    LEVEL_TOO_LOW = "level_too_low"
    REP_TOO_LOW = "rep_too_low"
    MAP_NOT_FOUND = "map_not_found"
    UNKNOWN = "unknown"


class SubGoalKind(Enum):
    COMPLETE_QUEST = "complete_quest"
    FARM_ITEMS = "farm_items"
    LEVEL_UP = "level_up"
    JOIN_MAP = "join_map"


@dataclass(slots=True)
class FailureReason:
    kind: FailureKind
    action: str = ""
    quest_id: int | None = None
    server_message: str = ""
    diagnosis: str = ""


@dataclass(slots=True)
class SubGoal:
    kind: SubGoalKind
    quest_id: int = 0
    map_name: str = ""
    target: str = ""
    detail: str = ""


_LEVEL_RE = re.compile(r"level\s*(\d+)", re.IGNORECASE)
_PREREQ_RES = (
    re.compile(r"must\s+complete", re.IGNORECASE),
    re.compile(r"complete\s+.+\s+first", re.IGNORECASE),
    re.compile(r"prerequisite", re.IGNORECASE),
    re.compile(r"previous\s+quest", re.IGNORECASE),
    re.compile(r"not\s+unlocked", re.IGNORECASE),
    re.compile(r"selesaikan\s+quest", re.IGNORECASE),
    re.compile(r"quest\s+sebelum", re.IGNORECASE),
)
_ITEMS_RES = (
    re.compile(r"don'?t\s+have", re.IGNORECASE),
    re.compile(r"do\s+not\s+have", re.IGNORECASE),
    re.compile(r"required\s+items?", re.IGNORECASE),
    re.compile(r"missing\s+items?", re.IGNORECASE),
    re.compile(r"need\s+.+\s+item", re.IGNORECASE),
    re.compile(r"butuh\s+.+\s+item", re.IGNORECASE),
    re.compile(r"item\s+kurang", re.IGNORECASE),
    # AQW turn-in pesan saat kill/progress quest belum cukup
    re.compile(r"missing\s+quest\s+progress", re.IGNORECASE),
    re.compile(r"quest\s+progress", re.IGNORECASE),
    re.compile(r"progress.*not.*complete", re.IGNORECASE),
    re.compile(r"not.*completed.*yet", re.IGNORECASE),
)
_REP_RES = (
    re.compile(r"reputa", re.IGNORECASE),
    re.compile(r"\brep\b", re.IGNORECASE),
    re.compile(r"faction", re.IGNORECASE),
)
_MAP_RES = (
    re.compile(r"map\s+(does\s+not\s+exist|not\s+found|invalid)", re.IGNORECASE),
    re.compile(r"cannot\s+join", re.IGNORECASE),
    re.compile(r"invalid\s+map", re.IGNORECASE),
)


def diagnose_failure(
    action: str,
    server_message: str,
    quest_id: int | None = None,
) -> FailureReason:
    """Classify one server rejection into a structured reason (never raises)."""
    msg = str(server_message or "")
    low = msg.casefold()
    act = str(action or "")

    if any(rx.search(msg) for rx in _MAP_RES):
        return FailureReason(
            kind=FailureKind.MAP_NOT_FOUND,
            action=act,
            quest_id=quest_id,
            server_message=msg,
            diagnosis=f"Map tujuan tidak ditemukan di server ({msg.strip() or 'tanpa pesan'}).",
        )
    if _LEVEL_RE.search(msg) and (
        "level" in low and ("must" in low or "need" in low or "at least" in low
                            or "harus" in low or "minimal" in low or "butuh" in low)
    ):
        m = _LEVEL_RE.search(msg)
        need = m.group(1) if m else "?"
        return FailureReason(
            kind=FailureKind.LEVEL_TOO_LOW,
            action=act,
            quest_id=quest_id,
            server_message=msg,
            diagnosis=f"Level karakter belum cukup (server minta level {need}).",
        )
    if any(rx.search(msg) for rx in _REP_RES):
        return FailureReason(
            kind=FailureKind.REP_TOO_LOW,
            action=act,
            quest_id=quest_id,
            server_message=msg,
            diagnosis="Reputasi/faction belum cukup untuk quest ini; farming reputasi dulu.",
        )
    if any(rx.search(msg) for rx in _ITEMS_RES):
        return FailureReason(
            kind=FailureKind.ITEMS_MISSING,
            action=act,
            quest_id=quest_id,
            server_message=msg,
            diagnosis="Item syarat turn-in kurang; harus farming item dulu sampai cukup.",
        )
    if any(rx.search(msg) for rx in _PREREQ_RES):
        return FailureReason(
            kind=FailureKind.PREREQUISITE_QUEST,
            action=act,
            quest_id=quest_id,
            server_message=msg,
            diagnosis="Quest sebelumnya di rantai belum selesai; harus kerjakan syarat sebelumnya dulu.",
        )
    return FailureReason(
        kind=FailureKind.UNKNOWN,
        action=act,
        quest_id=quest_id,
        server_message=msg,
        diagnosis=f"Server menolak tanpa pola yang dikenali ({msg.strip() or 'tanpa pesan'}); tahan retry, jangan spam.",
    )


def _scw_chain() -> tuple[Any, ...]:
    try:
        from .scw import SEVEN_CIRCLES_CHAIN
        return SEVEN_CIRCLES_CHAIN
    except Exception:
        return ()


class ReasoningEngine:
    """Plan the previous requirement for a diagnosed failure.

    Never invents new game facts: quest-chain order comes from ``scw.py``,
    completion state from the live ``QuestState`` feed, and required levels
    from the server message itself.
    """

    def __init__(
        self,
        quest_state: Any | None = None,
        current_level: int = 1,
        wiki: Any | None = None,
    ) -> None:
        self.quests = quest_state
        self.current_level = int(current_level or 1)
        self.wiki = wiki

    def plan_recovery(self, reason: FailureReason) -> list[SubGoal]:
        try:
            if reason.kind == FailureKind.PREREQUISITE_QUEST:
                return self._plan_prerequisite(reason)
            if reason.kind == FailureKind.ITEMS_MISSING:
                return self._plan_farm_items(reason)
            if reason.kind == FailureKind.LEVEL_TOO_LOW:
                return self._plan_level_up(reason)
        except Exception:
            return []
        return []

    # -- planners ---------------------------------------------------------

    def _plan_prerequisite(self, reason: FailureReason) -> list[SubGoal]:
        chain = _scw_chain()
        qid = int(reason.quest_id or 0)
        if chain and qid > 0:
            idx = next(
                (i for i, s in enumerate(chain) if int(s.quest_id) == qid), None
            )
            if idx is not None:
                # Earliest unfinished step at or before the failing quest is
                # the real previous requirement — never skip over it.
                for step in chain[: idx + 1]:
                    if self._completed(int(step.quest_id)):
                        continue
                    return [SubGoal(
                        kind=SubGoalKind.COMPLETE_QUEST,
                        quest_id=int(step.quest_id),
                        map_name=str(step.map_name),
                        target=str(step.target or ""),
                        detail=f"Selesaikan quest {step.quest_id} di {step.map_name} dulu sebelum {qid}.",
                    )]
        # Fallback: generic next-prerequisite from the chain planner.
        try:
            from .scw import SCWDependencyPlanner
            if self.quests is not None:
                step = SCWDependencyPlanner(self.quests).next_prerequisite()
                if step is not None:
                    return [SubGoal(
                        kind=SubGoalKind.COMPLETE_QUEST,
                        quest_id=int(step.quest_id),
                        map_name=str(step.map_name),
                        target=str(step.target or ""),
                        detail=f"Selesaikan quest {step.quest_id} di {step.map_name} dulu.",
                    )]
        except Exception:
            pass
        return []

    def _plan_farm_items(self, reason: FailureReason) -> list[SubGoal]:
        qid = int(reason.quest_id or 0)
        return [SubGoal(
            kind=SubGoalKind.FARM_ITEMS,
            quest_id=qid,
            target="",
            detail=f"Teruskan farming sampai item turn-in quest {qid} cukup, lalu turn-in lagi.",
        )]

    def _plan_level_up(self, reason: FailureReason) -> list[SubGoal]:
        m = _LEVEL_RE.search(str(reason.server_message or ""))
        need = int(m.group(1)) if m else 0
        if need <= 0:
            need = max(1, self.current_level + 1)
        return [SubGoal(
            kind=SubGoalKind.LEVEL_UP,
            quest_id=0,
            target=f"level {need}",
            detail=f"Naik level {self.current_level} -> {need} dulu di bracket XP sesuai level.",
        )]

    def _completed(self, quest_id: int) -> bool:
        try:
            if self.quests is None:
                return False
            return bool(self.quests.completed(int(quest_id)))
        except Exception:
            return False


def format_diagnosis_log(
    reason: FailureReason, steps: list[SubGoal] | tuple[SubGoal, ...]
) -> str:
    """One honest log line: what failed, why, and the previous requirement."""
    steps = list(steps or [])
    qid = reason.quest_id
    head = f"[REASON] Gagal {reason.action or 'aksi'}" + (
        f" quest {qid}" if qid else ""
    )
    body = f" | Penyebab: {reason.diagnosis}"
    if reason.server_message:
        body += f" | server: {reason.server_message.strip()[:160]}"
    if not steps:
        return head + body + " | Solusi: belum ada syarat sebelumnya yang bisa dipastikan; tahan retry."
    parts: list[str] = []
    for s in steps:
        if s.kind == SubGoalKind.COMPLETE_QUEST:
            where = f" di {s.map_name}" if s.map_name else ""
            parts.append(f"selesaikan quest {s.quest_id}{where} dulu")
        elif s.kind == SubGoalKind.FARM_ITEMS:
            parts.append(f"farming item quest {s.quest_id or qid or '?'} sampai cukup")
        elif s.kind == SubGoalKind.LEVEL_UP:
            parts.append(f"naik {s.target or 'level'} dulu")
        elif s.kind == SubGoalKind.JOIN_MAP:
            parts.append(f"join {s.map_name or s.target} dulu")
        else:
            parts.append(s.detail or s.kind.value)
    return head + body + " | Solusi: " + "; ".join(parts) + " -> bot kerjakan syarat sebelumnya otomatis."
