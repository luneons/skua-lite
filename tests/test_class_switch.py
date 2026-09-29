"""Class switching: scan inventory+bank, list owned classes, equip, per-class skills.

The wire for equipping is the server's own ``equipItem`` push command (Skua's
packet logger filters ``p[2] == "equipItem"``), so the bot speaks the same
command the server already emits instead of guessing a new one.
"""
import json

from skua_lite import combat, sfs


def _json(cmd: str, **fields) -> str:
    return json.dumps({"t": "xt", "b": {"r": 1, "o": {"cmd": cmd, **fields}}})


def _inventory_packet(*items) -> str:
    return _json("loadInventoryBig", items={str(i["ItemID"]): i for i in items})


def _bank_packet(*items) -> str:
    return _json("loadBank", items={str(i["ItemID"]): i for i in items})


def _area_packet(username: str = "alice", uid: int = 29185) -> str:
    """One live-shaped area snapshot: self in Enter plus two living monsters."""
    return _json(
        "moveToArea",
        areaId=42,
        areaName="lair-100000",
        strMapName="lair",
        uoBranch=[{
            "uoName": username, "uid": uid, "strFrame": "Enter", "strPad": "Spawn",
            "intHP": 900, "intHPMax": 900, "intMP": 300, "intMPMax": 300,
            "intState": 1,
        }],
        monBranch=[
            {"MonMapID": 1, "MonID": 100, "intHP": 500, "intHPMax": 500, "intState": 1},
            {"MonMapID": 2, "MonID": 100, "intHP": 400, "intHPMax": 500, "intState": 1},
        ],
        mondef=[{"MonID": 100, "strMonName": "Water Draconian", "sRace": "Dragonkin"}],
        monmap=[
            {"MonMapID": 1, "MonID": 100, "strFrame": "Enter"},
            {"MonMapID": 2, "MonID": 100, "strFrame": "Enter"},
        ],
    )


MAGE_INV = {
    "ItemID": 10, "sName": "Mage", "sType": "Class", "sES": "co", "bEquip": "1",
    "CharItemID": 5010,
}
WARRIOR_INV = {
    "ItemID": 20, "sName": "Warrior", "sType": "Class", "sES": "ar", "bEquip": "0",
    "CharItemID": 5020,
}
POTION = {"ItemID": 99, "sName": "Health Potion", "sType": "Item", "bEquip": "0"}
ECHO_BANK = {
    "ItemID": 30, "sName": "Echo Shaman", "sType": "Class", "CharItemID": 5030,
}


# ---------------------------------------------------------------------------
# Inventory + bank class discovery
# ---------------------------------------------------------------------------
def test_owned_classes_scan_covers_inventory_and_bank_with_sources():
    state = combat.CombatState(self_username="alice", self_user_id=29185)
    state.feed(_inventory_packet(MAGE_INV, WARRIOR_INV, POTION))
    state.feed(_bank_packet(ECHO_BANK))

    by_name = {entry.name: entry for entry in state.owned_classes}

    assert set(by_name) == {"Mage", "Warrior", "Echo Shaman"}
    assert by_name["Mage"].source == "equipped"
    assert by_name["Warrior"].source == "inventory"
    assert by_name["Echo Shaman"].source == "bank"
    # CharItemID travels with the entry: bankToInv needs it.
    assert by_name["Echo Shaman"].char_item_id == 5030
    assert state.class_name == "Mage"
    assert state.class_item_id == 10


def test_bank_class_never_overrides_equipped_class():
    state = combat.CombatState(self_username="alice", self_user_id=29185)
    state.feed(_inventory_packet(MAGE_INV, WARRIOR_INV))
    state.feed(_bank_packet(ECHO_BANK))

    assert state.class_name == "Mage"
    assert state.class_item_id == 10


def test_bank_load_marks_scan_complete():
    state = combat.CombatState(self_username="alice", self_user_id=29185)
    assert state.bank_loaded is False
    state.feed(_bank_packet(ECHO_BANK))
    assert state.bank_loaded is True


# ---------------------------------------------------------------------------
# Profile registry: no Mage-only dead end
# ---------------------------------------------------------------------------
def test_profile_for_known_class_matches_file_profile():
    profile = combat.profile_for("Mage")
    assert profile.matches("Mage")
    assert profile.skill_refs("farm_fast") == ("a4", "a2", "a1", "a3", "aa")


def test_profile_for_unknown_class_falls_back_to_generic_and_still_matches():
    profile = combat.profile_for("Echo Shaman")
    assert profile.matches("Echo Shaman")
    assert profile.matches("echo shaman")
    refs = profile.skill_refs("farm_fast")
    assert refs == ("a4", "a3", "a2", "a1", "aa")


