"""Tests for farming-mode packet builders and runtime (no AI, no Flash)."""
from __future__ import annotations

import struct
import threading
import time
import zlib
from unittest.mock import Mock

import pytest

from skua_lite import farming, sfs
from skua_lite.quest_state import QuestState
from skua_lite.auto_planner import AutoGoal, AutoPlanner
from skua_lite.combat import MonsterState
from skua_lite.mode import RunMode
from tests.test_client import MockSFSServer


def _fake_monster(*, cell="", alive=True, monster_id=7):
    return MonsterState(
        map_id=7, monster_id=monster_id, name="Skeleton", race="",
        cell=cell, hp=100 if alive else 0, max_hp=100, state=1 if alive else 0,
    )


@pytest.fixture
def mock_server():
    srv = MockSFSServer()
    srv.scripted.extend([
        "<msg t='sys'><body action='apiOK' r='0'></body></msg>",
        "%xt%loginResponse%-1%true%1%alice%Welcome!%",
        "<msg t='sys'><body action='joinOK' r='3'><pid id='1'/></body></msg>",
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":3,'
        '"areaName":"battleon-1","strMapName":"battleon"}}}',
        '{"t":"xt","b":{"r":3,"o":{"cmd":"loadInventoryBig","items":{"10":{"ItemID":10,"sName":"Mage","sType":"Class","sES":"co","bEquip":"1"}}}}}',
        '{"t":"xt","b":{"r":3,"o":{"cmd":"updateClass","uid":1,"sClassName":"Mage","ItemID":10}}}',
        '{"t":"xt","b":{"r":3,"o":{"cmd":"sAct","actions":{"active":[{"ref":"aa","nam":"Fireball","auto":true,"typ":"aa","tgt":"h","tgtMax":1,"cd":1800,"isOK":true},{"ref":"a4","nam":"Meteor","typ":"m","tgt":"h","tgtMax":3,"cd":12000,"isOK":true}]}}}}',
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"lair-100000","strMapName":"lair",'
        '"uoBranch":[{"uoName":"alice","uid":1,"strFrame":"Enter","intHP":900,"intHPMax":900,"intMP":300,"intMPMax":300,"intState":1}],'
        '"monBranch":[{"MonMapID":1,"MonID":100,"intHP":500,"intHPMax":500,"intState":1}],'
        '"mondef":[{"MonID":100,"strMonName":"Water Draconian"}],'
        '"monmap":[{"MonMapID":1,"MonID":100,"strFrame":"Enter"}]}}}',
    ])
    srv.start()
    yield srv
    srv.stop()


def _wire(pkt: bytes) -> str:
    return pkt.rstrip(b"\x00").decode("latin-1")


def _swf_tag(code: int, payload: bytes = b"") -> bytes:
    length = len(payload)
    if length < 63:
        return struct.pack("<H", (code << 6) | length) + payload
    return struct.pack("<HI", (code << 6) | 63, length) + payload


def _swf_bytes(labels: list[str]) -> bytes:
    body = b"\x08\x00" + b"\x00\x18" + struct.pack("<H", len(labels))
    for label in labels:
        body += _swf_tag(43, label.encode("utf-8") + b"\x00")
        body += _swf_tag(1)
    body += _swf_tag(0)
    payload = zlib.compress(body)
    return b"CWS" + bytes([10]) + struct.pack("<I", 8 + len(payload)) + payload


def test_get_drop_packet_wire_format():
    assert _wire(sfs.get_drop_packet(room=273, drop_id=9911)) == "%xt%zm%getDrop%273%9911%"


def test_rest_packet_sits_down_via_emotea_extension():
    assert _wire(sfs.rest_packet()) == "%xt%zm%emotea%1%rest%"


def test_rest_request_packet_repeats_rest_while_seated():
    assert _wire(sfs.rest_request_packet()) == "%xt%zm%restRequest%1%%"


def test_server_use_item_packet_wire_format():
    assert _wire(sfs.use_item_packet(room=273, item_id=1234)) == "%xt%zm%serverUseItem%273%+%1234%"


def test_sell_item_packet_wire_format():
    body = _wire(sfs.sell_item_packet(room=273, item_id=55, quantity=3, char_item_id=777))
    assert body == "%xt%zm%sellItem%273%55%3%777%"


def test_bank_packets_wire_format():
    assert _wire(sfs.load_bank_packet(room=273)) == "%xt%zm%loadBank%273%All%"
    body = _wire(sfs.bank_to_inventory_packet(room=273, item_id=11, char_item_id=22))
    assert body == "%xt%zm%bankToInv%273%11%22%"
    body = _wire(
        sfs.bank_swap_packet(room=273, inv_id=1, inv_char_id=2, bank_id=3, bank_char_id=4)
    )
    assert body == "%xt%zm%bankSwapInv%273%1%2%3%4%"


def test_get_map_item_packet_wire_format():
    assert _wire(sfs.get_map_item_packet(room=273, map_item_id=8206)) == (
        "%xt%zm%getMapItem%273%8206%"
    )


def test_get_quests_packet_wire_format():
    assert _wire(sfs.get_quests_packet(room=273, quest_id=7985)) == (
        "%xt%zm%getQuests%273%7985%"
    )


def test_try_quest_complete_packet_wire_format():
    body = _wire(
        sfs.try_quest_complete_packet(room=273, quest_id=101, reward_id=5, turn_ins="1,2")
    )
    assert body == "%xt%zm%tryQuestComplete%273%101%5%false%1,2%wvz%"


def test_aggro_mon_packet_wire_format():
    assert _wire(sfs.aggro_mon_packet(room=273, map_ids=[7, 9])) == "%xt%zm%aggroMon%273%7%9%"


def test_quest_state_tracks_failed_turn_in_response():
    state = QuestState()
    state.note_turn_in_sent(7980)
    failed = '{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr","bSuccess":0,"QuestID":7980,"msg":"Required items missing"}}}'

    assert state.feed(failed)
    status = state.status(7980)
    assert status.turn_in_pending is False
    assert status.last_turn_in_success is False
    assert status.last_message == "Required items missing"


