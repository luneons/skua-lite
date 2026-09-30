"""Quest-state reducer tests for turn-in readiness from live item quantities."""
import json

from skua_lite.quest_state import QuestState


def _packet(cmd: str, **obj) -> str:
    return json.dumps({"t": "xt", "b": {"r": -1, "o": {"cmd": cmd, **obj}}})


def test_newly_accepted_kill_quest_is_not_ready_to_turn_in():
    state = QuestState()
    state.feed(_packet("acceptQuest", QuestID=7979, bSuccess=1, msg="success"))
    state.feed(_packet(
        "getQuests",
        quests={
            "7979": {
                "QuestID": 7979,
                "sName": "Guards of Wrath",
                "turnin": [{"ItemID": 9001, "sName": "Wrath Guard Defeated", "iQty": 12}],
            }
        },
    ))

    assert state.accepted(7979)
    assert state.can_turn_in(7979) is False


def test_add_items_progress_unlocks_turn_in_only_at_required_quantity():
    state = QuestState()
    state.feed(_packet("acceptQuest", QuestID=7979, bSuccess=1, msg="success"))
    state.feed(_packet(
        "getQuests",
        quests={
            "7979": {
                "QuestID": 7979,
                "turnin": [{"ItemID": 9001, "sName": "Wrath Guard Defeated", "iQty": 12}],
            }
        },
    ))

    state.feed(_packet(
        "addItems",
        items={"9001": {"ItemID": 9001, "sName": "Wrath Guard Defeated", "iQty": 5, "iQtyNow": 5}},
    ))
    assert state.can_turn_in(7979) is False

    state.feed(_packet(
        "addItems",
        items={"9001": {"ItemID": 9001, "sName": "Wrath Guard Defeated", "iQty": 7, "iQtyNow": 12}},
    ))
    assert state.can_turn_in(7979) is True


def test_get_drop_quantity_unlocks_turn_in():
    state = QuestState()
    state.feed(_packet("acceptQuest", QuestID=7980, bSuccess=1, msg="success"))
    state.feed(_packet(
        "getQuests",
        quests={
            "7980": {
                "QuestID": 7980,
                "turnin": [{"ItemID": 9002, "sName": "War Medal", "iQty": 5}],
            }
        },
    ))
    state.feed(_packet(
        "getDrop", ItemID=9002, sName="War Medal", bSuccess=1, iQty=5
    ))
    assert state.can_turn_in(7980) is True


def test_missing_quest_progress_blocks_further_turn_in_until_progress_changes():
    state = QuestState()
    state.feed(_packet("acceptQuest", QuestID=7979, bSuccess=1, msg="success"))
    state.feed(_packet(
        "getQuests",
        quests={"7979": {"QuestID": 7979, "turnin": [{"ItemID": 9001, "iQty": 12}]}},
    ))
    state.note_turn_in_sent(7979, now=100.0)
    state.feed(_packet(
        "ccqr", QuestID=7979, bSuccess=0, msg="Missing Quest Progress"
    ))

    assert state.can_turn_in(7979) is False
    assert state.turn_in_ready(7979, cooldown_s=15.0, now=1000.0) is False

    state.feed(_packet(
        "addItems",
        items={"9001": {"ItemID": 9001, "iQty": 12, "iQtyNow": 12}},
    ))
    assert state.can_turn_in(7979) is True
    assert state.turn_in_ready(7979, cooldown_s=15.0, now=1000.0) is True
