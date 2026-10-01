"""Turn-in failure hooks for Seven Circles prerequisite recovery."""
from unittest.mock import Mock

from skua_lite.bot import BotState
from skua_lite.farming import FarmingRuntime


def _runtime() -> FarmingRuntime:
    bot = Mock(
        username="demo-user",
        session_user_id=1,
        room_id=42,
        level=35,
        state=BotState.IN_MAP,
    )
    return FarmingRuntime(bot=bot)


def test_missing_progress_on_farming_quest_with_locked_gate_triggers_story():
    """Live failure text + slot 0/10 must redirect to quest 7968."""
    runtime = _runtime()
    runtime.quest_state.note_quest_slots(["0"] * 396)
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest",'
        '"bSuccess":1,"QuestID":7979,"msg":"success"}}}'
    )

    runtime.quest_state.note_turn_in_sent(7979)
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr",'
        '"bSuccess":0,"QuestID":7979,"msg":"Missing Quest Progress"}}}'
    )

    assert runtime._scw_story_locked is True
    spot = runtime.auto_level_spot()
    assert spot is not None
    assert spot.map_name == "sevencircles"
    assert spot.cell == ""  # empty means target-aware hunt across the map
    assert spot.quests == (7968,)
    assert runtime.leveling_dependency.quest_id == 7968


def test_missing_progress_with_completed_gate_is_only_incomplete_farm_progress():
    """The same text must not false-trigger story when slot 395 is A (10)."""
    runtime = _runtime()
    runtime.quest_state.note_quest_slots(["0"] * 395 + ["A"])
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest",'
        '"bSuccess":1,"QuestID":7979,"msg":"success"}}}'
    )
    runtime.quest_state.note_turn_in_sent(7979)
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr",'
        '"bSuccess":0,"QuestID":7979,"msg":"Missing Quest Progress"}}}'
    )

    assert runtime._scw_story_locked is False
    spot = runtime.auto_level_spot()
    assert spot is not None
    assert spot.map_name == "sevencircleswar"


def test_explicit_prerequisite_failure_still_latches_story_recovery():
    runtime = _runtime()
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr",'
        '"bSuccess":0,"QuestID":7981,"msg":"Must complete previous quest first"}}}'
    )
    assert runtime._scw_story_locked is True
    assert runtime.auto_level_spot().quests == (7968,)


def test_gate_completion_releases_story_lock_and_returns_to_farm():
    runtime = _runtime()
    runtime._scw_story_locked = True
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr",'
        '"bSuccess":1,"QuestID":7977,"msg":"success"}}}'
    )
    assert runtime._scw_story_locked is False
    assert runtime.auto_level_spot().map_name == "sevencircleswar"