def test_quest_state_tracks_accept_reject_and_completion():
    state = QuestState()
    ok = '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":1,"QuestID":7980,"msg":"success"}}}'
    locked = '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":0,"QuestID":7985,"msg":"Missing requirement"}}}'
    complete = '{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr","bSuccess":1,"QuestID":7980,"msg":"success"}}}'

    assert state.feed(ok)
    assert state.accepted(7980)
    assert state.feed(locked)
    assert state.rejected(7985)
    assert state.reason(7985) == "Missing requirement"
    assert state.feed(complete)
    assert state.completed(7980)
    assert not state.accepted(7980)


def test_quest_state_learns_loaded_quest_data():
    state = QuestState()
    packet = '{"t":"xt","b":{"r":-1,"o":{"cmd":"getQuests","quests":{"7981":{"QuestID":7981,"sName":"Mega War Medals"}}}}}'
    assert state.feed(packet)
    assert state.accepted(7981)
    assert state.data(7981)["sName"] == "Mega War Medals"


def test_farming_runtime_feeds_quest_state_from_server():
    bot = Mock(username="alice", session_user_id=1, room_id=42, move_on_join=None)
    runtime = farming.FarmingRuntime(bot=bot)
    packet = '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":1,"QuestID":7980,"msg":"success"}}}'
    runtime.feed_packet(packet)
    assert runtime.quest_state.accepted(7980)


def test_live_scw_accept_packet_marks_gate_available_and_requests_data():
    """A captured Yorumi success response makes the gate authoritative."""
    bot = Mock(username="alice", session_user_id=1, room_id=42, move_on_join=None)
    runtime = farming.FarmingRuntime(bot=bot)
    runtime._send = Mock()
    packet = '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":1,"QuestID":7977,"msg":"success"}}}'

    runtime.feed_packet(packet)

    assert runtime.quest_state.accepted(7977)
    sent = runtime._send.call_args.args[0].rstrip(b"\x00").decode("latin-1")
    assert sent == "%xt%zm%getQuests%42%7977%"
    assert runtime.auto_level_spot().map_name == "sevencircleswar"


def test_scw_dependency_planner_uses_best_spot_only_after_gate():
    from skua_lite.scw import SCWDependencyPlanner

    quests = QuestState()
    planner = SCWDependencyPlanner(quests)
    assert planner.best_xp_spot() is None
    assert planner.next_prerequisite().quest_id == 7968

    accepted = '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":1,"QuestID":7977,"msg":"success"}}}'
    quests.feed(accepted)
    spot = planner.best_xp_spot()
    assert (spot.map_name, spot.cell, spot.quests) == (
        "sevencircleswar", "r9", (7979, 7980, 7981)
    )


def test_scw_dependency_chain_orders_story_before_war():
    from skua_lite.scw import SEVEN_CIRCLES_CHAIN

    ids = [step.quest_id for step in SEVEN_CIRCLES_CHAIN]
    assert ids[:10] == [7968, 7969, 7970, 7971, 7972, 7973, 7974, 7975, 7976, 7977]
    assert ids[10:] == [7979, 7980, 7981]
    assert SEVEN_CIRCLES_CHAIN[4].map_item_id == 8206


def test_leveling_loop_probes_scw_gate_before_combat(monkeypatch):
    import threading

    bot = Mock(level=8, current_map="sevencircleswar-100000", room_id=42)
    runtime = farming.FarmingRuntime(bot=bot)
    state = Mock(cell="r9", map_file_name="sevencircleswar.swf")
    runtime.combat = Mock(state=state, running=True)
    runtime._send = Mock()
    runtime._leveling_target = 100
    runtime._leveling_stop.clear()

    old_sleep = time.sleep
    monkeypatch.setattr(time, "sleep", lambda _s: old_sleep(0.01))
    thread = threading.Thread(target=runtime._leveling_loop)
    thread.start()
    deadline = time.monotonic() + 2
    while not runtime._send.called and time.monotonic() < deadline:
        old_sleep(0.02)
    runtime._leveling_stop.set()
    thread.join(timeout=1)

    bodies = [c.args[0].rstrip(b"\x00").decode("latin-1") for c in runtime._send.call_args_list]
    assert "%xt%zm%acceptQuest%42%7977%" in bodies
    assert "%xt%zm%acceptQuest%42%4007%" in bodies
    assert all("%7980%" not in body and "%7981%" not in body for body in bodies)


def test_scw_rejected_probe_suspends_level_goal_for_story_prerequisite():
    bot = Mock(level=8)
    runtime = farming.FarmingRuntime(bot=bot)
    rejected = '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":0,"QuestID":7977,"msg":"Missing requirement"}}}'
    runtime.feed_packet(rejected)

    assert runtime.auto_level_spot().map_name == "sevencircles"
    assert runtime.leveling_dependency.quest_id == 7968


def test_story_executor_runs_first_missing_quest_then_combat():
    from skua_lite.scw import SCWStoryExecutor

    bot = Mock(level=8, room_id=42)
    runtime = farming.FarmingRuntime(bot=bot)
    runtime._send = Mock()
    executor = SCWStoryExecutor(runtime)

    step = executor.next_step()
    assert step.quest_id == 7968
    assert step.map_name == "sevencircles"
    executor.execute_step(step)
    accept = runtime._send.call_args_list[0].args[0]
    body = accept.rstrip(b"\x00").decode("latin-1")
    assert body == "%xt%zm%acceptQuest%42%7968%"
    assert executor.plan_remaining()[1].quest_id == 7969


