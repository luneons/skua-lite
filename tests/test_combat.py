"""Combat protocol tests: capture, state parsing, Mage profile, and GAR.

Fixtures mirror the active Game.as paths:
- JSON moveToArea/updateClass/sAct
- STR mtls/respawnMon
- World.getActionResult GAR serialization
"""
from __future__ import annotations

import json
import time
from unittest.mock import Mock

import pytest

from skua_lite import combat, sfs


def _json_packet(cmd: str, **fields) -> str:
    obj = {"cmd": cmd, **fields}
    return json.dumps({"t": "xt", "b": {"r": 42, "o": obj}}, separators=(",", ":"))


def _mage_area_packet(username: str = "alice", uid: int = 29185) -> str:
    return _json_packet(
        "moveToArea",
        areaId=42,
        areaName="lair-100000",
        strMapName="lair",
        uoBranch=[
            {
                "uoName": username,
                "uid": uid,
                "strFrame": "Enter",
                "strPad": "Spawn",
                "intHP": 900,
                "intHPMax": 900,
                "intMP": 300,
                "intMPMax": 300,
                "intState": 1,
            }
        ],
        monBranch=[
            {"MonMapID": 1, "MonID": 100, "intHP": 500, "intHPMax": 500, "intState": 1},
            {"MonMapID": 2, "MonID": 100, "intHP": 400, "intHPMax": 500, "intState": 1},
            {"MonMapID": 9, "MonID": 200, "intHP": 800, "intHPMax": 800, "intState": 1},
        ],
        mondef=[
            {"MonID": 100, "strMonName": "Water Draconian", "sRace": "Dragonkin"},
            {"MonID": 200, "strMonName": "Other Monster", "sRace": "Elemental"},
        ],
        monmap=[
            {"MonMapID": 1, "MonID": 100, "strFrame": "Enter"},
            {"MonMapID": 2, "MonID": 100, "strFrame": "Enter"},
            {"MonMapID": 9, "MonID": 200, "strFrame": "Room2"},
        ],
    )


def _mixed_cell_packet() -> str:
    """Three species in the same cell plus one elsewhere, for `.attack auto`."""
    return _json_packet(
        "moveToArea",
        areaId=42,
        areaName="lair-100000",
        strMapName="lair",
        uoBranch=[
            {
                "uoName": "alice",
                "uid": 29185,
                "strFrame": "Enter",
                "intHP": 900,
                "intHPMax": 900,
                "intMP": 300,
                "intMPMax": 300,
                "intState": 1,
            }
        ],
        monBranch=[
            {"MonMapID": 1, "MonID": 100, "intHP": 500, "intHPMax": 500, "intState": 1},
            {"MonMapID": 2, "MonID": 100, "intHP": 400, "intHPMax": 500, "intState": 1},
            {"MonMapID": 3, "MonID": 300, "intHP": 200, "intHPMax": 300, "intState": 1},
            {"MonMapID": 9, "MonID": 200, "intHP": 100, "intHPMax": 800, "intState": 1},
        ],
        mondef=[
            {"MonID": 100, "strMonName": "Water Draconian"},
            {"MonID": 300, "strMonName": "Frogzard"},
            {"MonID": 200, "strMonName": "Other Monster"},
        ],
        monmap=[
            {"MonMapID": 1, "MonID": 100, "strFrame": "Enter"},
            {"MonMapID": 2, "MonID": 100, "strFrame": "Enter"},
            {"MonMapID": 3, "MonID": 300, "strFrame": "Enter"},
            {"MonMapID": 9, "MonID": 200, "strFrame": "Room2"},
        ],
    )


