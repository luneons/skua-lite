"""Headless AQW combat state and conservative auto-attack engine.

The wire shapes here follow the active Game.as paths: moveToArea builds
``monTree``/``uoTree``; updateClass and sAct describe the equipped class and its
actual actions; STR mtls/uotls/respawnMon mutate live state; World.getActionResult
serializes GAR. No Flash display-object or range shortcut is reproduced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable

from . import sfs


_CAPTURE_COMMANDS = {
    "moveToArea", "updateClass", "sAct", "mtls", "uotls", "tempSta",
    "respawnMon", "resPlayerTimed", "resTimed", "spcs", "sar", "sars", "gar",
    "moveToCell", "aura+", "aura+p", "aura-", "aura-p", "clearAuras",
}


# Pad names accepted by the area map (Skua MapService.Pads plus the diagonal
# pads the live maps expose). A pad is a position inside one cell.
PAD_NAMES = (
    "Spawn", "Center", "Left", "Right", "Up", "Down", "Top", "Bottom",
    "BottomLeft", "BottomRight", "TopLeft", "TopRight",
)


def default_pad_for(cell: str, pad: str | None = None) -> str:
    """Pick the pad for a cell the way the client jump menu does.

    ``JumpViewModel`` sends an explicit pad when the user chose one; otherwise
    the area entry cell resolves to ``Spawn`` and any other cell to ``Left``.
    """
    chosen = str(pad or "").strip()
    if chosen:
        return chosen
    return "Spawn" if str(cell or "").strip().casefold() == "enter" else "Left"


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}
    if value is None:
        return default
    return bool(value)


def _str_command(packet: str) -> tuple[str, list[str]] | None:
    """Return the AQW STR command and payload after SmartFox padding."""
    if not packet.startswith("%xt%"):
        return None
    parts = packet.split("%")
    # Inbound game STR: %xt%<cmd>%<room>%<arg>...%
    if len(parts) >= 5 and parts[1] == "xt" and parts[2] != "zm":
        tail = parts[4:]
        if tail and tail[-1] == "":
            tail = tail[:-1]
        return str(parts[2]), tail
    # Outbound zone-master STR: %xt%zm%<cmd>%<room>%...
    parsed = sfs.parse_str_packet(packet)
    if parsed is None:
        return None
    return str(parsed["cmd"]), list(parsed.get("args", []))


def _field_updates(encoded: str) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for part in encoded.split(","):
        key, sep, value = part.partition(":")
        if not sep or not key:
            continue
        if key.lower().startswith("int") or key.lower() in {"tx", "ty", "sp"}:
            updates[key] = _as_int(value)
        else:
            updates[key] = value
    return updates


@dataclass(slots=True)
class SkillState:
    ref: str
    name: str = ""
    target_kind: str = "h"
    min_targets: int = 1
    max_targets: int = 1
    cooldown_ms: int = 0
    mana_cost: int = 0
    unlocked: bool = True
    auto: bool = False
    damage: float | None = None
    item_id: int | None = None
    last_used: float = -1e9

    @classmethod
    def from_wire(cls, raw: dict[str, Any]) -> "SkillState":
        try:
            damage = float(raw["damage"]) if raw.get("damage") is not None else None
        except (TypeError, ValueError):
            damage = None
        return cls(
            ref=str(raw.get("ref") or ""),
            name=str(raw.get("nam") or ""),
            target_kind=str(raw.get("tgt") or "h"),
            min_targets=max(0, _as_int(raw.get("tgtMin"), 1)),
            max_targets=max(1, _as_int(raw.get("tgtMax"), 1)),
            cooldown_ms=max(0, _as_int(raw.get("cd"), 0)),
            mana_cost=max(0, _as_int(raw.get("mp"), 0)),
            unlocked=_as_bool(raw.get("isOK"), True),
            auto=_as_bool(raw.get("auto"), False),
            damage=damage,
            item_id=(_as_int(raw.get("sArg1")) or None),
        )

    def ready(self, now: float, mp: int) -> bool:
        return (
            self.unlocked
            and mp >= self.mana_cost
            and now - self.last_used >= self.cooldown_ms / 1000.0
        )


@dataclass(slots=True)
class MonsterState:
    map_id: int
    monster_id: int = 0
    name: str = ""
    race: str = ""
    cell: str = ""
    hp: int = 0
    max_hp: int = 0
    state: int = 0

    @property
    def alive(self) -> bool:
        return self.hp > 0 and self.state > 0


@dataclass(slots=True)
class ClassProfile:
    class_name: str
    aliases: tuple[str, ...]
    modes: dict[str, dict[str, Any]]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ClassProfile":
        name = str(raw.get("class_name") or "").strip()
        if not name:
            raise ValueError("class_name kosong")
        aliases = tuple(str(v).strip() for v in raw.get("aliases", [name]) if str(v).strip())
        modes = raw.get("modes")
        if not isinstance(modes, dict) or not modes:
            raise ValueError("modes class profile kosong")
        return cls(name, aliases or (name,), modes)

    @classmethod
    def load(cls, path: str | Path) -> "ClassProfile":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def matches(self, class_name: str) -> bool:
        wanted = class_name.strip().casefold()
        return wanted in {self.class_name.casefold(), *(v.casefold() for v in self.aliases)}

    def skill_refs(self, mode: str) -> tuple[str, ...]:
        selected = self.modes.get(mode) or self.modes.get("base")
        if not isinstance(selected, dict):
            raise ValueError(f"mode class tidak ada: {mode}")
        refs: list[str] = []
        for skill_id in selected.get("skills", []):
            index = _as_int(skill_id, -1)
            refs.append("aa" if index == 0 else f"a{index}")
        fallback = str(selected.get("fallback") or "").strip()
        if fallback and fallback not in refs:
            refs.append(fallback)
        return tuple(refs)


def mage_profile() -> ClassProfile:
    path = Path(__file__).with_name("class_profiles") / "mage.json"
    return ClassProfile.load(path)


def generic_profile(class_name: str) -> ClassProfile:
    """Safe order for an unknown equipped class: strongest slots first.

    Live sAct still decides what fires (cooldown, mana, locked, target kind),
    so this ordering only sets intent, not behavior.
    """
    name = str(class_name or "").strip() or "Unknown"
    return ClassProfile(
        class_name=name,
        aliases=(name,),
        modes={
            "base": {"skills": [4, 3, 2, 1], "fallback": "aa"},
            "farm_fast": {"skills": [4, 3, 2, 1], "fallback": "aa"},
        },
    )


def profile_for(class_name: str) -> ClassProfile:
    """File profile when the class has one, else a generic live-sAct profile."""
    wanted = str(class_name or "").strip().casefold()
    directory = Path(__file__).with_name("class_profiles")
    for path in sorted(directory.glob("*.json")):
        try:
            candidate = ClassProfile.load(path)
        except (OSError, ValueError):
            continue
        if candidate.matches(wanted):
            return candidate
    return generic_profile(class_name)


@dataclass(slots=True)
class OwnedClass:
    """One Class-category item the scan proved (Skua: sType == Class)."""

    name: str
    item_id: int
    char_item_id: int
    source: str  # "equipped" | "inventory" | "bank"


@dataclass(slots=True)
class CombatState:
    self_username: str
    self_user_id: int | None = None
    class_name: str = ""
    class_item_id: int | None = None
    cell: str = ""
    hp: int = 0
    max_hp: int = 0
    mp: int = 0
    max_mp: int = 0
    player_state: int = 0
    seen_self: bool = False
    respawn_move: tuple[str, str] | None = None
    skills: dict[str, SkillState] = field(default_factory=dict)
    monsters: dict[int, MonsterState] = field(default_factory=dict)
    owned_classes: list[OwnedClass] = field(default_factory=list)
    bank_loaded: bool = False
    _monster_defs: dict[int, dict[str, Any]] = field(default_factory=dict)
    # Players seen alive in the current area snapshot (lowercase username ->
    # (cell, pad)). Mirrors `World.uoTree`, which the client builds from the
    # same `moveToArea.uoBranch` payload.
    _area_players: dict[str, tuple[str, str]] = field(default_factory=dict)
    # Filename of the map SWF the server named in `moveToArea`
    # (`strMapFileName`). Used to enrich the cell list with every real SWF
    # scene label instead of guessing destinations.
    map_file_name: str = ""
    # Every cell confirmed by the map SWF scene labels. Unioned with the
    # server-observed cells, never guessed.
    map_cells: tuple[str, ...] = ()
    # Every pad genuinely observed in area/state updates (lowercase -> real).
    # `.cell <nama> <pad>` accepts any pad name and lets the server judge the
    # unknown ones, but known pads are shown first in `.cells`.
    _seen_pads: dict[str, str] = field(default_factory=dict)
    # Cell -> pad the server actually used (lowercase cell -> real pad), so an
    # implicit pad reuses an observed pair instead of a guess.
    _cell_pads: dict[str, str] = field(default_factory=dict)

    def feed(self, packet: str) -> None:
        parsed_json = sfs.parse_xt_json(packet)
        if parsed_json is not None:
            self._feed_json(str(parsed_json.get("cmd") or ""), parsed_json["obj"])
            return
        parsed_str = _str_command(packet)
        if parsed_str is not None:
            self._feed_str(*parsed_str)

    def _feed_json(self, cmd: str, obj: dict[str, Any]) -> None:
        if cmd == "moveToArea":
            self._monster_defs = {
                _as_int(item.get("MonID")): dict(item)
                for item in obj.get("mondef", [])
                if isinstance(item, dict) and _as_int(item.get("MonID")) > 0
            }
            maps = {
                _as_int(item.get("MonMapID")): dict(item)
                for item in obj.get("monmap", [])
                if isinstance(item, dict) and _as_int(item.get("MonMapID")) > 0
            }
            self.monsters.clear()
            for branch in obj.get("monBranch", []):
                if not isinstance(branch, dict):
                    continue
                map_id = _as_int(branch.get("MonMapID"))
                if map_id <= 0:
                    continue
                combined: dict[str, Any] = {}
                combined.update(self._monster_defs.get(_as_int(branch.get("MonID")), {}))
                combined.update(maps.get(map_id, {}))
                combined.update(branch)
                self.monsters[map_id] = self._monster_from(combined)
            file_name = str(obj.get("strMapFileName") or "").strip()
            if file_name:
                self.map_file_name = file_name
            self._area_players.clear()
            for player in obj.get("uoBranch", []):
                if not isinstance(player, dict):
                    continue
                username = str(player.get("uoName") or player.get("strUsername") or "")
                uid = _as_int(player.get("uid") or player.get("iUserID"))
                if not username:
                    continue
                self._area_players[username.casefold()] = (
                    str(player.get("strFrame") or ""),
                    str(player.get("strPad") or ""),
                )
                self._note_pad(player.get("strPad"), player.get("strFrame"))
                if username.casefold() == self.self_username.casefold() or (
                    self.self_user_id is not None and uid == self.self_user_id
                ):
                    self._update_self(player)
        elif cmd == "updateClass":
            self._update_class(obj)
        elif cmd in {"loadInventoryBig", "loadInventory"}:
            self._update_class_from_inventory(obj.get("items"))
        elif cmd == "loadBank":
            self._update_class_from_bank(obj.get("items"))
        elif cmd == "sAct":
            actions = obj.get("actions") or {}
            active = actions.get("active", []) if isinstance(actions, dict) else []
            parsed = {
                skill.ref: skill
                for raw in active
                if isinstance(raw, dict)
                for skill in [SkillState.from_wire(raw)]
                if skill.ref in {"aa", "a1", "a2", "a3", "a4", "i1"}
            }
            if parsed:
                self.skills = parsed
        elif cmd == "mtls":
            monster = self.monsters.get(_as_int(obj.get("id")))
            updates = obj.get("o") if isinstance(obj.get("o"), dict) else obj
            if monster is not None:
                self._update_monster(monster, updates)
        elif cmd in {"uotls", "tempSta"}:
            username = str(obj.get("unm") or obj.get("uoName") or "")
            updates = obj.get("o") if isinstance(obj.get("o"), dict) else obj
            if not username or username.casefold() == self.self_username.casefold():
                self._update_self(updates)

    def _feed_str(self, cmd: str, args: list[str]) -> None:
        if cmd == "mtls" and len(args) >= 2:
            monster = self.monsters.get(_as_int(args[0]))
            if monster is not None:
                self._update_monster(monster, _field_updates(args[1]))
        elif cmd == "resTimed":
            cell = str(args[0]).strip() if args else ""
            pad = str(args[1]).strip() if len(args) >= 2 else ""
            self.respawn_move = (cell or "Enter", pad or "Spawn")
        elif cmd == "respawnMon" and args:
            for raw_id in args[0].split(","):
                monster = self.monsters.get(_as_int(raw_id))
                if monster is not None:
                    monster.hp = monster.max_hp
                    monster.state = 1
        elif cmd in {"uotls", "tempSta"} and len(args) >= 2:
            if args[0].casefold() == self.self_username.casefold():
                self._update_self(_field_updates(args[1]))
        elif cmd == "spcs" and len(args) >= 2:
            monster = self.monsters.get(_as_int(args[0]))
            if monster is not None:
                monster.monster_id = _as_int(args[1])
                definition = self._monster_defs.get(monster.monster_id, {})
                monster.name = str(definition.get("strMonName") or monster.name)
                monster.max_hp = _as_int(definition.get("intHPMax"), monster.max_hp)
                monster.hp = 0
                monster.state = 0

    def _update_class(self, obj: dict[str, Any]) -> None:
        uid = _as_int(obj.get("uid"))
        if self.self_user_id is not None and uid not in {0, self.self_user_id}:
            return
        self.class_name = str(obj.get("sClassName") or self.class_name)
        item_id = _as_int(obj.get("ItemID") or obj.get("iItemID"))
        self.class_item_id = item_id or self.class_item_id

    def _update_class_from_inventory(self, items: Any) -> None:
        """Cache every inventory class and learn the equipped one from bEquip."""
        rows = self._class_rows(items)
        self.owned_classes = [
            entry for entry in self.owned_classes if entry.source == "bank"
        ]
        for raw in rows:
            equipped = _as_bool(raw.get("bEquip"))
            entry = OwnedClass(
                name=str(raw.get("sName") or "").strip(),
                item_id=_as_int(raw.get("ItemID")),
                char_item_id=_as_int(raw.get("CharItemID")),
                source="equipped" if equipped else "inventory",
            )
            self._upsert_owned_class(entry)
            if equipped:
                self.class_name = entry.name or self.class_name
                self.class_item_id = entry.item_id or self.class_item_id

    def _update_class_from_bank(self, items: Any) -> None:
        """Cache Class-category bank rows without touching equipped-class state."""
        self.bank_loaded = True
        self.owned_classes = [
            entry for entry in self.owned_classes if entry.source != "bank"
        ]
        for raw in self._class_rows(items):
            self._upsert_owned_class(OwnedClass(
                name=str(raw.get("sName") or "").strip(),
                item_id=_as_int(raw.get("ItemID")),
                char_item_id=_as_int(raw.get("CharItemID")),
                source="bank",
            ))

    @staticmethod
    def _class_rows(items: Any) -> list[dict[str, Any]]:
        if isinstance(items, dict):
            source = items.values()
        elif isinstance(items, list):
            source = items
        else:
            return []
        return [
            raw for raw in source
            if isinstance(raw, dict)
            and str(raw.get("sType") or raw.get("Category") or "").casefold() == "class"
            and str(raw.get("sName") or "").strip()
            and _as_int(raw.get("ItemID")) > 0
        ]

    def _upsert_owned_class(self, entry: OwnedClass) -> None:
        """Inventory wins if the same ItemID is echoed by a stale bank payload."""
        for index, current in enumerate(self.owned_classes):
            if current.item_id != entry.item_id:
                continue
            if current.source != "bank" and entry.source == "bank":
                return
            self.owned_classes[index] = entry
            return
        self.owned_classes.append(entry)

    def _monster_from(self, raw: dict[str, Any]) -> MonsterState:
        return MonsterState(
            map_id=_as_int(raw.get("MonMapID")),
            monster_id=_as_int(raw.get("MonID")),
            name=str(raw.get("strMonName") or ""),
            race=str(raw.get("sRace") or ""),
            cell=str(raw.get("strFrame") or ""),
            hp=_as_int(raw.get("intHP")),
            max_hp=_as_int(raw.get("intHPMax")),
            state=_as_int(raw.get("intState")),
        )

    def _update_monster(self, monster: MonsterState, updates: dict[str, Any]) -> None:
        monster.hp = _as_int(updates.get("intHP"), monster.hp)
        monster.max_hp = _as_int(updates.get("intHPMax"), monster.max_hp)
        monster.state = _as_int(updates.get("intState"), monster.state)
        monster.cell = str(updates.get("strFrame", monster.cell))

    def _update_self(self, updates: dict[str, Any]) -> None:
        self.seen_self = True
        self.cell = str(updates.get("strFrame", self.cell))
        self._note_pad(updates.get("strPad"), updates.get("strFrame", self.cell))
        self.hp = _as_int(updates.get("intHP"), self.hp)
        self.max_hp = _as_int(updates.get("intHPMax"), self.max_hp)
        self.mp = _as_int(updates.get("intMP"), self.mp)
        self.max_mp = _as_int(updates.get("intMPMax"), self.max_mp)
        self.player_state = _as_int(updates.get("intState"), self.player_state)

    def _note_pad(self, pad: Any, cell: Any = None) -> None:
        """Remember a pad name only when the server actually used it.

        Also records which pad a specific cell was observed standing on, so
        ``.cell <nama>`` without an explicit pad can reuse the real pair the
        client used instead of guessing.
        """
        name = str(pad or "").strip()
        if not name:
            return
        self._seen_pads.setdefault(name.casefold(), name)
        cell_name = str(cell or "").strip()
        if cell_name:
            self._cell_pads.setdefault(cell_name.casefold(), name)

    def observed_pad_for(self, cell: str) -> str | None:
        """Return the pad the server actually used with ``cell``, if any."""
        return self._cell_pads.get(str(cell or "").strip().casefold())

    def set_map_cells(self, cells: list[str] | tuple[str, ...]) -> None:
        """Record cells read from the map SWF named by ``strMapFileName``."""
        unique: dict[str, str] = {}
        for raw in cells or ():
            name = str(raw or "").strip()
            if name:
                unique.setdefault(name.casefold(), name)
        self.map_cells = tuple(unique.values())

    def known_cells(self) -> list[str]:
        """Return every cell name the server or map file actually revealed.

        Sources, in order: the map SWF scene labels (complete list when the
        server named one and it could be read), then the cells the server put
        the character, monsters, or other players into. Nothing is invented.
        """
        found: dict[str, str] = {}
        for name in self.map_cells:
            if name and str(name).strip():
                found.setdefault(str(name).strip().casefold(), str(name).strip())
        if self.cell.strip():
            found.setdefault(self.cell.strip().casefold(), self.cell.strip())
        for monster in self.monsters.values():
            if monster.cell.strip():
                found.setdefault(monster.cell.strip().casefold(), monster.cell.strip())
        for cell, _pad in self._area_players.values():
            if cell.strip():
                found.setdefault(cell.strip().casefold(), cell.strip())
        return sorted(found.values(), key=lambda name: (name.casefold(), name))

    def known_pads(self) -> list[str]:
        """Pads confirmed by server traffic, then the documented pad names."""
        found: dict[str, str] = dict(self._seen_pads)
        for name in PAD_NAMES:
            found.setdefault(name.casefold(), name)
        return [found[key] for key in sorted(found, key=lambda k: (k != "spawn", k))]

    def alive_in_cell(self) -> list[MonsterState]:
        """Return every living monster discovered in the player's current cell."""
        matches = [
            monster for monster in self.monsters.values()
            if monster.alive and monster.cell == self.cell
        ]
        return sorted(matches, key=lambda monster: (monster.hp, monster.map_id))

    def alive_monsters(self, name: str | None = None) -> list[MonsterState]:
        wanted = name.strip().casefold() if name else ""
        return [
            monster for monster in self.alive_in_cell()
            if not wanted or monster.name.casefold() == wanted
        ]


