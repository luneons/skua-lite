"""Generation-aware dynamic area state built only from server packets.

This module deliberately owns no combat policy and performs no I/O. Packet
receivers feed it complete frames; readers receive copy-safe snapshots. A
``moveToArea`` frame starts a new generation and atomically replaces every
area-local entity, preventing stale entities from a previous map from driving
future actions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from copy import deepcopy
import json
import threading
import time
from typing import Any, Callable

from . import sfs


SCHEMA_VERSION = 1


def _int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _updates(encoded: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for part in str(encoded or "").split(","):
        key, sep, value = part.partition(":")
        if not sep or not key:
            continue
        if key.lower().startswith("int") or key.lower() in {"tx", "ty", "sp"}:
            result[key] = _int(value)
        else:
            result[key] = value
    return result


def _str_command(packet: str) -> tuple[str, list[str]] | None:
    """Parse both inbound ``%xt%cmd%room%...`` and outbound zm envelopes."""
    if not packet.startswith("%xt%"):
        return None
    parts = packet.split("%")
    if len(parts) >= 5 and parts[1] == "xt" and parts[2] != "zm":
        args = parts[4:]
        if args and args[-1] == "":
            args = args[:-1]
        return str(parts[2]), args
    parsed = sfs.parse_str_packet(packet)
    if parsed is None:
        return None
    return str(parsed["cmd"]), list(parsed.get("args", []))


@dataclass(frozen=True, slots=True)
class SelfAreaState:
    username: str
    user_id: int | None
    cell: str | None
    pad: str | None
    hp: int | None
    max_hp: int | None
    mp: int | None
    max_mp: int | None
    state: int | None
    source: str = "wire"


@dataclass(frozen=True, slots=True)
class PlayerAreaState:
    username: str
    user_id: int | None
    cell: str | None
    pad: str | None
    hp: int | None
    max_hp: int | None
    state: int | None
    source: str = "wire"


@dataclass(frozen=True, slots=True)
class MonsterAreaState:
    map_id: int
    monster_id: int | None
    name: str | None
    cell: str | None
    hp: int | None
    max_hp: int | None
    state: int | None
    source: str = "wire"


@dataclass(frozen=True, slots=True)
class AreaSnapshot:
    schema_version: int
    generation: int
    room_id: int | None
    map_name: str | None
    map_base_name: str | None
    map_file_name: str | None
    self_state: SelfAreaState | None
    players: dict[str, PlayerAreaState]
    monsters: dict[int, MonsterAreaState]
    map_events: tuple[dict[str, Any], ...]
    cell_map: dict[str, Any] | None
    observed_at: float
    source: str = "wire"


@dataclass(slots=True)
class _MutableArea:
    generation: int = 0
    room_id: int | None = None
    map_name: str | None = None
    map_base_name: str | None = None
    map_file_name: str | None = None
    self_state: SelfAreaState | None = None
    players: dict[str, PlayerAreaState] = field(default_factory=dict)
    monsters: dict[int, MonsterAreaState] = field(default_factory=dict)
    monster_defs: dict[int, dict[str, Any]] = field(default_factory=dict)
    map_events: tuple[dict[str, Any], ...] = ()
    cell_map: dict[str, Any] | None = None
    observed_at: float = 0.0


class AreaStateStore:
    """Thread-safe reducer and atomic snapshot holder for one connection."""

    def __init__(
        self,
        *,
        self_username: str,
        self_user_id: int | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.self_username = str(self_username or "").strip()
        self.self_user_id = self_user_id
        self.clock = clock
        self._lock = threading.RLock()
        self._state = _MutableArea()

    @property
    def generation(self) -> int:
        with self._lock:
            return self._state.generation

    def feed(self, packet: str, *, generation: int | None = None) -> bool:
        """Reduce one packet; reject a packet explicitly tied to an old area."""
        with self._lock:
            if generation is not None and generation != self._state.generation:
                return False
            parsed = sfs.parse_xt_json(packet)
            if parsed is not None:
                return self._feed_json(
                    str(parsed.get("cmd") or ""), parsed["obj"], parsed.get("room")
                )
            parsed_str = _str_command(packet)
            if parsed_str is None:
                return False
            return self._feed_str(*parsed_str)

    def _feed_json(self, cmd: str, obj: dict[str, Any], envelope_room: Any) -> bool:
        if cmd == "moveToArea":
            generation = self._state.generation + 1
            area_id = _int(obj.get("areaId"), _int(envelope_room))
            state = _MutableArea(
                generation=generation,
                room_id=area_id,
                map_name=str(obj.get("areaName") or "").strip() or None,
                map_base_name=str(obj.get("strMapName") or "").strip() or None,
                map_file_name=str(obj.get("strMapFileName") or "").strip() or None,
                map_events=tuple(
                    deepcopy(event)
                    for event in (obj.get("event") or ())
                    if isinstance(event, dict)
                ),
                cell_map=(deepcopy(obj.get("cellMap")) if isinstance(obj.get("cellMap"), dict) else None),
                observed_at=self.clock(),
            )
            state.monster_defs = {
                int(mon_id): dict(item)
                for item in (obj.get("mondef") or ())
                if isinstance(item, dict)
                and (mon_id := _int(item.get("MonID"))) is not None
                and mon_id > 0
            }
            maps = {
                int(map_id): dict(item)
                for item in (obj.get("monmap") or ())
                if isinstance(item, dict)
                and (map_id := _int(item.get("MonMapID"))) is not None
                and map_id > 0
            }
            for branch in obj.get("monBranch") or ():
                if not isinstance(branch, dict):
                    continue
                map_id = _int(branch.get("MonMapID"))
                if map_id is None or map_id <= 0:
                    continue
                raw: dict[str, Any] = {}
                raw.update(state.monster_defs.get(_int(branch.get("MonID")) or 0, {}))
                raw.update(maps.get(map_id, {}))
                raw.update(branch)
                state.monsters[map_id] = self._monster(raw)
            for raw in obj.get("uoBranch") or ():
                if not isinstance(raw, dict):
                    continue
                player = self._player(raw)
                if not player.username:
                    continue
                key = player.username.casefold()
                state.players[key] = player
                if key == self.self_username.casefold() or (
                    self.self_user_id is not None and player.user_id == self.self_user_id
                ):
                    state.self_state = self._as_self(player, raw)
            self._state = state
            return True

        if cmd == "mtls":
            raw_id = _int(obj.get("id"))
            updates = obj.get("o") if isinstance(obj.get("o"), dict) else obj
            return self._update_monster(raw_id, updates)
        if cmd in {"uotls", "tempSta"}:
            username = str(obj.get("unm") or obj.get("uoName") or "").strip()
            updates = obj.get("o") if isinstance(obj.get("o"), dict) else obj
            return self._update_player(username, updates)
        return False

    def _feed_str(self, cmd: str, args: list[str]) -> bool:
        if cmd == "mtls" and len(args) >= 2:
            return self._update_monster(_int(args[0]), _updates(args[1]))
        if cmd in {"uotls", "tempSta"} and len(args) >= 2:
            return self._update_player(str(args[0]), _updates(args[1]))
        if cmd == "respawnMon" and args:
            changed = False
            for raw_id in args[0].split(","):
                map_id = _int(raw_id)
                monster = self._state.monsters.get(map_id or -1)
                if monster is None:
                    continue
                self._state.monsters[monster.map_id] = MonsterAreaState(
                    map_id=monster.map_id,
                    monster_id=monster.monster_id,
                    name=monster.name,
                    cell=monster.cell,
                    hp=monster.max_hp,
                    max_hp=monster.max_hp,
                    state=1,
                )
                changed = True
            if changed:
                self._touch()
            return changed
        return False

    def _monster(self, raw: dict[str, Any]) -> MonsterAreaState:
        map_id = _int(raw.get("MonMapID"), 0) or 0
        return MonsterAreaState(
            map_id=map_id,
            monster_id=_int(raw.get("MonID")),
            name=str(raw.get("strMonName") or "").strip() or None,
            cell=str(raw.get("strFrame") or "").strip() or None,
            hp=_int(raw.get("intHP")),
            max_hp=_int(raw.get("intHPMax")),
            state=_int(raw.get("intState")),
        )

    def _player(self, raw: dict[str, Any]) -> PlayerAreaState:
        return PlayerAreaState(
            username=str(raw.get("uoName") or raw.get("strUsername") or "").strip(),
            user_id=_int(raw.get("uid") or raw.get("iUserID")),
            cell=str(raw.get("strFrame") or "").strip() or None,
            pad=str(raw.get("strPad") or "").strip() or None,
            hp=_int(raw.get("intHP")),
            max_hp=_int(raw.get("intHPMax")),
            state=_int(raw.get("intState")),
        )

    def _as_self(self, player: PlayerAreaState, raw: dict[str, Any]) -> SelfAreaState:
        return SelfAreaState(
            username=player.username,
            user_id=player.user_id,
            cell=player.cell,
            pad=player.pad,
            hp=player.hp,
            max_hp=player.max_hp,
            mp=_int(raw.get("intMP")),
            max_mp=_int(raw.get("intMPMax")),
            state=player.state,
        )

    def _update_monster(self, map_id: int | None, updates: dict[str, Any]) -> bool:
        monster = self._state.monsters.get(map_id or -1)
        if monster is None:
            return False
        self._state.monsters[monster.map_id] = MonsterAreaState(
            map_id=monster.map_id,
            monster_id=_int(updates.get("MonID"), monster.monster_id),
            name=str(updates.get("strMonName") or monster.name or "").strip() or None,
            cell=str(updates.get("strFrame") or monster.cell or "").strip() or None,
            hp=_int(updates.get("intHP"), monster.hp),
            max_hp=_int(updates.get("intHPMax"), monster.max_hp),
            state=_int(updates.get("intState"), monster.state),
        )
        self._touch()
        return True

    def _update_player(self, username: str, updates: dict[str, Any]) -> bool:
        key = username.strip().casefold()
        if not key:
            return False
        old = self._state.players.get(key)
        if old is None and key != self.self_username.casefold():
            return False
        user_id = old.user_id if old else self.self_user_id
        player = PlayerAreaState(
            username=(old.username if old else self.self_username),
            user_id=user_id,
            cell=str(updates.get("strFrame") or (old.cell if old else "") or "").strip() or None,
            pad=str(updates.get("strPad") or (old.pad if old else "") or "").strip() or None,
            hp=_int(updates.get("intHP"), old.hp if old else None),
            max_hp=_int(updates.get("intHPMax"), old.max_hp if old else None),
            state=_int(updates.get("intState"), old.state if old else None),
        )
        self._state.players[key] = player
        if key == self.self_username.casefold() or (
            self.self_user_id is not None and user_id == self.self_user_id
        ):
            old_self = self._state.self_state
            self._state.self_state = SelfAreaState(
                username=player.username,
                user_id=player.user_id,
                cell=player.cell,
                pad=player.pad,
                hp=player.hp,
                max_hp=player.max_hp,
                mp=_int(updates.get("intMP"), old_self.mp if old_self else None),
                max_mp=_int(updates.get("intMPMax"), old_self.max_mp if old_self else None),
                state=player.state,
            )
        self._touch()
        return True

    def _touch(self) -> None:
        self._state.observed_at = self.clock()

    def snapshot(self) -> AreaSnapshot:
        with self._lock:
            state = self._state
            return AreaSnapshot(
                schema_version=SCHEMA_VERSION,
                generation=state.generation,
                room_id=state.room_id,
                map_name=state.map_name,
                map_base_name=state.map_base_name,
                map_file_name=state.map_file_name,
                self_state=deepcopy(state.self_state),
                players=deepcopy(state.players),
                monsters=deepcopy(state.monsters),
                map_events=deepcopy(state.map_events),
                cell_map=deepcopy(state.cell_map),
                observed_at=state.observed_at,
            )

    def as_dict(self) -> dict[str, Any]:
        snap = self.snapshot()
        result = asdict(snap)
        result["players"] = [
            result["players"][key]
            for key in sorted(result["players"], key=str.casefold)
        ]
        result["monsters"] = [
            result["monsters"][key]
            for key in sorted(result["monsters"], key=int)
        ]
        return result

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def report(self) -> list[str]:
        snap = self.snapshot()
        if snap.generation <= 0:
            return ["belum ada snapshot moveToArea [unknown]"]
        rows = [
            f"area {snap.map_name or '-'} room {snap.room_id if snap.room_id is not None else '-'} "
            f"generation {snap.generation} [wire]"
        ]
        if snap.self_state is not None:
            me = snap.self_state
            rows.append(
                f"self {me.username} cell {me.cell or '-'}/{me.pad or '-'} "
                f"hp {me.hp if me.hp is not None else '?'}/{me.max_hp if me.max_hp is not None else '?'} [wire]"
            )
        for map_id in sorted(snap.monsters):
            mon = snap.monsters[map_id]
            rows.append(
                f"m:{mon.map_id} {mon.name or '?'} "
                f"hp {mon.hp if mon.hp is not None else '?'}/{mon.max_hp if mon.max_hp is not None else '?'} "
                f"cell {mon.cell or '-'} [wire]"
            )
        for key in sorted(snap.players, key=str.casefold):
            player = snap.players[key]
            if snap.self_state is not None and player.username.casefold() == snap.self_state.username.casefold():
                continue
            rows.append(
                f"p:{player.user_id if player.user_id is not None else '?'} {player.username} "
                f"cell {player.cell or '-'}/{player.pad or '-'} "
                f"hp {player.hp if player.hp is not None else '?'}/{player.max_hp if player.max_hp is not None else '?'} [wire]"
            )
        return rows