def test_story_executor_fetches_map_item_for_map_item_quest():
    from skua_lite.scw import QuestStep, SCWStoryExecutor

    bot = Mock(level=8, room_id=7)
    runtime = farming.FarmingRuntime(bot=bot)
    runtime._send = Mock()
    executor = SCWStoryExecutor(runtime)
    step = QuestStep(7972, "sevencircles", map_item_id=8206, map_item_count=3)
    executor.execute_step(step)

    bodies = [c.args[0].rstrip(b"\x00").decode("latin-1") for c in runtime._send.call_args_list]
    assert "%xt%zm%acceptQuest%7%7972%" in bodies
    assert bodies.count("%xt%zm%getMapItem%7%8206%") == 3


def test_story_executor_completes_only_finished_requirements():
    from skua_lite.scw import SCWStoryExecutor

    bot = Mock(level=8, room_id=42)
    runtime = farming.FarmingRuntime(bot=bot)
    runtime._send = Mock()
    executor = SCWStoryExecutor(runtime)

    executor.note_turn_in_rejected(7968, "Missing Quest Progress")
    assert executor.next_step().quest_id == 7968

    executor.note_turn_in_ready(7968)
    executor.execute_step(executor.next_step())
    bodies = [c.args[0].rstrip(b"\x00").decode("latin-1") for c in runtime._send.call_args_list]
    assert "%xt%zm%tryQuestComplete%42%7968%-1%false%%wvz%" in bodies

def test_leveling_probe_promotes_to_scw_farm_after_gate_accepted(monkeypatch):
    import threading

    bot = Mock(level=8, current_map="sevencircleswar-100000", room_id=42)
    runtime = farming.FarmingRuntime(bot=bot)
    state = Mock(cell="r9", map_file_name="sevencircleswar.swf")
    runtime.combat = Mock(state=state, running=True)
    runtime._send = Mock()
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":1,"QuestID":7977,"msg":"success"}}}'
    )
    runtime._send.reset_mock()
    runtime._leveling_target = 100
    runtime._leveling_stop.clear()

    old_sleep = time.sleep
    monkeypatch.setattr(time, "sleep", lambda _s: old_sleep(0.01))
    thread = threading.Thread(target=runtime._leveling_loop)
    thread.start()
    deadline = time.monotonic() + 2
    while not runtime._send.called and time.monotonic() < deadline:
        old_sleep(0.02)
    runtime._leveling_stop.set()
    thread.join(timeout=1)

    bodies = [c.args[0].rstrip(b"\x00").decode("latin-1") for c in runtime._send.call_args_list]
    assert "%xt%zm%acceptQuest%42%7980%" in bodies
    assert "%xt%zm%acceptQuest%42%7981%" in bodies


def test_scw_story_step_completes_before_returning_to_farm():
    bot = Mock(level=8, room_id=42)
    runtime = farming.FarmingRuntime(bot=bot)
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":0,"QuestID":7977,"msg":"Missing requirement"}}}'
    )
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr","bSuccess":1,"QuestID":7968,"msg":"success"}}}'
    )
    assert runtime.auto_level_spot().quests == (7969,)


def test_leveling_loop_retries_story_step_until_completion_then_advances(monkeypatch):
    import threading

    bot = Mock(level=8, current_map="sevencircles-100000", room_id=42)
    runtime = farming.FarmingRuntime(bot=bot)
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":0,"QuestID":7977,"msg":"Missing requirement"}}}'
    )
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":1,"QuestID":7968,"msg":"success"}}}'
    )
    state = Mock(cell="Enter", map_file_name="sevencircles.swf")
    runtime.combat = Mock(state=state, running=True)
    runtime._send = Mock()
    runtime._leveling_target = 100
    runtime._leveling_stop.clear()

    old_sleep = time.sleep
    monkeypatch.setattr(time, "sleep", lambda _s: old_sleep(0.01))
    thread = threading.Thread(target=runtime._leveling_loop)
    thread.start()
    deadline = time.monotonic() + 2
    while not runtime._send.called and time.monotonic() < deadline:
        old_sleep(0.02)
    runtime._leveling_stop.set()
    thread.join(timeout=1)

    bodies = [c.args[0].rstrip(b"\x00").decode("latin-1") for c in runtime._send.call_args_list]
    assert "%xt%zm%acceptQuest%42%7968%" in bodies
    assert "%xt%zm%tryQuestComplete%42%7968%-1%false%%wvz%" in bodies


def test_combat_worker_exits_cleanly_when_socket_dies():
    from skua_lite.client import ConnectionFailed
    from skua_lite.combat import AutoAttackEngine, CombatState, generic_profile

    bot = Mock(room_id=42, session_user_id=1)
    bot._send_raw.side_effect = ConnectionFailed("socket belum terkoneksi (send)")
    engine = AutoAttackEngine(
        bot, target_name="*", class_profile=generic_profile("Mage")
    )
    engine.state.seen_self = True
    engine.state.player_state = 1
    engine.state.hp = 100
    engine.state.class_name = "Mage"
    engine.state.cell = "r9"
    engine.state.skills["aa"] = farming.combat.SkillState(ref="aa", target_kind="h")
    engine.state.monsters[15] = _fake_monster(cell="r9")
    engine.set_auto(True)

    assert engine.tick() is False
    assert "koneksi putus" in engine.last_action


def test_quest_state_turn_in_waits_for_authoritative_response():
    state = QuestState()
    assert state.turn_in_ready(7980, cooldown_s=15.0, now=100.0)
    state.note_turn_in_sent(7980, now=100.0)
    assert not state.turn_in_ready(7980, cooldown_s=15.0, now=101.0)
    state.feed('{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr","bSuccess":0,"QuestID":7980,"msg":"not enough"}}}')
    assert not state.turn_in_ready(7980, cooldown_s=15.0, now=110.0)
    assert state.turn_in_ready(7980, cooldown_s=15.0, now=116.0)


def test_leveling_reapplies_map_wide_combat_on_targetless_spot():
    bot = Mock(level=8, current_map="sevencircleswar-1", room_id=42)
    runtime = farming.FarmingRuntime(bot=bot)
    runtime.combat = Mock(state=Mock(cell="r9", map_file_name="scw.swf"), running=True)
    runtime.combat.set_map_wide = Mock()
    runtime.combat.start = Mock()
    runtime._send = Mock()
    runtime._leveling_target = 100
    runtime._leveling_stop.set()
    runtime.fight_all_in_map()
    runtime.combat.set_map_wide.assert_called_with(True)


