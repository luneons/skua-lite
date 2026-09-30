"""Seven Circles prerequisite plan derived from Skua story scripts."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class QuestStep:
    quest_id: int
    map_name: str
    target: str = "*"
    cell: str = ""
    pad: str = "Left"
    map_item_id: int = 0
    map_item_count: int = 0
    notes: str = ""


@dataclass(slots=True, frozen=True)
class XPSpot:
    map_name: str
    cell: str
    pad: str
    quests: tuple[int, ...]
    target: str = "*"


# Target leveling cukup sampai 7981 terbuka.
# 7977 (Ava-risky Business) = gate quest pembuka sevencircleswar.
# 7972 (Canto VI) = MapItem 8206 x3; tidak perlu cell, cukup di map.
SEVEN_CIRCLES_CHAIN: tuple[QuestStep, ...] = (
    QuestStep(7968, "sevencircles", "Limbo Guard"),
    QuestStep(7969, "sevencircles", "Luxuria Guard"),
    QuestStep(7970, "sevencircles", "Limbo Guard", "r2", notes="Limbo r2 then Luxuria r3"),
    QuestStep(7971, "sevencircles", "Luxuria"),
    QuestStep(7972, "sevencircles", target="", cell="", map_item_id=8206, map_item_count=3),
    QuestStep(7973, "sevencircles", "Gluttony Guard"),
    QuestStep(7974, "sevencircles", "Gluttony"),
    QuestStep(7975, "sevencircles", "Avarice Guard"),
    QuestStep(7976, "sevencircles", notes="Limbo/Luxuria/Gluttony/Avarice guards"),
    QuestStep(7977, "sevencircles", "Avarice"),
    QuestStep(7979, "sevencircleswar", "Wrath Guard"),
    QuestStep(7980, "sevencircleswar", "Wrath Guard", "r9"),
    QuestStep(7981, "sevencircleswar", "Wrath Guard", "r9"),
)

SCW_GATE_QUEST = 7977
SCW_XP_SPOT = XPSpot("sevencircleswar", "Enter", "Right", (7979, 7980, 7981), target="Wrath Guard")


class SCWDependencyPlanner:
    """Pure goal resolver: best XP if unlocked, otherwise next dependency."""

    def __init__(self, quest_state: Any) -> None:
        self.quests = quest_state

    def unlocked(self) -> bool:
        if self.quests.completed(SCW_GATE_QUEST):
            return True
        if self.quests.accepted(SCW_GATE_QUEST):
            return True
        for q in (7979, 7980, 7981):
            if self.quests.accepted(q):
                return True
        return False

    def best_xp_spot(self) -> XPSpot | None:
        return SCW_XP_SPOT if self.unlocked() else None

    def next_prerequisite(self) -> QuestStep | None:
        for step in SEVEN_CIRCLES_CHAIN:
            if self.quests.accepted(step.quest_id):
                return step
            if not self.quests.completed(step.quest_id):
                return step
        return None


class SCWStoryExecutor:
    """Execute one observed story sub-goal at a time, then resume leveling."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.quests = runtime.quest_state
        self._ready: set[int] = set()

    def plan_remaining(self) -> list[QuestStep]:
        return [
            step for step in SEVEN_CIRCLES_CHAIN
            if not self.quests.completed(step.quest_id)
        ]

    def next_step(self) -> QuestStep | None:
        return SCWDependencyPlanner(self.quests).next_prerequisite()

    def note_turn_in_rejected(self, quest_id: int, reason: str) -> None:
        self.quests.status(quest_id).last_message = str(reason)
        self._ready.discard(int(quest_id))

    def note_turn_in_ready(self, quest_id: int) -> None:
        self._ready.add(int(quest_id))

    def execute_step(self, step: QuestStep) -> None:
        room = int(getattr(self.runtime.bot, "room_id", 1) or 1)
        qid = int(step.quest_id)
        if not self.quests.accepted(qid):
            self.runtime._send(
                self.runtime_sfs.accept_quest_packet(room, qid),
                f"accept quest {qid}",
            )
        if step.map_item_id > 0:
            for _ in range(max(1, int(step.map_item_count))):
                self.runtime._send(
                    self.runtime_sfs.get_map_item_packet(room, step.map_item_id),
                    f"map item {step.map_item_id}",
                )
        if qid in self._ready:
            self.runtime._send(
                self.runtime_sfs.try_quest_complete_packet(room, qid, -1),
                f"complete quest {qid}",
            )

    @property
    def runtime_sfs(self):
        from . import sfs
        return sfs