def test_generic_profile_uses_only_live_sact_skills():
    profile = combat.profile_for("Echo Shaman")
    state = combat.CombatState(self_username="alice", self_user_id=29185)
    state.feed(_json("sAct", actions={"active": [
        {"ref": "aa", "nam": "Hit", "auto": True, "tgt": "h", "tgtMax": 1,
         "cd": 1500, "isOK": True},
        {"ref": "a1", "nam": "Blast", "tgt": "h", "tgtMax": 1, "cd": 3000,
         "isOK": True},
    ]}))

    chosen = [
        ref for ref in profile.skill_refs("farm_fast") if ref in state.skills
    ]
    assert chosen == ["a1", "aa"]


# ---------------------------------------------------------------------------
# Engine must follow the equipped class, not stay on Mage
# ---------------------------------------------------------------------------
def test_engine_swaps_profile_when_class_changes_and_then_attacks():
    sent: list[str] = []
    bot = _fake_bot(sent)
    engine = combat.AutoAttackEngine(
        bot, target_name="Water Draconian",
        class_profile=combat.mage_profile(), mode="farm_fast",
        clock=lambda: 100.0,
    )
    engine.feed(_area_packet())

    # Still Mage: the original profile owns the fight.
    engine.feed(_json("updateClass", uid=29185, sClassName="Warrior", ItemID=20))
    assert engine.tick() is False
    assert sent == []

    # Runtime hands over a profile for the newly equipped class.
    engine.set_class_profile(combat.profile_for("Warrior"))
    engine.feed(_json("sAct", actions={"active": [
        {"ref": "aa", "nam": "Slash", "auto": True, "tgt": "h", "tgtMax": 1,
         "cd": 1200, "isOK": True},
        {"ref": "a2", "nam": "Whirl", "tgt": "h", "tgtMax": 2, "cd": 4000,
         "isOK": True},
    ]}))

    assert engine.tick() is True
    assert sent == ["%xt%zm%gar%1%0%a2>m:2,a2>m:1%wvz%"]


def test_engine_class_swap_resets_stale_cooldowns():
    sent: list[str] = []
    times = iter((100.0, 100.2))
    engine = combat.AutoAttackEngine(
        _fake_bot(sent), target_name="Water Draconian",
        class_profile=combat.mage_profile(), mode="farm_fast",
        clock=lambda: next(times),
    )
    engine.feed(_area_packet())
    engine.feed(_json("updateClass", uid=29185, sClassName="Mage", ItemID=10))
    engine.feed(_json("sAct", actions={"active": [
        {"ref": "aa", "nam": "Fireball", "auto": True, "tgt": "h", "tgtMax": 1,
         "cd": 1800, "isOK": True},
        {"ref": "a4", "nam": "Meteor", "tgt": "h", "tgtMax": 3, "cd": 12000,
         "isOK": True},
    ]}))
    assert engine.tick() is True

    engine.set_class_profile(combat.profile_for("Warrior"))
    engine.feed(_json("updateClass", uid=29185, sClassName="Warrior", ItemID=20))
    # Same skill refs, new class: the old a4 cooldown must not block the new kit.
    assert engine.tick() is True
    assert sent[-1].startswith("%xt%zm%gar%")


# ---------------------------------------------------------------------------
# Wire format for equipping
# ---------------------------------------------------------------------------
def test_equip_packet_uses_server_equip_item_command():
    packet = sfs.equip_item_packet(room=84983, item_id=20)
    assert packet.rstrip(b"\x00").decode("latin-1") == "%xt%zm%equipItem%84983%20%"


# ---------------------------------------------------------------------------
# Runtime: list, pick, equip (inventory first, bank otherwise)
# ---------------------------------------------------------------------------
def _fake_bot(sent: list[str], room_id: int = 42, uid: int = 29185):
    class Bot:
        pass
    bot = Bot()
    bot.room_id = room_id
    bot.session_user_id = uid
    bot.username = "alice"
    bot.state = None
    bot._send_raw = lambda packet: sent.append(
        packet.rstrip(b"\x00").decode("latin-1")
    )
    return bot


def _runtime(sent: list[str]):
    from skua_lite import farming
    bot = _fake_bot(sent)
    runtime = farming.FarmingRuntime(bot=bot, profile=farming.FarmProfile())
    return runtime, bot


def test_runtime_lists_detected_classes_after_scan():
    sent: list[str] = []
    runtime, _bot = _runtime(sent)
    runtime.feed_packet(_inventory_packet(MAGE_INV, WARRIOR_INV))
    runtime.feed_packet(_bank_packet(ECHO_BANK))

    report = runtime.class_report()

    assert any("Mage" in row and "dipakai" in row for row in report)
    assert any("Warrior" in row for row in report)
    assert any("Echo Shaman" in row and "bank" in row for row in report)