def test_runtime_logs_authoritative_quest_turn_in_result():
    bot = Mock(level=8, room_id=42)
    logs: list[str] = []
    runtime = farming.FarmingRuntime(bot=bot, on_log=logs.append)
    runtime.quest_state.note_turn_in_sent(7980, now=100.0)

    runtime.feed_packet('{"t":"xt","b":{"r":-1,"o":{"cmd":"ccqr","bSuccess":0,"QuestID":7980,"msg":"Required items missing"}}}')

    assert any("turn-in 7980 GAGAL: Required items missing" in line for line in logs)
    assert runtime.quest_state.status(7980).turn_in_pending is False


def test_leveling_does_not_turn_in_quests_rejected_by_server(monkeypatch):
    import threading

    bot = Mock(level=8, current_map="oaklore-1", room_id=42)
    runtime = farming.FarmingRuntime(bot=bot)
    for q in (4007, 6257):
        runtime.feed_packet(
            '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":0,'
            f'"QuestID":{q},"msg":"Missing requirement"}}}}'
        )
    runtime.combat = Mock(state=Mock(cell="r3", map_file_name="oaklore.swf"), running=True)
    runtime._send = Mock()
    runtime._leveling_target = 100
    runtime._leveling_stop.clear()
    runtime._leveling_probe_done = True

    old_sleep = time.sleep
    monkeypatch.setattr(time, "sleep", lambda _s: old_sleep(0.02))
    thread = threading.Thread(target=runtime._leveling_loop)
    thread.start()
    old_sleep(0.15)
    runtime._leveling_stop.set()
    thread.join(timeout=1)

    bodies = [c.args[0].rstrip(b"\x00").decode("latin-1") for c in runtime._send.call_args_list]
    assert not any("tryQuestComplete" in body for body in bodies)


def test_quest_state_expires_lost_turn_in_after_timeout():
    state = QuestState()
    state.note_turn_in_sent(7980, now=100.0)
    assert state.expire_pending_turn_ins(timeout_s=60.0, now=150.0) == []
    assert state.expire_pending_turn_ins(timeout_s=60.0, now=161.0) == [7980]
    assert state.turn_in_ready(7980, cooldown_s=15.0, now=161.0)


def test_leveling_loop_refuses_second_turn_in_before_ccqr_response(monkeypatch):
    import threading

    bot = Mock(level=8, current_map="sevencircleswar-100000", room_id=42)
    runtime = farming.FarmingRuntime(bot=bot)
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":1,"QuestID":7977,"msg":"success"}}}'
    )
    for q in (7979, 7980, 7981):
        runtime.feed_packet(
            '{"t":"xt","b":{"r":-1,"o":{"cmd":"acceptQuest","bSuccess":1,'
            f'"QuestID":{q},"msg":"success"}}}}'
        )
    state = Mock(cell="r9", map_file_name="sevencircleswar.swf")
    runtime.combat = Mock(state=state, running=True)
    runtime.combat.set_map_wide = Mock()
    runtime.combat.start = Mock()
    runtime._send = Mock()
    runtime._leveling_target = 100
    runtime._leveling_stop.clear()

    old_sleep = time.sleep
    monkeypatch.setattr(time, "sleep", lambda s: old_sleep(0.02))
    thread = threading.Thread(target=runtime._leveling_loop)
    thread.start()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if runtime._send.called:
            old_sleep(0.15)  # let the loop tick twice more without ccqr
            break
        old_sleep(0.02)
    runtime._leveling_stop.set()
    thread.join(timeout=1)

    bodies = [c.args[0].rstrip(b"\x00").decode("latin-1") for c in runtime._send.call_args_list]
    # Verifikasi salah satu dari quest farming tidak di-turn-in dua kali sebelum ccqr
    farming_turn_ins = [b for b in bodies if "tryQuestComplete" in b]
    # Setiap quest harus paling banyak muncul 1x sebelum ccqr dijawab server
    assert len(farming_turn_ins) <= 3  # 3 quest farming, masing-masing max 1x


def test_farming_profile_defaults_enable_verified_mage_attack():
    profile = farming.FarmProfile()
    assert profile.map_name == "lair-100000"
    assert profile.pickup_drops is True
    assert profile.rest_between_rounds is True
    assert profile.auto_attack is True
    assert profile.class_name == "Mage"
    assert profile.target_monster == "Water Draconian"


def test_farming_runtime_never_builds_ai_router():
    bot = Mock()
    bot.state = Mock()
    runtime = farming.FarmingRuntime(bot=bot, profile=farming.FarmProfile())
    assert runtime.ai_router is None
    assert getattr(bot, "ai_router", None) is None


def test_farming_runtime_owns_and_ticks_auto_planner():
    bot = Mock()
    bot.state.value = "IN_MAP"
    bot.move_on_join = None
    bot.room_id = 273
    runtime = farming.FarmingRuntime(bot=bot)

    planner = bot.auto_planner
    assert isinstance(planner, AutoPlanner)
    calls: list[str] = []
    runtime.attack_auto = lambda: calls.append("attack")
    runtime.move_to_cell = lambda c, p=None: calls.append(f"move {c}")
    runtime.complete_quest = lambda q, *args: calls.append(f"turn_in {q}")

    runtime.start()
    planner.set_goal(AutoGoal(kind="farm", target_name="Skeleton"))
    runtime.combat.state.monsters = {
        1: _fake_monster(cell=runtime.combat.state.cell, alive=True)
    }

    import time
    deadline = time.monotonic() + 3.0
    while not calls and time.monotonic() < deadline:
        time.sleep(0.05)
    runtime.stop()
    assert "attack" in calls


