"""Tests for headless extraction of map cells from AQW SWF files."""
from __future__ import annotations

import struct
import zlib

import pytest

from skua_lite.map_cells import MapCellScanner, SWFCellError, parse_swf_cells


def _tag(code: int, payload: bytes = b"") -> bytes:
    length = len(payload)
    if length < 63:
        return struct.pack("<H", (code << 6) | length) + payload
    return struct.pack("<HI", (code << 6) | 63, length) + payload


def _enc_u32(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _scene_tag(labels: list[str]) -> bytes:
    payload = _enc_u32(0) + _enc_u32(len(labels))
    for frame, label in enumerate(labels):
        payload += _enc_u32(frame) + label.encode("utf-8") + b"\x00"
    return _tag(86, payload)


def _swf(labels: list[str], *, compressed: bool = False, scene_tag: bool = False) -> bytes:
    # RECT with Nbits=1 occupies two bytes. Then frame rate + frame count.
    body = b"\x08\x00" + b"\x00\x18" + struct.pack("<H", len(labels))
    if scene_tag:
        body += _scene_tag(labels)
    else:
        for label in labels:
            body += _tag(43, label.encode("utf-8") + b"\x00")
            body += _tag(1)
    body += _tag(0)
    signature = b"CWS" if compressed else b"FWS"
    header = signature + bytes([10]) + struct.pack("<I", 8 + len(body))
    return header + (zlib.compress(body) if compressed else body)


def test_parse_swf_cells_reads_frame_labels_from_fws_and_cws():
    expected = ["Enter", "Stairs", "Cave", "Lobby"]
    assert parse_swf_cells(_swf(expected)) == expected
    assert parse_swf_cells(_swf(expected, compressed=True)) == expected


def test_parse_swf_cells_reads_highly_compressed_cws_with_uncompressed_length():
    # In a real CWS header FileLength is the uncompressed size, so it can be
    # much larger than the physical compressed file.
    expected = [f"VeryLongRepeatedRoomName{index:03d}" for index in range(180)]
    payload = _swf(expected, compressed=True)
    assert struct.unpack_from("<I", payload, 4)[0] > len(payload)
    assert parse_swf_cells(payload) == expected


def test_parse_swf_cells_reads_encoded_define_scene_labels():
    # Tag 86 uses EncodedU32, including values > 63 and > 127.
    expected = ["Enter", "Stairs", "Cave", "Lobby"] + [
        f"Room{index}" for index in range(130)
    ]
    assert parse_swf_cells(_swf(expected, scene_tag=True)) == expected


def test_parse_swf_cells_deduplicates_labels_case_insensitively():
    assert parse_swf_cells(_swf(["Enter", "stairs", "Stairs", "Enter"])) == [
        "Enter", "stairs"
    ]


def test_parse_swf_cells_rejects_non_swf_data():
    with pytest.raises(SWFCellError):
        parse_swf_cells(b"not a swf")


def test_map_cell_scanner_uses_fixed_aqw_origin_and_cache(tmp_path):
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> bytes:
        calls.append(url)
        assert timeout == 8.0
        return _swf(["Enter", "Boss"])

    scanner = MapCellScanner(cache_dir=tmp_path, fetch=fetch)
    assert scanner.scan("maps/lair-v1.swf") == ["Enter", "Boss"]
    assert scanner.scan("maps/lair-v1.swf") == ["Enter", "Boss"]
    assert calls == ["https://game.aq.com/game/gamefiles/maps/lair-v1.swf"]


def test_map_cell_scanner_supports_server_absolute_aqw_map_url(tmp_path):
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> bytes:
        calls.append(url)
        return _swf(["Enter", "Cave"])

    scanner = MapCellScanner(cache_dir=tmp_path, fetch=fetch)
    url = "maps/lair-r9.swf?ver=123"
    assert scanner.scan(url) == ["Enter", "Cave"]
    assert calls == ["https://game.aq.com/game/gamefiles/maps/lair-r9.swf"]


def test_map_cell_scanner_rejects_unsafe_paths(tmp_path):
    scanner = MapCellScanner(cache_dir=tmp_path, fetch=lambda *_: b"")
    with pytest.raises(SWFCellError):
        scanner.scan("../../secret.swf")
    with pytest.raises(SWFCellError):
        scanner.scan("https://evil.example/map.swf")