def _mage_skills_packet() -> str:
    return _json_packet(
        "sAct",
        actions={
            "active": [
                {"ref": "aa", "nam": "Fireball", "auto": True, "typ": "aa", "tgt": "h", "tgtMin": 1, "tgtMax": 1, "cd": 1800, "mp": 0, "isOK": True},
                {"ref": "a1", "nam": "Explosion", "typ": "m", "tgt": "h", "tgtMin": 1, "tgtMax": 2, "cd": 4000, "mp": 10, "isOK": True},
                {"ref": "a2", "nam": "Ice Shard", "typ": "m", "tgt": "h", "tgtMin": 1, "tgtMax": 1, "cd": 5000, "mp": 15, "isOK": True},
                {"ref": "a3", "nam": "Arcane Shield", "typ": "m", "tgt": "s", "tgtMin": 1, "tgtMax": 1, "cd": 8000, "mp": 20, "isOK": True},
                {"ref": "a4", "nam": "Meteor", "typ": "m", "tgt": "h", "tgtMin": 1, "tgtMax": 3, "cd": 12000, "mp": 25, "isOK": True},
            ]
        },
    )


def test_gar_packet_serializes_hostile_area_and_item_targets():
    wire = lambda packet: packet.rstrip(b"\x00").decode("latin-1")
    assert wire(sfs.gar_packet(1, 12, "aa", ["m:1"])) == "%xt%zm%gar%1%12%aa>m:1%wvz%"
    assert wire(sfs.gar_packet(1, 13, "a1", ["m:1", "m:2"])) == (
        "%xt%zm%gar%1%13%a1>m:1,a1>m:2%wvz%"
    )
    assert wire(sfs.gar_packet(1, 15, "a2", ["p:29185", "p:29129"])) == (
        "%xt%zm%gar%1%15%a2>p:29185,a2>p:29129%wvz%"
    )
    assert wire(sfs.gar_packet(1, 24, "i1", ["m:1"], item_id=87139)) == (
        "%xt%zm%gar%1%24%i1>m:1%87139%wvz%"
    )


def test_gar_packet_rejects_bad_refs_targets_and_missing_item():
    for ref in ("a5", "gar", ""):
        try:
            sfs.gar_packet(1, 0, ref, ["m:1"])
        except ValueError:
            pass
        else:
            raise AssertionError(f"bad ref accepted: {ref}")
    for target in ("m:x", "p:-1", "x:1"):
        try:
            sfs.gar_packet(1, 0, "aa", [target])
        except ValueError:
            pass
        else:
            raise AssertionError(f"bad target accepted: {target}")
    try:
        sfs.gar_packet(1, 0, "i1", ["m:1"])
    except ValueError:
        pass
    else:
        raise AssertionError("i1 without item ID accepted")


def test_combat_state_learns_class_from_equipped_inventory_and_sact():
    state = combat.CombatState(self_username="alice", self_user_id=29185)
    state.feed(_mage_area_packet())
    state.feed(_mage_skills_packet())
    state.feed(_json_packet(
        "loadInventoryBig",
        items={
            "10": {"ItemID": 10, "sName": "Mage", "sType": "Class", "sES": "co", "bEquip": "1"},
            "11": {"ItemID": 11, "sName": "Warrior", "sType": "Class", "sES": "ar", "bEquip": "0"},
        },
    ))

    assert state.class_name == "Mage"
    assert state.class_item_id == 10
    assert state.cell == "Enter"
    assert state.hp == 900 and state.mp == 300
    assert [m.map_id for m in state.alive_monsters("Water Draconian")] == [2, 1]
    assert [m.map_id for m in state.alive_monsters()] == [2, 1]
    assert state.skills["a1"].max_targets == 2
    assert state.skills["a3"].target_kind == "s"


def test_combat_state_tracks_mtls_death_respawn_and_cell_change():
    state = combat.CombatState(self_username="alice", self_user_id=29185)
    state.feed(_mage_area_packet())
    state.feed("%xt%mtls%-1%1%intHP:0,intState:0%")
    assert [m.map_id for m in state.alive_monsters()] == [2]

    state.feed("%xt%respawnMon%-1%1%")
    assert [m.map_id for m in state.alive_monsters()] == [2, 1]

    state.feed("%xt%uotls%-1%alice%strFrame:Room2,intHP:800,intMP:250,intState:1%")
    assert state.cell == "Room2"
    assert [m.map_id for m in state.alive_monsters()] == [9]