class AutoAttackEngine:
    """Packet-driven combat loop for one class profile and monster name."""

    def __init__(
        self,
        bot: Any,
        *,
        target_name: str,
        class_profile: ClassProfile,
        mode: str = "farm_fast",
        interval: float = 0.1,
        capture_path: str | Path | None = None,
        clock: Callable[[], float] = time.monotonic,
        respawn_delay: float = 10.0,
        on_log: Callable[[str], None] | None = None,
        move_timeout: float = 2.0,
        move_retries: int = 1,
    ) -> None:
        self.bot = bot
        self.target_name = target_name.strip()
        if not self.target_name:
            raise ValueError("target_name kosong")
        self.class_profile = class_profile
        self.mode = mode
        self.interval = max(0.01, float(interval))
        self.capture_path = Path(capture_path) if capture_path else None
        self.clock = clock
        self.on_log = on_log or (lambda _message: None)
        self.state = CombatState(
            self_username=str(getattr(bot, "username", "")),
            self_user_id=getattr(bot, "session_user_id", None),
        )
        self.respawn_delay = max(0.0, float(respawn_delay))
        self.move_timeout = max(0.2, float(move_timeout))
        self.move_retries = max(0, int(move_retries))
        self._death_at: float | None = None
        self._respawn_sent = False
        self._auto = False
        # Map-wide goal: when enabled, the engine treats "attack the enemies in
        # this map" as one continuous goal: fight every living monster in the
        # current cell, move to another cell that still has enemies, repeat.
        self._map_wide = False
        # Pending map movement state. Proves the next arrival before more
        # combat is emitted, instead of trusting a fixed sleep.
        self._move_target: tuple[str, str] | None = None
        self._move_sent_at: float = 0.0
        self._move_attempts: int = 0
        self._move_status: str = ""
        self._blocked_cells: set[str] = set()
        self._action_id = 0
        self._last_non_auto_action = -1e9
        self._global_cooldown = 1.5
        self._capture = False
        self._running = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self.last_action = ""

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def auto(self) -> bool:
        """True = attack every living monster found in the current cell."""
        with self._lock:
            return self._auto

    @property
    def map_wide(self) -> bool:
        """True while the high-level clear-map goal owns combat/navigation."""
        with self._lock:
            return self._map_wide

    @property
    def move_status(self) -> str:
        with self._lock:
            return self._move_status

    @property
    def blocked_cells(self) -> set[str]:
        with self._lock:
            return set(self._blocked_cells)

    def set_map_wide(self, enabled: bool) -> None:
        """Enable/disable the goal "lawan semua musuh yang ada di map ini"."""
        with self._lock:
            self._map_wide = bool(enabled)
            self._auto = bool(enabled)
            self._move_target = None
            self._move_attempts = 0
            self._blocked_cells.clear()
            self._move_status = ""
        if enabled:
            self.on_log(
                "[GOAL] lawan semua musuh di map: scan -> lawan -> pindah -> ulang"
            )

    def set_auto(self, enabled: bool) -> None:
        with self._lock:
            self._auto = bool(enabled)
        if self._auto:
            self.on_log(
                "[COMBAT] mode auto: menyerang semua monster hidup di cell ini"
            )

    def set_class_profile(self, class_profile: ClassProfile) -> None:
        """Adopt the profile of a newly equipped class.

        Carried-over skill refs lose their tracked cooldown: ``a4`` on the new
        class is not the ``a4`` the previous class just fired.
        """
        with self._lock:
            self.class_profile = class_profile
            for skill in self.state.skills.values():
                skill.last_used = -1e9
            self._last_non_auto_action = -1e9
            self._action_id = 0
            name = class_profile.class_name
        self.on_log(f"[COMBAT] profil class -> {name} (skill dari sAct live)")

    def set_capture(self, enabled: bool) -> None:
        self._capture = bool(enabled)
        if self._capture and self.capture_path is not None:
            self.capture_path.parent.mkdir(parents=True, exist_ok=True)
            self.capture_path.write_text("", encoding="utf-8")

    def feed(self, packet: str, outbound: bool = False) -> None:
        with self._lock:
            self.state.feed(packet)
            if not outbound:
                self._drain_respawn_move()
            if self._capture and self.capture_path is not None and self._capture_worthy(packet):
                stamp = time.strftime("%H:%M:%S")
                direction = "OUT " if outbound else "IN  "
                with self.capture_path.open("a", encoding="utf-8") as handle:
                    handle.write(f"[{stamp}] {direction}{packet[:20000]}\n")

    def _drain_respawn_move(self) -> None:
        move = self.state.respawn_move
        if move is None:
            return
        self.state.respawn_move = None
        target_cell, target_pad = move
        room = _as_int(getattr(self.bot, "room_id", 0), 1)
        if room <= 0:
            room = 1
        self.bot._send_raw(
            sfs.xt_str("zm", "moveToCell", [target_cell, target_pad], room)
        )
        self.last_action = f"respawn-cell -> {target_cell}/{target_pad}"
        self.on_log(f"[COMBAT] respawn ke {target_cell}/{target_pad}")

    def _capture_worthy(self, packet: str) -> bool:
        parsed = sfs.parse_xt_json(packet)
        if parsed is not None:
            return str(parsed.get("cmd")) in _CAPTURE_COMMANDS
        command = _str_command(packet)
        return command is not None and command[0] in _CAPTURE_COMMANDS

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run, name="AutoAttackEngine", daemon=True
            )
            self._thread.start()
        self.on_log(
            f"[COMBAT] auto-attack ON: {self.class_profile.class_name} -> {self.target_name}"
        )

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        with self._lock:
            self._running = False
        self.on_log("[COMBAT] auto-attack OFF")

    def _run(self) -> None:
        try:
            while not self._stop_event.wait(self.interval):
                self.tick()
        finally:
            with self._lock:
                self._running = False

    def tick(self) -> bool:
        with self._lock:
            now = self.clock()
            if not self.state.seen_self:
                return False
            if self.state.player_state <= 0 or self.state.hp <= 0:
                self._tick_respawn(now)
                return False
            self._death_at = None
            self._respawn_sent = False
            if not self.class_profile.matches(self.state.class_name):
                return False
            if self._map_wide and self._move_target is not None:
                pending = self._update_pending_move(now)
                if pending is not None:
                    # Retried, failed, or still waiting: no combat this tick.
                    return pending
                # Arrival confirmed; fall through and keep fighting here.
            if self.auto:
                monsters = self.state.alive_in_cell()
            else:
                monsters = self.state.alive_monsters(self.target_name)
            if not monsters:
                if self._map_wide:
                    return self._tick_map_movement(now)
                return False
            skill = self._choose_skill(now)
            if skill is None:
                return False
            targets = self._targets_for(skill, monsters)
            if len(targets) < skill.min_targets:
                return False
            packet = sfs.gar_packet(
                room=1,
                action_id=self._action_id,
                action_ref=skill.ref,
                targets=targets,
                item_id=skill.item_id if skill.ref == "i1" else None,
            )
            self.bot._send_raw(packet)
            skill.last_used = now
            if skill.ref != "aa":
                self._last_non_auto_action = now
            self.last_action = f"{skill.ref} -> {','.join(targets)}"
            self._action_id = 0 if self._action_id >= 30 else self._action_id + 1
            return True

    def _destination_with_enemies(self) -> tuple[str, str] | None:
        """Pick a server-observed cell containing a live enemy.

        This is intentionally one-hop and evidence-driven: it does not claim a
        full SWF route graph. The destination comes directly from live
        ``monmap/monBranch`` state, while the pad reuses a server-observed pair
        when available and otherwise uses the client jump-menu default.
        """
        current = self.state.cell.casefold()
        grouped: dict[str, tuple[str, int]] = {}
        for monster in self.state.monsters.values():
            cell = monster.cell.strip()
            if not monster.alive or not cell or cell.casefold() == current:
                continue
            if cell in self._blocked_cells:
                continue
            key = cell.casefold()
            real, count = grouped.get(key, (cell, 0))
            grouped[key] = (real, count + 1)
        if not grouped:
            return None
        cell, _count = sorted(
            grouped.values(), key=lambda item: (-item[1], item[0].casefold())
        )[0]
        pad = self.state.observed_pad_for(cell) or default_pad_for(cell)
        return cell, pad

    def _send_map_move(self, cell: str, pad: str, now: float) -> None:
        room = _as_int(getattr(self.bot, "room_id", 0), 1)
        if room <= 0:
            room = 1
        self.bot._send_raw(sfs.move_to_cell_packet(room, cell, pad))
        self._move_sent_at = now
        self._move_attempts += 1
        prefix = "requested" if self._move_attempts == 1 else "retried"
        self._move_status = f"{prefix}:{cell}/{pad}"
        self.last_action = f"map-cell -> {cell}/{pad}"
        self.on_log(
            f"[GOAL] pindah ke {cell}/{pad} "
            f"(percobaan {self._move_attempts}/{self.move_retries + 1})"
        )

    def _tick_map_movement(self, now: float) -> bool:
        destination = self._destination_with_enemies()
        if destination is None:
            self.last_action = "map clear / menunggu respawn"
            return False
        cell, pad = destination
        self._move_target = destination
        self._move_attempts = 0
        self._send_map_move(cell, pad, now)
        return True

    def _update_pending_move(self, now: float) -> bool | None:
        """Return None only after server state confirms arrival."""
        target = self._move_target
        if target is None:
            return None
        cell, pad = target
        if self.state.cell.casefold() == cell.casefold():
            self._move_target = None
            self._move_status = f"confirmed:{cell}/{pad}"
            self.last_action = f"arrived -> {cell}/{pad}"
            self.on_log(f"[GOAL] tiba di {cell}/{pad}; lanjut lawan")
            return None
        if now - self._move_sent_at < self.move_timeout:
            return False
        if self._move_attempts <= self.move_retries:
            self._send_map_move(cell, pad, now)
            return True
        self._blocked_cells.add(cell)
        self._move_target = None
        self._move_status = f"failed:{cell}/{pad}"
        self.last_action = f"unreachable -> {cell}/{pad}"
        self.on_log(f"[GOAL] cell {cell}/{pad} gagal dijangkau; diblokir")
        return False

    def _tick_respawn(self, now: float) -> None:
        """Reproduce World.showResCounter -> resTimer -> resPlayer.

        The Flash client owns the 10s countdown and then sends
        ``resPlayerTimed``; without it the server keeps the avatar dead.
        """
        if self._death_at is None:
            self._death_at = now
            return
        if self._respawn_sent or (now - self._death_at) < self.respawn_delay:
            return
        uid = self.state.self_user_id or _as_int(
            getattr(self.bot, "session_user_id", 0)
        )
        if uid <= 0:
            return
        room = _as_int(getattr(self.bot, "room_id", 0), 1)
        if room <= 0:
            room = 1
        self.bot._send_raw(sfs.res_player_timed_packet(uid, room=room))
        self._respawn_sent = True
        self.last_action = "respawn -> p:%d" % uid
        self.on_log(f"[COMBAT] mati {self.respawn_delay:.0f}s -> minta respawn")

    def _choose_skill(self, now: float) -> SkillState | None:
        # Game.as applies a 1500ms global cooldown to every non-AA action.
        gcd_ready = (now - self._last_non_auto_action) >= self._global_cooldown
        for ref in self.class_profile.skill_refs(self.mode):
            skill = self.state.skills.get(ref)
            if skill is None:
                continue
            if skill.ref != "aa" and not gcd_ready:
                continue
            if skill.ready(now, self.state.mp):
                return skill
        return None

    def _targets_for(self, skill: SkillState, monsters: list[MonsterState]) -> list[str]:
        if skill.target_kind == "h":
            return [f"m:{monster.map_id}" for monster in monsters[: skill.max_targets]]
        if skill.target_kind in {"s", "f"}:
            uid = self.state.self_user_id or _as_int(getattr(self.bot, "session_user_id", 0))
            return [f"p:{uid}"] if uid > 0 else []
        return []

    def move_to_cell(self, cell: str, pad: str | None = None) -> tuple[str, str]:
        """Move to a cell exactly like ``World.moveToCell``.

        The wire is ``%xt%zm%moveToCell%<curRoom>%<cell>%<pad>%`` (World.as:2884):
        the room is the current area room, the cell keeps its server spelling,
        and the pad prefers an explicitly typed pad, then a cell->pad pair the
        server actually used, then the client rule (Enter -> Spawn, else Left).
        Any pad name is sent to the server as-is; unknown pads are judged by
        the server, never filtered here.
        """
        target_cell = str(cell or "").strip()
        if not target_cell:
            raise ValueError("format: .cell <nama> [pad]")
        explicit_pad = str(pad or "").strip()
        observed_pad = self.state.observed_pad_for(target_cell)
        target_pad = explicit_pad or observed_pad or default_pad_for(target_cell, None)
        pad_source = (
            "eksplisit" if explicit_pad
            else ("observed" if observed_pad else "default-client")
        )
        known = {name.casefold(): name for name in self.state.known_cells()}
        if target_cell.casefold() in known:
            target_cell = known[target_cell.casefold()]
        room = _as_int(getattr(self.bot, "room_id", 0), 1)
        if room <= 0:
            room = 1
        self.bot._send_raw(sfs.move_to_cell_packet(room, target_cell, target_pad))
        self.last_action = f"cell -> {target_cell}/{target_pad}"
        self.on_log(
            f"[CELL] pindah ke {target_cell}/{target_pad} (pad {pad_source})"
        )
        return target_cell, target_pad

    def cell_scan_report(self) -> list[str]:
        """Human-readable cell rows backed by server and SWF scans.

        Every row is something the server revealed (character, monster, or
        player cell) or a scene label read from the map SWF named by
        ``strMapFileName``. When the SWF could not be read, the header says so
        and only the observed cells are listed. The current cell comes first,
        the rest are alphabetical; nothing is truncated.
        """
        with self._lock:
            state = self.state
            cells = state.known_cells()
            if not cells and not state.map_cells and not state.map_file_name:
                # Nothing from the server yet: `.cells` must say so, not
                # invent a map. The caller prints the "join map dulu" hint.
                return []
            current = state.cell.strip().casefold()
            ordered = sorted(cells, key=lambda name: (name.casefold(), name))
            if current:
                ordered = [c for c in ordered if c.casefold() == current] + [
                    c for c in ordered if c.casefold() != current
                ]
            monster_count: dict[str, int] = {}
            for monster in state.monsters.values():
                if monster.alive and monster.cell.strip():
                    key = monster.cell.strip().casefold()
                    monster_count[key] = monster_count.get(key, 0) + 1
            pads = state.known_pads()[:6]
            if state.map_cells:
                header = (
                    f"map {state.map_file_name or '-'} "
                    f"({len(cells)} cell dari SWF+scan)"
                )
            else:
                suffix = (
                    f"strMapFileName={state.map_file_name}"
                    if state.map_file_name
                    else "belum ada moveToArea"
                )
                header = (
                    f"scan server parsial ({len(cells)} cell teramati; "
                    f"SWF belum dibaca: {suffix})"
                )
            rows = [header]
            for name in ordered:
                mark = " [KAMU]" if name.casefold() == current else ""
                pad_hint = state.observed_pad_for(name)
                suffix = f" | pad {pad_hint}" if pad_hint else ""
                rows.append(
                    f"{name}{mark} "
                    f"({monster_count.get(name.casefold(), 0)} monster){suffix}"
                )
            rows.append("pad: " + ", ".join(pads))
            return rows

    def status(self) -> str:
        monsters = (
            self.state.alive_in_cell()
            if self.auto
            else self.state.alive_monsters(self.target_name)
        )
        target = "auto (semua di cell)" if self.auto else self.target_name
        goal = "map-wide" if self._map_wide else "cell"
        move = f" | move {self._move_status}" if self._move_status else ""
        return (
            f"COMBAT {'ON' if self.running else 'OFF'} | mode {goal} "
            f"| class {self.state.class_name or '-'} "
            f"| cell {self.state.cell or '-'} | target {target} "
            f"| hidup {len(monsters)} | skill {len(self.state.skills)} "
            f"| last {self.last_action or '-'}{move}"
        )

    def scan_report(self) -> list[str]:
        """Human-readable rows for every monster found by the area scan.

        Used by `.combat` so the user can see exactly which MonMapIDs the
        engine knows about, which are eligible targets, and which live in a
        different cell.
        """
        with self._lock:
            eligible = {
                monster.map_id
                for monster in (
                    self.state.alive_in_cell()
                    if self.auto
                    else self.state.alive_monsters(self.target_name)
                )
            }
            rows: list[str] = []
            for monster in sorted(
                self.state.monsters.values(), key=lambda item: item.map_id
            ):
                if not monster.alive:
                    status = "MATI"
                elif monster.cell != self.state.cell:
                    status = "OTHER-CELL"
                elif monster.map_id in eligible:
                    status = "TARGET"
                else:
                    status = "SKIP"
                rows.append(
                    f"m:{monster.map_id} {monster.name or '?'} "
                    f"hp {monster.hp}/{monster.max_hp} "
                    f"cell {monster.cell or '-'} [{status}]"
                )
            return rows
