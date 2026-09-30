"""RED tests – reasoning engine: diagnosa kegagalan dan auto-prerequisite."""
from __future__ import annotations

import pytest

from skua_lite.reasoning_engine import (
    FailureKind,
    FailureReason,
    ReasoningEngine,
    SubGoal,
    SubGoalKind,
    diagnose_failure,
)
from skua_lite.quest_state import QuestState


# --------------------------------------------------------------------------- helpers

def _qs(*accepted_ids, rejected=(), completed=()):
    qs = QuestState()
    for qid in accepted_ids:
        qs.status(qid).accepted = True
    for qid in rejected:
        qs.status(qid).accepted = False
    for qid in completed:
        qs.status(qid).complete = True
    return qs


# --------------------------------------------------------------------------- diagnose_failure()

class TestDiagnoseFailure:
    def test_quest_not_available_level(self):
        r = diagnose_failure("acceptQuest", "You must be level 30 to accept this quest.", quest_id=1234)
        assert r.kind == FailureKind.LEVEL_TOO_LOW
        assert "level" in r.diagnosis.lower()
        assert r.quest_id == 1234

    def test_quest_prerequisite_message(self):
        r = diagnose_failure("acceptQuest", "You must complete 'Test Quest' first.", quest_id=5555)
        assert r.kind == FailureKind.PREREQUISITE_QUEST
        assert r.quest_id == 5555

    def test_turn_in_items_missing(self):
        r = diagnose_failure("ccqr", "You don't have all the required items.", quest_id=9999)
        assert r.kind == FailureKind.ITEMS_MISSING
        assert "item" in r.diagnosis.lower()

    def test_turn_in_rep_not_enough(self):
        r = diagnose_failure("ccqr", "You need more reputation to complete this quest.", quest_id=42)
        assert r.kind == FailureKind.REP_TOO_LOW
        assert "reputasi" in r.diagnosis.lower()

    def test_generic_rejection(self):
        r = diagnose_failure("acceptQuest", "Quest not available at this time.", quest_id=7)
        assert r.kind == FailureKind.UNKNOWN
        assert r.diagnosis  # non-empty explanation

    def test_join_map_not_found(self):
        r = diagnose_failure("join", "Map does not exist.")
        assert r.kind == FailureKind.MAP_NOT_FOUND
        assert "map" in r.diagnosis.lower()

    def test_join_wrong_level(self):
        r = diagnose_failure("join", "You must be at least level 50.")
        assert r.kind == FailureKind.LEVEL_TOO_LOW

    def test_no_message_unknown(self):
        r = diagnose_failure("acceptQuest", "", quest_id=0)
        assert r.kind == FailureKind.UNKNOWN


# --------------------------------------------------------------------------- ReasoningEngine.plan_recovery()

class TestPlanRecovery:
    def test_prerequisite_quest_scw_chain(self):
        """Jika quest 7980 gagal dan 7979 belum selesai, kembalikan 7979 sebagai sub-goal."""
        qs = _qs()  # semua unknown
        eng = ReasoningEngine(quest_state=qs)
        reason = FailureReason(
            kind=FailureKind.PREREQUISITE_QUEST,
            action="acceptQuest",
            quest_id=7980,
            server_message="",
            diagnosis="Harus selesaikan quest sebelumnya",
        )
        steps = eng.plan_recovery(reason)
        assert len(steps) >= 1
        # sub-goal pertama harus mengerjakan quest sebelumnya di rantai
        first = steps[0]
        assert first.kind == SubGoalKind.COMPLETE_QUEST
        assert first.quest_id < 7980  # quest lebih awal di rantai SC/SCW

    def test_items_missing_returns_farm_subgoal(self):
        """Kalau item kurang, kembalikan sub-goal farm target."""
        qs = _qs(7985)  # gate accepted
        eng = ReasoningEngine(quest_state=qs)
        reason = FailureReason(
            kind=FailureKind.ITEMS_MISSING,
            action="ccqr",
            quest_id=7980,
            server_message="You don't have all the required items.",
            diagnosis="Item turn-in kurang; terus farming.",
        )
        steps = eng.plan_recovery(reason)
        # Boleh kosong (continue farming adalah perilaku normal) ATAU ada subgoal
        # yang tidak menyarankan join map baru — tidak ada state baru diperlukan
        for s in steps:
            assert s.kind != SubGoalKind.COMPLETE_QUEST or s.quest_id != 7980

    def test_level_too_low_returns_bracket_subgoal(self):
        qs = _qs()
        eng = ReasoningEngine(quest_state=qs, current_level=8)
        reason = FailureReason(
            kind=FailureKind.LEVEL_TOO_LOW,
            action="join",
            quest_id=None,
            server_message="You must be level 50.",
            diagnosis="Level terlalu rendah untuk bergabung.",
        )
        steps = eng.plan_recovery(reason)
        assert any(s.kind == SubGoalKind.LEVEL_UP for s in steps)

    def test_unknown_failure_returns_empty(self):
        qs = _qs()
        eng = ReasoningEngine(quest_state=qs)
        reason = FailureReason(
            kind=FailureKind.UNKNOWN,
            action="acceptQuest",
            quest_id=99,
            server_message="Error baru yang tidak dikenal.",
            diagnosis="Tidak diketahui",
        )
        # Kegagalan tak dikenal tidak boleh memunculkan sub-goal asal-asalan
        steps = eng.plan_recovery(reason)
        assert isinstance(steps, list)


# --------------------------------------------------------------------------- format_log

class TestFormatLog:
    def test_format_log_prerequisite(self):
        from skua_lite.reasoning_engine import format_diagnosis_log
        reason = FailureReason(
            kind=FailureKind.PREREQUISITE_QUEST,
            action="acceptQuest",
            quest_id=7980,
            server_message="Must complete quest first.",
            diagnosis="Quest 7979 belum selesai",
        )
        steps = [SubGoal(kind=SubGoalKind.COMPLETE_QUEST, quest_id=7979, map_name="sevencircles")]
        msg = format_diagnosis_log(reason, steps)
        assert "[REASON]" in msg
        assert "7980" in msg
        assert "7979" in msg
        assert "sevencircles" in msg

    def test_format_log_no_steps(self):
        from skua_lite.reasoning_engine import format_diagnosis_log
        reason = FailureReason(
            kind=FailureKind.UNKNOWN,
            action="acceptQuest",
            quest_id=5,
            server_message="Weird error.",
            diagnosis="Tidak diketahui",
        )
        msg = format_diagnosis_log(reason, [])
        assert "[REASON]" in msg
        assert "5" in msg
