"""Deterministic offline replay for sanitized area packet captures."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
_SECRET_KEYS = {"password", "sToken", "token", "email", "session", "auth", "chat"}


class CaptureError(RuntimeError):
    """Raised when a capture manifest cannot be trusted or read."""


@dataclass(frozen=True, slots=True)
class ReplayResult:
    manifest_path: Path
    events_read: int
    inbound_reduced: int
    outbound_skipped: int
    final_generation: int
    area_json: str


def replay_capture(manifest_path: str | Path) -> ReplayResult:
    from .area_state import AreaStateStore

    manifest = Path(manifest_path)
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CaptureError(f"manifest tidak bisa dibaca: {manifest}: {exc}") from exc
    if int(data.get("schema_version", 0)) != SCHEMA_VERSION:
        raise CaptureError(
            f"schema capture tidak didukung: {data.get('schema_version')!r}"
        )
    events_path = manifest.parent / str(data.get("events") or "events.jsonl")
    store = AreaStateStore(
        self_username=str(data.get("self_username") or ""),
        self_user_id=data.get("self_user_id"),
    )
    events_read = inbound_reduced = outbound_skipped = 0
    try:
        lines = events_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CaptureError(f"events tidak bisa dibaca: {events_path}: {exc}") from exc
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError as exc:
            raise CaptureError(f"baris events rusak: {line[:120]}") from exc
        if not isinstance(event, dict) or "packet" not in event:
            raise CaptureError("baris events harus punya field 'packet'")
        for key, value in event.items():
            if str(key).casefold() in _SECRET_KEYS and value not in (None, "", [], {}):
                raise CaptureError(f"capture mengandung kunci sensitif: {key}")
        events_read += 1
        if str(event.get("direction", "IN")).upper() == "OUT":
            outbound_skipped += 1
            continue
        clock_value = event.get("ts")
        if isinstance(clock_value, (int, float)):
            store.clock = lambda clock_value=clock_value: float(clock_value)
        packet = str(event.get("packet") or "")
        if packet:
            store.feed(packet)
            inbound_reduced += 1

    area_json = store.to_json()
    expected = str(data.get("expected") or "")
    if expected:
        expected_path = manifest.parent / expected
        try:
            expected_text = expected_path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise CaptureError(
                f"expected snapshot tidak bisa dibaca: {expected_path}: {exc}"
            ) from exc
        if area_json != expected_text:
            raise CaptureError(
                "replay tidak deterministik: snapshot berbeda dari expected_area.json"
            )
    return ReplayResult(
        manifest_path=manifest,
        events_read=events_read,
        inbound_reduced=inbound_reduced,
        outbound_skipped=outbound_skipped,
        final_generation=store.generation,
        area_json=area_json,
    )
