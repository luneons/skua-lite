"""Tests for the generation-aware dynamic AQW area snapshot."""
from __future__ import annotations

import json
import threading

from skua_lite.area_state import AreaStateStore


def packet(cmd: str, room: int = 42, **fields) -> str:
    obj = {"cmd": cmd, **fields}
    return json.dumps({"t": "xt", "b": {"r": room, "o": obj}}, separators=(",", ":"))


def lair_snapshot() -> str:
    return packet(
        "moveToArea",
        areaId=42,
        areaName="lair-100000",
        strMapName="lair",
        strMapFileName="lair-v1.swf",
        uoBranch=[
            {"uoName": "alice", "uid": 1, "strFrame": "Enter", "strPad": "Spawn", "intHP": 900, "intHPMax": 900, "intMP": 300, "intMPMax": 300, "intState": 1},
            {"uoName": "bob", "uid": 2, "strFrame": "Boss", "strPad": "Left", "intHP": 700, "intHPMax": 800, "intState": 1},
        ],
        mondef=[
            {"MonID": 100, "strMonName": "Water Draconian"},
            {"MonID": 200, "strMonName": "Red Dragon"},
        ],
        monmap=[
            {"MonMapID": 1, "MonID": 100, "strFrame": "Enter"},
            {"MonMapID": 9, "MonID": 200, "strFrame": "Boss"},
        ],
        monBranch=[
            {"MonMapID": 1, "MonID": 100, "intHP": 500, "intHPMax": 500, "intState": 1},
            {"MonMapID": 9, "MonID": 200, "intHP": 3000, "intHPMax": 3000, "intState": 1},
        ],
        event=[{"typ": "gate", "cmd": "open"}],
        cellMap={"Enter": "Boss"},
    )


def test_move_to_area_creates_versioned_atomic_snapshot():
    store = AreaStateStore(self_username="alice", self_user_id=1)

    assert store.feed(lair_snapshot()) is True
    snap = store.snapshot()

    assert snap.generation == 1
    assert snap.room_id == 42
    assert snap.map_name == "lair-100000"
    assert snap.map_file_name == "lair-v1.swf"
    assert snap.self_state is not None and snap.self_state.cell == "Enter"
    assert snap.players["bob"].pad == "Left"
    assert snap.monsters[9].name == "Red Dragon"
    assert snap.monsters[9].cell == "Boss"
    assert snap.map_events == ({"typ": "gate", "cmd": "open"},)
    assert snap.cell_map == {"Enter": "Boss"}

    # Every read is immutable/copy-safe: callers cannot mutate live state.
    assert isinstance(snap.players, tuple) is False


def test_new_area_generation_drops_old_entities_and_ignores_stale_generation():
    store = AreaStateStore(self_username="alice", self_user_id=1)
    store.feed(lair_snapshot())
    old_generation = store.snapshot().generation

    store.feed(packet(
        "moveToArea",
        room=77,
        areaId=77,
        areaName="yulgar-1",
        strMapName="yulgar",
        strMapFileName="yulgar-v1.swf",
        uoBranch=[{"uoName": "alice", "uid": 1, "strFrame": "Enter", "strPad": "Spawn", "intHP": 900, "intState": 1}],
        mondef=[], monmap=[], monBranch=[], event=[], cellMap={},
    ))

    snap = store.snapshot()
    assert snap.generation == old_generation + 1
    assert snap.room_id == 77
    assert snap.monsters == {}
    assert "bob" not in snap.players

    # A packet captured for generation one cannot revive state in generation two.
    assert store.feed("%xt%mtls%-1%9%intHP:999,intState:1%", generation=old_generation) is False
    assert store.snapshot().monsters == {}


def test_incremental_updates_are_idempotent_and_preserve_unknowns():
    store = AreaStateStore(self_username="alice", self_user_id=1)
    store.feed(lair_snapshot())
    generation = store.snapshot().generation

    update = "%xt%mtls%-1%1%intHP:250,intState:1%"
    assert store.feed(update, generation=generation) is True
    assert store.feed(update, generation=generation) is True
    assert store.snapshot().monsters[1].hp == 250

    store.feed("%xt%uotls%-1%alice%strFrame:Boss,strPad:Center,intHP:800,intState:1%", generation=generation)
    self_state = store.snapshot().self_state
    assert self_state is not None
    assert self_state.cell == "Boss" and self_state.pad == "Center"
    assert self_state.mp == 300  # omitted field stays known from the snapshot


def test_snapshot_reads_are_safe_while_packets_arrive():
    store = AreaStateStore(self_username="alice", self_user_id=1)
    store.feed(lair_snapshot())
    failures: list[Exception] = []

    def writer():
        try:
            for hp in range(500, 399, -1):
                store.feed(f"%xt%mtls%-1%1%intHP:{hp},intState:1%")
        except Exception as exc:  # pragma: no cover - assertion reports it
            failures.append(exc)

    thread = threading.Thread(target=writer)
    thread.start()
    while thread.is_alive():
        snap = store.snapshot()
        assert snap.generation == 1
        assert 1 in snap.monsters
    thread.join()
    assert not failures
    assert store.snapshot().monsters[1].hp == 400


def test_area_report_and_json_are_deterministic_and_show_provenance():
    store = AreaStateStore(self_username="alice", self_user_id=1)
    store.feed(lair_snapshot())

    rows = store.report()
    assert rows[0].startswith("area lair-100000 room 42 generation 1 [wire]")
    assert any("self alice cell Enter/Spawn hp 900/900 [wire]" in row for row in rows)
    assert any("m:1 Water Draconian hp 500/500 cell Enter [wire]" in row for row in rows)
    assert any("p:2 bob cell Boss/Left hp 700/800 [wire]" in row for row in rows)

    first = store.to_json()
    second = store.to_json()
    assert first == second
    parsed = json.loads(first)
    assert parsed["schema_version"] == 1
    assert parsed["generation"] == 1
    assert parsed["monsters"][0]["map_id"] == 1
    assert parsed["monsters"][0]["source"] == "wire"