def test_farming_runtime_wires_auto_planner_actions_to_verified_packets():
    bot = Mock()
    bot.state.value = "IN_MAP"
    bot.move_on_join = None
    bot.room_id = 273
    runtime = farming.FarmingRuntime(bot=bot)
    planner = runtime.auto_planner
    assert isinstance(planner, AutoPlanner)

    # Stub only the action methods; the planner itself is the real object.
    calls: list[str] = []
    runtime.attack_auto = lambda: calls.append("attack")
    runtime.move_to_cell = lambda c, p=None: calls.append(f"move {c}")
    runtime.complete_quest = lambda q, *a: calls.append(f"turn_in {q}")

    planner.set_goal(AutoGoal(kind="farm", target_name="Skeleton"))

    # Observe one live enemy in our own cell -> attack.
    runtime.combat.state.monsters = {
        1: _fake_monster(cell=runtime.combat.state.cell, alive=True),
    }
    runtime.auto_tick()
    assert calls == ["attack"]

    # Enemy in another cell -> move there, not attack.
    calls.clear()
    runtime.combat.state.monsters = {
        1: _fake_monster(cell="Boss", alive=True),
    }
    runtime.auto_tick()
    assert calls == ["move Boss"]

    # No enemies anywhere -> wait, and emit no packet.
    calls.clear()
    runtime.combat.state.monsters = {}
    runtime.auto_tick()
    assert calls == []

    # Disconnect pauses instead of firing into a dead socket.
    calls.clear()
    bot.state = Mock(value="DISCONNECTED")
    runtime.auto_tick()
    assert calls == []


def test_auto_farm_goal_joins_private_room_only_when_flagged():
    bot = Mock()
    bot.state.value = "IN_MAP"
    bot.current_map = "battleon"
    bot.move_on_join = None
    bot.room_id = 273
    runtime = farming.FarmingRuntime(bot=bot)
    joined: list[tuple[str, bool]] = []
    runtime.join = lambda name, private=False: joined.append((name, private))

    runtime.set_auto_goal(
        AutoGoal(kind="farm", target_name="Skeleton", map_name="oaklore")
    )
    runtime.auto_tick()
    assert joined == [("oaklore", False)]

    joined.clear()
    runtime.set_auto_goal(AutoGoal(
        kind="farm", target_name="Skeleton", map_name="oaklore", private=True,
    ))
    runtime.auto_tick()
    assert joined == [("oaklore", True)]

    joined.clear()
    bot.current_map = "oaklore"
    runtime.set_auto_goal(AutoGoal(
        kind="farm", target_name="Skeleton", map_name="oaklore", private=True,
    ))
    runtime.auto_tick()
    assert joined == [("oaklore", True)]


def test_farming_runtime_refuses_drop_goal_until_item_tracking_exists():
    bot = Mock()
    bot.move_on_join = None
    bot.room_id = 273
    runtime = farming.FarmingRuntime(bot=bot)
    goal = AutoGoal(kind="drop", target_name="Skeleton", drop_name="Bone", quantity=5)
    with pytest.raises(ValueError):
        runtime.set_auto_goal(goal)


def test_farming_runtime_stop_stops_the_auto_goal():
    bot = Mock()
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(bot=bot)
    runtime.auto_planner.set_goal(AutoGoal(kind="farm", target_name="Skeleton"))
    assert runtime.auto_planner.active is True
    runtime.stop()
    assert runtime.auto_planner.active is False


def test_farming_runtime_rest_pickup_and_quest_use_verified_packets():
    sent: list[str] = []
    bot = Mock()
    bot.room_id = 273
    bot._send_raw = lambda pkt: sent.append(_wire(pkt))
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(bot=bot, profile=farming.FarmProfile())

    runtime.rest()
    runtime.pickup_drop(9911)
    runtime.use_booster(1234)
    runtime.complete_quest(quest_id=101, reward_id=5, turn_ins="1,2")

    assert "%xt%zm%emotea%1%rest%" in sent
    assert "%xt%zm%getDrop%273%9911%" in sent
    assert "%xt%zm%serverUseItem%273%+%1234%" in sent
    assert "%xt%zm%tryQuestComplete%273%101%5%false%1,2%wvz%" in sent


def test_farming_runtime_attack_controls_combat_engine():
    class FakeCombat:
        running = False
        target_name = "Water Draconian"
        auto = False
        map_wide = False

        def set_auto(self, enabled):
            self.auto = bool(enabled)

        def set_map_wide(self, enabled):
            self.map_wide = bool(enabled)

        def start(self):
            self.running = True

        def stop(self):
            self.running = False

        def status(self):
            return "COMBAT ON"

    bot = Mock()
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(bot=bot, profile=farming.FarmProfile())
    runtime.combat = FakeCombat()
    runtime.attack("Water Draconian")
    assert runtime.combat.running is True
    assert runtime.combat.auto is False
    assert runtime.combat.map_wide is False
    runtime.stop_attack()
    assert runtime.combat.running is False
    assert runtime.combat.map_wide is False
    assert runtime.combat_status() == "COMBAT ON"

    runtime.attack("auto")
    assert runtime.combat.running is True
    assert runtime.combat.auto is True
    assert runtime.combat.map_wide is False
    runtime.combat.target_name = "Water Draconian"

    with pytest.raises(ValueError):
        runtime.attack("Frogzard")


def test_farming_runtime_feeds_combat_and_captures_on_request(tmp_path):
    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(
        bot=bot,
        profile=farming.FarmProfile(),
        combat_capture_path=tmp_path / "combat.log",
    )
    runtime.set_combat_capture(True)
    runtime.feed_packet('{"t":"xt","b":{"r":42,"o":{"cmd":"updateClass","uid":29185,"sClassName":"Mage"}}}')
    assert runtime.combat.state.class_name == "Mage"
    assert "updateClass" in (tmp_path / "combat.log").read_text(encoding="utf-8")


