"""Runtime gear lists and type-scoped numbered equip."""
import pytest

from tests.test_inventory import _runtime_with_items


def test_gear_report_numbering_is_scoped_to_requested_type():
    rt = _runtime_with_items([])

    weapon_rows = rt.gear_report("Weapon")
    helm_rows = rt.gear_report("Helm")

    assert weapon_rows == [
        "[1] [inventory] Legendary Dagger (Weapon, ItemID 77)"
    ]
    assert helm_rows == [
        "[1] [bank] Dragon Helm (Helm, ItemID 40)"
    ]


def test_equip_weapon_number_uses_weapon_menu_number():
    sent = []
    rt = _runtime_with_items(sent)

    rt.equip_gear("Weapon", "1")

    assert "%xt%zm%equipItem%42%77%" in sent


def test_equip_helm_number_moves_bank_item_then_equips():
    sent = []
    rt = _runtime_with_items(sent)

    rt.equip_gear("Helm", "1")

    assert "%xt%zm%bankToInv%42%40%5040%" in sent
    assert "%xt%zm%equipItem%42%40%" in sent


def test_equip_gear_name_cannot_cross_item_type():
    rt = _runtime_with_items([])

    with pytest.raises(ValueError, match="weapon .*tidak ditemukan"):
        rt.equip_gear("Weapon", "Dragon Helm")
