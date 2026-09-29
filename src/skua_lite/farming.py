"""Headless farming runtime built from portable Skua 1.4.4 packets.

This module is deliberately separate from the AI assistant. It owns farming
state, and delegates combat to ``combat.AutoAttackEngine`` — the engine drives
target selection and skill use from server-pushed state (`moveToArea`, `sAct`,
`mtls`, `uotls`) and the verified `gar` wire format, with no Flash display
object involved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import threading
import time
from typing import Any, Callable

from .auto_planner import AutoDecision, AutoGoal, AutoObservation, AutoPlanner
from . import combat, sfs
from .area_state import AreaStateStore
from .inventory import ItemCatalog, OwnedItem
from .map_cells import MapCellScanner, SWFCellError


class FarmingUnsupported(RuntimeError):
    """Raised when an action still depends on Skua's Flash runtime."""


@dataclass(slots=True)
class FarmProfile:
    """Safe defaults for one farming session."""

    map_name: str = "lair-100000"
    private_room: int = 100000
    pickup_drops: bool = True
    rest_between_rounds: bool = True
    auto_attack: bool = True
    class_name: str = "Mage"
    target_monster: str = "Water Draconian"
    combat_mode: str = "farm_fast"
    desired_drop_ids: set[int] = field(default_factory=set)


