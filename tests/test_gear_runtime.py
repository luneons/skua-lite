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


def test_equip_weapon_accepts_item_id_for_polearm():
    from tests.test_gear_fixes import POLEARM
    from tests.test_inventory import _inv_packet

    sent = []
    rt = _runtime_with_items(sent)
    rt.feed_packet(_inv_packet(POLEARM))

    rt.equip_gear("Weapon", "1001")

    assert "%xt%zm%equipItem%42%1001%" in sent


def test_equip_weapon_accepts_global_item_menu_number():
    """A number copied from `.item` remains usable in `.weapon`."""
    from skua_lite.inventory import OwnedItem

    sent = []
    rt = _runtime_with_items(sent)
    # Put a weapon at global menu position 5; it is weapon-menu position 1.
    rt.item_catalog._items = [
        OwnedItem(f"Resource {i}", i, i + 100, "Resource", "inventory")
        for i in range(1, 5)
    ] + [
        OwnedItem("Golden Scythe", 99525, 599525, "Polearm", "inventory")
    ]

    rt.equip_gear("Weapon", "5")

    assert "%xt%zm%equipItem%42%99525%" in sent