def test_mage_fast_farm_profile_uses_skua_sequence_4213():
    profile = combat.ClassProfile.from_dict({
        "class_name": "Mage",
        "aliases": ["Mage"],
        "modes": {"farm_fast": {"skills": [4, 2, 1, 3], "fallback": "aa"}},
    })
    assert profile.skill_refs("farm_fast") == ("a4", "a2", "a1", "a3", "aa")
    assert profile.matches("mage")


def test_engine_scans_water_draconian_and_sends_area_skill_then_cooldown_fallback():
    sent: list[str] = []
    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot._send_raw = lambda packet: sent.append(packet.rstrip(b"\x00").decode("latin-1"))
    times = iter((100.0, 100.1, 102.0))
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
        mode="farm_fast",
        clock=lambda: next(times),
    )
    engine.feed(_mage_area_packet())
    engine.feed(_json_packet("updateClass", uid=29185, sClassName="Mage", ItemID=10))
    engine.feed(_mage_skills_packet())

    assert engine.tick() is True
    assert sent == ["%xt%zm%gar%1%0%a4>m:2,a4>m:1%wvz%"]
    # Global cooldown blocks non-AA skills, but Game.as permits the AA fallback.
    assert engine.tick() is True
    assert sent[-1] == "%xt%zm%gar%1%1%aa>m:2%wvz%"
    # a4 is cooling down, so after GCD the next ready Mage entry is a2.
    assert engine.tick() is True
    assert sent[-1] == "%xt%zm%gar%1%2%a2>m:2%wvz%"


def test_engine_requires_live_matching_class_and_monster():
    bot = Mock(room_id=42, session_user_id=29185, username="alice", _send_raw=Mock())
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
    )
    engine.feed(_mage_area_packet())
    engine.feed(_json_packet("updateClass", uid=29185, sClassName="Warrior", ItemID=20))
    engine.feed(_mage_skills_packet())
    assert engine.tick() is False
    bot._send_raw.assert_not_called()


def test_engine_can_capture_combat_packets_without_chat_or_tokens(tmp_path):
    capture = tmp_path / "combat_capture.log"
    engine = combat.AutoAttackEngine(
        Mock(room_id=42, session_user_id=29185, username="alice", _send_raw=Mock()),
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
        capture_path=capture,
    )
    engine.set_capture(True)
    engine.feed(_mage_area_packet())
    engine.feed(_mage_skills_packet())
    engine.feed("%xt%chatm%-1%zone~my secret chat%Alice%29185%42%0%")
    text = capture.read_text(encoding="utf-8")
    assert "moveToArea" in text and "sAct" in text
    assert "my secret chat" not in text


def test_combat_state_parses_live_nested_uotls_and_mtls():
    state = combat.CombatState(self_username="stars bot", self_user_id=29467)
    state.feed(_mage_area_packet())
    state.feed(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"uotls","unm":"stars bot",'
        '"o":{"intHPMax":3035,"intMPMax":100,"intHP":3035,"intMP":94,'
        '"intState":1,"strFrame":"Enter"}}}}'
    )
    assert (state.hp, state.max_hp, state.mp, state.player_state, state.cell) == (
        3035, 3035, 94, 1, "Enter"
    )

    state.feed(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"uotls","unm":"stars bot",'
        '"o":{"intState":0,"intHP":0}}}}'
    )
    assert state.hp == 0 and state.player_state == 0

    state.feed(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"mtls","id":1,'
        '"o":{"intState":0,"intHP":0}}}}'
    )
    assert state.monsters[1].hp == 0 and state.monsters[1].state == 0


