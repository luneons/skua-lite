"""Startup run-mode selection for the two intentionally separate flows."""
from __future__ import annotations

from enum import Enum
from typing import Callable


class RunMode(str, Enum):
    """Top-level mode; modes are fixed for the lifetime of one process."""

    ASSISTANT = "assistant"
    FARMING = "farming"

    @property
    def label(self) -> str:
        return "AI ASISTEN" if self is RunMode.ASSISTANT else "FARMING"


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
    while True:
        selected = parse_mode(input("Pilih mode [1/2]: "))
        if selected is not None:
            output(f"[MODE] {selected.label} dipilih.")
            return selected
        output("[WARN] Mode tidak dikenal. Masukkan 1/AI atau 2/FARMING.")