def test_farming_orchestrator_stays_active_and_joins_farm_map(mock_server, tmp_path, monkeypatch):
    """Farming mode: no AFK packet, no AI, and the farm map is the target."""
    from skua_lite import bot as bot_mod, credentials, login, runner, servers

    monkeypatch.setattr(
        login, "aqw_login",
        lambda u, p, *, timeout=20: login.LoginToken(username=u, token="TOK", success=True),
    )
    monkeypatch.setattr(
        servers, "fetch_server_list",
        lambda *, timeout=20: {"Yorumi": servers.Server(
            name="Yorumi", ip=mock_server.host, port=mock_server.port,
            online=True, full=False, upgrade_only=False,
        )},
    )
    # Even with AI configured, farming must not build the assistant stack.
    monkeypatch.setenv("SKUA_AI_BASE_URL", "https://ai.example/v1")
    monkeypatch.setenv("SKUA_AI_API_KEY", "test-key")
    monkeypatch.setenv("SKUA_AI_MODEL", "test-model")
    monkeypatch.setattr(
        runner, "openai_chat_generator",
        lambda _cfg: pytest.fail("farming mode must not build an AI generator"),
    )

    store = credentials.CredentialStore(base_dir=tmp_path)
    store.save("alice", "pw")
    monkeypatch.setattr("builtins.input", lambda *a, **k: "y")

    orch = runner.Orchestrator(
        server_name="Yorumi", store=store, mode=RunMode.FARMING
    )
    orch.auto_relogin = False
    assert orch.target_map == "lair-100000"

    orch.connect("alice", "pw")
    assert orch.bot.state == bot_mod.BotState.IN_MAP
    assert orch.bot.ai_router is None
    assert orch.farming is not None and orch.farming.running is True
    assert orch.bot.is_afk is False

    orch.farming.pickup_drop(9911)
    time.sleep(0.2)
    assert any("%xt%zm%getDrop%42%9911%" in p for p in mock_server.received)
    assert not any("%xt%zm%cmd%42%afk%" in p for p in mock_server.received)

    # Combat state must be seeded by the handshake script itself.
    assert orch.farming.combat.state.class_name == "Mage"
    alive = orch.farming.combat.state.alive_monsters("Water Draconian")
    assert [monster.map_id for monster in alive] == [1]
    orch.farming.attack("Water Draconian")
    time.sleep(0.2)
    assert any("%xt%zm%gar%1%0%a4>m:1%wvz%" in p for p in mock_server.received)

    orch.shutdown()


def test_farm_cli_accepts_dot_prefix_and_auto_attack():
    from skua_lite import cli

    assert cli.parse_farm_command(".status") == ("status", "")
    assert cli.parse_farm_command(".") == ("status", "")
    assert cli.parse_farm_command(".join lair-100000") == ("join", "lair-100000")
    assert cli.parse_farm_command(".rest") == ("rest", "")
    assert cli.parse_farm_command(".combat") == ("combat", "")
    assert cli.parse_farm_command(".attack auto") == ("attack", "auto")
    assert cli.parse_farm_command(".attack off") == ("attack", "off")
    assert cli.parse_farm_command(".capture on") == ("capture", "on")
    assert cli.parse_farm_command(".chat /join lair-100000") == (
        "chat", "/join lair-100000"
    )
    assert cli.parse_farm_command(".chat /goto mele") == ("chat", "/goto mele")
    assert cli.parse_farm_command(".cells") == ("cells", "")
    assert cli.parse_farm_command(".cell Stairs") == ("cell", "Stairs")
    assert cli.parse_farm_command(".cell Cave BottomLeft") == (
        "cell", "Cave BottomLeft"
    )
    assert cli.parse_farm_command(".drop 9911") == ("drop", "9911")
    # Legacy `farm ...` spelling keeps working.
    assert cli.parse_farm_command("farm join yulgar") == ("join", "yulgar")
    assert cli.parse_farm_command(".say hi") == ("", "")
    assert cli.parse_farm_command("chat halo") == ("", "")

    calls: list[tuple[str, object]] = []

    class FakeRuntime:
        def attack(self, name=""):
            if str(name).strip().lower() == "auto":
                self.attack_auto()
                return
            calls.append(("attack", name))

        def attack_auto(self):
            calls.append(("attack_auto", None))

        def stop_attack(self):
            calls.append(("stop_attack", None))

        def rest(self):
            calls.append(("rest", None))

        def chat(self, message):
            calls.append(("chat", message))

        def move_to_cell(self, cell, pad=None):
            calls.append(("cell", (cell, pad)))

        def cell_scan_report(self):
            calls.append(("cells", None))
            return ["Enter [KAMU] (1 monster)", "Boss (0 monster)"]

        def combat_status(self):
            calls.append(("combat", None))
            return "ok"

    orch = Mock()
    orch.farming = FakeRuntime()

    cli.dispatch_farm(orch, "attack", "auto")
    cli.dispatch_farm(orch, "chat", "/goto mele")
    cli.dispatch_farm(orch, "cell", "Stairs")
    cli.dispatch_farm(orch, "cell", "Cave BottomLeft")
    cli.dispatch_farm(orch, "cells", "")
    cli.dispatch_farm(orch, "rest", "")
    cli.dispatch_farm(orch, "combat", "")
    cli.dispatch_farm(orch, "attack", "off")

    assert calls == [
        ("attack_auto", None),
        ("chat", "/goto mele"),
        ("cell", ("Stairs", None)),
        ("cell", ("Cave", "BottomLeft")),
        ("cells", None),
        ("rest", None),
        ("combat", None),
        ("stop_attack", None),
    ]


def test_farming_control_accepts_goal_sentence_not_only_commands():
    from skua_lite import cli

    assert cli.parse_farm_command("lawan semua musuh yang ada di map ini") == (
        "goal", "clear_map"
    )
    assert cli.parse_farm_command("Lawan semua musuh di map ini") == (
        "goal", "clear_map"
    )
    assert cli.parse_farm_command("berhenti lawan musuh") == ("goal", "stop")

    calls: list[str] = []

    class GoalRuntime:
        def fight_all_in_map(self):
            calls.append("clear_map")

        def stop_goal(self):
            calls.append("stop")

    orch = Mock(farming=GoalRuntime())
    cli.dispatch_farm(orch, "goal", "clear_map")
    cli.dispatch_farm(orch, "goal", "stop")
    assert calls == ["clear_map", "stop"]


