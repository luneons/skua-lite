"""Test alur auto-recovery prerequisite Seven Circles sebelum masuk farming."""
from skua_lite.quest_state import QuestState
from skua_lite.scw import (
    SCW_GATE_QUEST,
    SCW_XP_SPOT,
    SEVEN_CIRCLES_CHAIN,
    SCWDependencyPlanner,
)


def _accept(qid: int, success: int = 1, msg: str = "success") -> str:
    return f'{{"t":"xt","b":{{"r":-1,"o":{{"cmd":"acceptQuest","bSuccess":{success},"QuestID":{qid},"msg":"{msg}"}}}}}}'


def _ccqr(qid: int, success: int = 1) -> str:
    return f'{{"t":"xt","b":{{"r":-1,"o":{{"cmd":"ccqr","bSuccess":{success},"QuestID":{qid}}}}}}}'


def test_planner_is_locked_when_7977_is_only_accepted_not_completed():
    """Menerima (accept) 7977 belum berarti story selesai; harus completed atau farming quest accepted."""
    qs = QuestState()
    qs.feed(_accept(7977, success=1))  # accept doang
    planner = SCWDependencyPlanner(qs)
    # Harus masih terkunci karena 7977 belum di turn-in/complete
    assert not planner.unlocked()
    assert planner.best_xp_spot() is None
    # Menunjuk ke 7968 sebagai quest pertama yang belum selesai
    assert planner.next_prerequisite().quest_id == 7968


def test_planner_unlocks_when_7977_is_completed():
    qs = QuestState()
    qs.feed(_ccqr(7977, success=1))
    planner = SCWDependencyPlanner(qs)
    assert planner.unlocked()
    assert planner.best_xp_spot() == SCW_XP_SPOT


def test_planner_unlocks_when_story_slot_requirement_is_met():
    # Slot 395 bernilai 10 membuktikan story Seven Circles selesai di server
    qs = QuestState()
    qs.note_quest_slots(["0"] * 395 + ["10"])
    planner = SCWDependencyPlanner(qs)
    assert planner.unlocked()
    assert planner.best_xp_spot() == SCW_XP_SPOT


def test_planner_locks_when_story_slot_is_zero():
    # Akun baru: slot 395 bernilai 0 -> story BELUM selesai, wajib 7968 di sevencircles
    qs = QuestState()
    qs.note_quest_slots(["0"] * 395 + ["0"])
    planner = SCWDependencyPlanner(qs)
    assert not planner.unlocked()
    assert planner.best_xp_spot() is None
    assert planner.next_prerequisite().quest_id == 7968


def test_next_prerequisite_advances_sequentially():
    qs = QuestState()
    planner = SCWDependencyPlanner(qs)
    assert planner.next_prerequisite().quest_id == 7968

    qs.feed(_ccqr(7968, 1))
    assert planner.next_prerequisite().quest_id == 7969

    qs.feed(_ccqr(7969, 1))
    assert planner.next_prerequisite().quest_id == 7970
