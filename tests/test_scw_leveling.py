"""Tests for Seven Circles Story & Leveling Prerequisite Planner."""
import json
from unittest.mock import Mock

from skua_lite.quest_state import QuestState
from skua_lite.scw import (
    SCW_GATE_QUEST,
    SCW_XP_SPOT,
    SEVEN_CIRCLES_CHAIN,
    SCWDependencyPlanner,
    SCWStoryExecutor,
)


def _ccqr(quest_id: int, success: int = 1) -> str:
    """Paket ccqr dalam format JSON envelope yang diterima feed()."""
    return json.dumps({
        "t": "xt",
        "b": {"r": -1, "o": {"cmd": "ccqr", "bSuccess": success, "QuestID": quest_id}},
    })


def test_chain_target_is_7981_and_gate_is_7977():
    ids = [step.quest_id for step in SEVEN_CIRCLES_CHAIN]
    assert ids == [7968,7969,7970,7971,7972,7973,7974,7975,7976,7977,7979,7980,7981]
    assert SCW_GATE_QUEST == 7977


def test_canto_vi_is_map_item_quest_no_cell():
    step = next(s for s in SEVEN_CIRCLES_CHAIN if s.quest_id == 7972)
    assert step.map_item_id == 8206
    assert step.map_item_count == 3
    assert step.map_name == "sevencircles"
    assert step.target == ""
    assert step.cell == ""


def test_farming_quests_are_7979_7980_7981_only():
    assert SCW_XP_SPOT.quests == (7979, 7980, 7981)
    assert SCW_XP_SPOT.map_name == "sevencircleswar"
    assert (SCW_XP_SPOT.cell, SCW_XP_SPOT.pad) == ("Enter", "Right")
    assert SCW_XP_SPOT.target == "Wrath Guard"


def test_planner_locked_before_7977():
    qs = QuestState()
    planner = SCWDependencyPlanner(qs)
    assert not planner.unlocked()
    assert planner.best_xp_spot() is None


def test_planner_unlocked_after_7977():
    qs = QuestState()
    qs.feed(_ccqr(7977))
    planner = SCWDependencyPlanner(qs)
    assert planner.unlocked()
    assert planner.best_xp_spot() == SCW_XP_SPOT


def test_first_prerequisite_is_7968():
    qs = QuestState()
    assert SCWDependencyPlanner(qs).next_prerequisite().quest_id == 7968


def test_prerequisite_advances_after_completion():
    qs = QuestState()
    p = SCWDependencyPlanner(qs)
    qs.feed(_ccqr(7968))
    assert p.next_prerequisite().quest_id == 7969
    qs.feed(_ccqr(7969))
    assert p.next_prerequisite().quest_id == 7970


def test_prerequisite_none_when_all_done():
    qs = QuestState()
    for s in SEVEN_CIRCLES_CHAIN:
        qs.feed(_ccqr(s.quest_id))
    assert SCWDependencyPlanner(qs).next_prerequisite() is None


def test_prerequisite_skips_7978_gap():
    qs = QuestState()
    for qid in [7968,7969,7970,7971,7972,7973,7974,7975,7976,7977]:
        qs.feed(_ccqr(qid))
    assert SCWDependencyPlanner(qs).next_prerequisite().quest_id == 7979


def test_executor_sends_map_item_3x_for_7972():
    runtime = Mock(); runtime.bot = Mock(room_id=42); runtime.quest_state = QuestState()
    executor = SCWStoryExecutor(runtime)
    step = next(s for s in SEVEN_CIRCLES_CHAIN if s.quest_id == 7972)
    executor.execute_step(step)
    sent = [str(call.args[0]) for call in runtime._send.call_args_list]
    assert any("acceptQuest%42%7972%" in p for p in sent)
    assert len([p for p in sent if "getMapItem%42%8206%" in p]) == 3


def test_executor_sends_accept_for_kill_quest():
    runtime = Mock(); runtime.bot = Mock(room_id=5); runtime.quest_state = QuestState()
    executor = SCWStoryExecutor(runtime)
    step = next(s for s in SEVEN_CIRCLES_CHAIN if s.quest_id == 7968)
    executor.execute_step(step)
    sent = [str(call.args[0]) for call in runtime._send.call_args_list]
    assert any("acceptQuest%5%7968%" in p for p in sent)
