"""Gear-type commands: .class, .weapon, .armor, .helm, .cape

Each command without argument → auto-scan + list items of that type.
With a number → equip by menu number.
With a name → equip by exact name.
"""
from types import SimpleNamespace
from unittest.mock import Mock

from skua_lite import cli


def _orch(runtime):
    return SimpleNamespace(farming=runtime, bot=Mock())


# ---------------------------------------------------------------------------
# Parser: bare commands
# ---------------------------------------------------------------------------
def test_parser_bare_class_returns_class_action():
    assert cli.parse_farm_command(".class") == ("class", "")

def test_parser_bare_weapon_returns_weapon_action():
    assert cli.parse_farm_command(".weapon") == ("weapon", "")

def test_parser_bare_armor_returns_armor_action():
    assert cli.parse_farm_command(".armor") == ("armor", "")

def test_parser_bare_helm_returns_helm_action():
    assert cli.parse_farm_command(".helm") == ("helm", "")

def test_parser_bare_cape_returns_cape_action():
    assert cli.parse_farm_command(".cape") == ("cape", "")


# Parser: number selection
def test_parser_class_number():
    assert cli.parse_farm_command(".class 2") == ("class", "2")

def test_parser_weapon_number():
    assert cli.parse_farm_command(".weapon 3") == ("weapon", "3")


# Parser: name selection
def test_parser_weapon_name():
    assert cli.parse_farm_command(".weapon Necrotic Sword of Doom") == (
        "weapon", "Necrotic Sword of Doom"
    )


# ---------------------------------------------------------------------------
# Dispatch: bare command → scan + list of that type
# ---------------------------------------------------------------------------
def test_class_bare_scans_and_lists(capsys):
    runtime = Mock()
    runtime.scan_classes.return_value = [
        "[1] [dipakai] Mage (ItemID 10)",
        "[2] [bank] Warrior (ItemID 20)",
    ]

    assert cli.dispatch_farm(_orch(runtime), "class", "") == "farm"
    runtime.scan_classes.assert_called_once()
    output = capsys.readouterr().out
    assert "Mage" in output
    assert "Warrior" in output
    assert ".class <nomor>" in output


def test_weapon_bare_scans_and_lists(capsys):
    runtime = Mock()
    runtime.scan_gear.return_value = [
        "[1] [dipakai] BLoD (Weapon, ItemID 55)",
        "[2] [bank] NSoD (Weapon, ItemID 66)",
    ]

    assert cli.dispatch_farm(_orch(runtime), "weapon", "") == "farm"
    runtime.scan_gear.assert_called_once_with("Weapon")
    output = capsys.readouterr().out
    assert "BLoD" in output
    assert "NSoD" in output
    assert ".weapon <nomor>" in output


def test_armor_bare_scans_and_lists(capsys):
    runtime = Mock()
    runtime.scan_gear.return_value = [
        "[1] [inventory] Legion Armor (Armor, ItemID 33)",
    ]

    assert cli.dispatch_farm(_orch(runtime), "armor", "") == "farm"
    runtime.scan_gear.assert_called_once_with("Armor")
    output = capsys.readouterr().out
    assert "Legion Armor" in output
    assert ".armor <nomor>" in output


def test_helm_bare_scans_and_lists(capsys):
    runtime = Mock()
    runtime.scan_gear.return_value = [
        "[1] [bank] Dragon Helm (Helm, ItemID 40)",
    ]

    assert cli.dispatch_farm(_orch(runtime), "helm", "") == "farm"
    runtime.scan_gear.assert_called_once_with("Helm")
    assert ".helm <nomor>" in capsys.readouterr().out


def test_cape_bare_scans_and_lists(capsys):
    runtime = Mock()
    runtime.scan_gear.return_value = [
        "[1] [inventory] Shadow Cape (Cape, ItemID 90)",
    ]

    assert cli.dispatch_farm(_orch(runtime), "cape", "") == "farm"
    runtime.scan_gear.assert_called_once_with("Cape")
    assert ".cape <nomor>" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Dispatch: number/name → equip
# ---------------------------------------------------------------------------
def test_class_number_equips(capsys):
    runtime = Mock()
    runtime.select_class.return_value = "equip Warrior dari bank"

    assert cli.dispatch_farm(_orch(runtime), "class", "2") == "farm"
    runtime.select_class.assert_called_once_with("2")
    assert "equip Warrior" in capsys.readouterr().out


def test_weapon_number_equips(capsys):
    runtime = Mock()
    runtime.equip_gear.return_value = "equip NSoD (Weapon)"

    assert cli.dispatch_farm(_orch(runtime), "weapon", "2") == "farm"
    runtime.equip_gear.assert_called_once_with("Weapon", "2")
    assert "equip NSoD" in capsys.readouterr().out


def test_armor_name_equips(capsys):
    runtime = Mock()
    runtime.equip_gear.return_value = "equip Legion Armor (Armor)"

    assert cli.dispatch_farm(_orch(runtime), "armor", "Legion Armor") == "farm"
    runtime.equip_gear.assert_called_once_with("Armor", "Legion Armor")
    assert "Legion Armor" in capsys.readouterr().out


def test_helm_number_equips(capsys):
    runtime = Mock()
    runtime.equip_gear.return_value = "equip Dragon Helm (Helm)"

    assert cli.dispatch_farm(_orch(runtime), "helm", "1") == "farm"
    runtime.equip_gear.assert_called_once_with("Helm", "1")


def test_cape_name_equips(capsys):
    runtime = Mock()
    runtime.equip_gear.return_value = "equip Shadow Cape (Cape)"

    assert cli.dispatch_farm(_orch(runtime), "cape", "Shadow Cape") == "farm"
    runtime.equip_gear.assert_called_once_with("Cape", "Shadow Cape")


# ---------------------------------------------------------------------------
# Legacy .class scan / .class use still work
# ---------------------------------------------------------------------------
def test_class_scan_still_works(capsys):
    runtime = Mock()
    runtime.scan_classes.return_value = ["[1] [dipakai] Mage (ItemID 10)"]

    assert cli.dispatch_farm(_orch(runtime), "class", "scan") == "farm"
    runtime.scan_classes.assert_called_once()
    assert "Mage" in capsys.readouterr().out


def test_class_use_name_still_works(capsys):
    runtime = Mock()
    runtime.select_class.return_value = "equip Mage dari inventory"

    assert cli.dispatch_farm(_orch(runtime), "class", "use Mage") == "farm"
    runtime.select_class.assert_called_once_with("Mage")