class FarmingRuntime:
    """Mode-local farming controls; this object never creates an AI router."""

    def __init__(
        self,
        bot: Any,
        profile: FarmProfile | None = None,
        *,
        on_log: Callable[[str], None] | None = None,
        combat_capture_path: str | Path | None = None,
        cell_scanner: MapCellScanner | None = None,
    ) -> None:
        self.bot = bot
        self.profile = profile or FarmProfile()
        self.ai_router = None
        self._on_log = on_log or (lambda _message: None)
        self._running = False
        self._lock = threading.RLock()
        self.cell_scanner = cell_scanner or MapCellScanner()
        self._scanned_map = ""
        self._scan_thread: threading.Thread | None = None
        self._observed_class = ""
        # Full item picture (inventory + bank, every type), separate from the
        # class-only view combat keeps for its profile.
        self.item_catalog = ItemCatalog()
        self.area_state = AreaStateStore(
            self_username=str(getattr(bot, "username", "")),
            self_user_id=getattr(bot, "session_user_id", None),
        )
        default_capture = Path.cwd() / "combat_capture.log"
        self.combat = combat.AutoAttackEngine(
            self.bot,
            target_name=self.profile.target_monster,
            class_profile=self._combat_profile(),
            mode=self.profile.combat_mode,
            on_log=self._on_log,
            capture_path=combat_capture_path or default_capture,
        )
        # Enforce the mode boundary even if a caller hands us a reused bot.
        self.bot.ai_router = None
        self.bot.move_on_join = None
        if hasattr(self.bot, "afk_on_join"):
            self.bot.afk_on_join = False
        # Autonomous goal loop — seams are injected so everything is testable
        # without a live server. count_drop is explicitly a stub (item tracking
        # needs a live capture first); drop goals are refused in set_auto_goal.
        self.auto_planner = AutoPlanner(
            bot=self.bot,
            on_log=self._on_log,
            observe=self._observe_auto,
            apply=self._apply_auto,
            count_drop=lambda _goal: 0,  # TODO: wire when item tracker lands
        )
        # Expose on the bot so the CLI layer can reach it.
        self.bot.auto_planner = self.auto_planner

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def _combat_profile(self) -> combat.ClassProfile:
        """Start on Mage defaults; feed_packet re-aims live beyond that."""
        try:
            return combat.profile_for(self.profile.class_name)
        except ValueError:
            return combat.generic_profile(self.profile.class_name or "Mage")

    def feed_packet(self, packet: str, outbound: bool = False) -> None:
        self.combat.feed(packet, outbound=outbound)
        if not outbound:
            self._sync_class_profile()
            self.area_state.feed(packet)
            try:
                self.item_catalog.feed(packet)
            except Exception:
                pass
            self._scan_map_cells_if_changed()

    def _sync_class_profile(self) -> None:
        """Follow the class the server says is equipped, whatever changed it.

        Tracks the last *observed* class instead of the adopted profile name so
        an optimistic ``.class use X`` is not reverted by stale state before the
        server confirms it.
        """
        observed = (self.combat.state.class_name or "").strip()
        if not observed or observed == self._observed_class:
            return
        self._observed_class = observed
        self._adopt_equipped_profile(assume=observed)

    def _scan_map_cells_if_changed(self) -> None:
        """Start one non-blocking SWF scan for the map the server named."""
        file_name = self.combat.state.map_file_name
        if not file_name:
            return
        with self._lock:
            if file_name == self._scanned_map:
                return
            self._scanned_map = file_name
            thread = threading.Thread(
                target=self._scan_map_cells,
                args=(file_name,),
                name="MapCellScanner",
                daemon=True,
            )
            self._scan_thread = thread
            thread.start()

    def _scan_map_cells(self, file_name: str) -> None:
        """Download and parse one map asset outside the packet-reader thread."""
        try:
            cells = self.cell_scanner.scan(file_name)
        except (SWFCellError, OSError, ValueError) as exc:
            self._on_log(
                f"[CELL] scan SWF map gagal ({exc}); pakai cell teramati saja"
            )
            return
        # Ignore a stale result when the character joined another map while
        # this download was in flight.
        with self._lock:
            if file_name != self.combat.state.map_file_name:
                return
            self.combat.state.set_map_cells(cells)
        self._on_log(f"[CELL] scan {file_name}: {len(cells)} cell dari SWF")

    def move_to_cell(self, cell: str, pad: str | None = None) -> tuple[str, str]:
        """Move to another cell in the current area (`.cell <nama> [pad]`)."""
        return self.combat.move_to_cell(cell, pad)

    def cell_scan_report(self, limit: int | None = None) -> list[str]:
        """Cell list from the SWF scan plus every server-observed cell.

        Unbounded by default: the user asked for every destination the scan can
        prove, and the SWF route can legitimately return dozens of cells.
        """
        rows = self.combat.cell_scan_report()
        if limit is None:
            return list(rows)
        return list(rows[: max(1, int(limit))])

    def area_report(self) -> list[str]:
        """Return the shared generation-aware dynamic area snapshot."""
        return self.area_state.report()

    def area_json(self) -> str:
        """Return deterministic machine-readable area state."""
        return self.area_state.to_json()

    def set_combat_capture(self, enabled: bool) -> None:
        self.combat.set_capture(enabled)
        state = "ON" if enabled else "OFF"
        self._on_log(f"[COMBAT] capture {state}: {self.combat.capture_path}")

    def start(self) -> None:
        """Mark the farming controller active; combat starts on explicit command."""
        with self._lock:
            self._running = True
        self._auto_thread = threading.Thread(
            target=self._auto_loop, name="SkuaAutoPlanner", daemon=True
        )
        self._auto_thread.start()
        self._on_log("[FARM] runtime aktif; AI/Admin tidak dimuat")
        self._on_log(
            f"[COMBAT] siap: {self.profile.class_name} -> {self.profile.target_monster}; "
            "jalankan `.capture on`, lalu `.attack <nama>` atau `.attack auto`"
        )

    def stop(self) -> None:
        self.combat.stop()
        self.auto_planner.stop()
        with self._lock:
            self._running = False
        self._on_log("[FARM] runtime dihentikan")

    # ------------------------------------------------------------------
    # Autonomous goal loop (`.auto <tujuan>`)
    # ------------------------------------------------------------------
    def set_auto_goal(self, goal: AutoGoal) -> AutoGoal:
        """Accept an autonomous goal, refusing shapes the bot cannot observe.

        `drop` goals need a live item counter; without it the goal would look
        active while looping forever, so it is refused instead of faked.
        """
        if goal.kind == "drop":
            raise ValueError(
                "tujuan drop belum bisa: bot belum punya pelacak item "
                "(butuh capture inventory dulu). Pakai '.auto farming <monster>'."
            )
        if goal.kind == "quest":
            raise ValueError(
                "tujuan quest belum bisa: bot belum melacak progres quest. "
                "Pakai '.auto farming <monster>'."
            )
        return self.auto_planner.set_goal(goal)

    def _observe_auto(self) -> AutoObservation:
        """Read live server-pushed state; never invents facts."""
        connected = self._in_map()
        state = self.combat.state
        enemies_in_cell = len(state.alive_in_cell()) if connected else 0
        cells: list[str] = []
        seen: set[str] = set()
        if connected:
            current = (state.cell or "").casefold()
            for monster in state.monsters.values():
                cell = (monster.cell or "").strip()
                if not monster.alive or not cell:
                    continue
                key = cell.casefold()
                if key == current or key in seen:
                    continue
                seen.add(key)
                cells.append(cell)
        return AutoObservation(
            connected=connected,
            enemies_in_cell=enemies_in_cell,
            cells_with_enemies=tuple(sorted(cells, key=str.casefold)),
        )

    def _in_map(self) -> bool:
        state = getattr(self.bot, "state", None)
        value = getattr(state, "value", state)
        return str(value) == "IN_MAP"

    def _apply_auto(self, decision: AutoDecision) -> None:
        """Perform the decided action with verified packets only."""
        action = decision.action
        if action == "idle":
            self.stop_attack()
        elif action == "attack":
            self.attack_auto()
        elif action == "move" and decision.cell:
            self.move_to_cell(decision.cell)
        elif action in {"done", "turn_in"}:
            self.stop_attack()
            if action == "turn_in" and decision.quest_id:
                self.complete_quest(decision.quest_id)
            self._on_log(f"[AUTO] selesai: {decision.reason}")
        # `wait` and `paused` deliberately emit nothing.

    def auto_tick(self) -> bool:
        """Run one planner iteration synchronously (also used by tests)."""
        return self.auto_planner.tick()

    def _auto_loop(self, interval: float = 1.0) -> None:
        """Pump the planner while the runtime is alive; stop ends it."""
        import time as _time
        while True:
            with self._lock:
                if not self._running:
                    return
            try:
                self.auto_tick()
            except Exception as exc:
                self._on_log(f"[AUTO] loop berhenti: {exc}")
                return
            _time.sleep(interval)

    def _send(self, packet: bytes, label: str) -> None:
        self.bot._send_raw(packet)
        self._on_log(f"[FARM] {label}")

    def join(self, map_name: str) -> None:
        target = map_name.strip()
        if not target:
            raise ValueError("nama map tidak boleh kosong")
        self.bot.join_map(target)
        self.profile.map_name = target

    def move(self, x: int, y: int, speed: int = 10) -> None:
        self.bot.move(int(x), int(y), int(speed))

    def rest(self) -> None:
        self._send(sfs.rest_packet(), "rest request")

    def chat(self, message: str) -> None:
        """Send normal chat or execute verified slash commands via ``AQWBot``."""
        text = str(message).strip()
        if not text:
            raise ValueError("format: .chat <pesan atau /command>")
        self.bot.chat(text)

    def pickup_drop(self, drop_id: int) -> None:
        self._send(
            sfs.get_drop_packet(self.bot.room_id, int(drop_id)),
            f"ambil drop {int(drop_id)}",
        )

    def use_booster(self, item_id: int) -> None:
        self._send(
            sfs.use_item_packet(self.bot.room_id, int(item_id)),
            f"gunakan item {int(item_id)}",
        )

    def aggro(self, map_ids: list[int] | tuple[int, ...]) -> None:
        self._send(
            sfs.aggro_mon_packet(self.bot.room_id, map_ids),
            "aggro monster " + ",".join(str(i) for i in map_ids),
        )

    def complete_quest(
        self,
        quest_id: int,
        reward_id: int = -1,
        turn_ins: str = "",
    ) -> None:
        self._send(
            sfs.try_quest_complete_packet(
                self.bot.room_id,
                int(quest_id),
                int(reward_id),
                turn_ins,
            ),
            f"turn-in quest {int(quest_id)}",
        )

    def sell(
        self,
        item_id: int,
        quantity: int,
        char_item_id: int,
    ) -> None:
        self._send(
            sfs.sell_item_packet(
                self.bot.room_id,
                int(item_id),
                int(quantity),
                int(char_item_id),
            ),
            f"jual item {int(item_id)} x{int(quantity)}",
        )

    def load_bank(self) -> None:
        self._send(sfs.load_bank_packet(self.bot.room_id), "muat bank")

    def class_report(self) -> list[str]:
        """Numbered menu of every detected class: equipped, inventory, bank.

        The number is what `.class use <nomor>` accepts, so the user never has
        to retype an exact class name.
        """
        rows = []
        classes = self.item_catalog.items_by_type("Class")
        for index, item in enumerate(classes, 1):
            marker = {
                "equipped": "[dipakai]",
                "inventory": "[inventory]",
                "bank": "[bank]",
            }.get(item.source, f"[{item.source}]")
            rows.append(f"[{index}] {marker} {item.name} (ItemID {item.item_id})")
        if not rows:
            state = self.combat.state
            rows.append(
                f"belum ada class terdeteksi; jalankan `.class scan` "
                f"(dipakai sekarang: {state.class_name or '?'})"
            )
        return rows

    def _resolve_class(self, token: str) -> OwnedItem | None:
        """Accept either a 1-based menu number or an exact class name."""
        text = str(token or "").strip()
        if not text:
            return None
        if text.isdigit():
            return self.item_catalog.by_type_number("Class", int(text))
        return self.item_catalog.find(text)

    def item_report(self, item_type: str = "") -> list[str]:
        """Numbered menu of every scanned item, optionally filtered by type."""
        items = (
            self.item_catalog.items_by_type(item_type)
            if item_type.strip()
            else self.item_catalog.all_items()
        )
        rows = []
        for index, item in enumerate(items, 1):
            marker = {
                "equipped": "[dipakai]",
                "inventory": "[inventory]",
                "bank": "[bank]",
            }.get(item.source, f"[{item.source}]")
            rows.append(
                f"[{index}] {marker} {item.name} "
                f"({item.item_type}, ItemID {item.item_id})"
            )
        if not rows:
            rows.append(
                "belum ada item terdeteksi; jalankan `.item scan` dulu"
            )
        return rows

    def gear_report(self, item_type: str) -> list[str]:
        """Numbered menu for one equipment slot (Weapon/Armor/Helm/Cape)."""
        return self.item_report(item_type)

    def scan_gear(self, item_type: str, timeout: float = 8.0) -> list[str]:
        """Fetch inventory+bank once, then list only the requested gear type."""
        self.scan_items(timeout=timeout)
        return self.gear_report(item_type)

    def equip_gear(self, item_type: str, token: str) -> str:
        """Equip by number from that slot's menu or by exact item name."""
        text = str(token or "").strip()
        if not text:
            raise ValueError(f"format: .{item_type.casefold()} <nomor|nama item>")
        if text.isdigit():
            match = self.item_catalog.by_type_number(item_type, int(text))
        else:
            match = self.item_catalog.find(text)
            if match is not None and match.item_type.casefold() != item_type.casefold():
                match = None
        if match is None:
            known = ", ".join(
                item.name for item in self.item_catalog.items_by_type(item_type)
            )
            raise ValueError(
                f"{item_type.casefold()} '{text}' tidak ditemukan "
                f"(terdeteksi: {known or 'tidak ada'})"
            )
        if match.source == "equipped":
            return f"{match.name} sudah dipakai"
        if match.source == "bank":
            self.bank_to_inventory(match.item_id, match.char_item_id)
        self._send(
            sfs.equip_item_packet(self.bot.room_id, match.item_id),
            f"equip {match.name}",
        )
        return f"equip {match.name} ({match.item_type})"

    def equip_item(self, token: str) -> str:
        """Equip any scanned item by menu number or exact name.

        Classes and gear use the same path: move from bank first when needed,
        then send the server's own `equipItem` command.
        """
        text = str(token or "").strip()
        if not text:
            raise ValueError("format: .equip <nomor|nama item>")
        if text.isdigit():
            match = self.item_catalog.by_number(int(text))
        else:
            match = self.item_catalog.find(text)
        if match is None:
            known = ", ".join(item.name for item in self.item_catalog.all_items()[:20])
            raise ValueError(
                f"item '{text}' tidak ditemukan "
                f"(terdeteksi: {known or 'belum ada'})"
            )
        if match.source == "equipped":
            return f"{match.name} sudah dipakai"
        if match.source == "bank":
            self.bank_to_inventory(match.item_id, match.char_item_id)
        self._send(
            sfs.equip_item_packet(self.bot.room_id, match.item_id),
            f"equip {match.name}",
        )
        # A class changes the skill kit; gear does not.
        if match.item_type.casefold() == "class":
            self._adopt_equipped_profile(assume=match.name)
            return f"equip {match.name}; tunggu sAct live untuk skill"
        return f"equip {match.name} ({match.item_type})"

    def select_class(self, class_name: str) -> str:
        """Equip a detected class by menu number or name."""
        wanted = str(class_name or "").strip()
        if not wanted:
            raise ValueError("format: .class use <nomor|nama class>")
        match = self._resolve_class(wanted)
        if match is None:
            self.scan_classes(timeout=6.0)
            match = self._resolve_class(wanted)
        if match is None:
            known = ", ".join(
                item.name for item in self.item_catalog.items_by_type("Class")
            )
            raise ValueError(
                f"class '{wanted}' tidak terdeteksi "
                f"(terdeteksi: {known or 'tidak ada'})"
            )
        if match.source == "equipped":
            self._adopt_equipped_profile()
            return f"{match.name} sudah dipakai"
        if match.source == "bank":
            # The server processes the transfer asynchronously; equipping in a
            # separate step once inventory confirms is the safe order.
            self.bank_to_inventory(match.item_id, match.char_item_id)
        self._send(
            sfs.equip_item_packet(self.bot.room_id, match.item_id),
            f"equip class {match.name}",
        )
        self._adopt_equipped_profile(assume=match.name)
        where = "bank" if match.source == "bank" else "inventory"
        return f"equip {match.name} dari {where}; tunggu sAct live untuk skill"

    def scan_items(self, timeout: float = 8.0) -> list[str]:
        """Request full inventory+bank and return a numbered all-item menu."""
        have_inventory = bool(self.item_catalog.all_items())
        if not have_inventory:
            room = int(getattr(self.bot, "room_id", 1) or 1)
            uid = int(getattr(self.bot, "session_user_id", 0) or 0)
            if uid > 0:
                self._send(
                    sfs.retrieve_inventory_packet(room, uid), "minta inventory"
                )
        if not self.item_catalog.bank_loaded:
            self.load_bank()
        deadline = time.monotonic() + max(0.0, float(timeout))
        while time.monotonic() < deadline:
            if self.item_catalog.all_items() and self.item_catalog.bank_loaded:
                break
            time.sleep(0.05)
        return self.item_report("")

    def scan_classes(self, timeout: float = 8.0) -> list[str]:
        """Request inventory+bank, then keep packets the main loop feeds us."""
        state = self.combat.state
        have_inv = bool(state.owned_classes) or bool(state.class_name)
        if not have_inv:
            room = int(getattr(self.bot, "room_id", 1) or 1)
            uid = int(getattr(self.bot, "session_user_id", 0) or 0)
            if uid > 0:
                self._send(
                    sfs.retrieve_inventory_packet(room, uid), "minta inventory"
                )
        if not state.bank_loaded:
            self.load_bank()
        deadline = time.monotonic() + max(0.0, float(timeout))
        while time.monotonic() < deadline:
            with self._lock:
                have_inv = bool(state.owned_classes) or bool(state.class_name)
                if have_inv and state.bank_loaded:
                    break
            time.sleep(0.05)
        return self.class_report()

    def _adopt_equipped_profile(self, assume: str = "") -> None:
        # An explicit equip request is authoritative until the server confirms:
        # the old class_name stays cached until the next loadInventoryBig.
        target = (
            assume.strip()
            or (self.combat.state.class_name or "").strip()
            or self.profile.class_name
        )
        try:
            profile = combat.profile_for(target)
        except ValueError:
            profile = combat.generic_profile(target)
        self.combat.set_class_profile(profile)
        self.profile.class_name = profile.class_name

    def bank_to_inventory(self, item_id: int, char_item_id: int) -> None:
        self._send(
            sfs.bank_to_inventory_packet(
                self.bot.room_id, int(item_id), int(char_item_id)
            ),
            f"bank -> inventory item {int(item_id)}",
        )

    def bank_from_inventory(self, item_id: int, char_item_id: int) -> None:
        self._send(
            sfs.bank_from_inventory_packet(
                self.bot.room_id, int(item_id), int(char_item_id)
            ),
            f"inventory -> bank item {int(item_id)}",
        )

    def attack(self, monster_name: str = "") -> None:
        target = monster_name.strip() or self.profile.target_monster
        if target.casefold() == "auto":
            self.attack_auto()
            return
        if target.casefold() != self.combat.target_name.casefold():
            raise ValueError(
                f"target sesi ini: {self.combat.target_name}; diminta {target}"
            )
        # A named target is the narrower goal: leave map-wide mode so the
        # engine stops navigating on its own.
        self.combat.set_map_wide(False)
        self.combat.set_auto(False)
        self.combat.start()

    def attack_auto(self) -> None:
        """Attack every living monster discovered in the current cell."""
        self.combat.set_map_wide(False)
        self.combat.set_auto(True)
        self.combat.start()

    def fight_all_in_map(self) -> None:
        """High-level goal: fight every enemy in this map, not one command at a time."""
        self.combat.set_map_wide(True)
        self.combat.start()
        self._on_log(
            "[GOAL] aktif: lawan semua musuh di map ini "
            "(lawan cell ini -> pindah ke cell yang masih ada musuh -> ulang)"
        )

    def stop_goal(self) -> None:
        self.combat.set_map_wide(False)
        self.combat.stop()
        self._on_log("[GOAL] dihentikan")

    def stop_attack(self) -> None:
        self.combat.set_map_wide(False)
        self.combat.stop()

    def combat_status(self) -> str:
        return self.combat.status()

    def combat_scan_report(self, limit: int = 8) -> list[str]:
        rows = self.combat.scan_report()
        return list(rows[: max(1, int(limit))])

    def attack_by_id(self, monster_id: int) -> None:
        raise FarmingUnsupported(
            "serangan memakai nama target agar scan cell yang memutuskan MonMapID; "
            f"abaikan id manual {int(monster_id)}"
        )

    def status(self) -> str:
        state = getattr(self.bot, "state", None)
        state_value = getattr(state, "value", state or "UNKNOWN")
        return (
            f"FARM {'ON' if self.running else 'READY'} | state {state_value} "
            f"| map {getattr(self.bot, 'current_map', '') or '-'} "
            f"| room {getattr(self.bot, 'room_id', '-')} "
            f"| AI OFF | {self.combat.status()}"
        )
