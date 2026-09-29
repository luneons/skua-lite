"""Item scan, numbered selection, and generic equip.

All items from inventory and bank — not only classes — are catalogued and can
be equipped or moved by number so the user doesn't have to type exact names.
"""
import json

import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from skua_lite import farming, sfs
from skua_lite.inventory import ItemCatalog, OwnedItem


# ---------------------------------------------------------------------------
# Data: sample items from inventory + bank
# ---------------------------------------------------------------------------
MAGE_ITEM = {"ItemID": 10, "CharItemID": 5010, "sName": "Mage", "sType": "Class",
              "bEquip": "1", "iQty": 1}
WARRIOR_ITEM = {"ItemID": 20, "CharItemID": 5020, "sName": "Warrior", "sType": "Class",
                "bEquip": "0", "iQty": 1}
SWORD = {"ItemID": 77, "CharItemID": 5077, "sName": "Legendary Dagger", "sType": "Weapon",
         "bEquip": "0", "iQty": 1}  # not equipped, so equipping triggers a packet
SWORD_EQUIPPED = {"ItemID": 77, "CharItemID": 5077, "sName": "Legendary Dagger", "sType": "Weapon",
                  "bEquip": "1", "iQty": 1}
POTION = {"ItemID": 99, "CharItemID": 5099, "sName": "Health Potion", "sType": "Item",
          "bEquip": "0", "iQty": 5}
ECHO_BANK = {"ItemID": 30, "CharItemID": 5030, "sName": "Echo Shaman", "sType": "Class",
             "iQty": 1}
HELM_BANK = {"ItemID": 40, "CharItemID": 5040, "sName": "Dragon Helm", "sType": "Helm",
             "iQty": 1}


def _inv_packet(*items):
    body = {str(it["ItemID"]): it for it in items}
    return json.dumps({"t": "xt", "b": {"r": 1, "o": {
        "cmd": "loadInventoryBig", "items": body
    }}})


def _bank_packet(*items):
    body = {str(it["ItemID"]): it for it in items}
    return json.dumps({"t": "xt", "b": {"r": 1, "o": {"cmd": "loadBank", "items": body}}})


# ---------------------------------------------------------------------------
# ItemCatalog: full catalogue (not class-only)
# ---------------------------------------------------------------------------
def test_catalog_contains_all_item_types_from_inventory_and_bank():
    cat = ItemCatalog()
    cat.feed(_inv_packet(MAGE_ITEM, WARRIOR_ITEM, SWORD, POTION))
    cat.feed(_bank_packet(ECHO_BANK, HELM_BANK))

    names = {item.name for item in cat.all_items()}
    assert names == {"Mage", "Warrior", "Legendary Dagger", "Health Potion",
                     "Echo Shaman", "Dragon Helm"}


def test_catalog_records_source_equipped_inventory_bank():
    cat = ItemCatalog()
    cat.feed(_inv_packet(MAGE_ITEM, WARRIOR_ITEM))
    cat.feed(_bank_packet(ECHO_BANK))

    by = {i.name: i for i in cat.all_items()}
    assert by["Mage"].source == "equipped"
    assert by["Warrior"].source == "inventory"
    assert by["Echo Shaman"].source == "bank"


def test_catalog_filters_by_type():
    cat = ItemCatalog()
    cat.feed(_inv_packet(MAGE_ITEM, SWORD, POTION))

    classes = cat.items_by_type("Class")
    assert [i.name for i in classes] == ["Mage"]
    weapons = cat.items_by_type("Weapon")
    assert [i.name for i in weapons] == ["Legendary Dagger"]


def test_catalog_numbered_lookup_is_1_based():
    cat = ItemCatalog()
    cat.feed(_inv_packet(MAGE_ITEM, WARRIOR_ITEM))
    cat.feed(_bank_packet(ECHO_BANK))

    items = cat.all_items()
    assert cat.by_number(1) is items[0]
    assert cat.by_number(len(items)) is items[-1]
    assert cat.by_number(0) is None
    assert cat.by_number(len(items) + 1) is None


def test_catalog_by_type_number_filters_then_indexes():
    cat = ItemCatalog()
    cat.feed(_inv_packet(MAGE_ITEM, SWORD))
    cat.feed(_bank_packet(ECHO_BANK))

    assert cat.by_type_number("Class", 1).name == "Mage"
    assert cat.by_type_number("Class", 2).name == "Echo Shaman"
    assert cat.by_type_number("Class", 3) is None


def test_catalog_clears_on_new_inventory_refetch():
    cat = ItemCatalog()
    cat.feed(_inv_packet(MAGE_ITEM, SWORD))
    cat.feed(_inv_packet(WARRIOR_ITEM))

    names = {i.name for i in cat.all_items()}
    assert "Mage" not in names
    assert "Warrior" in names


# ---------------------------------------------------------------------------
# Runtime: scan → numbered selection for classes
# ---------------------------------------------------------------------------
def _runtime_with_items(mocked_sent):
    bot = Mock()
    bot.room_id = 42
    bot.session_user_id = 29185
    bot.username = "alice"
    bot.state = None
    bot._send_raw = lambda p: mocked_sent.append(p.rstrip(b"\x00").decode("latin-1"))
    rt = farming.FarmingRuntime(bot=bot)
    rt.feed_packet(_inv_packet(MAGE_ITEM, WARRIOR_ITEM, SWORD))
    rt.feed_packet(_bank_packet(ECHO_BANK, HELM_BANK))
    return rt


def test_class_scan_returns_numbered_menu():
    rt = _runtime_with_items([])
    report = rt.class_report()
    assert any("[1]" in row for row in report)
    assert any("Mage" in row for row in report)
    assert any("Warrior" in row for row in report)
    assert any("Echo Shaman" in row for row in report)


def test_select_class_by_number_equips_correct_item():
    sent = []
    rt = _runtime_with_items(sent)
    report = rt.class_report()
    # find which number is Warrior
    warrior_num = next(
        int(row.split("]")[0].lstrip("[")) for row in report if "Warrior" in row
    )
    rt.select_class(str(warrior_num))
    assert "%xt%zm%equipItem%42%20%" in sent


def test_select_class_by_name_still_works():
    sent = []
    rt = _runtime_with_items(sent)
    rt.select_class("Echo Shaman")
    assert "%xt%zm%bankToInv%42%30%5030%" in sent


# ---------------------------------------------------------------------------
# Generic equip: any item, not only class
# ---------------------------------------------------------------------------
def test_equip_item_by_number_sends_equip_packet():
    sent = []
    rt = _runtime_with_items(sent)
    cat = rt.item_catalog
    items = cat.all_items()
    sword = next(i for i in items if i.name == "Legendary Dagger")
    idx = items.index(sword) + 1

    rt.equip_item(str(idx))
    assert "%xt%zm%equipItem%42%77%" in sent


def test_equip_item_by_name_sends_equip_packet():
    sent = []
    rt = _runtime_with_items(sent)
    rt.equip_item("Legendary Dagger")
    assert "%xt%zm%equipItem%42%77%" in sent


def test_equip_item_from_bank_moves_first():
    sent = []
    rt = _runtime_with_items(sent)
    rt.equip_item("Dragon Helm")
    assert "%xt%zm%bankToInv%42%40%5040%" in sent
    assert "%xt%zm%equipItem%42%40%" in sent


def test_equip_item_unknown_raises_value_error():
    rt = _runtime_with_items([])
    with pytest.raises(ValueError, match="tidak ditemukan"):
        rt.equip_item("Barang Yang Tidak Ada")