def test_engine_capture_marks_inbound_and_outbound_combat_packets(tmp_path):
    capture = tmp_path / "combat_capture.log"
    engine = combat.AutoAttackEngine(
        Mock(room_id=42, session_user_id=29185, username="alice", _send_raw=Mock()),
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
        capture_path=capture,
    )
    engine.set_capture(True)
    engine.feed(_mage_skills_packet())
    engine.feed("%xt%zm%resPlayerTimed%42%29185%", outbound=True)
    engine.feed("%xt%chatm%-1%zone~my secret chat%Alice%29185%42%0%")
    text = capture.read_text(encoding="utf-8")
    assert "IN  " in text and "sAct" in text
    assert "OUT " in text and "resPlayerTimed" in text
    assert "my secret chat" not in text


def test_engine_respawns_once_after_death_like_world_res_player():
    """Live capture 2026-09-29: after death the server only repeats
    ``uotls ... intState:0,intHP:0``; the Flash client owns the 10s countdown
    (World.showResCounter -> resTimer -> resPlayer) and sends resPlayerTimed.
    Headless must reproduce that or the character stays dead forever."""
    wire = lambda packet: packet.rstrip(b"\x00").decode("latin-1")
    sent: list[str] = []
    bot = Mock(room_id=42, session_user_id=29467, username="mele")
    bot._send_raw = lambda packet: sent.append(wire(packet))
    times = iter((100.0, 111.0, 111.5, 112.0, 113.0))
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
        mode="farm_fast",
        clock=lambda: next(times),
    )
    engine.feed(_mage_area_packet(username="mele", uid=29467))
    engine.feed(_json_packet("updateClass", uid=29467, sClassName="Mage", ItemID=10))
    engine.feed(_mage_skills_packet())
    engine.feed(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"uotls","unm":"mele",'
        '"o":{"intState":0,"intHP":0}}}}'
    )
    assert engine.state.player_state == 0 and engine.state.hp == 0

    # Dead: no attack packet, and the 10s countdown has not elapsed.
    assert engine.tick() is False
    assert sent == []

    # Countdown elapsed -> exactly one respawn request.
    assert engine.tick() is False
    assert sent == ["%xt%zm%resPlayerTimed%42%29467%"]

    # Repeated ticks must not spam the server.
    assert engine.tick() is False
    assert engine.tick() is False
    assert len(sent) == 1

    # Alive again resets the latch so the next death can respawn too.
    engine.feed(
        '{"t":"xt","b":{"r":-1,"o":{"cmd":"uotls","unm":"mele",'
        '"o":{"intState":1,"intHP":3035,"intHPMax":3035}}}}'
    )
    assert engine.tick() is True
    assert len(sent) == 2


def test_sfs_builds_respawn_packet_from_world_call_site():
    wire = lambda packet: packet.rstrip(b"\x00").decode("latin-1")
    assert wire(sfs.res_player_timed_packet(29467, room=42)) == (
        "%xt%zm%resPlayerTimed%42%29467%"
    )
    try:
        sfs.res_player_timed_packet(0)
    except ValueError:
        pass
    else:
        raise AssertionError("uid 0 accepted")


def test_engine_respawn_delay_defaults_to_ten_seconds():
    engine = combat.AutoAttackEngine(
        Mock(room_id=-1, session_user_id=29467, username="mele", _send_raw=Mock()),
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
    )
    assert engine.respawn_delay == 10.0


def test_engine_handles_res_timed_by_moving_to_spawn():
    wire = lambda packet: packet.rstrip(b"\x00").decode("latin-1")
    sent: list[str] = []
    bot = Mock(room_id=42, session_user_id=29467, username="mele")
    bot._send_raw = lambda packet: sent.append(wire(packet))
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
    )
    engine.feed(_mage_area_packet(username="mele", uid=29467))
    engine.feed("%xt%resTimed%-1%Enter%Spawn%")
    assert sent == ["%xt%zm%moveToCell%42%Enter%Spawn%"]