def test_select_class_in_inventory_sends_equip_and_swaps_profile():
    sent: list[str] = []
    runtime, _bot = _runtime(sent)
    runtime.feed_packet(_inventory_packet(MAGE_INV, WARRIOR_INV))
    runtime.feed_packet(_bank_packet(ECHO_BANK))

    runtime.select_class("Warrior")

    assert sent == ["%xt%zm%equipItem%42%20%"]
    assert runtime.combat.class_profile.matches("Warrior")


def test_select_class_from_bank_moves_to_inventory_then_equips():
    sent: list[str] = []
    runtime, _bot = _runtime(sent)
    runtime.feed_packet(_inventory_packet(MAGE_INV))
    runtime.feed_packet(_bank_packet(ECHO_BANK))

    runtime.select_class("Echo Shaman")

    assert sent == [
        "%xt%zm%bankToInv%42%30%5030%",
        "%xt%zm%equipItem%42%30%",
    ]


def test_select_class_unknown_name_reports_what_was_detected():
    sent: list[str] = []
    runtime, _bot = _runtime(sent)
    runtime.feed_packet(_inventory_packet(MAGE_INV, WARRIOR_INV))
    runtime.feed_packet(_bank_packet(ECHO_BANK))

    try:
        runtime.select_class("Necromancer")
    except ValueError as exc:
        message = str(exc)
    else:  # pragma: no cover - explicit failure is the point
        raise AssertionError("unknown class must be refused")

    assert "Necromancer" in message
    assert "Mage" in message and "Warrior" in message
    assert sent == []


def test_scan_classes_requests_inventory_and_bank_when_unknown():
    sent: list[str] = []
    runtime, _bot = _runtime(sent)

    runtime.scan_classes(timeout=0.01)

    assert any("%xt%zm%retrieveInventory%42%29185%" in p for p in sent)
    assert any("%xt%zm%loadBank%42%" in p for p in sent)


# ---------------------------------------------------------------------------
# The equipped class drives the rotation, whoever equipped it
# ---------------------------------------------------------------------------
def test_feed_packet_adopts_profile_when_equipped_class_changes():
    sent: list[str] = []
    runtime, _bot = _runtime(sent)
    assert runtime.combat.class_profile.matches("Mage")

    runtime.feed_packet(
        _json("updateClass", uid=29185, sClassName="Echo Shaman", ItemID=30)
    )

    assert runtime.combat.class_profile.matches("Echo Shaman")


def test_runtime_attacks_with_live_skills_of_a_non_mage_class():
    sent: list[str] = []
    runtime, _bot = _runtime(sent)
    runtime.feed_packet(_area_packet())
    runtime.feed_packet(
        _json("updateClass", uid=29185, sClassName="Echo Shaman", ItemID=30)
    )
    runtime.feed_packet(_json("sAct", actions={"active": [
        {"ref": "aa", "nam": "Staff Hit", "auto": True, "tgt": "h", "tgtMax": 1,
         "cd": 1500, "mp": 0, "isOK": True},
        {"ref": "a3", "nam": "Totem", "tgt": "h", "tgtMin": 1, "tgtMax": 2,
         "cd": 4000, "mp": 10, "isOK": True},
    ]}))

    assert runtime.combat.tick() is True
    assert sent[-1] == "%xt%zm%gar%1%0%a3>m:2,a3>m:1%wvz%"


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------
def test_class_command_parses_scan_list_and_use():
    from skua_lite import cli

    assert cli.parse_farm_command(".class scan") == ("class", "scan")
    assert cli.parse_farm_command(".class list") == ("class", "list")
    assert cli.parse_farm_command(".class use Warrior") == ("class", "use Warrior")


def test_dispatch_class_scan_lists_choices(capsys):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from skua_lite import cli

    runtime = Mock()
    runtime.scan_classes.return_value = [
        "[dipakai] Mage (ItemID 10)",
        "[bank] Echo Shaman (ItemID 30)",
    ]
    orch = SimpleNamespace(farming=runtime, bot=Mock())

    assert cli.dispatch_farm(orch, "class", "scan") == "farm"
    output = capsys.readouterr().out
    assert "[CLASS 1] [dipakai] Mage" in output
    assert "[CLASS 2] [bank] Echo Shaman" in output
    assert ".class use <nama class>" in output


def test_dispatch_class_use_keeps_names_with_spaces(capsys):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from skua_lite import cli

    runtime = Mock()
    runtime.select_class.return_value = "equip Echo Shaman dari bank"
    orch = SimpleNamespace(farming=runtime, bot=Mock())

    assert cli.dispatch_farm(orch, "class", "use Echo Shaman") == "farm"
    runtime.select_class.assert_called_once_with("Echo Shaman")
    assert "equip Echo Shaman dari bank" in capsys.readouterr().out
