"""Headless parser for AQW map cells.

The live game client (and Skua) read the complete cell list from the map's
own Flash scene labels (``world.map.currentScene.labels``). This module gives
headless mode the same list: download the map SWF named by ``moveToArea``
``strMapFileName``, then read every ``DefineSceneAndFrameLabelData`` (tag 86)
and ``FrameLabel`` (tag 43) label without executing Flash.

Only real SWF frame labels are returned. This never guesses cell names.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import urllib.request
import zlib
from typing import Callable


MAP_ORIGIN = "https://game.aq.com/game/gamefiles/maps/"
# Kept short: the scan runs once per new map name and must not stall the
# packet reader for long when the CDN is unreachable.
DEFAULT_FETCH_TIMEOUT = 8.0


class SWFCellError(ValueError):
    """Raised when a map filename or SWF payload is unusable."""


def _read_record_header(view: memoryview, pos: int) -> tuple[int, int, int]:
    """Return (tag_code, header_size, payload_size) for one SWF tag."""
    if pos + 2 > len(view):
        raise SWFCellError("SWF terpotong pada header tag")
    packed = struct.unpack_from("<H", view, pos)[0]
    code = packed >> 6
    size = packed & 0x3F
    header = 2
    if size == 63:
        if pos + 6 > len(view):
            raise SWFCellError("SWF terpotong pada long tag")
        size = struct.unpack_from("<I", view, pos + 2)[0]
        header = 6
    return code, header, size


def _read_enc_u32(payload: bytes, cursor: int) -> tuple[int, int]:
    """Read one SWF EncodedU32, returning (value, new_cursor)."""
    value = 0
    shift = 0
    while True:
        if cursor >= len(payload):
            raise SWFCellError("EncodedU32 SWF terpotong")
        byte = payload[cursor]
        cursor += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, cursor
        shift += 7
        if shift > 35:
            raise SWFCellError("EncodedU32 SWF terlalu panjang")


def _labels_from_tags(body: bytes) -> list[str]:
    view = memoryview(body)
    if len(view) < 4:
        raise SWFCellError("SWF body terlalu pendek")
    # RECT: first byte holds the 5-bit Nbits field in its high bits.
    nbits = view[0] >> 3
    rect_bytes = (5 + nbits * 4 + 7) // 8
    pos = rect_bytes + 4  # RECT, frame rate (2), frame count (2)
    if pos > len(view):
        raise SWFCellError("SWF header scene tidak lengkap")
    found: dict[str, str] = {}
    while pos < len(view):
        code, header, size = _read_record_header(view, pos)
        start = pos + header
        end = start + size
        if end > len(view):
            raise SWFCellError("payload tag SWF di luar file")
        payload = bytes(view[start:end])
        pos = end
        if code == 0:  # End
            break
        if code == 43:  # FrameLabel
            end_name = payload.find(b"\x00")
            label = payload[:end_name] if end_name != -1 else payload
            name = label.decode("utf-8", errors="replace").strip()
            if name and name.casefold() not in found:
                found[name.casefold()] = name
        elif code == 86:  # DefineSceneAndFrameLabelData
            cursor = 0
            try:
                scene_count, cursor = _read_enc_u32(payload, cursor)
                for _ in range(scene_count):
                    _offset, cursor = _read_enc_u32(payload, cursor)
                    end_name = payload.find(b"\x00", cursor)
                    if end_name == -1:
                        cursor = len(payload)
                        break
                    cursor = end_name + 1
                frame_count, cursor = _read_enc_u32(payload, cursor)
                for _ in range(frame_count):
                    _frame, cursor = _read_enc_u32(payload, cursor)
                    end_name = payload.find(b"\x00", cursor)
                    if end_name == -1:
                        cursor = len(payload)
                        break
                    name = payload[cursor:end_name].decode(
                        "utf-8", errors="replace"
                    ).strip()
                    cursor = end_name + 1
                    if name and name.casefold() not in found:
                        found[name.casefold()] = name
            except SWFCellError:
                continue
    return list(found.values())


def parse_swf_cells(payload: bytes) -> list[str]:
    """Return deduplicated map cells from SWF bytes (FWS or CWS)."""
    if len(payload) < 8 or payload[:3] not in (b"FWS", b"CWS"):
        raise SWFCellError("bukan file SWF (butuh signature FWS/CWS)")
    version = payload[3]
    if version > 40:
        raise SWFCellError(f"versi SWF tidak masuk akal: {version}")
    declared = struct.unpack_from("<I", payload, 4)[0]
    if declared < 8:
        raise SWFCellError("ukuran header SWF tidak konsisten")
    # In a CWS file FileLength is the *uncompressed* size, so it legitimately
    # exceeds the physical file size. Only an uncompressed FWS must agree.
    if payload[:3] == b"FWS" and len(payload) > 8 and declared > len(payload):
        raise SWFCellError("ukuran header SWF tidak konsisten")
    body = payload[8:]
    if payload[:3] == b"CWS":
        try:
            body = zlib.decompress(body)
        except zlib.error as exc:
            raise SWFCellError(f"gagal dekompres SWF map: {exc}") from exc
    cells = _labels_from_tags(body)
    if not cells:
        raise SWFCellError("tidak ada label cell di SWF map")
    return cells


def _default_fetch(url: str, timeout: float = DEFAULT_FETCH_TIMEOUT) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "AQW/Skua-Lite", "Referer": MAP_ORIGIN}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _origin_url(safe: str) -> str:
    """Resolve one relative map file to its canonical gamefiles/maps URL."""
    return f"{MAP_ORIGIN}{safe}"


def _safe_filename(file_name: str) -> str:
    clean = str(file_name or "").strip().replace("\\", "/").lstrip("/")
    # Only a URL query tail (`?ver=...`) is tolerated. Full absolute server
    # URLs are rejected so the fetch origin stays pinned to gamefiles/maps.
    clean = clean.split("?", 1)[0]
    if (
        not clean
        or clean != str(file_name or "").strip().split("?", 1)[0]
        or clean.startswith(("http://", "https://"))
        or clean.endswith("/")
        or ".." in clean.split("/")
    ):
        raise SWFCellError(f"nama file map tidak aman: {file_name!r}")
    if clean.startswith("maps/"):
        clean = clean[5:]
    if not clean:
        raise SWFCellError(f"nama file map tidak aman: {file_name!r}")
    if not clean.lower().endswith(".swf"):
        clean += ".swf"
    return clean


@dataclass(slots=True)
class MapCellScanner:
    """Download+cache map SWFs, then scan every SWF scene label."""

    cache_dir: Path | str = Path.cwd() / ".map_cache"
    fetch: Callable[[str, float], bytes] = _default_fetch

    def scan(self, file_name: str) -> list[str]:
        safe = _safe_filename(file_name)
        cached = Path(self.cache_dir) / safe
        if cached.is_file():
            try:
                return parse_swf_cells(cached.read_bytes())
            except (OSError, SWFCellError):
                pass
        payload = self.fetch(f"{MAP_ORIGIN}{safe}", DEFAULT_FETCH_TIMEOUT)
        cells = parse_swf_cells(payload)
        try:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(payload)
        except OSError:
            pass
        return cells
