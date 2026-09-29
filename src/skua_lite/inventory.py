"""Generic inventory + bank catalogue: all items, numbered selection.

The combat state only tracked Class-type rows, so the `.class` menu could not
show armor, weapons, or helms and items could not be chosen by number. This
module owns the full picture: inventory, bank, equipped source, and the
numbered lookups the runtime menus use. One plain dataclass, no sockets.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from . import sfs

# AQW stores weapons by *sub-type* in `sType`, never the literal word "Weapon":
# a polearm row says "Polearm", a wand says "Wand", a generic test row may say
# "Weapon" itself. Grouping them is what makes `.weapon` list every weapon the
# account owns. Extend this set when a new sub-type shows up in a scan; it is
# the only place that mapping lives.
WEAPON_TYPES = frozenset({
    "weapon", "sword", "axe", "dagger", "polearm", "staff", "wand", "mace",
    "bow", "gun", "handgun", "whip", "gauntlet",
})

# Category name -> the concrete `sType` values that belong to it.
CATEGORY_TYPES: dict[str, frozenset[str]] = {
    "weapon": WEAPON_TYPES,
    "armor": frozenset({"armor"}),
    "helm": frozenset({"helm", "helmet"}),
    "cape": frozenset({"cape"}),
    "class": frozenset({"class"}),
}


def category_types(category: str) -> frozenset[str] | None:
    """Concrete `sType` values for a category, or None when not a category."""
    return CATEGORY_TYPES.get(str(category or "").strip().casefold())


@dataclass(slots=True)
class OwnedItem:
    """One inventory/bank row the scan proved (any sType)."""

    name: str
    item_id: int
    char_item_id: int
    item_type: str
    source: str  # "equipped" | "inventory" | "bank"
    equipped: bool = False
    quantity: int = 1


def item_from_row(raw: Mapping[str, Any], source: str) -> OwnedItem | None:
    if not isinstance(raw, Mapping):
        return None
    item_id = _as_int(raw.get("ItemID") or raw.get("iItemID"))
    name = str(raw.get("sName") or "").strip()
    if item_id <= 0 or not name:
        return None
    source = str(source or "inventory").strip() or "inventory"
    item_type = str(raw.get("sType") or raw.get("sES") or "").strip() or "unknown"
    equipped = source == "inventory" and _as_bool(raw.get("bEquip"), False)
    return OwnedItem(
        name=name,
        item_id=item_id,
        char_item_id=_as_int(raw.get("CharItemID") or raw.get("icharItemID")),
        item_type=item_type,
        source="equipped" if equipped else source,
        equipped=equipped,
        quantity=max(1, _as_int(raw.get("iQty") or raw.get("Quantity"), 1)),
    )


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n", ""}:
        return False
    return default


class ItemCatalog:
    """All scanned items (inventory + bank), with stable numbered lookups."""

    def __init__(self) -> None:
        self._items: list[OwnedItem] = []
        self.bank_loaded = False

    def all_items(self) -> list[OwnedItem]:
        return list(self._items)

    def items_by_type(self, item_type: str) -> list[OwnedItem]:
        wanted = str(item_type or "").strip().casefold()
        cat_types = category_types(wanted)
        if cat_types is not None:
            return [it for it in self._items if it.item_type.casefold() in cat_types]
        return [it for it in self._items if it.item_type.casefold() == wanted]

    def items_by_category(self, category: str) -> list[OwnedItem]:
        return self.items_by_type(category)

    def by_number(self, number: int) -> OwnedItem | None:
        index = _as_int(number, 0) - 1
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def by_type_number(self, item_type: str, number: int) -> OwnedItem | None:
        rows = self.items_by_type(item_type)
        index = _as_int(number, 0) - 1
        if 0 <= index < len(rows):
            return rows[index]
        return None

    def find(self, name: str) -> OwnedItem | None:
        wanted = str(name or "").strip().casefold()
        if not wanted:
            return None
        for item in self._items:
            if item.name.casefold() == wanted or str(item.item_id) == wanted:
                return item
        return None

    def feed(self, packet: str) -> None:
        parsed = sfs.parse_xt_json(packet)
        if parsed is None:
            return
        cmd = str(parsed.get("cmd") or "")
        obj = parsed.get("obj")
        if not isinstance(obj, dict):
            return
        items = obj.get("items")
        if cmd in {"loadInventoryBig", "loadInventory"}:
            self._replace_inventory(items)
        elif cmd == "loadBank":
            self.bank_loaded = True
            self._replace_bank(items)

    def _iter_rows(self, items: Any) -> list[dict[str, Any]]:
        if isinstance(items, dict):
            source: list[Any] = list(items.values())
        elif isinstance(items, list):
            source = items
        else:
            return []
        return [raw for raw in source if isinstance(raw, dict)]

    def _replace_inventory(self, items: Any) -> None:
        """Full refresh of the inventory side (equipped + carried rows)."""
        kept = [item for item in self._items if item.source == "bank"]
        seen: set[int] = set()
        rows: list[OwnedItem] = []
        for raw in self._iter_rows(items):
            parsed = item_from_row(raw, "inventory")
            if parsed is None or parsed.item_id in seen:
                continue
            seen.add(parsed.item_id)
            rows.append(parsed)
        self._items = rows + kept

    def _replace_bank(self, items: Any) -> None:
        """Full refresh of the bank side; never touches equipped rows."""
        kept = [item for item in self._items if item.source != "bank"]
        seen = {item.item_id for item in kept}
        rows: list[OwnedItem] = []
        for raw in self._iter_rows(items):
            parsed = item_from_row(raw, "bank")
            if parsed is None or parsed.item_id in seen:
                continue
            seen.add(parsed.item_id)
            rows.append(parsed)
        self._items = kept + rows


try:  # Python < 3.9 lacks the builtin generic used in annotations above.
    Mapping  # type: ignore[name-defined]  # noqa: F821
except NameError:  # pragma: no cover - import the ABC on old interpreters
    from collections.abc import Mapping  # type: ignore[no-redef]
