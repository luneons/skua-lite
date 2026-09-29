"""Offline replay tests for sanitized area captures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skua_lite.area_replay import CaptureError, replay_capture


FIXTURE = Path(__file__).parent / "fixtures" / "area" / "lair_synthetic"


def test_sanitized_capture_replays_to_exact_expected_snapshot():
    result = replay_capture(FIXTURE / "manifest.json")
    expected = (FIXTURE / "expected_area.json").read_text(encoding="utf-8").strip()

    assert result.area_json == expected
    assert result.events_read == 4
    assert result.inbound_reduced == 4
    assert result.outbound_skipped == 0
    assert result.final_generation == 1


def test_replay_skips_outbound_frames_and_uses_capture_timestamps(tmp_path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        '\n'.join([
            json.dumps({"ts": 10.0, "direction": "IN", "packet": '{"t":"xt","b":{"r":-1,"o":{"cmd":"moveToArea","areaId":9,"areaName":"test-1","strMapName":"test","uoBranch":[],"monBranch":[],"mondef":[],"monmap":[]}}}'}),
            json.dumps({"ts": 11.0, "direction": "OUT", "packet": "%xt%zm%moveToCell%9%Boss%Left%"}),
        ]) + '\n',
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "kind": "synthetic-sanitized",
        "self_username": "alice",
        "self_user_id": 1,
        "events": "events.jsonl",
    }), encoding="utf-8")

    result = replay_capture(manifest)
    parsed = json.loads(result.area_json)
    assert parsed["observed_at"] == 10.0
    assert result.events_read == 2
    assert result.inbound_reduced == 1
    assert result.outbound_skipped == 1


def test_replay_rejects_unknown_schema_and_unredacted_secret_keys(tmp_path):
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps({"ts": 1.0, "direction": "IN", "password": "secret", "packet": "x"}) + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 99,
        "kind": "synthetic-sanitized",
        "self_username": "alice",
        "events": "events.jsonl",
    }), encoding="utf-8")

    with pytest.raises(CaptureError, match="schema"):
        replay_capture(manifest)

    manifest.write_text(json.dumps({
        "schema_version": 1,
        "kind": "synthetic-sanitized",
        "self_username": "alice",
        "events": "events.jsonl",
    }), encoding="utf-8")
    with pytest.raises(CaptureError, match="sensitif"):
        replay_capture(manifest)