def test_farming_runtime_map_goal_owns_combat_and_navigation():
    class GoalCombat:
        running = False
        map_wide = False

        def set_map_wide(self, enabled):
            self.map_wide = bool(enabled)

        def start(self):
            self.running = True

        def stop(self):
            self.running = False

    logs: list[str] = []
    bot = Mock()
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(
        bot=bot, profile=farming.FarmProfile(), on_log=logs.append
    )
    runtime.combat = GoalCombat()

    runtime.fight_all_in_map()
    assert runtime.combat.map_wide is True
    assert runtime.combat.running is True
    assert any("semua musuh" in line for line in logs)

    runtime.stop_goal()
    assert runtime.combat.map_wide is False
    assert runtime.combat.running is False


def test_farming_area_report_uses_shared_generation_snapshot():
    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(bot=bot, profile=farming.FarmProfile())
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"lair-100000","strMapName":"lair","strMapFileName":"lair-v1.swf",'
        '"uoBranch":[{"uoName":"alice","uid":29185,"strFrame":"Enter",'
        '"strPad":"Spawn","intHP":900,"intHPMax":900,"intState":1}],'
        '"monBranch":[{"MonMapID":1,"MonID":100,"intHP":500,"intHPMax":500,"intState":1}],'
        '"mondef":[{"MonID":100,"strMonName":"Water Draconian"}],'
        '"monmap":[{"MonMapID":1,"MonID":100,"strFrame":"Enter"}]}}}'
    )

    rows = runtime.area_report()
    assert rows[0] == "area lair-100000 room 42 generation 1 [wire]"
    assert any("m:1 Water Draconian" in row for row in rows)
    assert runtime.area_json() == runtime.area_json()


def test_farming_cli_dispatches_area_human_and_json_reports(capsys):
    from skua_lite import cli

    assert cli.parse_farm_command(".area") == ("area", "")
    assert cli.parse_farm_command(".area json") == ("area", "json")

    class Runtime:
        def area_report(self):
            return ["area lair-1 room 42 generation 1 [wire]"]

        def area_json(self):
            return '{"schema_version":1}'

    orch = Mock(farming=Runtime())
    cli.dispatch_farm(orch, "area", "")
    cli.dispatch_farm(orch, "area", "json")
    out = capsys.readouterr().out
    assert "[AREA] area lair-1 room 42 generation 1 [wire]" in out
    assert '{"schema_version":1}' in out


def test_farming_runtime_scans_map_swf_cells_and_moves_between_them(tmp_path):
    from skua_lite.map_cells import MapCellScanner

    logs: list[str] = []
    scanned: list[str] = []

    def fetch(url, timeout):
        scanned.append(url)
        return _swf_bytes(["Enter", "Stairs", "Cave"])

    sent: list[str] = []
    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot.move_on_join = None
    bot._send_raw = lambda pkt: sent.append(_wire(pkt))
    runtime = farming.FarmingRuntime(
        bot=bot,
        profile=farming.FarmProfile(),
        on_log=logs.append,
        cell_scanner=MapCellScanner(cache_dir=tmp_path, fetch=fetch),
    )

    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"lair-100000","strMapName":"lair","strMapFileName":"lair-v1.swf",'
        '"uoBranch":[{"uoName":"alice","uid":29185,"strFrame":"Enter",'
        '"strPad":"Spawn","intHP":900,"intHPMax":900,"intState":1}],'
        '"monBranch":[],"mondef":[],"monmap":[]}}}'
    )

    deadline = time.monotonic() + 10
    while not scanned and time.monotonic() < deadline:
        time.sleep(0.01)
    while (
        not runtime.combat.state.map_cells and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert scanned == ["https://game.aq.com/game/gamefiles/maps/lair-v1.swf"]
    assert runtime.cell_scan_report()[0].startswith("map lair-v1.swf")
    assert any("Stairs" in row for row in runtime.cell_scan_report())
    assert any("scan lair-v1.swf" in line for line in logs)

    runtime.move_to_cell("Stairs")
    assert sent == ["%xt%zm%moveToCell%42%Stairs%Left%"]

    # A second feed must not re-download the same map file.
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"lair-100000","strMapName":"lair","strMapFileName":"lair-v1.swf",'
        '"uoBranch":[{"uoName":"alice","uid":29185,"strFrame":"Enter",'
        '"strPad":"Spawn","intHP":900,"intHPMax":900,"intState":1}],'
        '"monBranch":[],"mondef":[],"monmap":[]}}}'
    )
    assert len(scanned) == 1


def test_farming_runtime_keeps_observed_cells_when_swf_scan_fails():
    from skua_lite.map_cells import SWFCellError

    logs: list[str] = []

    def fetch(url, timeout):
        raise SWFCellError("bukan file SWF")

    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(
        bot=bot, profile=farming.FarmProfile(), on_log=logs.append, cell_scanner=None
    )

    class FailingScanner:
        def scan(self, file_name):
            raise SWFCellError("bukan file SWF")

    runtime.cell_scanner = FailingScanner()
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"lair-100000","strMapName":"lair","strMapFileName":"lair-v1.swf",'
        '"uoBranch":[{"uoName":"alice","uid":29185,"strFrame":"Enter",'
        '"strPad":"Spawn","intHP":900,"intHPMax":900,"intState":1}],'
        '"monBranch":[{"MonMapID":1,"MonID":100,"intHP":500,"intHPMax":500,"intState":1}],'
        '"mondef":[{"MonID":100,"strMonName":"Water Draconian"}],'
        '"monmap":[{"MonMapID":1,"MonID":100,"strFrame":"Boss"}]}}}'
    )

    report = runtime.cell_scan_report()
    assert report[0].startswith("scan server parsial")
    assert any(row.startswith("Enter [KAMU]") for row in report)
    assert any(row.startswith("Boss ") for row in report)
    assert any("scan SWF map gagal" in line for line in logs)


