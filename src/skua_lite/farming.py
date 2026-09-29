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
from typing import Any, Callable

from . import combat, sfs
from .area_state import AreaStateStore
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

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def _combat_profile(self) -> combat.ClassProfile:
        if self.profile.class_name.casefold() == "mage":
            return combat.mage_profile()
        raise FarmingUnsupported(
            f"profil class belum tersedia: {self.profile.class_name}"
        )

    def feed_packet(self, packet: str, outbound: bool = False) -> None:
        self.combat.feed(packet, outbound=outbound)
        if not outbound:
            self.area_state.feed(packet)
            self._scan_map_cells_if_changed()

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
        self._on_log("[FARM] runtime aktif; AI/Admin tidak dimuat")
        self._on_log(
            f"[COMBAT] siap: {self.profile.class_name} -> {self.profile.target_monster}; "
            "jalankan `.capture on`, lalu `.attack <nama>` atau `.attack auto`"
        )

    def stop(self) -> None:
        self.combat.stop()
        with self._lock:
            self._running = False
        self._on_log("[FARM] runtime dihentikan")

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
