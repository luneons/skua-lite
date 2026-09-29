"""Fixing item discovery rules for sub-types and numbered lists.

Weapons in AQW have multiple `sType`s: Sword, Dagger, Polearm, Wand, Mace, etc.
`.weapon` should match them all. Numbered lookups must use the printed menu number.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from skua_lite import cli
from skua_lite.inventory import ItemCatalog
from tests.test_inventory import _inv_packet, _bank_packet, SWORD


POLEARM = {"ItemID": 1001, "CharItemID": 5001, "sName": "Golden Scythe", "sType": "Polearm", "iQty": 1}
WAND = {"ItemID": 1002, "CharItemID": 5002, "sName": "Cosmos Wand", "sType": "Wand", "iQty": 1}
DAGGER = {"ItemID": 1003, "CharItemID": 5003, "sName": "Twin Blade", "sType": "Dagger", "iQty": 1}
AXE = {"ItemID": 1004, "CharItemID": 5004, "sName": "Battle Axe", "sType": "Axe", "iQty": 1}
BOW = {"ItemID": 1005, "CharItemID": 5005, "sName": "Elven Bow", "sType": "Bow", "iQty": 1}
MACE = {"ItemID": 1006, "CharItemID": 5006, "sName": "Spiked Mace", "sType": "Mace", "iQty": 1}
WHIP = {"ItemID": 1007, "CharItemID": 5007, "sName": "Techno Whip", "sType": "Whip", "iQty": 1}
STAFF = {"ItemID": 1008, "CharItemID": 5008, "sName": "Oak Staff", "sType": "Staff", "iQty": 1}
GUN = {"ItemID": 1009, "CharItemID": 5009, "sName": "Hand Cannon", "sType": "Gun", "iQty": 1}


def test_catalog_weapon_type_groups_subtypes():
    cat = ItemCatalog()
    cat.feed(_inv_packet(SWORD, POLEARM, WAND, DAGGER, AXE, BOW, MACE, WHIP, STAFF, GUN))
    
    # "Weapon" request should cover all sub-types
    weapons = cat.items_by_category("Weapon")
    names = {item.name for item in weapons}
    
    assert "Golden Scythe" in names
    assert "Cosmos Wand" in names
    assert "Twin Blade" in names
    assert "Techno Whip" in names
    assert "Hand Cannon" in names
    assert len(weapons) == 10


def test_catalog_find_by_id_works_like_find_by_name():
    cat = ItemCatalog()
    cat.feed(_inv_packet(WAND))
    
    item = cat.find("1002")  # ID search
    assert item is not None
    assert item.name == "Cosmos Wand"
    
    item_by_name = cat.find("Cosmos Wand")
    assert item_by_name is not None
    assert item_by_name.item_id == 1002


def test_cli_list_output_does_not_double_number():
    from skua_lite import cli
    
    runtime = Mock()
    runtime.item_report.return_value = [
        "[1] [inventory] Magic Wand (Wand, ItemID 1)",
        "[2] [bank] Doom Sword (Sword, ItemID 2)"
    ]
    orch = SimpleNamespace(farming=runtime, bot=Mock())
    
    # Capture print in cli
    import io
    from contextlib import redirect_stdout
    f = io.StringIO()
    with redirect_stdout(f):
        cli.dispatch_farm(orch, "item", "list")
        
    output = f.getvalue()
    # It should render a clean numbered menu, not one number per layer.
    assert "2 item ditemukan" in output
    assert "  1. [inventory] Magic Wand (Wand, ItemID 1)" in output
    assert "[ITEM 1] [1]" not in output