def test_engine_does_not_respawn_before_self_state_is_loaded():
    bot = Mock(room_id=42, session_user_id=29467, username="mele", _send_raw=Mock())
    times = iter((100.0, 120.0))
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
        clock=lambda: next(times),
    )
    assert engine.tick() is False
    assert engine.tick() is False
    bot._send_raw.assert_not_called()


def test_engine_auto_mode_attacks_any_alive_monster_from_area_scan():
    """`.attack auto`: no name filter, but the scan still owns the target."""
    wire = lambda packet: packet.rstrip(b"\x00").decode("latin-1")
    sent: list[str] = []
    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot._send_raw = lambda packet: sent.append(wire(packet))
    times = iter((100.0, 100.1))
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
        mode="farm_fast",
        clock=lambda: next(times),
    )
    engine.feed(_mixed_cell_packet())
    engine.feed(_json_packet("updateClass", uid=29185, sClassName="Mage", ItemID=10))
    engine.feed(_mage_skills_packet())

    assert engine.auto is False
    # Same cell (Enter): m:1/m:2 Water Draconian + m:3 Frogzard.
    # Other Monster (m:9) is in Room2, not scanned as a valid target.
    assert sorted(m.map_id for m in engine.state.alive_in_cell()) == [1, 2, 3]

    engine.set_auto(True)
    assert engine.auto is True
    assert engine.tick() is True
    assert sent == ["%xt%zm%gar%1%0%a4>m:3,a4>m:2,a4>m:1%wvz%"]

    engine.set_auto(False)
    assert engine.auto is False
    # Named mode is back: only Water Draconian is eligible, and the 1.5s GCD
    # after a4 leaves `aa` as the ready fallback.
    assert engine.tick() is True
    assert sent[-1] == "%xt%zm%gar%1%1%aa>m:2%wvz%"


def test_engine_map_goal_moves_to_other_enemy_cell_and_keeps_fighting():
    """High-level map goal clears the current cell, moves, then keeps fighting."""
    sent: list[str] = []
    now = [100.0]
    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot._send_raw = lambda packet: sent.append(
        packet.rstrip(b"\x00").decode("latin-1")
    )
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
        clock=lambda: now[0],
        move_timeout=2.0,
        move_retries=1,
    )
    engine.feed(_mixed_cell_packet())
    engine.feed(_json_packet("updateClass", uid=29185, sClassName="Mage", ItemID=10))
    engine.feed(_mage_skills_packet())
    engine.set_map_wide(True)
    assert "map-wide" in engine.status()

    assert engine.tick() is True
    assert "m:1" in sent[-1] or "m:2" in sent[-1] or "m:3" in sent[-1]

    for map_id in (1, 2, 3):
        engine.feed(f"%xt%mtls%-1%{map_id}%intHP:0,intState:0%")
    now[0] = 102.0

    # No live enemy remains in Enter: navigate to the cell that still has m:9.
    assert engine.tick() is True
    assert sent[-1] == "%xt%zm%moveToCell%42%Room2%Left%"
    assert engine.move_status == "requested:Room2/Left"

    # Pending movement is not reported as combat and is not spammed.
    assert engine.tick() is False
    assert sent.count("%xt%zm%moveToCell%42%Room2%Left%") == 1

    # Server state confirms arrival; the same map goal attacks m:9 automatically.
    engine.feed("%xt%uotls%-1%alice%strFrame:Room2,strPad:Left,intHP:900,intState:1%")
    now[0] = 104.0
    assert engine.tick() is True
    assert "m:9" in sent[-1]
    assert engine.move_status == "confirmed:Room2/Left"
    assert engine.map_wide is True


