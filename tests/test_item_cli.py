"""CLI flow: scan inventory+bank, show numbered choices, equip class/item."""
from types import SimpleNamespace
from unittest.mock import Mock

from skua_lite import cli


def _orch(runtime):
    return SimpleNamespace(farming=runtime, bot=Mock())


def test_parser_accepts_item_and_equip_commands():
    assert cli.parse_farm_command(".item scan") == ("item", "scan")
    assert cli.parse_farm_command(".item list") == ("item", "list")
    assert cli.parse_farm_command(".item type Weapon") == ("item", "type Weapon")
    assert cli.parse_farm_command(".equip 4") == ("equip", "4")
    assert cli.parse_farm_command(".equip Dragon Helm") == ("equip", "Dragon Helm")


def test_class_scan_prints_numbered_choices_and_simple_choose_hint(capsys):
    runtime = Mock()
    runtime.scan_classes.return_value = [
        "[1] [dipakai] Mage (ItemID 10)",
        "[2] [inventory] Warrior (ItemID 20)",
        "[3] [bank] Echo Shaman (ItemID 30)",
    ]

    assert cli.dispatch_farm(_orch(runtime), "class", "scan") == "farm"
    output = capsys.readouterr().out
    assert "[CLASS] [1] [dipakai] Mage" in output
    assert "[CLASS] [3] [bank] Echo Shaman" in output
    assert ".class <nomor>" in output


def test_class_use_number_passes_number_unchanged_to_runtime(capsys):
    runtime = Mock()
    runtime.select_class.return_value = "equip Warrior dari inventory"

    assert cli.dispatch_farm(_orch(runtime), "class", "use 2") == "farm"
    runtime.select_class.assert_called_once_with("2")
    assert "equip Warrior" in capsys.readouterr().out


def test_item_scan_requests_inventory_and_bank_then_lists_all_items(capsys):
    runtime = Mock()
    runtime.scan_items.return_value = [
        "[1] [dipakai] Mage (Class, ItemID 10)",
        "[2] [inventory] Dagger (Weapon, ItemID 77)",
        "[3] [bank] Dragon Helm (Helm, ItemID 40)",
    ]

    assert cli.dispatch_farm(_orch(runtime), "item", "scan") == "farm"
    runtime.scan_items.assert_called_once()
    output = capsys.readouterr().out
    assert "Mage" in output and "Dagger" in output and "Dragon Helm" in output
    assert ".equip <nomor>" in output


def test_item_type_filters_the_menu(capsys):
    runtime = Mock()
    runtime.item_report.return_value = ["[1] [inventory] Dagger (Weapon, ItemID 77)"]

    assert cli.dispatch_farm(_orch(runtime), "item", "type Weapon") == "farm"
    runtime.item_report.assert_called_once_with("Weapon")
    assert "Dagger" in capsys.readouterr().out


def test_equip_number_passes_to_generic_runtime_equip(capsys):
    runtime = Mock()
    runtime.equip_item.return_value = "equip Dragon Helm (Helm)"

    assert cli.dispatch_farm(_orch(runtime), "equip", "3") == "farm"
    runtime.equip_item.assert_called_once_with("3")
    assert "Dragon Helm" in capsys.readouterr().out


def test_item_list_without_scan_uses_cached_catalog(capsys):
    runtime = Mock()
    runtime.item_report.return_value = ["[1] [inventory] Potion (Item, ItemID 99)"]
    assert cli.dispatch_farm(_orch(runtime), "item", "list") == "farm"
    runtime.scan_items.assert_not_called()
    runtime.item_report.assert_called_once_with("")