def test_farming_map_swf_scan_runs_in_background_and_never_truncates(tmp_path):
    from skua_lite.map_cells import MapCellScanner

    release = threading.Event()
    entered = threading.Event()

    def slow_fetch(url, timeout):
        assert timeout == url_timeout(url)
        entered.set()
        assert release.wait(timeout=10)
        return _swf_bytes([*[f"Cell{i:03d}" for i in range(60)], "Enter"])

    def url_timeout(url):
        from skua_lite.map_cells import DEFAULT_FETCH_TIMEOUT
        return DEFAULT_FETCH_TIMEOUT

    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot.move_on_join = None
    runtime = farming.FarmingRuntime(
        bot=bot,
        profile=farming.FarmProfile(),
        cell_scanner=MapCellScanner(cache_dir=tmp_path, fetch=slow_fetch),
    )

    entered.clear()
    runtime.feed_packet(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":42,'
        '"areaName":"lair-100000","strMapName":"lair","strMapFileName":"lair-v1.swf",'
        '"uoBranch":[{"uoName":"alice","uid":29185,"strFrame":"Enter",'
        '"strPad":"Spawn","intHP":900,"intHPMax":900,"intState":1}],'
        '"monBranch":[],"mondef":[],"monmap":[]}}}'
    )

    # The packet thread returns while the download still runs.
    assert entered.wait(timeout=10)
    assert runtime.cell_scan_report()[0].startswith("scan server parsial")

    release.set()
    deadline = time.monotonic() + 10
    while (
        runtime.cell_scan_report()[0].startswith("scan server parsial")
        and time.monotonic() < deadline
    ):
        time.sleep(0.02)
    report = runtime.cell_scan_report()
    assert report[0].startswith("map lair-v1.swf")
    assert len(report) == 1 + 61 + 1  # header + all cells + pad row
    assert any(row.startswith("Cell059 ") for row in report)
    assert rows_in_observed_order(report)


def rows_in_observed_order(report: list[str]) -> bool:
    enter = next(i for i, row in enumerate(report) if row.startswith("Enter [KAMU]"))
    first_cell = next(i for i, row in enumerate(report) if row.startswith("Cell000 "))
    return enter < first_cell


def test_farm_cli_parses_combat_capture_and_dispatches_commands():
    from skua_lite import cli

    assert cli.parse_farm_command("farm status") == ("status", "")
    assert cli.parse_farm_command("farm") == ("status", "")
    assert cli.parse_farm_command("farm join yulgar") == ("join", "yulgar")
    assert cli.parse_farm_command("farm attack Water Draconian") == ("attack", "Water Draconian")
    assert cli.parse_farm_command("farm capture on") == ("capture", "on")
    assert cli.parse_farm_command("chat halo") == ("", "")

    calls: list[tuple[str, object]] = []

    class FakeRuntime:
        def status(self):
            calls.append(("status", None))
            return "ok"

        def join(self, target, private=False):
            calls.append(("join", target))

        def complete_quest(self, quest_id, reward_id=-1, turn_ins=""):
            calls.append(("quest", (quest_id, reward_id, turn_ins)))

        def load_bank(self):
            calls.append(("bank", "load"))

        def sell(self, item_id, quantity, char_item_id):
            calls.append(("sell", (item_id, quantity, char_item_id)))

        def attack(self, target):
            calls.append(("attack", target))

        def set_combat_capture(self, enabled):
            calls.append(("capture", enabled))

    orch = Mock()
    orch.farming = FakeRuntime()

    cli.dispatch_farm(orch, "status", "")
    cli.dispatch_farm(orch, "join", "yulgar")
    cli.dispatch_farm(orch, "quest", "101 5 1,2")
    cli.dispatch_farm(orch, "bank", "load")
    cli.dispatch_farm(orch, "sell", "55 3 777")
    cli.dispatch_farm(orch, "attack", "Water Draconian")
    cli.dispatch_farm(orch, "capture", "on")

    assert calls == [
        ("status", None),
        ("join", "yulgar"),
        ("quest", (101, 5, "1,2")),
        ("bank", "load"),
        ("sell", (55, 3, 777)),
        ("attack", "Water Draconian"),
        ("capture", True),
    ]


def test_farming_orchestrator_connect_skips_ai_and_afk(monkeypatch):
    """connect() in farming mode never builds the assistant stack."""
    from skua_lite import runner

    monkeypatch.setattr(runner.AIConfig, "from_env", lambda: Mock(configured=True))
    monkeypatch.setattr(
        runner,
        "openai_chat_generator",
        lambda cfg: pytest.fail("farming mode must not build a generator"),
    )

    orch = runner.Orchestrator(mode=RunMode.FARMING)
    assert orch.mode is RunMode.FARMING

    built = {}

    class FakeBot:
        def __init__(self, **kwargs):
            built.update(kwargs)
            self.current_map = "battleon-100000"
            self.room_id = 3
            self.is_afk = False
            self.state = Mock(value="IN_MAP")
            self.ai_router = kwargs.get("ai_router")

        def start(self):
            self.state = Mock(value="IN_MAP")

    monkeypatch.setattr(runner.bot_mod, "AQWBot", FakeBot)
    monkeypatch.setattr(
        runner.login, "aqw_login", lambda u, p: Mock(username=u, token="t")
    )
    monkeypatch.setattr(
        runner.servers,
        "fetch_server_list",
        lambda: [Mock(name="Yorumi", ip="1.2.3.4", port=5588)],
    )
    monkeypatch.setattr(runner.servers, "pick", lambda lst, name: lst[0])
    orch.auto_relogin = False

    orch.connect("alice", "pw")
    assert built.get("ai_router") is None
    assert orch.farming is not None
    assert orch.farming.running is True