def test_engine_map_goal_retries_movement_once_then_blocks_unreachable_cell():
    sent: list[str] = []
    now = [10.0]
    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    bot._send_raw = lambda packet: sent.append(
        packet.rstrip(b"\x00").decode("latin-1")
    )
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
        clock=lambda: now[0],
        move_timeout=1.0,
        move_retries=1,
    )
    engine.feed(_mixed_cell_packet())
    engine.feed(_json_packet("updateClass", uid=29185, sClassName="Mage", ItemID=10))
    engine.feed(_mage_skills_packet())
    for map_id in (1, 2, 3):
        engine.feed(f"%xt%mtls%-1%{map_id}%intHP:0,intState:0%")
    engine.set_map_wide(True)

    assert engine.tick() is True
    now[0] = 11.1
    assert engine.tick() is True  # one bounded retry
    now[0] = 12.2
    assert engine.tick() is False

    assert sent == [
        "%xt%zm%moveToCell%42%Room2%Left%",
        "%xt%zm%moveToCell%42%Room2%Left%",
    ]
    assert engine.move_status == "failed:Room2/Left"
    assert "Room2" in engine.blocked_cells


def test_engine_auto_mode_stops_when_no_monster_is_alive_in_cell():
    bot = Mock(room_id=42, session_user_id=29185, username="alice", _send_raw=Mock())
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
    )
    engine.feed(_mage_area_packet())
    engine.feed(_json_packet("updateClass", uid=29185, sClassName="Mage", ItemID=10))
    engine.feed(_mage_skills_packet())
    engine.feed("%xt%mtls%-1%1%intHP:0,intState:0%")
    engine.feed("%xt%mtls%-1%2%intHP:0,intState:0%")
    engine.set_auto(True)

    assert engine.tick() is False
    bot._send_raw.assert_not_called()
    assert "auto" in engine.status()


def test_engine_scan_report_lists_monsters_found_by_the_area_scan():
    bot = Mock(room_id=42, session_user_id=29185, username="alice", _send_raw=Mock())
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
    )
    engine.feed(_mixed_cell_packet())
    engine.feed(_json_packet("updateClass", uid=29185, sClassName="Mage", ItemID=10))
    engine.feed(_mage_skills_packet())

    rows = engine.scan_report()
    assert len(rows) == 4
    # Named mode: only the two same-cell Water Draconian are eligible.
    assert "m:1" in rows[0] and "Water Draconian" in rows[0] and "TARGET" in rows[0]
    assert "TARGET" in rows[1] and "m:2" in rows[1]
    assert "m:3" in rows[2] and "TARGET" not in rows[2]
    # m:9 lives in another cell, so the scan reports it as out of cell.
    assert "m:9" in rows[3] and "OTHER-CELL" in rows[3]

    engine.set_auto(True)
    rows = engine.scan_report()
    assert sum("TARGET" in row for row in rows) == 3


def test_state_scans_cells_from_area_snapshot_for_move_to_cell():
    """`.cells` must list only cells the server actually revealed."""
    state = combat.CombatState(self_username="alice", self_user_id=29185)
    state.feed(_mixed_cell_packet())

    # Self cell (Enter) + monster cells (Enter, Room2) + nothing invented.
    assert state.known_cells() == ["Enter", "Room2"]
    assert state.cell == "Enter"


def test_state_cell_scan_includes_other_player_cells():
    state = combat.CombatState(self_username="alice", self_user_id=29185)
    state.feed(_json_packet(
        "moveToArea",
        areaId=42,
        strMapName="lair",
        uoBranch=[
            {"uoName": "alice", "uid": 29185, "strFrame": "Enter", "strPad": "Spawn"},
            {"uoName": "ME LE", "uid": 29637, "strFrame": "Boss", "strPad": "Left"},
        ],
        monBranch=[],
        mondef=[],
        monmap=[],
    ))

    assert state.known_cells() == ["Boss", "Enter"]


def test_move_to_cell_default_pad_follows_client_rule():
    # JumpViewModel: cell "Enter" -> pad "Spawn"; otherwise pad "Left".
    assert combat.default_pad_for("Enter") == "Spawn"
    assert combat.default_pad_for("stairs") == "Left"
    assert combat.default_pad_for("Stairs", "Bottom") == "Bottom"
    assert "BottomLeft" in combat.PAD_NAMES


