"""Startup run-mode selection for the two intentionally separate flows."""
from __future__ import annotations

from enum import Enum
import queue
import threading
import time
from typing import Any, Callable


class RunMode(str, Enum):
    """Top-level mode; modes are fixed for the lifetime of one process."""

    ASSISTANT = "assistant"
    FARMING = "farming"

    @property
    def label(self) -> str:
        return "AI ASISTEN" if self is RunMode.ASSISTANT else "FARMING"


class StartupSignal:
    """Thread-safe signal untuk sinkronisasi pilihan mode dan akun via Telegram/CLI."""

    def __init__(self) -> None:
        self.selected_mode: RunMode | None = None
        self.selected_account_flow: tuple[str, list[str] | None] | None = None
        self._event = threading.Event()

    def set_mode(self, mode: RunMode | None) -> None:
        self.selected_mode = mode
        self._event.set()

    def set_account_flow(self, flow: tuple[str, list[str] | None]) -> None:
        self.selected_account_flow = flow
        self._event.set()

    def reset(self) -> None:
        self.selected_mode = None
        self.selected_account_flow = None
        self._event.clear()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)


def parse_mode(value: str | RunMode | None) -> RunMode | None:
    """Parse a human/CLI mode value without guessing unknown input."""
    if isinstance(value, RunMode):
        return value
    normalized = " ".join((value or "").strip().lower().replace("_", " ").split())
    if normalized in {
        "1", "ai", "assistant", "asisten", "ai asisten", "mode ai", "mode asisten",
        "mode ai asisten",
    }:
        return RunMode.ASSISTANT
    if normalized in {"2", "farm", "farming", "mode farm", "mode farming"}:
        return RunMode.FARMING
    return None


def select_mode(
    explicit: str | RunMode | None = None,
    *,
    output: Callable[[str], None] = print,
    signal: Any = None,
) -> RunMode:
    """Return an explicit mode or ask at startup until the choice is valid."""
    selected = parse_mode(explicit)
    if explicit is not None:
        if selected is None:
            raise ValueError(f"mode tidak dikenal: {explicit}")
        return selected

    output("\nPILIH MODE SKUA-LITE")
    output("  [1] MODE AI ASISTEN - login, AFK di Yulgar, AI/Admin aktif")
    output("  [2] MODE FARMING    - flow farming terpisah, AI/Admin mati")
    output("  (Pilihan bisa diketik di bawah atau ditekan lewat tombol Telegram)")

    # Jalur cepat: jika signal Telegram sudah memilih mode sebelum prompt
    if signal is not None and getattr(signal, "selected_mode", None) is not None:
        chosen: RunMode = signal.selected_mode
        output(f"[MODE] {chosen.label} dipilih via Telegram.")
        return chosen

    # Jika tidak ada signal dari Telegram, gunakan input blocking biasa
    if signal is None:
        while True:
            selected = parse_mode(input("Pilih mode [1/2]: "))
            if selected is not None:
                output(f"[MODE] {selected.label} dipilih.")
                return selected
            output("[WARN] Mode tidak dikenal. Masukkan 1/AI atau 2/FARMING.")

    # Mendengarkan input terminal DAN signal Telegram secara asinkron
    input_queue: queue.Queue[str] = queue.Queue()

    def _reader() -> None:
        try:
            line = input("Pilih mode [1/2]: ")
            input_queue.put(line)
        except Exception:
            pass

    reader_thread = threading.Thread(target=_reader, name="Mode-CLI-Reader", daemon=True)
    reader_thread.start()

    while True:
        # 1. Cek apakah ada pilihan dari Telegram
        if getattr(signal, "selected_mode", None) is not None:
            chosen = signal.selected_mode
            output(f"\n[MODE] {chosen.label} dipilih via Telegram.")
            return chosen

        # 2. Cek apakah ada baris input dari terminal
        try:
            raw_line = input_queue.get_nowait()
            selected = parse_mode(raw_line)
            if selected is not None:
                output(f"[MODE] {selected.label} dipilih.")
                return selected
            output("[WARN] Mode tidak dikenal. Masukkan 1/AI atau 2/FARMING.")
            reader_thread = threading.Thread(target=_reader, name="Mode-CLI-Reader", daemon=True)
            reader_thread.start()
        except queue.Empty:
            pass

        time.sleep(0.1)
