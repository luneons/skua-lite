"""Readable menu rendering for item/gear listings.

The runtime rows carry their own `[n] source name (type, ItemID x)` prefix.
The CLI must not bolt a second number onto that; it renders the prefix as a
clean leading number and adds a count header so the user knows how many items
were found and which command picks one.
"""
from types import SimpleNamespace
from unittest.mock import Mock

from skua_lite import cli


def _orch(runtime):
    return SimpleNamespace(farming=runtime, bot=Mock())


def test_weapon_menu_renders_count_header_and_leading_numbers(capsys):
    runtime = Mock()
    runtime.scan_gear.return_value = [
        "[1] [inventory] Golden Dragon Scythe (Polearm, ItemID 99525)",
        "[2] [bank] Necrotic Blade (Sword, ItemID 4242)",
    ]

    assert cli.dispatch_farm(_orch(runtime), "weapon", "") == "farm"
    out = capsys.readouterr().out

    assert "2 weapon ditemukan" in out
    assert "  1. [inventory] Golden Dragon Scythe (Polearm, ItemID 99525)" in out
    assert "  2. [bank] Necrotic Blade (Sword, ItemID 4242)" in out
    assert "[WEAPON 1]" not in out
    assert ".weapon <nomor>" in out


def test_empty_menu_still_explains_what_to_do(capsys):
    runtime = Mock()
    runtime.scan_gear.return_value = [
        "belum ada item terdeteksi; jalankan `.item scan` dulu"
    ]

    assert cli.dispatch_farm(_orch(runtime), "weapon", "") == "farm"
    out = capsys.readouterr().out

    assert "belum ada item terdeteksi" in out
    assert "0 weapon" not in out


def test_class_menu_renders_count_header(capsys):
    runtime = Mock()
    runtime.scan_classes.return_value = [
        "[1] [dipakai] Mage (ItemID 10)",
        "[2] [bank] King's Echo (ItemID 95742)",
    ]

    assert cli.dispatch_farm(_orch(runtime), "class", "") == "farm"
    out = capsys.readouterr().out

    assert "2 class ditemukan" in out
    assert "  1. [dipakai] Mage (ItemID 10)" in out
    assert ".class <nomor>" in out


def test_item_menu_uses_same_readable_layout(capsys):
    runtime = Mock()
    runtime.scan_items.return_value = [
        "[1] [inventory] Magical Cosmos Wand (Wand, ItemID 87931)",
        "[2] [inventory] Bonehead Face (Helm, ItemID 96449)",
    ]

    assert cli.dispatch_farm(_orch(runtime), "item", "scan") == "farm"
    out = capsys.readouterr().out

    assert "2 item ditemukan" in out
    assert "  1. [inventory] Magical Cosmos Wand (Wand, ItemID 87931)" in out
    assert ".equip <nomor>" in out


def test_menu_without_counted_rows_passes_message_through(capsys):
    runtime = Mock()
    runtime.scan_items.return_value = ["belum ada item terdeteksi; jalankan `.item scan` dulu"]

    assert cli.dispatch_farm(_orch(runtime), "item", "scan") == "farm"
    out = capsys.readouterr().out

    assert "belum ada item terdeteksi" in out
    assert "item ditemukan" not in out