def test_engine_move_to_cell_uses_area_room_and_default_pad():
    bot = Mock(room_id=80123, session_user_id=29185, username="alice")
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
    )
    engine.feed(_mixed_cell_packet())

    cell, pad = engine.move_to_cell("Stairs")
    wire = bot._send_raw.call_args[0][0].rstrip(b"\x00").decode("latin-1")
    assert (cell, pad) == ("Stairs", "Left")
    assert wire == "%xt%zm%moveToCell%80123%Stairs%Left%"

    cell, pad = engine.move_to_cell("room2", "BottomLeft")
    wire = bot._send_raw.call_args[0][0].rstrip(b"\x00").decode("latin-1")
    assert (cell, pad) == ("Room2", "BottomLeft")
    assert wire == "%xt%zm%moveToCell%80123%Room2%BottomLeft%"

    # A cell the scan never revealed keeps the spelling the user typed; the
    # server decides whether it exists.
    cell, pad = engine.move_to_cell("cave")
    wire = bot._send_raw.call_args[0][0].rstrip(b"\x00").decode("latin-1")
    assert (cell, pad) == ("cave", "Left")
    assert wire == "%xt%zm%moveToCell%80123%cave%Left%"

    with pytest.raises(ValueError):
        engine.move_to_cell("   ")


def test_engine_move_to_cell_prefers_observed_pad_pair():
    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
    )
    engine.feed(_json_packet(
        "moveToArea",
        areaId=42,
        strMapName="lair",
        uoBranch=[
            {"uoName": "alice", "uid": 29185, "strFrame": "Enter", "strPad": "Spawn"},
            {"uoName": "ME LE", "uid": 29637, "strFrame": "Room2", "strPad": "Bottom"},
        ],
        monBranch=[],
        mondef=[],
        monmap=[],
    ))

    # No explicit pad: reuse the observed Room2/Bottom pair, not the default.
    cell, pad = engine.move_to_cell("room2")
    wire = bot._send_raw.call_args[0][0].rstrip(b"\x00").decode("latin-1")
    assert (cell, pad) == ("Room2", "Bottom")
    assert wire == "%xt%zm%moveToCell%42%Room2%Bottom%"

    # The scan report shows which pad was actually observed per cell.
    rows = engine.cell_scan_report()
    assert any(
        row.startswith("Room2 ") and "pad Bottom" in row for row in rows
    )


def test_engine_cell_scan_report_marks_current_and_partial_state():
    bot = Mock(room_id=42, session_user_id=29185, username="alice")
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
    )
    rows = engine.cell_scan_report()
    assert rows == []

    engine.feed(_mixed_cell_packet())
    rows = engine.cell_scan_report()
    assert rows[0].startswith("scan server parsial")
    assert any(row.startswith("Enter [KAMU]") for row in rows)
    assert any(row.startswith("Room2 ") for row in rows)
    assert rows[-1].startswith("pad: ")

    engine.state.set_map_cells(["Enter", "Stairs", "Cave"])
    rows = engine.cell_scan_report()
    assert rows[0].startswith("map ")
    assert any(row.startswith("Stairs ") for row in rows)


def test_engine_start_stop_runs_background_tick_loop():
    bot = Mock(room_id=42, session_user_id=29185, username="alice", _send_raw=Mock())
    engine = combat.AutoAttackEngine(
        bot,
        target_name="Water Draconian",
        class_profile=combat.mage_profile(),
        interval=0.01,
    )
    engine.feed(_mage_area_packet())
    engine.feed(_json_packet("updateClass", uid=29185, sClassName="Mage", ItemID=10))
    engine.feed(_mage_skills_packet())
    engine.start()
    time.sleep(0.05)
    engine.stop()
    assert engine.running is False
    assert bot._send_raw.call_count >= 1
