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
# Syarat story dari live getQuests(7977): slot quest 395, nilai 10.
# strQuests[395] >= 10 berarti Seven Circles selesai; kurang dari itu = belum.
SCW_GATE_SLOT = 395
SCW_GATE_VALUE = 10
# Live getQuests(7968..7977): same slot 395, values 1..10.
SCW_STORY_VALUES: dict[int, int] = {
    quest_id: value for value, quest_id in enumerate(range(7968, 7978), start=1)
}
SCW_XP_SPOT = XPSpot("sevencircleswar", "Enter", "Right", (7979, 7980, 7981), target="Wrath Guard")


class SCWDependencyPlanner:
    """Pure goal resolver: best XP if unlocked, otherwise next dependency."""

    def __init__(self, quest_state: Any) -> None:
        self.quests = quest_state

    def story_requirement_checked(self) -> bool | None:
        """Status story dari strQuests server (bukan tebakan dari accept).

        True = slot 395 >= 10 (Seven Circles selesai).
        False = slot 395 < 10 (Seven Circles BELUM selesai).
        None = data server belum tersedia (fallback ke probe).
        """
        try:
            met = self.quests.story_requirement_met(SCW_GATE_SLOT, SCW_GATE_VALUE)
        except AttributeError:
            return None
        return met

    def unlocked(self) -> bool:
        """Farming terbuka HANYA jika syarat story 7977 terpenuhi.

        Prioritas:
        1. strQuests slot 395 >= 10 -> story selesai -> True.
           strQuests slot 395 < 10 -> story BELUM selesai -> False.
        2. ccqr 7977 sukses -> True.
        3. Farming quest (7979/7980/7981) di-accept -> True (fallback).
           Catatan: accept saja BUKAN bukti mutlak — turn-in farming yang
           ditolak server tetap mengaktifkan _scw_story_locked.
        """
        story = self.story_requirement_checked()
        if story is True:
            return True
        if story is False:
            return False
        # Data slot belum tersedia: percaya ccqr(7977) sukses saja.
        # JANGAN percaya accepted(farming quest) — AQW menerima acceptQuest
        # oleh id di akun baru walau story belum selesai, dan turn-in tetap
        # gagal. Accept bukan bukti unlock.
        if self.quests.completed(SCW_GATE_QUEST):
            return True
        return False

    def best_xp_spot(self) -> XPSpot | None:
        return SCW_XP_SPOT if self.unlocked() else None

    def next_prerequisite(self) -> QuestStep | None:
        """Quest pertama dalam chain yang belum diselesaikan.

        Cek dua sumber bukti:
        1. ccqr sukses dalam sesi ini (quests.completed)
        2. strQuests slot server (quests.quest_completed_by_slot)
        """
        current_story_value = None
        try:
            current_story_value = self.quests.quest_slot_value(SCW_GATE_SLOT)
        except AttributeError:
            pass
        for step in SEVEN_CIRCLES_CHAIN:
            # Lewati bila ccqr sukses di sesi ini.
            if self.quests.completed(step.quest_id):
                continue
            # Untuk chain 7968..7977, slot 395 langsung menunjukkan langkah
            # terakhir yang selesai, bahkan sebelum getQuests per-step dimuat.
            required_value = SCW_STORY_VALUES.get(step.quest_id)
            if (
                required_value is not None
                and current_story_value is not None
                and current_story_value >= required_value
            ):
                continue
            # Fallback generik bila quest data iSlot/iValue sudah dimuat.
            slot_status = None
            try:
                slot_status = self.quests.quest_completed_by_slot(step.quest_id)
            except AttributeError:
                pass
            if slot_status is True:
                continue
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
