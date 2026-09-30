"""Seven Circles prerequisite plan derived from Skua's story scripts."""
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


# Exact order in Scripts/Story/Legion/SevenCircles(War).cs, through the 7985
# gate required by CoreFarms.SevenCirclesWar(). Special multi-target quest data
# remains explicit in notes so the executor cannot silently treat it as one kill.
SEVEN_CIRCLES_CHAIN: tuple[QuestStep, ...] = (
    QuestStep(7968, "sevencircles", "Limbo Guard"),
    QuestStep(7969, "sevencircles", "Luxuria Guard"),
    QuestStep(7970, "sevencircles", "Limbo Guard", "r2", notes="Limbo r2 then Luxuria r3"),
    QuestStep(7971, "sevencircles", "Luxuria"),
    QuestStep(7972, "sevencircles", map_item_id=8206, map_item_count=3),
    QuestStep(7973, "sevencircles", "Gluttony Guard"),
    QuestStep(7974, "sevencircles", "Gluttony"),
    QuestStep(7975, "sevencircles", "Avarice Guard"),
    QuestStep(7976, "sevencircles", notes="Limbo/Luxuria/Gluttony/Avarice guards"),
    QuestStep(7977, "sevencircles", "Avarice"),
    QuestStep(7979, "sevencircleswar", "Wrath Guard"),
    QuestStep(7980, "sevencircleswar", "Wrath Guard", "r9"),
    QuestStep(7981, "sevencircleswar", "Wrath Guard", "r9"),
    QuestStep(7982, "sevencircleswar", "Wrath"),
    QuestStep(7983, "sevencircleswar", "Heresy Guard"),
    QuestStep(7984, "sevencircleswar", "Violence's Gatekeeper"),
    QuestStep(7985, "sevencircleswar", "Violence Guard", "r9"),
)

SCW_GATE_QUEST = 7985
SCW_XP_SPOT = XPSpot("sevencircleswar", "r9", "Left", (7980, 7981, 7985))


class SCWDependencyPlanner:
    """Pure goal resolver: best XP if unlocked, otherwise next dependency."""

    def __init__(self, quest_state: Any) -> None:
        self.quests = quest_state

    def unlocked(self) -> bool:
        return bool(self.quests.accepted(SCW_GATE_QUEST))

    def best_xp_spot(self) -> XPSpot | None:
        return SCW_XP_SPOT if self.unlocked() else None

    def next_prerequisite(self) -> QuestStep | None:
        for step in SEVEN_CIRCLES_CHAIN:
            # Accepted means this is the active sub-goal: keep working it until
            # ccqr proves completion. A rejected/unknown later quest must never
            # let the chain skip over this one.
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
        # Local import keeps this pure data module independent from runtime.
        from . import sfs
        return sfs
